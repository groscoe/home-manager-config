"""Install only an exact, read-only Linux SMART sudo rule; never run from activation."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import tempfile

SMART_ARGS = ['-i', '-H', '-A', '-j']
TARGET = Path('/etc/sudoers.d/hardware-health')


def policy(config):
    user, executable, devices = config['user'], config['smartctl'], config['devices']
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', user):
        raise ValueError('Invalid sudo user')
    # Avoid wildcard arguments, user-owned binaries, and arbitrary device access.
    if executable not in ('/usr/sbin/smartctl', '/usr/bin/smartctl'):
        raise ValueError('Use a root-owned native smartctl in /usr/bin or /usr/sbin')
    if not devices or len(devices) != len(set(devices)) or not all(re.fullmatch(r'/dev/nvme\d+', d) for d in devices):
        raise ValueError('Expected explicit NVMe controllers, without wildcards')
    return ('# Managed by the Home Manager hardware-health access installer.\n'
            '# Only identification and SMART health reads; no tests/settings/writes.\n'
            + ''.join(f'{user} ALL=(root) NOPASSWD: {executable} -i -H -A -j {device}\n' for device in devices))


def trusted_executable(path):
    path = path.resolve(strict=True)
    for parent in [path, *path.parents]:
        metadata = parent.stat()
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ValueError(f'Untrusted executable/ancestor: {parent}')
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('Not an executable regular file')


def atomic_file(path, contents):
    fd, temp = tempfile.mkstemp(prefix='hardware-health-', dir=path.parent)
    try:
        os.fchmod(fd, 0o440)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--check', action='store_true', help='Validate the proposed narrow policy without installing it')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run the declared installer, which prompts for sudo')
    config = json.loads(args.config.read_text())
    contents = policy(config).encode()
    pwd.getpwnam(config['user'])
    for name in [config['smartctl'], '/usr/sbin/visudo', '/usr/bin/sudo', '/usr/sbin/runuser']:
        trusted_executable(Path(name))
    if not re.search(r'^\s*[@#]includedir\s+/etc/sudoers.d\s*$', Path('/etc/sudoers').read_text(), re.M):
        raise ValueError('The native sudo policy does not include /etc/sudoers.d')
    subprocess.run(['/usr/sbin/visudo', '-c'], check=True)
    with tempfile.NamedTemporaryFile(prefix='hardware-health-policy-', mode='wb') as candidate:
        candidate.write(contents)
        candidate.flush()
        os.fchmod(candidate.fileno(), 0o440)
        subprocess.run(['/usr/sbin/visudo', '-c', '-f', candidate.name], check=True)
    for device in config['devices']:
        if not stat.S_ISCHR(Path(device).stat().st_mode):
            raise ValueError(f'Not an NVMe controller character device: {device}')
        result = subprocess.run([config['smartctl'], *SMART_ARGS, device], capture_output=True, text=True, timeout=30)
        if result.returncode & 7 or 'nvme_smart_health_information_log' not in json.loads(result.stdout):
            raise ValueError('The exact read command failed; access policy unchanged')
    old = None
    if TARGET.exists() or TARGET.is_symlink():
        metadata = TARGET.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ValueError('Unexpected existing hardware-health sudo policy')
        old = TARGET.read_bytes()
    if args.check:
        print('Read-only SMART access preflight passed; no changes made.')
        return
    if old == contents:
        print('Read-only SMART policy is already installed.')
        return
    backup = Path(tempfile.mkdtemp(prefix='hardware-health-' + dt.datetime.now().strftime('%Y%m%d-'), dir='/var/backups'))
    os.chmod(backup, 0o700)
    if old is not None:
        (backup / 'previous').write_bytes(old)
    rollback = '''import os, pathlib, subprocess, tempfile
if os.geteuid() != 0: raise SystemExit("sudo is required")
root = pathlib.Path(__file__).resolve().parent
target = pathlib.Path("/etc/sudoers.d/hardware-health")
old = root / "previous"
if old.exists():
    fd, name = tempfile.mkstemp(prefix="hardware-health-", dir=target.parent)
    with os.fdopen(fd, "wb") as stream: stream.write(old.read_bytes())
    os.chmod(name, 0o440)
    subprocess.run(["/usr/sbin/visudo", "-c", "-f", name], check=True)
    os.replace(name, target)
else:
    target.unlink(missing_ok=True)
subprocess.run(["/usr/sbin/visudo", "-c"], check=True)
print("Previous SMART access policy restored.")
'''
    (backup / 'rollback.py').write_text(rollback)
    try:
        atomic_file(TARGET, contents)
        subprocess.run(['/usr/sbin/visudo', '-c'], check=True)
        for device in config['devices']:
            result = subprocess.run(['/usr/sbin/runuser', '-u', config['user'], '--', '/usr/bin/sudo', '-n',
                                     config['smartctl'], *SMART_ARGS, device], capture_output=True, text=True, timeout=30)
            if result.returncode & 7 or 'nvme_smart_health_information_log' not in json.loads(result.stdout):
                raise ValueError('Noninteractive SMART read failed; restoring prior policy')
    except BaseException:
        if old is None:
            TARGET.unlink(missing_ok=True)
        else:
            atomic_file(TARGET, old)
        subprocess.run(['/usr/sbin/visudo', '-c'], check=True)
        raise
    print('Installed exact read-only SMART query permission. No service or charging changes.')
    print(f'Backup: {backup}')
    print(f'Rollback: sudo /usr/bin/python3 -I {backup}/rollback.py')


if __name__ == '__main__':
    main()
