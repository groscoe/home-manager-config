import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('restore_vm', Path(__file__).with_name('vm.py'))
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class RestoreBoundaryTests(unittest.TestCase):
    def test_refuses_unmarked_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / 'valuable').write_text('keep')
            with patch.object(vm, 'ROOT', root):
                with self.assertRaises(ValueError): vm.initialize()
            self.assertEqual((root / 'valuable').read_text(), 'keep')

    def test_refuses_changed_filesystem_record(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / 'ownership.json').write_text(json.dumps({
                'purpose': vm.PURPOSE, 'root': str(root), 'device': -1}))
            with patch.object(vm, 'ROOT', root):
                with self.assertRaises(ValueError): vm.initialize()

    def fixture(self, root):
        directory = root / 'run'
        directory.mkdir(mode=0o700)
        (directory / 'manifest.json').write_text(json.dumps({
            'purpose': vm.PURPOSE, 'uuid': '12345678-1234-4234-8234-123456789abc'}))
        for name in ('root.qcow2', 'nix.qcow2', 'vault.qcow2', 'uefi-vars.fd', 'seed.img', 'client-key', 'known-hosts'):
            (directory / name).touch(mode=0o600)
        return directory

    def test_refuses_public_state_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            root.chmod(0o755)
            with self.assertRaises(ValueError): vm.private_directory(root)

    def test_refuses_symlink_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); (root / 'target').mkdir(mode=0o700)
            (root / 'link').symlink_to(root / 'target')
            with self.assertRaises(ValueError): vm.private_directory(root / 'link')

    def test_refuses_external_disk_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); directory = self.fixture(root)
            for bad in (Path('/dev/sda'), root / 'outside'):
                if bad.name == 'outside': bad.touch()
                with self.assertRaises(ValueError): vm.owned_file(bad, directory)
            (directory / 'root.qcow2').unlink()
            (directory / 'root.qcow2').symlink_to(root / 'outside')
            with self.assertRaises(ValueError): vm.owned_file(directory / 'root.qcow2', root)

    def test_qemu_exposes_only_owned_disks_and_loopback_ssh(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); directory = self.fixture(root)
            with patch.object(vm, 'ROOT', root):
                argv = vm.qemu_args(directory, {'qemu': '/nix/store/test/bin/qemu', 'firmware': '/nix/store/test/code.fd'})
            self.assertIn('user,id=net0,ipv6=off,hostfwd=tcp:127.0.0.1:22222-:22', argv)
            self.assertFalse(any('/dev/' in arg or 'virtfs' in arg or 'hostdev' in arg for arg in argv))
            self.assertEqual(sum(arg == '-drive' for arg in argv), 6)
            self.assertIn('unix:' + str(directory / 'viewer.sock'), argv)

    def test_offline_mode_keeps_explicit_loopback_forward(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); directory = self.fixture(root)
            with patch.object(vm, 'ROOT', root):
                argv = vm.qemu_args(directory, {'qemu': 'qemu', 'firmware': '/nix/store/test/code.fd'}, True)
            self.assertIn('user,id=net0,ipv6=off,hostfwd=tcp:127.0.0.1:22222-:22,restrict=on', argv)

    def test_guest_ssh_cannot_inherit_agent_or_host_alias_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); directory = self.fixture(root)
            with patch.object(vm, 'ROOT', root): argv = vm.ssh_args(directory)
            self.assertEqual(argv[1:3], ['-F', '/dev/null'])
            self.assertIn('ForwardAgent=no', argv)
            self.assertIn('IdentitiesOnly=yes', argv)
            self.assertIn('StrictHostKeyChecking=yes', argv)

    def test_guest_command_stops_when_identity_check_fails(self):
        with patch.object(vm, 'guest_check', side_effect=ValueError('wrong machine')), patch.object(vm, 'run') as execute:
            with self.assertRaises(ValueError): vm.guest_exec(Path('/unused'), 'sudo touch /should-never-run')
            execute.assert_not_called()

    def test_readiness_never_retries_a_host_key_failure(self):
        error = subprocess.CalledProcessError(255, 'ssh', stderr='Host key verification failed')
        with patch.object(vm, 'guest_check', side_effect=error), patch.object(vm.time, 'sleep') as sleep:
            with self.assertRaises(subprocess.CalledProcessError): vm.wait_ready(Path('/unused'))
            sleep.assert_not_called()

    def test_readiness_retries_only_transient_connection_failure(self):
        error = subprocess.CalledProcessError(255, 'ssh', stderr='Connection refused')
        with patch.object(vm, 'guest_check', side_effect=[error, None]) as check, patch.object(vm.time, 'sleep'):
            vm.wait_ready(Path('/unused'))
            self.assertEqual(check.call_count, 2)


if __name__ == '__main__':
    unittest.main()
