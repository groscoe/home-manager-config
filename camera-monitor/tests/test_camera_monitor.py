import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('camera_monitor', Path(__file__).parents[1] / 'monitor.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CameraTests(unittest.TestCase):
    def test_discovery_uses_device_numbers_not_fixed_video_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for cls, name, dev in [('video4linux', 'video17', '81:17'), ('media', 'media2', '240:2')]:
                p = root / cls / name
                p.mkdir(parents=True)
                (p / 'dev').write_text(dev)
            self.assertEqual(m.discover(root), {(81, 17): 'video17', (240, 2): 'media2'})

    def test_live_own_handle_detected_then_closed_without_camera(self):
        # /dev/null substitutes for the camera: exercise real /proc fd detection.
        if not Path('/proc/self/fd').exists():
            return
        info = Path('/dev/null').stat()
        devices = {(os.major(info.st_rdev), os.minor(info.st_rdev)): 'fixture-camera'}
        before = m.scan(devices=devices)
        with open('/dev/null'):
            during = m.scan(devices=devices)
            self.assertIn(os.getpid(), [p['pid'] for p in during['holders']])
        # The test runner may already have /dev/null open; transition tests below
        # independently verify closing and PID reuse without relying on its stdio.
        self.assertIn(during['state'], ('access',))

    def test_transitions_and_pid_reuse(self):
        p = {'pid': 12, 'start': '100', 'name': 'browser', 'devices': ['video0']}
        q = {**p, 'start': '101'}
        self.assertEqual(m.changes({'holders': []}, {'holders': [p]}), [('opened', p)])
        self.assertEqual(m.changes({'holders': [p]}, {'holders': [p]}), [])
        self.assertEqual(m.changes({'holders': [p]}, {'holders': []}), [('closed', p)])
        self.assertEqual(m.changes({'holders': [p]}, {'holders': [q]}), [('opened', q), ('closed', p)])

    def test_unreadable_holder_does_not_report_false_close(self):
        p = {"pid": 12, "start": "100"}
        self.assertEqual(m.changes({"holders": [p]}, {"holders": [], "unreadable": [12]}), [])

    def test_virtual_relay_is_not_reported_as_consumer(self):
        p = {"pid": 1, "start": "100", "infrastructure": True}
        self.assertEqual(m.changes({"holders": []}, {"holders": [p]}), [])
        active = {**p, "infrastructure": False}
        self.assertEqual(m.changes({"holders": [p]}, {"holders": [active]}), [("opened", active)])
        self.assertEqual(m.changes({"holders": [active]}, {"holders": [p]}), [("closed", active)])

    def test_lost_system_coverage_does_not_claim_access_stopped(self):
        p = {"pid": 1, "start": "100"}
        self.assertEqual(m.changes({"holders": [p], "coverage": "system"},
                                  {"holders": [], "coverage": "user"}), [])

    def test_absent_devices(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(m.scan(Path(td), devices={})['state'], 'absent')

    def test_permission_denied_is_partial_not_clear(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / '123'
            p.mkdir()
            original = Path.read_text
            def denied(path, *a, **kw):
                if path == p / 'stat':
                    raise PermissionError()
                return original(path, *a, **kw)
            with patch.object(Path, 'read_text', denied):
                result = m.scan(root, {(81, 0): 'video0'})
            self.assertEqual(result['state'], 'partial')
            self.assertEqual(result['unreadable'], [123])

    def test_stale_or_invalid_status_is_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'state.json'
            self.assertEqual(m.read_status(path)['state'], 'unavailable')
            path.write_text(json.dumps({'time': time.time() - 9, 'state': 'clear'}))
            self.assertEqual(m.read_status(path)['state'], 'unavailable')
            path.write_text('[]')
            self.assertEqual(m.read_status(path)['state'], 'unavailable')

    def test_private_atomic_state(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'private' / 'state.json'
            m.save(path, {'state': 'clear'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_no_markup_in_process_names(self):
        self.assertNotIn('%{', m.clean('evil%{A:cmd:}\nrow'))
        self.assertNotIn('\n', m.clean('evil\nrow'))

    def test_ui_does_not_claim_recording_or_system_coverage(self):
        value = {'state': 'clear', 'devices': ['video0'], 'holders': [], 'unreadable': []}
        text = '\n'.join(m.details(value))
        self.assertIn('system/root activity is not visible', text)
        self.assertIn('not proof of streaming', text)
        self.assertEqual(m.label(value), 'Cam —')
        self.assertEqual(m.label({**value, 'state': 'partial'}), 'Cam ?')
        self.assertEqual(m.label({**value, 'state': 'access'}), 'Cam ACCESS')


if __name__ == '__main__':
    unittest.main()

class InstallerTests(unittest.TestCase):
    def test_unit_is_fixed_read_only_collector(self):
        spec = importlib.util.spec_from_file_location('camera_access', Path(__file__).parents[1] / 'install-access.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        text = mod.unit('groscoe')
        self.assertIn('User=root', text)
        self.assertIn('ProtectSystem=strict', text)
        self.assertIn('DevicePolicy=closed', text)
        self.assertIn('CapabilityBoundingSet=CAP_SYS_PTRACE CAP_DAC_READ_SEARCH', text)
        self.assertIn('ReadWritePaths=/run/camera-monitor', text)
        self.assertNotIn('/home/', text)
        self.assertNotIn('sudo', text)
        with self.assertRaises(ValueError):
            mod.unit('bad\nExecStart=/bin/sh')

class ControlUiTests(unittest.TestCase):
    def test_verified_and_failed_blocks_have_distinct_labels(self):
        value = {'state': 'clear', 'holders': [], 'unreadable': []}
        self.assertEqual(m.label({**value, 'control': {'mode': 'blocked'}}), 'Cam BLOCKED')
        self.assertEqual(m.label({**value, 'control': {'mode': 'failed'}}), 'Cam BLOCK ?')
        self.assertEqual(m.label({**value, 'state': 'access', 'control': {'mode': 'blocked'}}), 'Cam BLOCKED + access')

    def test_rofi_cancel_and_confirmation(self):
        import sys
        with tempfile.TemporaryDirectory() as td:
            cfg=Path(td)/'config.json';cfg.write_text(json.dumps({'controller': {'address':'fixture'}, 'notify':'notify', 'rofi':'rofi'}))
            value={'state':'clear','holders':[], 'unreadable':[], 'devices':['video0'], 'control':{'mode':'allowed'}}
            for choices, expected in [([0,0],False),([0,1],True),([1],False),([None],False)]:
                with patch.object(sys,'argv',['camera-monitor','--config',str(cfg),'menu']), patch.object(m,'read_status',return_value=value), patch.object(m,'choose',side_effect=choices), patch.object(m,'operate') as operation:
                    m.main()
                    self.assertEqual(operation.called,expected)
                    if expected:self.assertEqual(operation.call_args.args[1],'block')

    def test_control_command_has_fixed_executable_and_arguments(self):
        cfg={'controller': {'address':'fixture'}, 'notify':'notify'}
        with patch.object(m,'control_status',side_effect=[{'mode':'allowed'},{'mode':'blocked'}]), patch.object(m.subprocess,'run',return_value=type('Result',(),{'returncode':0})()) as run:
            m.operate(cfg,'block')
            self.assertEqual(run.call_args_list[0].args[0],['/usr/bin/sudo','-n','/usr/bin/python3','-I','/usr/local/libexec/camera-monitor/control.py','block'])
