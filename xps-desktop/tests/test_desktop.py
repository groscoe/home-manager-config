import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


server = load('server')
client = load('client')
installer = load('install-backlight-access')


class DesktopSecurityTests(unittest.TestCase):
    @staticmethod
    def backlight_fixture(root):
        device = root / 'intel_backlight'
        device.mkdir()
        (device / 'brightness').write_text('96000\n')
        (device / 'max_brightness').write_text('96000\n')
        return device, {'backlightDevice': 'intel_backlight'}, root / 'recovery.json'

    def test_hardware_backlight_zero_and_exact_restoration(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name);device, cfg, path = self.backlight_fixture(root)
            server.prepare_backlight(cfg, path, root)
            self.assertEqual(int((device / 'brightness').read_text()), 0)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            server.prepare_backlight(cfg, path, root)
            self.assertEqual(json.loads(path.read_text())['previous'], 96000)
            server.restore_backlight(cfg, path, root)
            self.assertEqual(int((device / 'brightness').read_text()), 96000)
            self.assertFalse(path.exists())

    def test_manual_brightness_change_is_preserved(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name);device, cfg, path = self.backlight_fixture(root)
            server.prepare_backlight(cfg, path, root)
            (device / 'brightness').write_text('12000\n')
            server.prepare_backlight(cfg, path, root)
            self.assertEqual(json.loads(path.read_text())['previous'], 96000)
            server.restore_backlight(cfg, path, root)
            self.assertEqual(int((device / 'brightness').read_text()), 12000)

    def test_missing_backlight_permission_changes_nothing(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name);device, cfg, path = self.backlight_fixture(root)
            with patch.object(server.os, 'access', return_value=False):
                with self.assertRaisesRegex(RuntimeError, 'install-xps-backlight-access'):
                    server.prepare_backlight(cfg, path, root)
            self.assertEqual(int((device / 'brightness').read_text()), 96000)
            self.assertFalse(path.exists())

    def test_changed_backlight_range_refuses_saved_value(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name);device, cfg, path = self.backlight_fixture(root)
            server.prepare_backlight(cfg, path, root)
            (device / 'max_brightness').write_text('10\n')
            with self.assertRaisesRegex(RuntimeError, 'device changed'):
                server.restore_backlight(cfg, path, root)
            self.assertEqual(int((device / 'brightness').read_text()), 0)
            self.assertTrue(path.exists())

    def test_backlight_cleanup_runs_even_if_x11_and_compositor_cleanup_fail(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name);config = root / 'config.json';config.write_text('{}')
            with patch.object(server.sys, 'argv', ['server.py', str(config), 'restore-display']), \
                 patch.object(server, 'runtime_directory', return_value=root), \
                 patch.object(server, 'restore_display', side_effect=RuntimeError('X server gone')), \
                 patch.object(server, 'restore_compositor', side_effect=RuntimeError('session bus gone')), \
                 patch.object(server, 'restore_backlight') as restore:
                with self.assertRaises(RuntimeError):
                    server.main()
                restore.assert_called_once_with({}, root / 'backlight-state.json', brightness_before_cleanup=None)

    def test_dpms_reset_cannot_replace_saved_or_manually_adjusted_brightness(self):
        for manual in (0, 12000):
            with self.subTest(manual=manual), tempfile.TemporaryDirectory() as name:
                root = Path(name);device, cfg, path = self.backlight_fixture(root)
                server.prepare_backlight(cfg, path, root)
                (device / 'brightness').write_text('48000\n')  # Driver reset during power cleanup.
                server.restore_backlight(cfg, path, root, brightness_before_cleanup=manual)
                self.assertEqual(int((device / 'brightness').read_text()), 96000 if manual == 0 else manual)

    def test_missing_backlight_device_does_not_skip_other_cleanup(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name);config = root / 'config.json';config.write_text('{}')
            (root / 'backlight-state.json').write_text('{}')
            with patch.object(server.sys, 'argv', ['server.py', str(config), 'restore-display']), \
                 patch.object(server, 'runtime_directory', return_value=root), \
                 patch.object(server, 'backlight_device', return_value=root / 'missing'), \
                 patch.object(server, 'restore_display') as display, \
                 patch.object(server, 'restore_compositor') as compositor, \
                 patch.object(server, 'restore_backlight') as backlight:
                with self.assertRaises(FileNotFoundError):
                    server.main()
                display.assert_called_once()
                compositor.assert_called_once()
                backlight.assert_called_once()

    def test_backlight_rule_is_limited_to_one_attribute_and_private_group(self):
        rule = installer.rule_for('groscoe', 'intel_backlight')
        self.assertIn('KERNEL=="intel_backlight"', rule)
        self.assertEqual(rule.count('/sys%p/brightness'), 2)
        self.assertNotIn('/dev/', rule)
        self.assertNotIn('MODE=', rule)
        for group in ['groscoe other', '../root', 'groscoe;command']:
            with self.assertRaises(RuntimeError):
                installer.rule_for(group, 'intel_backlight')

    def test_alternative_backlight_name_and_unsafe_names(self):
        rule = installer.rule_for('groscoe', 'amdgpu_bl1')
        self.assertIn('KERNEL=="amdgpu_bl1"', rule)
        self.assertNotIn('intel_backlight', rule)
        self.assertEqual(str(installer.device_path('amdgpu_bl1')), '/sys/class/backlight/amdgpu_bl1/brightness')
        for device in ['../root', '/sys/devices', '.', '..', 'intel*', 'name"', 'name;command']:
            with self.subTest(device=device), self.assertRaises(RuntimeError):
                installer.rule_for('groscoe', device)

    def test_backlight_installer_refuses_conflicting_rule_and_symlinks(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'rule';expected = installer.rule_for('groscoe', 'intel_backlight')
            installer.check_rule(path, expected)
            path.write_text('unrelated rule\n')
            with self.assertRaises(RuntimeError):
                installer.check_rule(path, expected)
            self.assertEqual(path.read_text(), 'unrelated rule\n')
            path.unlink();path.symlink_to(Path(name) / 'missing')
            with self.assertRaises(RuntimeError):
                installer.check_rule(path, expected)

    def test_compositor_mode_restores_original_and_preserves_daemon(self):
        for original in (0, 1, 2):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as name:
                path = Path(name) / 'compositor.json'
                state = {'mode': original}
                def mode(cfg, env, owner, value=None):
                    if value is None:
                        return state['mode']
                    state['mode'] = value
                with patch.object(server, 'compositor_owner', return_value=':1.42'), patch.object(server, 'compositor_mode', side_effect=mode):
                    server.prepare_compositor({}, {'DISPLAY': ':0', 'XAUTHORITY': '/inert/auth'}, path)
                    self.assertEqual(state['mode'], 0)
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                    server.prepare_compositor({}, {'DISPLAY': ':0', 'XAUTHORITY': '/inert/auth'}, path)
                    self.assertEqual(json.loads(path.read_text())['previous'], original)
                    server.restore_compositor({}, path)
                    self.assertEqual(state['mode'], original)
                self.assertFalse(path.exists())

    def test_compositor_manual_override_or_replacement_is_preserved(self):
        for owner, mode in [(':1.42', 1), (':1.43', 0), (None, 0)]:
            with self.subTest(owner=owner, mode=mode), tempfile.TemporaryDirectory() as name:
                path = Path(name) / 'compositor.json'
                path.write_text(json.dumps({'owner': ':1.42', 'previous': 2, 'environment': {'DISPLAY': ':0'}}))
                path.chmod(0o600)
                with patch.object(server, 'compositor_owner', return_value=owner), patch.object(server, 'compositor_mode', return_value=mode) as call:
                    server.restore_compositor({}, path)
                    self.assertTrue(all(len(c.args) == 3 for c in call.call_args_list))
                self.assertFalse(path.exists())

    def test_absent_compositor_is_not_started_for_sharing(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'compositor.json'
            with patch.object(server, 'compositor_owner', return_value=None), patch.object(server, 'compositor_mode') as mode:
                server.prepare_compositor({}, {'DISPLAY': ':0', 'XAUTHORITY': '/inert/auth'}, path)
                mode.assert_not_called()
            self.assertFalse(path.exists())

    def test_client_count_only_includes_connected_vnc_sockets_owned_by_the_service(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            p = root / '42'
            (p / 'fd').mkdir(parents=True)
            (p / 'net').mkdir()
            (p / 'comm').write_text('x0vncserver\n')
            for fd, inode in [('3', '100'), ('4', '101'), ('5', '102')]:
                (p / 'fd' / fd).symlink_to('socket:[' + inode + ']')
            (p / 'net/unix').write_text('Num RefCount Protocol Flags Type St Inode Path\n'
                '0: 2 0 10000 0001 01 100 /run/private/desktop.sock\n'
                '0: 2 0 0 0001 03 101 /run/private/desktop.sock\n'
                '0: 2 0 0 0001 03 102 /tmp/.X11-unix/X0\n'
                '0: 2 0 0 0001 03 103 /run/private/desktop.sock\n')
            self.assertEqual(server.active_vnc_clients(42, '/run/private/desktop.sock', root), 1)
            (p / 'fd/4').unlink()
            self.assertEqual(server.active_vnc_clients(42, '/run/private/desktop.sock', root), 0)
            (p / 'comm').write_text('unrelated\n')
            with self.assertRaises(RuntimeError):
                server.active_vnc_clients(42, '/run/private/desktop.sock', root)

    @staticmethod
    def fake_gamma(args, **kwargs):
        if args[1] == 'save':
            p = Path(args[2])
            p.write_bytes(b'inert exact-colour-lookup-table fixture')
            p.chmod(0o600)

    def test_display_power_is_restored_without_changing_idle_lock_settings(self):
        for initially_enabled in [True, False]:
            with self.subTest(initially_enabled=initially_enabled), tempfile.TemporaryDirectory() as name:
                state = {'enabled': initially_enabled, 'monitor': 'Off' if initially_enabled else 'On'}
                original = dict(state)
                calls = []

                def power(cfg, env, *args):
                    calls.append(args)
                    if args == ('q',):
                        return ('DPMS is Enabled\nMonitor is %s\n' % state['monitor']) if state['enabled'] else 'DPMS is Disabled\n'
                    if args in [('+dpms',), ('-dpms',)]:
                        state['enabled'] = args == ('+dpms',)
                    elif args[:2] == ('dpms', 'force'):
                        state['monitor'] = args[2].title()
                    else:
                        self.fail('Unexpected display/locking command: ' + repr(args))
                    return ''

                path = Path(name) / 'power.json'
                cfg = {'panelGamma': '/inert/panel-gamma'}
                with patch.object(server, 'display_power', side_effect=power), patch.object(server.subprocess, 'run', side_effect=self.fake_gamma) as gamma:
                    server.prepare_display(cfg, {'DISPLAY': ':0', 'XAUTHORITY': '/inert/auth'}, path)
                    self.assertFalse(state['enabled'])
                    self.assertEqual(state['monitor'], 'On')
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                    server.restore_display(cfg, path)
                    self.assertEqual([c.args[0][1] for c in gamma.call_args_list], ['save', 'blank', 'restore'])
                self.assertEqual(state, original)
                self.assertFalse(path.exists())
                self.assertFalse(any('s' in args or 'off' == args[0] for args in calls))

    def test_display_startup_failure_retains_recovery_and_can_restore(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'power.json'
            status = 'DPMS is Enabled\nMonitor is Off\n'

            def startup(cfg, env, *args):
                if args == ('q',):
                    return status
                if args == ('-dpms',):
                    raise RuntimeError('inert simulated failure')
                return ''

            cfg = {'panelGamma': '/inert/panel-gamma'}
            with patch.object(server, 'display_power', side_effect=startup), patch.object(server.subprocess, 'run', side_effect=self.fake_gamma):
                with self.assertRaises(RuntimeError):
                    server.prepare_display(cfg, {'DISPLAY': ':0', 'XAUTHORITY': '/inert/auth'}, path)
            self.assertTrue(path.exists())
            with patch.object(server, 'display_power', return_value=status) as power, patch.object(server.subprocess, 'run', side_effect=self.fake_gamma) as gamma:
                server.restore_display(cfg, path)
                self.assertIn(('+dpms',), [x.args[2:] for x in power.call_args_list])
                self.assertIn(('dpms', 'force', 'off'), [x.args[2:] for x in power.call_args_list])
                self.assertEqual(gamma.call_args.args[0][1], 'restore')
            self.assertFalse(path.exists())

    def test_manual_display_power_change_takes_precedence_over_old_state(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'power.json'
            path.write_text(json.dumps({'environment': {'DISPLAY': ':0'}, 'enabled': False,
                                        'monitor': 'On', 'prepared': True}))
            path.chmod(0o600)
            with patch.object(server, 'display_power', return_value='DPMS is Enabled\nMonitor is On\n') as power:
                server.restore_display({}, path)
                self.assertEqual(power.call_count, 1)
            self.assertFalse(path.exists())

    def test_password_metadata_accepts_private_file_and_rejects_symlink_and_public_file(self):
        with tempfile.TemporaryDirectory() as name:
            p = Path(name) / 'password'
            p.write_bytes(b'12345678')
            p.chmod(0o600)
            self.assertEqual(server.private_password(p), p)
            alias = Path(name) / 'link'
            alias.symlink_to(p)
            with self.assertRaises(RuntimeError):
                server.private_password(alias)
            p.chmod(0o644)
            with self.assertRaises(RuntimeError):
                server.private_password(p)

    def test_refuses_public_cache_and_symlink(self):
        with tempfile.TemporaryDirectory() as name:
            p = Path(name) / 'private'
            self.assertEqual(client.private_directory(p), p)
            p.chmod(0o755)
            with self.assertRaises(RuntimeError):
                client.private_directory(p)
            alias = Path(name) / 'alias'
            alias.symlink_to(p)
            with self.assertRaises(RuntimeError):
                client.private_directory(alias)

    def test_i3_environment_is_unique_and_does_not_export_other_variables(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            auth = root / 'auth'
            auth.write_text('inert fixture')
            proc = root / '42'
            proc.mkdir()
            (proc / 'comm').write_text('i3\n')
            (proc / 'environ').write_bytes(b'DISPLAY=:0\0XAUTHORITY=' + str(auth).encode() + b'\0UNRELATED=do-not-export\0')
            self.assertEqual(server.i3_environment(root), {'DISPLAY': ':0', 'XAUTHORITY': str(auth)})
            second = root / '43'
            second.mkdir()
            (second / 'comm').write_text('i3\n')
            (second / 'environ').write_bytes((proc / 'environ').read_bytes())
            with self.assertRaises(RuntimeError):
                server.i3_environment(root)

    def test_port_collision_prevents_remote_startup(self):
        with tempfile.TemporaryDirectory() as name, socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            cfg = {'localPort': listener.getsockname()[1]}
            with patch.object(client.subprocess, 'run') as run:
                with self.assertRaises(SystemExit) as error:
                    client.worker(cfg, Path(name))
                self.assertEqual(error.exception.code, 1)
                run.assert_not_called()
            self.assertIn('already in use', (Path(name) / 'error.txt').read_text())

    def test_recent_disconnect_does_not_block_reconnecting(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            listener.listen()
            self.assertFalse(client.local_port_free(port))
            with socket.create_connection(('127.0.0.1', port)) as peer:
                accepted, _ = listener.accept()
                with accepted:
                    accepted.shutdown(socket.SHUT_WR)
                    self.assertEqual(peer.recv(1), b'')
        self.assertTrue(client.local_port_free(port))

    def test_ssh_disables_only_its_own_forwarding_and_keeps_host_key_checking(self):
        args = client.ssh_base({'ssh': '/usr/bin/ssh', 'sshPort': 2222})
        self.assertIn('ForwardAgent=no', args)
        self.assertIn('ForwardX11=no', args)
        self.assertIn('BatchMode=yes', args)
        self.assertFalse(any('StrictHostKeyChecking=no' in x for x in args))


if __name__ == '__main__':
    unittest.main()
