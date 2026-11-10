"""Install a fixed event-only BPF collector; camera controls are untouched."""
import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
import time

LIB = Path('/usr/local/libexec/camera-monitor')
UNIT = Path('/etc/systemd/system/camera-monitor-collector.service')
GCROOT = Path('/nix/var/nix/gcroots/camera-monitor-events')


def unit(group, engine='/nix/store/' + '0' * 32 + '-camera-events'):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', group):
        raise ValueError('Unsupported group name')
    if not re.fullmatch(r'/nix/store/[a-z0-9]{32}-camera-events', str(engine)):
        raise ValueError('Unsupported immutable event-engine path')
    return f'''[Unit]
Description=Event-driven camera access collector (eBPF; no frame capture)
After=local-fs.target
RequiresMountsFor=/nix/store

[Service]
Type=simple
User=root
Group={group}
ExecStart=/usr/bin/python3 -I /usr/local/libexec/camera-monitor/collector.py --engine {engine}/bin/camera-events --object /usr/local/libexec/camera-monitor/camera.bpf.o
Restart=on-failure
RestartSec=3
RuntimeDirectory=camera-monitor
RuntimeDirectoryMode=0750
UMask=0027
NoNewPrivileges=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
CapabilityBoundingSet=CAP_SYS_PTRACE CAP_DAC_READ_SEARCH CAP_BPF CAP_PERFMON
DevicePolicy=closed
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/run/camera-monitor
RestrictAddressFamilies=AF_UNIX AF_NETLINK

[Install]
WantedBy=multi-user.target
'''


def safe_existing(path, directory=False):
    if not path.exists() and not path.is_symlink():
        return
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError('Unsafe protected destination: ' + str(path))


def immutable(path):
    path = path.resolve(strict=True)
    info = path.stat()
    if not str(path).startswith('/nix/store/') or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('Source must be immutable and root-owned: ' + str(path))
    return path


def atomic(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        f.write(data)
        os.fchmod(f.fileno(), 0o644)
        os.fchown(f.fileno(), 0, 0)
    tmp.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--collector', required=True, type=Path)
    p.add_argument('--engine', required=True, type=Path)
    p.add_argument('--user', required=True)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    source = immutable(args.source)
    collector = immutable(args.collector)
    engine = immutable(args.engine)
    immutable(engine / 'bin/camera-events')
    obj = immutable(engine / 'lib/camera.bpf.o')
    account = pwd.getpwnam(args.user)
    group = grp.getgrgid(account.pw_gid).gr_name
    content = unit(group, str(engine)).encode()
    compile(source.read_text(), str(source), 'exec')
    compile(collector.read_text(), str(collector), 'exec')
    if args.check:
        print('Immutable sources, engine, unit and account validated; no changes made.')
        return
    if os.geteuid() != 0:
        raise SystemExit('Run through install-camera-monitor-access (sudo required).')
    os.umask(0o077)
    for directory in (Path('/usr/local'), Path('/usr/local/libexec'), GCROOT.parent):
        safe_existing(directory, True)
    safe_existing(LIB, True)
    destinations = {LIB / 'monitor.py': source, LIB / 'collector.py': collector, LIB / 'camera.bpf.o': obj}
    for path in [*destinations, UNIT]:
        safe_existing(path)
    if GCROOT.is_symlink():
        if GCROOT.lstat().st_uid != 0:
            raise RuntimeError('Untrusted event-engine GC root')
    elif GCROOT.exists():
        raise RuntimeError('Event-engine GC root is not a symlink')
    backup = Path(tempfile.mkdtemp(prefix='camera-monitor-ebpf-', dir='/var/backups'))
    paths = [*destinations, UNIT]
    manifest = {}
    for index, path in enumerate(paths):
        name = str(index)
        manifest[str(path)] = name if path.exists() else None
        if path.exists():
            shutil.copy2(path, backup / name)
            if (backup / name).read_bytes() != path.read_bytes():
                raise RuntimeError('Backup verification failed')
    enabled = subprocess.run(['/bin/systemctl', 'is-enabled', '--quiet', UNIT.name]).returncode == 0
    active = subprocess.run(['/bin/systemctl', 'is-active', '--quiet', UNIT.name]).returncode == 0
    meta = {'files': manifest, 'gcroot': os.readlink(GCROOT) if GCROOT.is_symlink() else None,
            'enabled': enabled, 'active': active}
    (backup / 'manifest.json').write_text(json.dumps(meta))
    rollback = backup / 'rollback.py'
    rollback.write_text('''import json,os,shutil,subprocess
from pathlib import Path
root=Path(__file__).parent
m=json.loads((root/'manifest.json').read_text())
for target,name in m['files'].items():
 p=Path(target)
 if name is None:p.unlink(missing_ok=True)
 else:shutil.copy2(root/name,p)
g=Path('/nix/var/nix/gcroots/camera-monitor-events')
g.unlink(missing_ok=True)
if m['gcroot']:g.symlink_to(m['gcroot'])
subprocess.run(['/bin/systemctl','daemon-reload'],check=True)
subprocess.run(['/bin/systemctl','enable' if m['enabled'] else 'disable','camera-monitor-collector.service'],check=True)
subprocess.run(['/bin/systemctl','restart' if m['active'] else 'stop','camera-monitor-collector.service'],check=True)
''')
    print('Backup:', backup, flush=True)
    print('Rollback: sudo /usr/bin/python3 -I', rollback, flush=True)
    try:
        prior_stream = json.loads(Path('/run/camera-monitor/status.json').read_text()).get('trace', {}).get('stream')
    except (OSError, ValueError):
        prior_stream = None
    try:
        LIB.mkdir(mode=0o755, parents=True, exist_ok=True)
        for path, origin in destinations.items():
            atomic(path, origin.read_bytes())
        atomic(UNIT, content)
        GCROOT.unlink(missing_ok=True)
        GCROOT.symlink_to(engine)
        subprocess.run(['/bin/systemd-analyze', 'verify', str(UNIT)], check=True)
        subprocess.run(['/bin/systemctl', 'daemon-reload'], check=True)
        subprocess.run(['/bin/systemctl', 'enable', UNIT.name], check=True)
        subprocess.run(['/bin/systemctl', 'restart', UNIT.name], check=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                status = json.loads(Path('/run/camera-monitor/status.json').read_text())
                trace = status.get('trace', {})
                if trace.get('backend') == 'ebpf' and trace.get('ready') and trace.get('stream') != prior_stream and status['time'] >= time.time() - 3:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(.2)
        else:
            raise RuntimeError('BPF collector did not become ready under service hardening')
    except BaseException:
        subprocess.run(['/usr/bin/python3', '-I', str(rollback)], check=True)
        raise
    print('EBPF_CAMERA_COLLECTOR_INSTALLED', flush=True)
    print('Camera permissions, controls, driver state and video streams were not changed.')


if __name__ == '__main__':
    main()
