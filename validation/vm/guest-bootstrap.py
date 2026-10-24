"""Guest-only Ubuntu bootstrap. Refuse to run outside this marked QEMU guest."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import urllib.request


def guard():
    marker = Path('/etc/hm-restore-test.json')
    assert os.geteuid() == 0
    assert marker.is_file() and marker.stat().st_uid == 0
    cfg = json.loads(marker.read_text())
    assert cfg['purpose'] == 'disposable-home-manager-restore-test'
    assert Path('/etc/hostname').read_text().strip() == 'hm-xps-restore'
    assert Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower() == cfg['uuid']
    assert subprocess.check_output(['systemd-detect-virt', '--vm'], text=True).strip() in ('kvm', 'qemu')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    assert release['ID'].strip('"') == 'ubuntu' and release['VERSION_ID'].strip('"') == '22.04'
    assert os.uname().machine == 'x86_64'
    return cfg


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def guest_volume(serial, label, mountpoint):
    device = Path('/dev/disk/by-id/virtio-' + serial)
    assert device.is_block_device(), device
    assert subprocess.check_output(['lsblk', '-ndo', 'SERIAL', str(device)], text=True).strip() == serial
    probe = subprocess.run(['blkid', '-o', 'export', str(device)], capture_output=True, text=True)
    if probe.returncode == 2:
        run('mkfs.ext4', '-q', '-L', label, str(device))
    else:
        assert probe.returncode == 0
        values = dict(line.split('=', 1) for line in probe.stdout.splitlines() if '=' in line)
        assert values['TYPE'] == 'ext4' and values['LABEL'] == label
    destination = Path(mountpoint)
    destination.mkdir(exist_ok=True)
    fstab = Path('/etc/fstab')
    line = f'LABEL={label} {mountpoint} ext4 defaults 0 2\n'
    text = fstab.read_text()
    if line not in text:
        assert not any(x.split()[1:2] == [mountpoint] for x in text.splitlines() if x and not x.startswith('#'))
        with fstab.open('a') as stream:
            stream.write(line)
    if not os.path.ismount(destination):
        run('mount', mountpoint)
    assert subprocess.check_output(['findmnt', '-no', 'LABEL', mountpoint], text=True).strip() == label


def main():
    guard()
    # cloud-init is not a root login session; provide root's real home to Nix
    # and all its child commands, including the final daemon verification.
    os.environ['HOME'] = '/root'
    state = Path('/var/lib/hm-restore-test')
    state.mkdir(mode=0o700, exist_ok=True)
    guest_volume('HMNIX', 'HMNIX', '/nix')
    guest_volume('HMVAULT', 'HMVAULT', '/vault')
    run('chown', 'groscoe:groscoe', '/vault')
    packages = [
        'ca-certificates', 'curl', 'git', 'xz-utils', 'bzip2', 'python3', 'sudo',
        'openssh-server', 'dbus-user-session', 'dbus-x11', 'xorg', 'xauth', 'xvfb',
        'python3-pyqt5', 'python3-pyqt5.qtquick', 'fprintd', 'libpam-fprintd',
        'i3lock', 'sddm', 'qml-module-qtquick-layouts', 'qml-module-qtquick-controls2',
        'qml-module-qtgraphicaleffects', 'libqt5svg5', 'network-manager', 'bluez',
        'pulseaudio', 'policykit-1', 'gnome-screenshot', 'fonts-dejavu-core',
    ]
    env = os.environ.copy()
    env['DEBIAN_FRONTEND'] = 'noninteractive'
    run('apt-get', '-o', 'DPkg::Lock::Timeout=300', 'update', env=env)
    run('apt-get', '-o', 'DPkg::Lock::Timeout=300', 'install', '-y', '--no-install-recommends', *packages, env=env)
    (state / 'ubuntu-packages.json').write_text(json.dumps(packages, indent=2) + '\n')
    with (state / 'ubuntu-package-versions.tsv').open('w') as output:
        run('dpkg-query', '-W', '-f=${binary:Package}\t${Version}\t${db:Status-Status}\n', stdout=output)
    # Keep the initial bootstrap headless; enable SDDM deliberately after HM activation.
    run('systemctl', 'disable', '--now', 'sddm.service')
    run('systemctl', 'set-default', 'multi-user.target')
    # Guest-only test controls, outside HM's managed files. Remove deliberately
    # once synthetic backup/scanner fixtures have been supplied.
    Path('/etc/hm-restore-test-block-automation').touch()
    for name in ('restic-backup.service', 'clamav-scan.service'):
        directory = Path('/etc/systemd/user') / (name + '.d')
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'restore-test.conf').write_text(
            '[Unit]\nConditionPathExists=!/etc/hm-restore-test-block-automation\n')
    if not Path('/nix/var/nix/profiles/default/bin/nix').exists():
        version = '2.34.9'
        expected = 'e8912e087582b3799e0e5a6b06f9d63386c54821f77ad4de3b9b748736ad364e'
        url = f'https://releases.nixos.org/nix/nix-{version}/nix-{version}-x86_64-linux.tar.xz'
        archive = state / 'nix-installer.tar.xz'
        with urllib.request.urlopen(url, timeout=120) as response, archive.open('wb') as output:
            while data := response.read(1024 * 1024):
                output.write(data)
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
        unpacked = state / 'installer'
        unpacked.mkdir(exist_ok=True)
        run('tar', '-xJf', str(archive), '-C', str(unpacked))
        run('sh', str(unpacked / f'nix-{version}-x86_64-linux/install'),
            '--daemon', '--yes', '--no-modify-profile', '--no-channel-add', env=env)
    nix_conf = Path('/etc/nix/nix.conf')
    text = nix_conf.read_text()
    additions = '\n# Disposable guest test settings\nexperimental-features = nix-command flakes\nmax-jobs = 2\ncores = 2\n'
    if additions not in text:
        with nix_conf.open('a') as stream:
            stream.write(additions)
        run('systemctl', 'restart', 'nix-daemon.service')
    run('/nix/var/nix/profiles/default/bin/nix', 'store', 'info', '--store', 'daemon')
    (state / 'bootstrap-complete.json').write_text(json.dumps({'status': 'complete', 'nixVersion': '2.34.9'}, indent=2) + '\n')
    print('HM_RESTORE_GUEST_BOOTSTRAP_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
