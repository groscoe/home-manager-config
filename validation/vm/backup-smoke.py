"""Guest-only synthetic protected-export, backup and restore integration test."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import pwd
import secrets
import socket
import stat
import subprocess
import sys
import tarfile

USER_HOME = Path('/home/groscoe')
STATE = Path('/srv/hm-restore-backup')
RESTIC = str(USER_HOME / '.nix-profile/bin/restic')


def guard():
    assert socket.gethostname() == 'hm-xps-restore'
    marker = Path('/etc/hm-restore-test.json')
    assert marker.stat().st_uid == 0
    cfg = json.loads(marker.read_text())
    assert cfg['purpose'] == 'disposable-home-manager-restore-test'
    assert subprocess.check_output(['systemd-detect-virt', '--vm'], text=True).strip() in ('kvm', 'qemu')
    if os.geteuid() == 0:
        assert Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower() == cfg['uuid']


def call(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def setup():
    guard()
    assert os.geteuid() == 0
    user = pwd.getpwnam('groscoe')
    assert user.pw_uid == 1000
    STATE.mkdir(mode=0o700, exist_ok=True)
    os.chown(STATE, user.pw_uid, user.pw_gid)
    credentials = Path('/etc/restic-env')
    if credentials.exists():
        assert (STATE / 'fixture-marker.json').exists(), 'Refuse existing non-fixture credentials'
    else:
        Path('/etc/restic-password').write_text(secrets.token_urlsafe(32) + '\n')
        credentials.write_text('export RESTIC_REPOSITORY=/srv/hm-restore-backup/repository\n'
                               'export RESTIC_PASSWORD_FILE=/etc/restic-password\n')
        for file in (credentials, Path('/etc/restic-password')):
            os.chown(file, 0, user.pw_gid)
            file.chmod(0o640)
        (STATE / 'fixture-marker.json').write_text(json.dumps({'synthetic': True}) + '\n')
    parent = USER_HOME / '.local/state/liqwid-infra'
    parent.mkdir(parents=True, exist_ok=True)
    os.chown(parent, user.pw_uid, user.pw_gid)
    parent.chmod(0o700)
    global_state = parent / 'global'
    global_state.mkdir(mode=0o700, exist_ok=True)
    (global_state / 'tailscaled.state').write_text('SYNTHETIC-TAILSCALE-STATE-NOT-A-REAL-IDENTITY\n')
    (global_state / 'tailscaled.state').chmod(0o600)
    (global_state / 'tailscaled.log').write_text('SYNTHETIC-IGNORED-LOG\n')
    desktop = USER_HOME / 'Desktop'
    desktop.mkdir(exist_ok=True)
    os.chown(desktop, user.pw_uid, user.pw_gid)
    header = desktop / 'luks-header.img'
    header.write_text('SYNTHETIC-NOT-A-LUKS-HEADER\n')
    header.chmod(0o400)
    data_parent = USER_HOME / 'Projects/onebus/data'
    data_parent.mkdir(parents=True, exist_ok=True)
    for directory in (USER_HOME / 'Projects/onebus', data_parent):
        os.chown(directory, user.pw_uid, user.pw_gid)
    database = data_parent / 'postgis'
    database.mkdir(mode=0o700, exist_ok=True)
    os.chown(database, 999, 999)
    data = database / 'synthetic-data.txt'
    data.write_text('SYNTHETIC-COLD-DATABASE-BYTES\n')
    os.chown(data, 999, 999)
    data.chmod(0o600)
    existing = subprocess.run(['docker', 'inspect', 'onebus-postgis'], capture_output=True)
    if existing.returncode:
        call('docker', 'create', '--name', 'onebus-postgis', 'busybox:1.37.0', 'sleep', '300')
    assert subprocess.check_output(['docker', 'inspect', '--format', '{{.State.Running}}', 'onebus-postgis'], text=True).strip() == 'false'


def extract_fixture():
    guard()
    assert os.geteuid() == 0
    target = STATE / 'privileged-restored'
    target.mkdir(mode=0o700, exist_ok=True)
    source = STATE / 'restored/vault/.restic-protected'
    for archive in source.glob('*.tar'):
        with tarfile.open(archive) as stream:
            for item in stream.getmembers():
                path = PurePosixPath(item.name)
                assert not path.is_absolute() and '..' not in path.parts
                assert str(path).startswith('home/groscoe/')
                assert item.isfile() or item.isdir(), 'Synthetic fixture should have no links/devices'
            stream.extractall(target, numeric_owner=True, filter='fully_trusted')
    database = target / 'home/groscoe/Projects/onebus/data/postgis/synthetic-data.txt'
    assert database.read_text() == 'SYNTHETIC-COLD-DATABASE-BYTES\n'
    assert (database.stat().st_uid, database.stat().st_gid, stat.S_IMODE(database.stat().st_mode)) == (999, 999, 0o600)
    header = target / 'home/groscoe/Desktop/luks-header.img'
    assert header.read_text() == 'SYNTHETIC-NOT-A-LUKS-HEADER\n'
    assert (header.stat().st_uid, stat.S_IMODE(header.stat().st_mode)) == (0, 0o400)
    state = target / 'home/groscoe/.local/state/liqwid-infra/global/tailscaled.state'
    assert state.read_text() == 'SYNTHETIC-TAILSCALE-STATE-NOT-A-REAL-IDENTITY\n'
    assert state.stat().st_uid == 0
    assert not state.with_name('tailscaled.log').exists()
    print('HM_RESTORE_PROTECTED_CONTENTS_AND_NUMERIC_PERMISSIONS_VERIFIED')


def main():
    guard()
    if sys.argv[1:] == ['--setup']:
        setup(); return
    if sys.argv[1:] == ['--extract-fixture']:
        extract_fixture(); return
    assert os.geteuid() == 1000
    call('sudo', '-n', '/usr/bin/python3', '-I', str(Path(__file__).resolve()), '--setup')
    raw = subprocess.check_output(['/bin/bash', '-c', 'set +x; set -a; source /etc/restic-env; exec /usr/bin/env -0'])
    env = dict(os.fsdecode(item).split('=', 1) for item in raw.split(b'\0') if item)
    env['RESTIC_CACHE_DIR'] = str(USER_HOME / '.cache/hm-restore-backup')
    def restic(*args):
        return subprocess.check_output([RESTIC, *args], env=env, text=True)
    if not (STATE / 'repository/config').exists():
        restic('init')
    call(str(USER_HOME / '.local/bin/install-restic-backup-export'))
    call(str(USER_HOME / '.local/bin/restic-backup'), '--run')
    snapshots = json.loads(restic('snapshots', '--json'))
    assert snapshots[-1]['hostname'] == 'hm-xps-restore'
    assert set(snapshots[-1]['paths']) == {'/home/groscoe', '/vault'}
    snapshot = snapshots[-1]['id']
    restic('check', '--read-data')
    restic('restore', snapshot, '--target', str(STATE / 'restored'),
           '--include', '/vault/.restic-protected', '--include', '/home/groscoe/restore-smoke/fixture.csv')
    original = (USER_HOME / 'restore-smoke/fixture.csv').read_bytes()
    restored = (STATE / 'restored/home/groscoe/restore-smoke/fixture.csv').read_bytes()
    assert original == restored
    call('sudo', '-n', '/usr/bin/python3', '-I', str(Path(__file__).resolve()), '--extract-fixture')
    call('sudo', '-n', 'docker', 'start', 'onebus-postgis')
    try:
        result = subprocess.run(['sudo', '-n', 'systemctl', 'start', 'restic-protected-export.service'], capture_output=True, text=True)
        assert result.returncode != 0, 'Running database was not refused'
        journal = subprocess.check_output(['sudo', '-n', 'journalctl', '-u', 'restic-protected-export.service', '-n', '25', '--no-pager'], text=True)
        assert 'Database container is running' in journal
    finally:
        call('sudo', '-n', 'docker', 'stop', '--time', '2', 'onebus-postgis')
    call('sudo', '-n', 'systemctl', 'start', 'restic-protected-export.service')
    success_file = USER_HOME / '.cache/restic-backup/last-success.json'
    before_success = success_file.read_bytes()
    before_ids = {item['id'] for item in json.loads(restic('snapshots', '--json'))}
    # Refuse a partially readable source rather than quietly taking a partial backup.
    unreadable = USER_HOME / 'restore-smoke/unreadable-fixture.csv'
    assert not unreadable.exists()
    call('sudo', '-n', 'install', '-o', 'root', '-g', 'root', '-m', '0600',
         str(USER_HOME / 'restore-smoke/fixture.csv'), str(unreadable))
    try:
        result = subprocess.run([str(USER_HOME / '.local/bin/restic-backup'), '--run'], capture_output=True, text=True)
        assert result.returncode != 0, 'Unreadable file did not stop the backup'
        output = result.stdout + result.stderr
        assert 'unreadable-fixture.csv' in output and 'permission denied' in output.lower(), output
    finally:
        call('sudo', '-n', 'rm', '--', str(unreadable))
    assert success_file.read_bytes() == before_success
    assert {item['id'] for item in json.loads(restic('snapshots', '--json'))} == before_ids
    # Verify an actually unmounted synthetic volume cannot become an empty backup.
    call('sudo', '-n', 'systemctl', 'stop', 'restic-protected-export.timer')
    call('sudo', '-n', 'umount', '/vault')
    try:
        assert not Path('/vault').is_mount()
        result = subprocess.run([str(USER_HOME / '.local/bin/restic-backup'), '--run'], capture_output=True, text=True)
        assert result.returncode == 0 and 'Deferred: required backup volume is not mounted' in result.stdout
    finally:
        call('sudo', '-n', 'mount', '/vault')
        call('sudo', '-n', 'systemctl', 'start', 'restic-protected-export.timer')
    assert success_file.read_bytes() == before_success
    assert {item['id'] for item in json.loads(restic('snapshots', '--json'))} == before_ids
    report = {'snapshot': snapshot, 'roots': ['/home/groscoe', '/vault'], 'repositoryCheckReadData': True,
              'userFileRoundtrip': True, 'protectedArchiveOwnershipAndModes': True,
              'ignoredLogOmitted': True, 'runningDatabaseRefused': True,
              'sourceReadErrorRefused': True, 'missingRequiredMountDeferred': True,
              'unsafeAttemptsCreatedNoSnapshotAndPreservedLastSuccess': True,
              'realDatabaseEngineRestoreTested': False, 'onlySyntheticState': True}
    (USER_HOME / 'restore-smoke/backup-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
