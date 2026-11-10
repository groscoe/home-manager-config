import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('camera_control',ROOT/'control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
spec=importlib.util.spec_from_file_location('camera_control_installer',ROOT/'install-controls.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
CFG={'address':'0000:00:05.0','driver':'intel-ipu6','vendor':'0x8086','device':'0x465d','virtualCameraName':'Intel MIPI Camera'}


class FakePermissions:
    def __init__(self): self.denied=False
    def snapshot(self): return [{'node':'video0','acl':'fixture'}]
    def restrict(self,saved,boot=False): self.denied=True
    def restore(self,saved): self.denied=False


class ControlsTests(unittest.TestCase):
    def fixture(self,td,fail=None):
        root=Path(td);state=root/'state';state.mkdir()
        device=root/'sys/bus/pci/devices'/CFG['address'];device.mkdir(parents=True)
        driver=root/'sys/bus/pci/drivers'/CFG['driver'];driver.mkdir(parents=True)
        for k in ['vendor','device']:(device/k).write_text(CFG[k])
        (device/'driver_override').write_text('(null)')
        (device/'driver').symlink_to(driver)
        calls=[]
        def write(path,value):
            calls.append((path.name,value))
            if path.name==fail:raise OSError('fixture failure')
            if path.name=='unbind':(device/'driver').unlink()
            elif path.name=='bind':(device/'driver').symlink_to(driver)
            else:path.write_text(value)
        c=m.Controller(CFG,state,root/'sys',run=lambda *a:calls.append(a),write=write,permissions=FakePermissions())
        return c,calls

    def test_fixed_identity_and_argument_validation(self):
        for key,value in [('address','../../wrong'),('driver','intel-ipu6; sh'),('vendor','8086'),('device','*')]:
            with self.assertRaises(ValueError):m.validate({**CFG,key:value})
        with self.assertRaises(ValueError):m.validate({**CFG,'extra':'evil'})

    def test_wrong_hardware_refused_before_changes(self):
        with tempfile.TemporaryDirectory() as td:
            c,calls=self.fixture(td);(c.device/'vendor').write_text('0x0000')
            with self.assertRaises(RuntimeError):c.block()
            self.assertEqual(calls,[]);self.assertFalse(c.marker.exists())

    def test_complete_cycle_and_idempotence(self):
        with tempfile.TemporaryDirectory() as td,patch.object(m,'trusted_json',lambda p:json.loads(p.read_text())),patch.object(m.subprocess,'run',return_value=Mock(returncode=0)):
            c,calls=self.fixture(td);c.block();self.assertIsNone(c.inspect())
            c.block();c.block(boot=True);self.assertIsNone(c.inspect())
            c.unblock();self.assertEqual(c.inspect(),CFG['driver']);self.assertFalse(c.marker.exists())
            self.assertEqual((c.device/'driver_override').read_text(),'\n')
            self.assertEqual(sum(1 for call in calls if call[0]=='unbind'),1)
            c.unblock();self.assertEqual(c.inspect(),CFG['driver'])

    def test_unbind_failure_leaves_requested_block_not_false_success(self):
        with tempfile.TemporaryDirectory() as td,patch.object(m.subprocess,'run',return_value=Mock(returncode=0)):
            c,calls=self.fixture(td,fail='unbind')
            with self.assertRaises(OSError):c.block()
            self.assertTrue(c.marker.exists());self.assertEqual(c.inspect(),CFG['driver'])

    def test_existing_override_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            c,calls=self.fixture(td);(c.device/'driver_override').write_text('vfio-pci')
            with self.assertRaises(RuntimeError):c.block()
            self.assertFalse(c.marker.exists());self.assertEqual(calls,[])

    def test_unblock_failure_returns_to_blocked(self):
        with tempfile.TemporaryDirectory() as td,patch.object(m,'trusted_json',lambda p:json.loads(p.read_text())),patch.object(m.subprocess,'run',return_value=Mock(returncode=0)):
            c,calls=self.fixture(td,fail='bind');c.block()
            with self.assertRaises(OSError):c.unblock()
            self.assertIsNone(c.inspect());self.assertTrue(c.marker.exists())
            self.assertEqual((c.device/'driver_override').read_text().strip(),m.OVERRIDE)

    def test_boot_without_block_marker_does_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            c,calls=self.fixture(td);c.block(boot=True);self.assertEqual(calls,[])

    def test_boot_marker_missing_device_is_safe(self):
        with tempfile.TemporaryDirectory() as td,patch.object(m,'trusted_json',lambda p:json.loads(p.read_text())):
            c,calls=self.fixture(td);m.save_marker(c.marker,{'controller':CFG,'original_override':'','relay_active':True,'virtual':[]})
            import shutil
            shutil.rmtree(c.device)
            c.block(boot=True);self.assertTrue(c.marker.exists());self.assertEqual(calls,[])

    def test_policy_grants_only_two_literal_commands(self):
        text=installer.policy('groscoe')
        self.assertNotIn('*',text);self.assertNotIn('enforce',text)
        self.assertEqual(text.count('/usr/bin/python3 -I /usr/local/libexec/camera-monitor/control.py '),2)
        with self.assertRaises(ValueError):installer.policy('bad\nroot ALL=ALL')

    def test_boot_rules_are_hardware_specific_and_relay_guarded(self):
        rule=installer.rule(CFG)
        for value in CFG.values():
            if value!=CFG['driver']:self.assertIn(value,rule)
        self.assertIn('TEST=="/var/lib/camera-monitor-control/blocked.json"',rule)
        self.assertIn('Before=v4l2-relayd.service',installer.unit())
        self.assertIn('TAG-="uaccess"',rule)
        self.assertIn('MODE="0000"',rule)
        self.assertIn('/devices/virtual/video4linux/*',rule)


if __name__=='__main__':unittest.main()
