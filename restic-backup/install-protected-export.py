"""Install only the local protected-export helper and its hourly system timer."""
from pathlib import Path
import argparse
import grp
import importlib.util
import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile

# Import immutable source without generating unregistered files in /nix/store.
sys.dont_write_bytecode = True

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--program', type=Path, required=True)
p.add_argument('--config', type=Path, required=True)
a = p.parse_args()
assert os.geteuid() == 0, 'This installation needs sudo.'
for source in [a.program, a.config]:
    s = source.lstat()
    assert str(source).startswith('/nix/store/') and stat.S_ISREG(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022
config = json.loads(a.config.read_text())
account = pwd.getpwnam(config['user'])
config['gid'] = account.pw_gid
members = set(grp.getgrgid(config['gid']).gr_mem) | {u.pw_name for u in pwd.getpwall() if u.pw_gid == config['gid']}
assert members <= {config['user'], 'root'}, 'Export group must be private.'
assert config['directory'] == '/vault/.restic-protected'
assert subprocess.run(['/usr/bin/mountpoint', '-q', '/vault']).returncode == 0, '/vault must be mounted.'
destination = Path(config['directory'])
spec = importlib.util.spec_from_file_location('protected_export', a.program)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
vault = exporter.open_path('/vault', directory=True)
try:
    created = False
    try:
        os.mkdir('.restic-protected', mode=0o750, dir_fd=vault)
        created = True
    except FileExistsError:
        pass
    directory = os.open('.restic-protected', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=vault)
    try:
        if created:
            os.fchown(directory, 0, config['gid'])
        s = os.fstat(directory)
        assert s.st_uid == 0 and s.st_gid == config['gid'] and stat.S_IMODE(s.st_mode) == 0o750
    finally:
        os.close(directory)
finally:
    os.close(vault)
targets = {
    Path('/usr/local/libexec/restic-protected-export.py'): a.program.read_bytes(),
    Path('/etc/restic-protected-export.json'): (json.dumps(config, indent=2) + '\n').encode(),
    Path('/etc/systemd/system/restic-protected-export.service'): b'''[Unit]
Description=Local protected-file export for personal Restic backups
RequiresMountsFor=/vault /home
ConditionACPower=true
ConditionPathIsMountPoint=/vault

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I /usr/local/libexec/restic-protected-export.py
UMask=0077
Nice=15
IOSchedulingClass=idle
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/vault/.restic-protected
PrivateTmp=true
PrivateDevices=true
NoNewPrivileges=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
''',
    Path('/etc/systemd/system/restic-protected-export.timer'): b'''[Unit]
Description=Refresh protected local backup exports hourly on AC

[Timer]
OnCalendar=hourly
RandomizedDelaySec=1m
Persistent=true
Unit=restic-protected-export.service

[Install]
WantedBy=timers.target
'''
}
backup = Path(tempfile.mkdtemp(prefix='xps-restic-export-', dir='/var/backups'))
before = {}
for target in targets:
    for parent in target.parents:
        if parent.exists():
            s = parent.lstat()
            assert stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022, 'Unsafe installation parent: ' + str(parent)
    if target.exists() or target.is_symlink():
        s = target.lstat()
        assert stat.S_ISREG(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022
        saved = backup / target.relative_to('/')
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved)
        before[str(target)] = True
    else:
        before[str(target)] = False
enabled = subprocess.run(['/usr/bin/systemctl', 'is-enabled', 'restic-protected-export.timer'], capture_output=True, text=True).stdout.strip() == 'enabled'
(backup / 'before.json').write_text(json.dumps({'files': before, 'timer_enabled': enabled}, indent=2) + '\n')
rollback = '''from pathlib import Path
import json, shutil, subprocess
root=Path(__file__).parent
m=json.loads((root/'before.json').read_text())
subprocess.run(['systemctl','disable','--now','restic-protected-export.timer'],check=False)
subprocess.run(['systemctl','stop','restic-protected-export.service'],check=False)
for name, existed in m['files'].items():
 p=Path(name)
 if existed: shutil.copy2(root/p.relative_to('/'),p)
 else: p.unlink(missing_ok=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
if m['timer_enabled']: subprocess.run(['systemctl','enable','--now','restic-protected-export.timer'],check=True)
print('Prior exporter policy restored. Exported data retained on /vault.')
'''
(backup / 'rollback.py').write_text(rollback)
print('Backup:', backup, flush=True)
print('Rollback: sudo /usr/bin/python3 -I', backup / 'rollback.py', flush=True)
try:
    for target, content in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.chmod(0o644)
        temporary.replace(target)
    subprocess.run(['/usr/bin/systemd-analyze', 'verify', '/etc/systemd/system/restic-protected-export.service', '/etc/systemd/system/restic-protected-export.timer'], check=True)
    subprocess.run(['/usr/bin/systemctl', 'daemon-reload'], check=True)
    subprocess.run(['/usr/bin/systemctl', 'enable', '--now', 'restic-protected-export.timer'], check=True)
    subprocess.run(['/usr/bin/systemctl', 'start', 'restic-protected-export.service'], check=True)
    manifest = json.loads((destination / 'manifest.json').read_text())
    assert {r['path'] for r in manifest['sources']} == {r['path'] for r in config['sources']}
    print('XPS_RESTIC_PROTECTED_EXPORT_INSTALLED')
except BaseException:
    subprocess.run(['/usr/bin/python3', '-I', str(backup / 'rollback.py')], check=True)
    raise
