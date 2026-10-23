"""Test startup restoration against disposable files; never call systemd."""

import importlib.util
import json
import os
import pathlib
import tempfile
from unittest import mock

SOURCE = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('startup', SOURCE / 'nix_startup.py')
startup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(startup)


def expect_failure(callback, message):
    try:
        callback()
    except (ValueError, RuntimeError, OSError) as error:
        assert message in str(error), error
    else:
        raise AssertionError('Expected rejection: ' + message)


def main():
    os.umask(0o022)
    results = []
    with tempfile.TemporaryDirectory(prefix='xps-nix-test-', dir='/tmp') as directory:
        root = pathlib.Path(directory)
        uid, gid = os.getuid(), os.getgid()
        initial = startup.current(root, uid, gid)
        assert startup.inspect(root, fixture=True)['would_change']
        assert startup.current(root, uid, gid) == initial, 'Inspection changed files'
        old_umask = os.umask(0o002)
        try:
            result = startup.apply(root, fixture=True)
        finally:
            os.umask(old_umask)
        assert result['changed'] and not result['would_change']
        backup = pathlib.Path(result['backup'])
        assert backup.stat().st_mode & 0o777 == 0o700
        assert (backup / 'state.json').stat().st_mode & 0o777 == 0o600
        assert json.loads((backup / 'state.json').read_text())['before'] == initial
        count = len(list((root / 'var/backups').iterdir()))
        second = startup.apply(root, fixture=True)
        assert not second['changed'] and second['backup'] is None
        assert len(list((root / 'var/backups').iterdir())) == count
        results += ['read-only inspection', 'fresh convergence with group-writable umask', 'private complete backup', 'idempotence']

        service = root / 'etc/systemd/system/nix-daemon.service'
        service.chmod(0o600)
        assert startup.inspect(root, fixture=True)['would_change']
        repaired = startup.apply(root, fixture=True)
        assert service.stat().st_mode & 0o777 == 0o644
        startup.rollback(repaired['backup'], root, fixture=True)
        assert service.stat().st_mode & 0o777 == 0o600
        startup.apply(root, fixture=True)
        results += ['metadata repair and exact rollback']

        before = startup.current(root, uid, gid)
        service.write_text('Old service definition\n')
        changed = startup.apply(root, fixture=True)
        service.write_text('Later administrator change\n')
        expect_failure(lambda: startup.rollback(changed['backup'], root, fixture=True), 'changed since')
        service.write_bytes((SOURCE / 'nix-units/nix-daemon.service').read_bytes())
        startup.rollback(changed['backup'], root, fixture=True)
        assert service.read_text() == 'Old service definition\n'
        startup.apply(root, fixture=True)
        assert startup.current(root, uid, gid) == before
        results += ['rollback refuses subsequent changes', 'content rollback']

        service.write_text('Before injected failure\n')
        before = startup.current(root, uid, gid)
        writer = startup.write_state
        calls = 0

        def fail_once(*args):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError('injected failure')
            return writer(*args)

        with mock.patch.object(startup, 'write_state', fail_once):
            expect_failure(lambda: startup.apply(root, fixture=True), 'injected failure')
        assert startup.current(root, uid, gid) == before
        results += ['automatic rollback after partial failure']

        with mock.patch.object(startup.shutil, 'copyfile', side_effect=OSError('injected backup failure')):
            expect_failure(lambda: startup.apply(root, fixture=True), 'injected backup failure')
        assert startup.current(root, uid, gid) == before
        results += ['backup failure leaves startup objects untouched']

        reloads = 0

        def fail_first_reload(fixture):
            nonlocal reloads
            reloads += 1
            if reloads == 1:
                raise RuntimeError('injected reload failure')

        with mock.patch.object(startup, 'reload_systemd', fail_first_reload):
            expect_failure(lambda: startup.apply(root, fixture=True), 'injected reload failure')
        assert reloads == 2 and startup.current(root, uid, gid) == before
        results += ['reload failure restores the prior definitions']

    with tempfile.TemporaryDirectory(prefix='xps-nix-test-', dir='/tmp') as directory:
        root = pathlib.Path(directory)
        uid, gid = os.getuid(), os.getgid()
        legacy_payloads = {}
        for item in startup.manifest():
            if item['kind'] in ['file', 'link']:
                target = root / item['legacy_targets'][0].lstrip('/')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('Original Nix installer definition: ' + target.name + '\n')
                legacy_payloads[str(target)] = target.read_bytes()
                destination = root / item['path'].lstrip('/')
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(target)
        before = startup.current(root, uid, gid)
        result = startup.apply(root, fixture=True)
        assert not startup.inspect(root, fixture=True)['would_change']
        for name, data in legacy_payloads.items():
            assert pathlib.Path(name).read_bytes() == data, 'Modified installer link target'
        startup.rollback(result['backup'], root, fixture=True)
        assert startup.current(root, uid, gid) == before
        results += ['known installer links adopted without following them', 'installer links restored by rollback']
        service = root / 'etc/systemd/system/nix-daemon.service'
        service.unlink()
        service.symlink_to('/unreviewed/destination')
        expect_failure(lambda: startup.apply(root, fixture=True), 'Unreviewed symlink')
        results += ['unreviewed link rejected']

    with tempfile.TemporaryDirectory(prefix='xps-nix-test-', dir='/tmp') as directory:
        root = pathlib.Path(directory)
        unit = root / 'etc/systemd/system/custom-start-nix-in-other-partition.service'
        unit.parent.mkdir(parents=True)
        unit.write_text('[Unit]\nRequiresMountsFor=/nix/store\n\n[Service]\nExecStart=systemctl enable --now nix-daemon.socket\nKillMode=process\n\n[Install]\nWantedBy=multi-user.target\n')
        link = root / 'etc/systemd/system/multi-user.target.wants/custom-start-nix-in-other-partition.service'
        link.parent.mkdir()
        link.symlink_to(unit)
        before = startup.current(root, os.getuid(), os.getgid())
        result = startup.apply(root, fixture=True)
        assert not unit.exists() and not link.is_symlink()
        startup.rollback(result['backup'], root, fixture=True)
        assert startup.current(root, os.getuid(), os.getgid()) == before
        unit.write_text('Different custom configuration\n')
        expect_failure(lambda: startup.apply(root, fixture=True), 'Unreviewed obsolete unit')
        results += ['known obsolete workaround retired and restored', 'unknown workaround rejected']

    expect_failure(lambda: startup.inspect(pathlib.Path('/etc'), fixture=True), 'disposable')
    results += ['fixture escape rejected']
    print(json.dumps({'nix_startup_tests_passed': results}, indent=2))


if __name__ == '__main__':
    main()
