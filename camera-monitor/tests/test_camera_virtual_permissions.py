import importlib.util
from pathlib import Path
import os
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('camera_virtual_backend',Path(__file__).resolve().parents[1]/'control.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class VirtualPermissionsTests(unittest.TestCase):
    def test_virtual_camera_acl_and_mode_are_restored(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);node=root/'sys/devices/virtual/video4linux/video0';node.mkdir(parents=True)
            (node/'name').write_text('Intel MIPI Camera');(node/'dev').write_text('81:0')
            dev=root/'dev';dev.mkdir();target=dev/'video0'
            info=SimpleNamespace(st_mode=stat.S_IFCHR|0o660,st_uid=0,st_gid=44,st_rdev=os.makedev(81,0))
            acl='user::rw-\nuser:1000:rw-\ngroup::rw-\nmask::rw-\nother::---\n'
            original=Path.lstat;calls=[]
            def metadata(path,*a,**kw):return info if path==target else original(path,*a,**kw)
            def chmod(path,mode):
                self.assertEqual(path,target);info.st_mode=stat.S_IFCHR|mode
            v=m.VirtualCamera('Intel MIPI Camera',root/'sys',dev,run=lambda *a:calls.append(a))
            with patch.object(Path,'lstat',metadata),patch.object(m.os,'chmod',chmod),patch.object(m.os,'chown') as chown,patch.object(m.subprocess,'check_output',return_value=acl),patch.object(m.subprocess,'run') as setfacl:
                saved=v.snapshot();self.assertEqual(saved[0]['mode'],0o660)
                v.restrict(saved);self.assertTrue(v.blocked())
                v.restore(saved);self.assertFalse(v.blocked());self.assertEqual(info.st_mode&0o777,0o660)
                self.assertEqual(saved[0]['acl'],acl)
                self.assertEqual(setfacl.call_args.kwargs['input'],acl)
                chown.assert_called_once_with(target,0,44)
                self.assertTrue(all('video0' in ' '.join(c) or 'settle' in c for c in calls))

    def test_wrong_device_number_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);node=root/'sys/devices/virtual/video4linux/video0';node.mkdir(parents=True)
            (node/'name').write_text('Intel MIPI Camera');(node/'dev').write_text('81:0')
            dev=root/'dev';target=dev/'video0'
            info=SimpleNamespace(st_mode=stat.S_IFCHR|0o660,st_uid=0,st_gid=44,st_rdev=os.makedev(81,1))
            original=Path.lstat
            def metadata(path,*a,**kw):return info if path==target else original(path,*a,**kw)
            with patch.object(Path,'lstat',metadata),patch.object(m.os,'chmod') as chmod:
                with self.assertRaisesRegex(RuntimeError,'identity'):m.VirtualCamera('Intel MIPI Camera',root/'sys',dev).snapshot()
                chmod.assert_not_called()

    def test_different_virtual_camera_is_not_touched(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);node=root/'sys/devices/virtual/video4linux/video0';node.mkdir(parents=True)
            (node/'name').write_text('Other virtual camera')
            v=m.VirtualCamera('Intel MIPI Camera',root/'sys',root/'dev')
            self.assertEqual(v.nodes(),[])
            with self.assertRaisesRegex(RuntimeError,'absent'):v.snapshot()
