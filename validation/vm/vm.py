"""Bounded, unprivileged runner for the disposable xps Ubuntu restore guest."""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path('/home/groscoe/.cache/hm-restore-test')
REPO = Path('/home/groscoe/Projects/home-manager-config')
IMAGE_URL = 'https://cloud-images.ubuntu.com/jammy/20261020/'
IMAGE = 'jammy-server-cloudimg-amd64.img'
PURPOSE = 'disposable-home-manager-restore-test'
SOURCE = Path(__file__).resolve().parent


def private_directory(path):
    path = Path(path)
    if path.resolve() != path.absolute():
        raise ValueError('Refusing a symlink in the test path: ' + str(path))
    meta = path.stat()
    if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != os.getuid() or meta.st_mode & 0o077:
        raise ValueError('Test directory must be private and user-owned: ' + str(path))


def owned_file(path, root):
    path, root = Path(path), Path(root)
    if not path.is_relative_to(root) or path.resolve() != path.absolute():
        raise ValueError('Refusing path outside test directory or symlink: ' + str(path))
    meta = path.stat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.getuid():
        raise ValueError('Expected a user-owned regular test file: ' + str(path))
    return path


def save(path, obj):
    assert not path.exists() and not path.is_symlink(), path
    with path.open('x') as stream:
        json.dump(obj, stream, indent=2)
        stream.write('\n')
    path.chmod(0o600)


def initialize():
    if os.geteuid() == 0:
        raise ValueError('Run the host VM controller as the normal user')
    if not ROOT.exists():
        ROOT.mkdir(mode=0o700, parents=True)
    private_directory(ROOT)
    marker = ROOT / 'ownership.json'
    if not marker.exists():
        if any(ROOT.iterdir()):
            raise ValueError('Refusing a nonempty directory without a test ownership record')
        save(marker, {'purpose': PURPOSE, 'root': str(ROOT), 'device': ROOT.stat().st_dev})
    record = json.loads(owned_file(marker, ROOT).read_text())
    if (record.get('purpose'), record.get('root'), record.get('device')) != (PURPOSE, str(ROOT), ROOT.stat().st_dev):
        raise ValueError('Test directory ownership or filesystem identity changed')


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def load_runtime():
    private_directory(ROOT)
    pinned = os.environ.get('HM_RESTORE_RUNTIME')
    if pinned:
        path = Path(pinned)
        assert str(path.resolve()).startswith('/nix/store/'), 'Runtime must be immutable Nix-store data'
        result = json.loads(path.read_text())
        assert set(result) == {'qemu', 'qemu-img', 'cloud-localds', 'firmware', 'variables'}
        assert all(str(Path(p).resolve()).startswith('/nix/store/') and Path(p).is_file() for p in result.values())
        return result
    # Compatibility with the private runtime record used by the initial rehearsal.
    values = json.loads(owned_file(ROOT / 'runtime.json', ROOT).read_text())
    paths = [p for item in values for p in item['outputs'].values()]
    # Nix 2.34 and newer can represent outputs as objects.
    paths = [p['path'] if isinstance(p, dict) else p for p in paths]
    result = {}
    for path in paths:
        p = Path(path)
        if (p / 'bin/qemu-system-x86_64').exists():
            result['qemu'] = str(p / 'bin/qemu-system-x86_64')
        if (p / 'bin/cloud-localds').exists():
            result['cloud-localds'] = str(p / 'bin/cloud-localds')
        if (p / 'FV/OVMF_CODE.fd').exists():
            result['firmware'] = str(p / 'FV/OVMF_CODE.fd')
            result['variables'] = str(p / 'FV/OVMF_VARS.fd')
    # qemu-img can be a separate propagated output in Nixpkgs.
    qemu_parent = Path(result['qemu']).parent
    if (qemu_parent / 'qemu-img').exists():
        result['qemu-img'] = str(qemu_parent / 'qemu-img')
    else:
        result['qemu-img'] = shutil.which('qemu-img')
    assert all(result.get(k) for k in ('qemu', 'qemu-img', 'cloud-localds', 'firmware', 'variables')), result
    return result


def download(url, target):
    assert not target.exists() and not target.is_symlink()
    partial = target.with_name(target.name + '.partial')
    assert not partial.exists()
    with urllib.request.urlopen(url, timeout=120) as response, partial.open('xb') as output:
        while data := response.read(1024 * 1024):
            output.write(data)
    partial.replace(target)


def image_base():
    directory = ROOT / 'images'
    directory.mkdir(mode=0o700, exist_ok=True)
    private_directory(directory)
    image = directory / IMAGE
    if (directory / 'verified.json').exists():
        expected = json.loads(owned_file(directory / 'verified.json', ROOT).read_text())['sha256']
        assert hashlib.sha256(owned_file(image, ROOT).read_bytes()).hexdigest() == expected
        return image
    for filename in ('SHA256SUMS', 'SHA256SUMS.gpg', IMAGE):
        target = directory / filename
        if not target.exists():
            download(IMAGE_URL + filename, target)
    run('/usr/bin/gpgv', '--keyring', '/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg',
        str(directory / 'SHA256SUMS.gpg'), str(directory / 'SHA256SUMS'))
    checksums = {}
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split(None, 1)
        checksums[name.lstrip('*')] = digest
    expected = checksums[IMAGE]
    assert hashlib.sha256(image.read_bytes()).hexdigest() == expected
    image.chmod(0o400)
    save(directory / 'verified.json', {'url': IMAGE_URL + IMAGE, 'sha256': expected,
                                     'signatureKeyring': '/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg'})
    return image


def ssh_args(directory):
    private_directory(directory)
    return ['/usr/bin/ssh', '-F', '/dev/null', '-i', str(owned_file(directory / 'client-key', ROOT)),
            '-o', 'IdentitiesOnly=yes', '-o', 'ForwardAgent=no', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + str(owned_file(directory / 'known-hosts', ROOT)),
            '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4',
            '-p', '22222', 'groscoe@127.0.0.1']


def guest_check(directory):
    manifest = json.loads(owned_file(directory / 'manifest.json', ROOT).read_text())
    code = ('import json,pathlib,subprocess; p=pathlib.Path; '
            'marker=p("/etc/hm-restore-test.json"); '
            'assert marker.is_file() and not marker.is_symlink() and marker.stat().st_uid==0; '
            'j=json.loads(marker.read_text()); '
            f'assert j["uuid"]=={manifest["uuid"]!r}; '
            'assert j["purpose"]=="disposable-home-manager-restore-test"; '
            'assert p("/etc/hostname").read_text().strip()=="hm-xps-restore"; '
            f'assert p("/sys/class/dmi/id/product_uuid").read_text().strip().lower()=={manifest["uuid"]!r}; '
            'assert subprocess.check_output(["systemd-detect-virt","--vm"],text=True).strip() in ("qemu","kvm"); '
            'print("HM_RESTORE_GUEST_IDENTITY_OK")')
    import shlex
    return run(*ssh_args(directory), 'sudo -n /usr/bin/python3 -I -c ' + shlex.quote(code), capture_output=True, text=True)


def guest_exec(directory, command, **kwargs):
    guest_check(directory)
    return run(*ssh_args(directory), command, **kwargs)


def wait_ready(directory, timeout=180):
    deadline = time.monotonic() + timeout
    while True:
        try:
            guest_check(directory)
            return
        except subprocess.CalledProcessError as error:
            text = (error.stderr or '').lower()
            transient = error.returncode == 255 and any(value in text for value in (
                'connection refused', 'connection timed out', 'connection reset', 'connection closed',
            ))
            if not transient or time.monotonic() >= deadline:
                raise
            time.sleep(3)


def qemu_args(directory, tools, isolated=False):
    manifest = json.loads(owned_file(directory / 'manifest.json', ROOT).read_text())
    assert manifest['purpose'] == PURPOSE
    assert str(uuid.UUID(manifest['uuid'])) == manifest['uuid']
    argv = [tools['qemu'], '-name', 'HM Restore Test', '-uuid', manifest['uuid'],
            '-machine', 'q35,accel=kvm', '-cpu', 'host', '-smp', '4', '-m', '8192',
            '-display', 'none', '-vga', 'virtio', '-vnc', 'unix:' + str(directory / 'viewer.sock'),
            '-qmp', 'unix:' + str(directory / 'qmp.sock') + ',server=on,wait=off',
            '-serial', 'file:' + str(directory / 'console.log'),
            '-pidfile', str(directory / 'qemu.pid'), '-daemonize',
            '-drive', 'if=pflash,format=raw,readonly=on,file=' + tools['firmware'],
            '-drive', 'if=pflash,format=raw,file=' + str(owned_file(directory / 'uefi-vars.fd', ROOT)),
            '-netdev', 'user,id=net0,ipv6=off,hostfwd=tcp:127.0.0.1:22222-:22' + (',restrict=on' if isolated else ''),
            '-device', 'virtio-net-pci,netdev=net0',
            '-drive', 'if=virtio,format=raw,readonly=on,file=' + str(owned_file(directory / 'seed.img', ROOT))]
    for name, serial in (('root', 'HMROOT'), ('nix', 'HMNIX'), ('vault', 'HMVAULT')):
        disk = owned_file(directory / (name + '.qcow2'), ROOT)
        argv += ['-drive', f'if=none,id={name},format=qcow2,cache=writeback,file={disk}',
                 '-device', f'virtio-blk-pci,drive={name},serial={serial}']
    return argv


def qmp(directory, command, arguments=None):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(10)
        connection.connect(str(directory / 'qmp.sock'))
        with connection.makefile('rwb') as stream:
            assert json.loads(stream.readline())['QMP']
            for operation in ('qmp_capabilities', command):
                request = {'execute': operation}
                if operation == command and arguments is not None:
                    request['arguments'] = arguments
                stream.write((json.dumps(request) + '\n').encode())
                stream.flush()
                while True:
                    reply = json.loads(stream.readline())
                    if 'return' in reply:
                        break
                    if 'error' in reply:
                        raise RuntimeError(reply)
            return reply['return']


def prepare():
    initialize()
    if (ROOT / 'current-run').exists():
        assert not (current() / 'qmp.sock').exists(), 'Stop the current guest before preparing another'
    tools = load_runtime()
    assert os.geteuid() != 0, 'The VM host runner must not run as root'
    assert shutil.disk_usage(ROOT).free > 80 * 2**30
    assert not subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True), 'Source checkout must be clean'
    commit = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    assert len(commit) == 40 and all(c in '0123456789abcdef' for c in commit)
    base = image_base()
    meta = json.loads(subprocess.check_output([tools['qemu-img'], 'info', '--output=json', str(base)], text=True))
    assert meta['format'] == 'qcow2' and not meta.get('backing-filename')
    instance = str(uuid.uuid4())
    runs = ROOT / 'runs'
    runs.mkdir(mode=0o700, exist_ok=True)
    directory = runs / instance[:8]
    directory.mkdir(mode=0o700)
    save(directory / 'manifest.json', {'purpose': PURPOSE, 'uuid': instance, 'commit': commit,
                                     'baseImage': str(base), 'hostDataMounted': False})
    for key in ('client-key', 'host-key'):
        run('/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(directory / key))
    public = (directory / 'host-key.pub').read_text().strip()
    (directory / 'known-hosts').write_text('[127.0.0.1]:22222 ' + public + '\n')
    # Alphanumeric input is independent of the greeter/i3 keyboard layout.
    password = secrets.token_hex(16)
    (directory / 'guest-login.txt').write_text('User: groscoe\nPassword: ' + password + '\n')
    (directory / 'guest-login.txt').chmod(0o600)
    hashed = subprocess.check_output(['/usr/bin/openssl', 'passwd', '-6', '-stdin'], input=password + '\n', text=True).strip()
    for name, size in (('root', '24G'), ('nix', '96G'), ('vault', '8G')):
        args = [tools['qemu-img'], 'create', '-f', 'qcow2']
        if name == 'root':
            args += ['-F', 'qcow2', '-b', str(base)]
        run(*args, str(directory / (name + '.qcow2')), size)
    shutil.copyfile(tools['variables'], directory / 'uefi-vars.fd')
    cloud = {
        'hostname': 'hm-xps-restore', 'manage_etc_hosts': True, 'ssh_pwauth': False,
        'users': [{'name': 'groscoe', 'uid': 1000, 'shell': '/bin/bash', 'groups': ['adm', 'sudo'],
                   'sudo': 'ALL=(ALL) NOPASSWD:ALL', 'lock_passwd': False, 'passwd': hashed,
                   'ssh_authorized_keys': [(directory / 'client-key.pub').read_text().strip()]}],
        'ssh_keys': {'ed25519_private': (directory / 'host-key').read_text(),
                     'ed25519_public': (directory / 'host-key.pub').read_text()},
        'write_files': [
            {'path': '/etc/hm-restore-test.json', 'permissions': '0644',
             'content': json.dumps({'uuid': instance, 'purpose': PURPOSE}) + '\n'},
            {'path': '/usr/local/sbin/hm-guest-bootstrap.py', 'permissions': '0700',
             'content': (SOURCE / 'guest-bootstrap.py').read_text()},
        ],
        'runcmd': [['/usr/bin/python3', '-I', '/usr/local/sbin/hm-guest-bootstrap.py']],
    }
    (directory / 'user-data').write_text('#cloud-config\n' + json.dumps(cloud, indent=2) + '\n')
    (directory / 'user-data').chmod(0o600)
    save(directory / 'meta-data', {'instance-id': instance, 'local-hostname': 'hm-xps-restore'})
    run(tools['cloud-localds'], str(directory / 'seed.img'), str(directory / 'user-data'), str(directory / 'meta-data'))
    run('git', '-C', str(REPO), 'bundle', 'create', str(directory / 'source.bundle'), 'HEAD')
    assert subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip() == commit
    (ROOT / 'current-run').write_text(directory.name + '\n')
    print(json.dumps({'prepared': str(directory), 'uuid': instance}, indent=2))


def current():
    initialize()
    name = owned_file(ROOT / 'current-run', ROOT).read_text().strip()
    assert len(name) == 8 and all(c in '0123456789abcdef' for c in name)
    directory = ROOT / 'runs' / name
    private_directory(directory)
    return directory


def watchdog(directory):
    while (directory / 'qmp.sock').is_socket():
        if shutil.disk_usage(ROOT).free < 24 * 2**30:
            qmp(directory, 'stop')
            (directory / 'capacity-pause.json').write_text(json.dumps({'reason': 'host /home reserve below 24 GiB'}) + '\n')
            return
        time.sleep(10)


def main():
    global REPO
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'start', 'status', 'powerdown', 'watchdog', 'exercise'))
    parser.add_argument('stage', nargs='?')
    parser.add_argument('--repo', type=Path, default=REPO)
    parser.add_argument('--isolated', action='store_true')
    args = parser.parse_args()
    REPO = args.repo.resolve()
    os.umask(0o077)
    if args.command == 'prepare':
        prepare()
        return
    directory = current()
    if args.command == 'start':
        assert shutil.disk_usage(ROOT).free > 32 * 2**30
        with open('/dev/kvm', 'rb') as kvm:
            assert fcntl.ioctl(kvm, 0xAE00, 0) == 12, 'Unsupported KVM API'
        assert not (directory / 'qmp.sock').exists(), 'Already running or stale socket; inspect first'
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 22222))
        run(*qemu_args(directory, load_runtime(), args.isolated))
        with (directory / 'watchdog.log').open('a') as log:
            subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()), 'watchdog'],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        wait_ready(directory)
        print('VM started and identity verified; private SSH on 127.0.0.1:22222')
    elif args.command == 'status':
        guest_check(directory)
        print(guest_exec(directory, 'sudo /usr/bin/python3 -I -c ' +
            "'from pathlib import Path; p=Path(\"/var/lib/hm-restore-test/bootstrap-complete.json\"); print(p.read_text() if p.exists() else \"bootstrap in progress\")'",
            capture_output=True, text=True).stdout)
    elif args.command == 'powerdown':
        qmp(directory, 'system_powerdown')
    elif args.command == 'watchdog':
        watchdog(directory)
    elif args.command == 'exercise':
        if args.stage is None:
            parser.error('exercise requires a stage; see validation/vm/README.md')
        os.execv(sys.executable, [sys.executable, '-I', str(SOURCE / 'exercise.py'), args.stage])


if __name__ == '__main__':
    main()
