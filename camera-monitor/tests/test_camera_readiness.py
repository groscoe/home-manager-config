import importlib.util
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('camera_live_selftest',Path(__file__).resolve().parents[1]/'test-controls.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ReadinessTests(unittest.TestCase):
    def test_missing_and_incomplete_first_snapshot_are_retried(self):
        good=json.dumps({'time':time.time(),'coverage':'system','holders':[{'pid':1}]})
        with patch.object(Path,'read_text',side_effect=[FileNotFoundError(),'{',good]),patch.object(m.time,'sleep'):
            self.assertEqual(m.wait_snapshot(Path('/fixture'))['coverage'],'system')

    def test_stale_snapshot_is_not_used(self):
        old=json.dumps({'time':time.time()-20,'coverage':'system'})
        good=json.dumps({'time':time.time(),'coverage':'system'})
        with patch.object(Path,'read_text',side_effect=[old,good]),patch.object(m.time,'sleep'):
            self.assertEqual(m.wait_snapshot(Path('/fixture'))['coverage'],'system')

    def test_ready_predicate_waits_for_relay_handles(self):
        empty=json.dumps({'time':time.time(),'coverage':'system','holders':[]})
        ready=json.dumps({'time':time.time(),'coverage':'system','holders':[{'pid':1}]})
        with patch.object(Path,'read_text',side_effect=[empty,ready]),patch.object(m.time,'sleep'):
            self.assertTrue(m.wait_snapshot(Path('/fixture'),ready=lambda x:bool(x['holders']))['holders'])

    def test_missing_collector_times_out_with_useful_error(self):
        with patch.object(Path,'read_text',side_effect=FileNotFoundError()),patch.object(m.time,'sleep'),patch.object(m.time,'monotonic',side_effect=[0,0,20]):
            with self.assertRaisesRegex(RuntimeError,'fresh, ready system snapshot'):
                m.wait_snapshot(Path('/fixture'),timeout=12)
