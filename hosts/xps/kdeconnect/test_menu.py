import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('menu', Path(__file__).with_name('menu.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class MenuTests(unittest.TestCase):
    def test_names_and_availability(self):
        with patch.object(m, 'run', side_effect=['id2', 'id1 My phone name\nid2 Laptop\n0 devices found']):
            self.assertEqual(m.devices(), [('id1','My phone name',False),('id2','Laptop',True)])
    def test_cancel_and_invalid_choice(self):
        for code, output in [(1,''),(0,'-1'),(0,'123'),(0,'nonsense')]:
            with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, output, '')):
                self.assertIsNone(m.choose('Devices', ['Phone']))
    def test_clipboard_uses_exact_device_argument(self):
        with patch.object(m, 'choose', return_value=2), patch.object(m,'run') as run, patch.object(m,'notify'):
            m.device_menu(('id;evil','Phone',True))
            run.assert_called_once_with('kdeconnect-cli','--device','id;evil','--send-clipboard')
    def test_offline_device_cannot_ring(self):
        with patch.object(m,'choose',return_value=None) as choose, patch.object(m,'run') as run:
            m.device_menu(('id','Phone',False))
            self.assertNotIn('Ring / find device',choose.call_args.args[1])
            run.assert_not_called()
    def test_missing_file_never_sent(self):
        with patch.object(m,'choose',return_value=3), patch.object(m,'ask',return_value='/nonexistent/kdeconnect-test'), patch.object(m,'run') as run:
            with self.assertRaises(RuntimeError):m.device_menu(('id','Phone',True))
            run.assert_not_called()
    def test_error_surfaced(self):
        with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','Device not reachable')):
            with self.assertRaisesRegex(RuntimeError,'not reachable'):m.run('kdeconnect-cli','--ping')
    def test_no_devices_still_has_settings(self):
        with patch.object(m,'run'), patch.object(m,'devices',return_value=[]), patch.object(m,'choose',return_value=3) as choose:
            m.main()
            self.assertIn('Open KDE Connect settings',choose.call_args.args[1])

spec_session = importlib.util.spec_from_file_location('session', Path(__file__).with_name('session.py'))
session = importlib.util.module_from_spec(spec_session)
spec_session.loader.exec_module(session)

class SessionTests(unittest.TestCase):
    def test_headless_instance_restarts_at_login(self):
        with patch.object(session.subprocess,'run') as run, patch.object(session.subprocess,'check_output',return_value='123\n'), patch.object(session.Path,'read_bytes',return_value=b'QT_QPA_PLATFORM=offscreen\0'):
            session.start('/usr/bin/systemctl')
            self.assertEqual(run.call_count,2)
            self.assertEqual(run.call_args.args[0][-2:],['restart','kdeconnect.service'])
    def test_x11_instance_is_not_interrupted(self):
        with patch.object(session.subprocess,'run') as run, patch.object(session.subprocess,'check_output',return_value='123\n'), patch.object(session.Path,'read_bytes',return_value=b'QT_QPA_PLATFORM=xcb\0'):
            session.start('/usr/bin/systemctl')
            self.assertEqual(run.call_count,1)
    def test_process_exit_race_is_safe(self):
        with patch.object(session.subprocess,'run') as run, patch.object(session.subprocess,'check_output',return_value='123\n'), patch.object(session.Path,'read_bytes',side_effect=FileNotFoundError):
            session.start('/usr/bin/systemctl')
            self.assertEqual(run.call_count,1)
    def test_zero_pid_is_not_read(self):
        with patch.object(session.subprocess,'run') as run, patch.object(session.subprocess,'check_output',return_value='0\n'), patch.object(session.Path,'read_bytes') as read:
            session.start('/usr/bin/systemctl')
            read.assert_not_called()

if __name__ == '__main__':unittest.main()
