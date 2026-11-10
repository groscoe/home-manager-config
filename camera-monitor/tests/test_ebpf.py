import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
m=load('event_ui',ROOT/'monitor.py')
c=load('event_collector',ROOT/'collector.py')
i=load('event_installer',ROOT/'install-access.py')

class EventTests(unittest.TestCase):
    def record(self,seq=1):
        return {'seq':seq,'pid':23,'name':'short-lived','devices':['video1'],'known':True,'action':'opened'}
    def test_brief_event_survives_clear_current_snapshot(self):
        e=self.record()
        v={'trace':{'stream':'a'},'state':'clear','holders':[],'events':[e]}
        batch,cursor,gap=m.journal_batch(v,{},[])
        self.assertEqual(batch[0]['pid'],23)
        self.assertEqual(cursor,{'stream':'a','seq':1})
        self.assertFalse(gap)
    def test_duplicate_after_restart_not_notified_twice(self):
        v={'trace':{'stream':'a'},'events':[self.record()]}
        prior=[{**self.record(),'event_id':'a:1'}]
        self.assertEqual(m.journal_batch(v,{},prior)[0],[])
    def test_released_inherited_handle_keeps_original_opener(self):
        e={**self.record(),'action':'released'}
        self.assertEqual(m.journal_batch({'trace':{'stream':'a'},'events':[e]}, {},[])[0][0]['name'],'short-lived')
    def test_unknown_startup_release_has_no_invented_opener(self):
        v={'trace':{'stream':'a'},'events':[{**self.record(),'known':False}]}
        batch,cursor,gap=m.journal_batch(v,{},[])
        self.assertEqual(batch,[])
        self.assertEqual(cursor['seq'],1)
    def test_root_buffer_overrun_is_visible(self):
        v={'trace':{'stream':'a'},'events':[self.record(20)]}
        self.assertTrue(m.journal_batch(v,{'stream':'a','seq':1},[])[2])
    def test_stream_restart_exposes_monitoring_gap(self):
        v={'trace':{'stream':'new'},'events':[]}
        self.assertTrue(m.journal_batch(v,{'stream':'old','seq':3},[])[2])
    def test_kernel_loss_never_claims_clear(self):
        v=c.snapshot_trace({'state':'clear'},'s',[],1)
        self.assertEqual(v['state'],'partial')
        self.assertEqual(m.label({**v,'unreadable':[],'holders':[]}), 'Cam ?')
    def test_dead_engine_never_claims_clear(self):
        v=c.snapshot_trace({'state':'clear'},'s',[],0,False,'engine failed')
        self.assertEqual(v['state'],'unavailable')
    def test_access_still_visible_when_events_lost(self):
        v=c.snapshot_trace({'state':'access'},'s',[],2)
        self.assertEqual(m.label({**v,'unreadable':[]}), 'Cam ACCESS ?')
    def test_live_event_captures_metadata_without_exited_proc(self):
        raw={'pid':99999999,'uid':1000,'start_ns':10,'major':81,'minor':1,'time_ns':int(time.clock_gettime(time.CLOCK_BOOTTIME)*1e9) if hasattr(time,'CLOCK_BOOTTIME') else 1,'action':1,'known':1,'name':'bad%{A:cmd:}\n'}
        # CLOCK_BOOTTIME is Linux-only; keep metadata conversion test portable.
        with patch.object(c.time,'clock_gettime',return_value=1),patch.object(c.time,'CLOCK_BOOTTIME',1,create=True):
            e=c.event_record(raw,{(81,1):'video1'},1)
        self.assertIn('unavailable',e['executable'])
        self.assertNotIn('%{',e['name'])
        self.assertNotIn('commandline',e)
    def test_fixed_unit_caps_and_no_camera_open_permission(self):
        text=i.unit('groscoe')
        self.assertIn('CAP_BPF CAP_PERFMON',text)
        self.assertNotIn('CAP_SYS_ADMIN',text)
        self.assertIn('DevicePolicy=closed',text)
        self.assertIn('RestrictAddressFamilies=AF_UNIX AF_NETLINK',text)
        self.assertIn('/collector.py --engine /nix/store/',text)
        with self.assertRaises(ValueError):i.unit('groscoe','/tmp/untrusted-engine')
    def test_detail_view_contains_brief_events_and_warning(self):
        v={'state':'clear','devices':['video1'],'holders':[],'unreadable':[], 'trace':{'backend':'ebpf','ready':True,'lost':1},'events':[{**self.record(),'time':'now'}]}
        text='\n'.join(m.details(v))
        self.assertIn('short-lived',text)
        self.assertIn('history is incomplete',text)
        self.assertIn('60-second reconciliation',text)

if __name__=='__main__':unittest.main()
