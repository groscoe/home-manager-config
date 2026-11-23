import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('bounded_scan',Path(__file__).parents[1]/'scan.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ScanTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  self.state=self.root/'state';self.state.mkdir();self.files=self.root/'files';self.files.mkdir()
  self.db=m.connect(self.state);self.addCleanup(self.db.close)
  self.cfg={'roots':[str(self.files)],'inventory_seconds':120,'recheck_days':7,'clamscan':'/usr/bin/clamscan','retain_reports':14,
   'daily':{'max_file_mib':256,'max_scan_mib':512,'file_seconds':120,'container_files':10000,'max_files':2,'input_mib':4,'job_seconds':2700,'batch_size':128},
   'rescan':{'max_file_mib':512,'max_scan_mib':1024,'file_seconds':600,'container_files':20000,'max_files':4,'max_attempts':2,'retry_hours':6,'job_seconds':2700}}
 def file(self,name='doc.pdf',data='hello'):
  p=self.files/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_text(data);return p
 def row(self,p):
  fp,size=m.fingerprint(p);return {'path':str(p),'fp':fp,'size':size,'attempts':0}
 def test_symlinks_submounts_and_dependencies_excluded_but_source_kept(self):
  p=self.file('project/main.py');self.file('project/node_modules/pkg.js');self.file('project/.git/objects/a');self.file('project/.git/config');self.file('.cache/a')
  (self.files/'link').symlink_to(p)
  out=m.inventory(self.db,self.cfg,'r')
  names={Path(r[0]).relative_to(self.files).as_posix() for r in self.db.execute('SELECT path FROM files')}
  self.assertEqual(names,{'project/main.py','project/.git/config'})
  self.assertGreater(out['policy_omissions']['cache_or_generated_directory'],0)
 def test_unchanged_clean_skipped_until_periodic_recheck(self):
  p=self.file();m.inventory(self.db,self.cfg,'r')
  m.apply_outcomes(self.db,[self.row(p)],{str(p):('clean','OK')},'daily',self.cfg,time.time())
  self.assertEqual(m.select_daily(self.db,self.cfg,'r',time.time())[1],0)
  self.assertEqual(m.select_daily(self.db,self.cfg,'r',time.time()+8*86400)[1],1)
 def test_file_change_invalidates_prior_clean_result(self):
  p=self.file();m.inventory(self.db,self.cfg,'r');m.apply_outcomes(self.db,[self.row(p)],{str(p):('clean','OK')},'daily',self.cfg,time.time())
  p.write_text('changed');m.inventory(self.db,self.cfg,'s');self.assertEqual(m.select_daily(self.db,self.cfg,'s',time.time())[1],1)
 def test_batch_selection_bounded_and_reports_backlog(self):
  for n in range(5):self.file(str(n)+'.txt')
  m.inventory(self.db,self.cfg,'r');rows,total=m.select_daily(self.db,self.cfg,'r',time.time())
  self.assertEqual(len(rows),2);self.assertEqual(total,5)
 def test_known_failed_documents_go_to_queue_not_daily_duplicate(self):
  p=self.file();fp,_=m.fingerprint(p);m.queue_file(self.db,p,fp,'timeout');m.inventory(self.db,self.cfg,'r')
  self.assertEqual(m.select_daily(self.db,self.cfg,'r',time.time())[1],0)
 def test_legacy_report_only_queues_valid_documents_inside_scope(self):
  p=self.file();outside=self.root/'outside.pdf';outside.write_text('x');zipfile=self.file('x.zip')
  report=self.state/'scan-20261110-020651.log';report.write_text(''.join(str(x)+': Heuristics.Limits.Exceeded.MaxScanTime FOUND\n' for x in [p,outside,zipfile]))
  (self.state/'last-scan.json').write_text(json.dumps({'report':str(report)}))
  self.assertEqual(m.seed_report(self.db,self.state,[self.files]),1)
  self.assertEqual(m.seed_report(self.db,self.state,[self.files]),0)
 def test_parse_distinguishes_threats_limits_clean_and_unknown(self):
  paths=['/files/a.pdf','/files/b.pdf','/files/c.txt']
  text='/files/a.pdf: Heuristics.Limits.Exceeded.MaxFiles FOUND\n/files/b.pdf: Example-Signature FOUND\n/files/c.txt: OK\n/mystery: Unknown FOUND\n'
  out,unknown=m.parse_lines(text,paths)
  self.assertEqual([out[p][0] for p in paths],['limits','detected','clean']);self.assertEqual(len(unknown),1)
 def test_later_ok_cannot_clear_threat(self):
  out,_=m.parse_lines('/files/a: Evil FOUND\n/files/a: OK\n',['/files/a']);self.assertEqual(out['/files/a'][0],'detected')
 def test_modified_during_scan_is_not_marked_clean(self):
  p=self.file();m.inventory(self.db,self.cfg,'r');row=self.row(p);p.write_text('new content')
  out=m.apply_outcomes(self.db,[row],{str(p):('clean','OK')},'daily',self.cfg,time.time())
  self.assertEqual(out['changed'],1)
 def test_missing_output_is_error_not_clean(self):
  p=self.file();m.inventory(self.db,self.cfg,'r')
  self.assertEqual(m.apply_outcomes(self.db,[self.row(p)],{},'daily',self.cfg,time.time())['error'],1)
 def test_retry_limit_does_not_reset_on_same_unchanged_file(self):
  p=self.file();row=self.row(p);m.queue_file(self.db,p,row['fp'],'timeout')
  m.apply_outcomes(self.db,[row],{str(p):('limits','time')},'rescan',self.cfg,time.time())
  row['attempts']=1;m.apply_outcomes(self.db,[row],{str(p):('limits','time')},'rescan',self.cfg,time.time())
  m.queue_file(self.db,p,row['fp'],'timeout')
  q=self.db.execute('SELECT * FROM queue').fetchone();self.assertEqual(q['state'],'needs_review');self.assertEqual(q['attempts'],2)
 def test_successful_target_updates_inventory_and_resolves_queue(self):
  p=self.file();row=self.row(p);m.queue_file(self.db,p,row['fp'],'timeout')
  m.apply_outcomes(self.db,[row],{str(p):('clean','OK')},'rescan',self.cfg,time.time())
  self.assertEqual(self.db.execute('SELECT state FROM queue').fetchone()[0],'resolved')
  self.assertEqual(self.db.execute('SELECT state FROM files').fetchone()[0],'clean')
 def test_changed_target_gets_new_bounded_attempt_cycle(self):
  p=self.file();fp,_=m.fingerprint(p);m.queue_file(self.db,p,fp,'time');self.db.execute("UPDATE queue SET state='needs_review',attempts=2");p.write_text('new')
  rows,_=m.select_targets(self.db,self.cfg,[self.files],time.time());self.assertEqual(rows[0]['attempts'],0)
 def test_symlink_target_is_never_scanned(self):
  p=self.file();row=self.row(p);m.queue_file(self.db,p,row['fp'],'time');p.unlink();p.symlink_to('/etc/hostname')
  rows,blocked=m.select_targets(self.db,self.cfg,[self.files],time.time());self.assertEqual(rows,[]);self.assertEqual(blocked['unavailable'],1)
 def test_control_character_path_refused(self):
  p=self.file('bad\nname.pdf')
  with self.assertRaises(ValueError):m.valid(p,[self.files])
 def test_rescan_caps_and_no_destructive_flags(self):
  cmd=m.command(self.cfg,'rescan',Path('/private/list'),Path('/private/extract'))
  self.assertIn('--max-filesize=512M',cmd);self.assertIn('--max-scansize=1024M',cmd);self.assertIn('--max-scantime=600000',cmd)
  self.assertIn('--max-files=20000',cmd);self.assertIn('--max-recursion=17',cmd)
  self.assertFalse(any(x.startswith(('--remove','--move','--copy')) for x in cmd))
 def test_private_atomic_reports(self):
  p=self.state/'report.json';m.save(p,{'a':1});self.assertEqual(p.stat().st_mode&0o777,0o600)
 def test_battery_defers_before_inventory_or_content_scan(self):
  with patch.object(m,'on_ac',return_value=False),patch.object(m,'inventory') as inv,patch.object(m,'run_batch') as batch:
   result=m.execute(self.cfg,'daily',self.state,self.db);self.assertEqual(result['reason'],'battery');inv.assert_not_called();batch.assert_not_called()
 def test_stopped_job_resumes_after_ac_instead_of_daily_gate(self):
  (self.state/'daily-last.json').write_text(json.dumps({'status':'battery','finished_epoch':time.time()}))
  with patch.object(m,'on_ac',return_value=True),patch.object(m.shutil,'disk_usage',return_value=type('Disk',(),{'free':10*2**30})()),patch.object(m,'notify'),patch.object(m,'inventory',return_value={}),patch.object(m,'select_daily',return_value=([],0)):
   self.assertNotEqual(m.execute(self.cfg,'daily',self.state,self.db).get('reason'),'daily gate')

class BatchTerminationTests(unittest.TestCase):
 def test_battery_stops_child_and_preserves_no_result_as_unscanned(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);p=root/'file.pdf';p.write_text('test')
   cfg={'clamscan':'clamscan','daily':{'max_file_mib':256,'max_scan_mib':512,'file_seconds':120,'container_files':10000}}
   child=type('Child',(),{'returncode':-15,'poll':lambda self:None,'terminate':lambda self:setattr(self,'stopped',True),'wait':lambda self,timeout:None})()
   with patch.object(m.subprocess,'Popen',return_value=child),patch.object(m,'on_ac',return_value=False):
    outcomes,reason,code,unknown=m.run_batch(cfg,'daily',[{'path':str(p)}],root,time.monotonic()+60,[False],root/'report.log')
   self.assertEqual(reason,'battery');self.assertTrue(child.stopped);self.assertEqual(outcomes,{})
 def test_global_job_budget_stops_child(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);cfg={'clamscan':'clamscan','daily':{'max_file_mib':256,'max_scan_mib':512,'file_seconds':120,'container_files':10000}}
   child=type('Child',(),{'returncode':-15,'poll':lambda self:None,'terminate':lambda self:setattr(self,'stopped',True),'wait':lambda self,timeout:None})()
   with patch.object(m.subprocess,'Popen',return_value=child),patch.object(m,'on_ac',return_value=True):
    out,reason,code,unknown=m.run_batch(cfg,'daily',[],root,0,[False],root/'report.log')
   self.assertEqual(reason,'job_budget');self.assertTrue(child.stopped)

if __name__=='__main__':unittest.main()
