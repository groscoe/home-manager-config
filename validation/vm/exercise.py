"""Collect actual fresh-guest evidence; every operation checks the guest identity."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import shlex
import subprocess
import time
import socket
import struct

spec = importlib.util.spec_from_file_location('restore_vm', Path(__file__).with_name('vm.py'))
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)
NIX = '/nix/var/nix/profiles/default/bin/nix'
PROJECT = '/home/groscoe/Projects/home-manager-config'


def upload(directory, name):
    target = '/home/groscoe/restore-smoke/' + name
    vm.guest_exec(directory, 'mkdir -p /home/groscoe/restore-smoke; cat > ' + shlex.quote(target),
                  input=(vm.SOURCE / name).read_text(), text=True)


def scenario(directory, name):
    scripts = json.loads((vm.SOURCE / 'scenarios.json').read_text())
    return phase(directory, name, scripts[name])


def desktop_login(directory):
    # Never request or use a real password. Only the generated hex guest value.
    running = vm.guest_exec(directory, 'pgrep -x i3 || true', capture_output=True, text=True).stdout.strip()
    if running:
        return
    deadline = time.monotonic() + 60
    while not vm.guest_exec(directory, 'pgrep -x sddm-greeter || true', capture_output=True, text=True).stdout.strip():
        assert time.monotonic() < deadline, 'Guest greeter did not appear'
        time.sleep(2)
    password = (directory / 'guest-login.txt').read_text().split('Password: ', 1)[1].strip()
    assert len(password) == 32 and all(c in '0123456789abcdef' for c in password)
    time.sleep(2)
    for char in password:
        vm.qmp(directory, 'send-key', {'keys': [{'type': 'qcode', 'data': char}], 'hold-time': 30})
        time.sleep(.06)
    vm.qmp(directory, 'send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}], 'hold-time': 30})
    for _ in range(30):
        if vm.guest_exec(directory, 'pgrep -x i3 || true', capture_output=True, text=True).stdout.strip():
            return
        time.sleep(1)
    raise RuntimeError('Generated guest password did not open i3; inspect private greeter logs')


def lock_roundtrip(directory):
    phase(directory, 'desktop-lock', 'sudo -n loginctl lock-sessions\nsleep 1\npgrep -x i3lock\n')
    vm.qmp(directory, 'send-key', {'keys': [{'type': 'qcode', 'data': 'esc'}], 'hold-time': 30})
    password = (directory / 'guest-login.txt').read_text().split('Password: ', 1)[1].strip()
    assert len(password) == 32 and all(c in '0123456789abcdef' for c in password)
    for char in password:
        vm.qmp(directory, 'send-key', {'keys': [{'type': 'qcode', 'data': char}], 'hold-time': 30})
        time.sleep(.06)
    vm.qmp(directory, 'send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}], 'hold-time': 30})
    phase(directory, 'desktop-password-unlock', 'sleep 2\nif pgrep -x i3lock; then exit 1; fi\npgrep -x i3\n')


def screenshot(directory):
    # With no connected viewer, QEMU's headless framebuffer can remain stale.
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(10)
        client.connect(str(directory / 'viewer.sock'))
        def read(count):
            data = b''
            while len(data) < count:
                chunk = client.recv(count - len(data))
                if not chunk:
                    raise EOFError('Private VM console closed')
                data += chunk
            return data
        assert read(12).startswith(b'RFB 003.')
        client.sendall(b'RFB 003.008\n')
        assert 1 in read(read(1)[0])
        client.sendall(b'\x01')
        assert read(4) == bytes(4)
        client.sendall(b'\x01')
        initial = read(24)
        width, height = struct.unpack('>HH', initial[:4])
        read(struct.unpack('>I', initial[20:24])[0])
        client.sendall(struct.pack('>BBHHHH', 3, 0, 0, 0, width, height))
        time.sleep(1)
        screens = directory / 'screens'
        screens.mkdir(mode=0o700, exist_ok=True)
        vm.qmp(directory, 'screendump', {'filename': str(screens / 'desktop.png'), 'format': 'png'})


def phase(directory, name, script, allowed=(0,), stdin=None):
    logdir = directory / 'evidence'
    logdir.mkdir(mode=0o700, exist_ok=True)
    original_name = name
    attempt = 1
    while (logdir / (name + '.log')).exists():
        attempt += 1
        name = original_name + '-attempt' + str(attempt)
    command = '/bin/bash -c ' + shlex.quote('set -eu\n' + script)
    started = time.time()
    with (logdir / (name + '.log')).open('w') as output:
        try:
            result = vm.guest_exec(directory, command, input=stdin, stdout=output, stderr=subprocess.STDOUT, text=True)
            code = result.returncode
        except subprocess.CalledProcessError as error:
            code = error.returncode
            if error.stderr:
                output.write(error.stderr)
    record = {'name': name, 'phase': original_name, 'attempt': attempt, 'returncode': code, 'expected': list(allowed),
              'passed': code in allowed, 'durationSeconds': round(time.time() - started, 2),
              'guestScript': script}
    (logdir / (name + '.json')).write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: record[k] for k in ('name', 'returncode', 'passed', 'durationSeconds')}), flush=True)
    if code not in allowed:
        raise RuntimeError('Guest stage failed; inspect ' + str(logdir / (name + '.log')))
    return logdir / (name + '.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('bootstrap', 'fixtures', 'policies', 'build', 'activate',
                                         'applications', 'backup', 'desktop', 'rollback', 'reboot-check'))
    args = parser.parse_args()
    directory = vm.current()
    if args.stage == 'bootstrap':
        vm.wait_ready(directory)
        phase(directory, 'bootstrap', 'sudo cloud-init status --wait\nsudo test -f /var/lib/hm-restore-test/bootstrap-complete.json\n' +
              f'{NIX} --version\nfindmnt / /nix /vault || findmnt --real\n')
        bundle = vm.owned_file(directory / 'source.bundle', vm.ROOT)
        vm.guest_check(directory)
        with bundle.open('rb') as source:
            vm.run(*vm.ssh_args(directory), 'umask 077; cat > /home/groscoe/source.bundle', stdin=source)
        expected = hashlib.sha256(bundle.read_bytes()).hexdigest()
        phase(directory, 'source',
              f'echo "{expected}  /home/groscoe/source.bundle" | sha256sum -c -\n'
              'mkdir -p /home/groscoe/Projects\n'
              f'if [ ! -d {PROJECT}/.git ]; then git clone --no-checkout /home/groscoe/source.bundle {PROJECT}; fi\n'
              f'git -C {PROJECT} checkout --detach {json.loads((directory / "manifest.json").read_text())["commit"]}\n'
              f'test "$(git -C {PROJECT} rev-parse HEAD)" = {json.loads((directory / "manifest.json").read_text())["commit"]}\n')
    elif args.stage == 'fixtures':
        phase(directory, 'fixtures', f'cd {PROJECT}\n{NIX} build --no-link --no-update-lock-file '
              '.#checks.x86_64-linux.xps-host .#checks.x86_64-linux.personal-scripts\n')
    elif args.stage == 'policies':
        prefix = (f'cd {PROJECT}\n'
                  f'tool="$({NIX} build --no-link --print-out-paths --no-update-lock-file .#xps-host)"\n')
        # Cloud-init's 0600 SSH fragment requires privileged inspection. Execute
        # the immutable built tool; keep the fragment's permissions unchanged.
        phase(directory, 'policy-before', prefix + 'sudo -n "$tool/bin/xps-host" check\n', (0, 1))
        password = (directory / 'guest-login.txt').read_text().split('Password: ', 1)[1].strip() + '\n'
        for name in ('policy-apply', 'policy-second-apply'):
            latest = phase(directory, name, prefix + 'sudo -n "$tool/bin/xps-host" apply\n', stdin=password)
        text = latest.read_text()
        assert re.search(r'changed=0\b', text), 'Second host-policy apply did not converge'
        phase(directory, 'policy-check', prefix + 'sudo -n "$tool/bin/xps-host" check\n')
    elif args.stage == 'build':
        phase(directory, 'home-build', f'cd {PROJECT}\n{NIX} build --no-link --print-out-paths --no-update-lock-file .#homeConfigurations.xps.activationPackage\n')
        phase(directory, 'full-flake-check', f'cd {PROJECT}\n{NIX} flake check --no-update-lock-file --show-trace\n')
    elif args.stage == 'activate':
        phase(directory, 'activation', f'''cd {PROJECT}
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
generation=$({NIX} build --no-link --print-out-paths --no-update-lock-file .#homeConfigurations.xps.activationPackage)
"$generation/home-path/bin/home-manager" -b pre-recovery switch --flake .#xps
"$generation/activate"
test "$(readlink -f /home/groscoe/.local/state/nix/profiles/home-manager)" = "$generation"
''')
    elif args.stage == 'applications':
        scenario(directory, 'login-shell')
        scenario(directory, 'shell-and-python')
        upload(directory, 'notebook-smoke.py')
        for name in ('jupyter-notebook', 'development-c', 'development-c-clang'):
            scenario(directory, name)
    elif args.stage == 'backup':
        phase(directory, 'backup-os-prerequisites', 'sudo -n env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y --no-install-recommends docker.io x11-apps\nsudo -n systemctl start docker.service\n')
        upload(directory, 'backup-smoke.py')
        phase(directory, 'backup-restore', '/usr/bin/python3 -I /home/groscoe/restore-smoke/backup-smoke.py\n')
    elif args.stage == 'desktop':
        scenario(directory, 'desktop-session-setup')
        desktop_login(directory)
        scenario(directory, 'virtual-monitor-adaptation')
        phase(directory, 'desktop-terminal', '''export DISPLAY=:0 XAUTHORITY=/home/groscoe/.Xauthority
i3-msg 'exec alacritty --title Recovery-terminal'
sleep 3
pgrep -a alacritty
''')
        scenario(directory, 'desktop-applications')
        scenario(directory, 'sddm-theme-mock')
        lock_roundtrip(directory)
        screenshot(directory)
    elif args.stage == 'rollback':
        scenario(directory, 'home-manager-rollback')
        scenario(directory, 'nix-native-rollback')
    elif args.stage == 'reboot-check':
        # No graphical login is implied by an SSH-only reboot check.
        script = json.loads((vm.SOURCE / 'scenarios.json').read_text())['post-reboot-acceptance']
        script = script.replace('systemctl --user is-active ssh-agent picom dunst xsettingsd polybar',
                                'systemctl --user is-active ssh-agent')
        phase(directory, 'post-reboot-acceptance', script)


if __name__ == '__main__':
    main()
