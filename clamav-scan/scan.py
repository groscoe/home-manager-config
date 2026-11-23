"""Bounded, incremental ClamAV scans with a private document-rescan queue."""
import argparse
from collections import Counter
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import time
import uuid

DOCS={'.pdf','.epub'}
CACHE_RE=r'(^|/)(\.cache|cache|caches|Cache|Caches|__pycache__|\.npm|\.pnpm-store|\.direnv|node_modules|\.stack-work|dist-newstyle)(/|$)'
EXCLUDES=[CACHE_RE,r'(^|/)\.git/objects(/|$)',r'^/vault/(lost\+found|\.clamav-scan)(/|$)']
SCHEMA='''CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,fp TEXT,size INTEGER,priority INTEGER,seen TEXT,state TEXT,last_checked REAL DEFAULT 0,last_attempt REAL DEFAULT 0);
CREATE INDEX IF NOT EXISTS file_seen ON files(seen,state);
CREATE TABLE IF NOT EXISTS queue(path TEXT PRIMARY KEY,fp TEXT,state TEXT,attempts INTEGER DEFAULT 0,next_try REAL DEFAULT 0,reason TEXT,last_result TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);'''


def save(path,value):
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name)
    try:
        with os.fdopen(fd,'w') as f:json.dump(value,f,ensure_ascii=False,indent=2)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def fingerprint(path):
    s=path.lstat()
    if not stat.S_ISREG(s.st_mode):raise ValueError('not a regular file')
    return json.dumps([s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns],separators=(',',':')),s.st_size


def valid(path,roots):
    if any(c in str(path) for c in '\n\r\0'):raise ValueError('control character in pathname')
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('symlink or noncanonical path')
    root=next((r for r in roots if path.is_relative_to(r)),None)
    if root is None or path.stat().st_dev!=root.stat().st_dev:raise ValueError('outside scope or different filesystem')
    if any(m!=root and m.is_relative_to(root) and path.is_relative_to(m) for m in mountpoints()):raise ValueError('nested mount')
    if any(re.search(p,str(path)) for p in EXCLUDES):raise ValueError('excluded cache/dependency path')
    return fingerprint(path)


def connect(state):
    db=sqlite3.connect(state/'inventory.sqlite');db.row_factory=sqlite3.Row
    db.executescript(SCHEMA);return db


def queue_file(db,path,fp,reason,renew=False):
    old=db.execute('SELECT * FROM queue WHERE path=?',(str(path),)).fetchone()
    if old is None or old['fp']!=fp or renew and old['state']=='resolved':
        db.execute('INSERT OR REPLACE INTO queue VALUES(?,?,?,0,0,?,NULL)',(str(path),fp,'pending',reason))


def mountpoints():
    result=set()
    try:
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            name=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),line.split()[4]);result.add(Path(name))
    except OSError:pass
    return result


def inventory(db,cfg,run):
    start=time.monotonic();deadline=start+cfg['inventory_seconds'];roots=list(map(Path,cfg['roots']))
    omitted=Counter();errors=[];count=0;truncated=False;mounts=mountpoints()
    for root in roots:
        if root.is_symlink() or not root.is_dir():errors.append('Missing/symlinked scan root: '+str(root));continue
        root_device=root.stat().st_dev
        for base,dirs,files in os.walk(root,followlinks=False,onerror=lambda e:errors.append(str(e))):
            if time.monotonic()>deadline:truncated=True;break
            kept=[]
            for name in dirs:
                p=Path(base)/name
                if any(re.search(pattern,str(p)) for pattern in EXCLUDES):omitted['cache_or_generated_directory']+=1;continue
                try:
                    s=p.lstat()
                    if p in mounts or not stat.S_ISDIR(s.st_mode) or s.st_dev!=root_device:omitted['symlink_or_submount']+=1
                    else:kept.append(name)
                except OSError as e:errors.append(str(e))
            dirs[:]=kept
            for name in files:
                p=Path(base)/name
                if time.monotonic()>deadline:truncated=True;break
                try:
                    s=p.lstat()
                    if not stat.S_ISREG(s.st_mode) or s.st_dev!=root_device:omitted['nonregular_or_other_fs']+=1;continue
                    if any(c in str(p) for c in '\n\r\0'):omitted['unsupported_pathname']+=1;continue
                    fp,size=fingerprint(p);priority=-1 if s.st_mtime_ns/1e9>time.time()-86400 else 0 if p.suffix.lower() in DOCS else 1;old=db.execute('SELECT fp FROM files WHERE path=?',(str(p),)).fetchone()
                    if old is None:
                        db.execute('INSERT INTO files VALUES(?,?,?,?,?, ?,0,0)',(str(p),fp,size,priority,run,'pending'))
                    elif old['fp']!=fp:
                        db.execute('UPDATE files SET fp=?,size=?,seen=?,priority=-1,state=?,last_checked=0,last_attempt=0 WHERE path=?',(fp,size,run,'pending',str(p)))
                    else:db.execute('UPDATE files SET seen=?,priority=? WHERE path=?',(run,priority,str(p)))
                    if size>cfg['daily']['max_file_mib']*2**20:
                        db.execute('UPDATE files SET state=? WHERE path=?',('oversized',str(p)))
                        stale=bool(old and db.execute('SELECT last_checked FROM files WHERE path=?',(str(p),)).fetchone()[0]<time.time()-cfg['recheck_days']*86400)
                        if p.suffix.lower() in DOCS:queue_file(db,p,fp,'Daily file-size limit',renew=stale)
                    count+=1
                except (OSError,ValueError) as e:errors.append(str(e))
            if truncated:break
        if truncated:break
    db.commit()
    return {'files_seen':count,'policy_omissions':dict(omitted),'inventory_errors':errors,'inventory_truncated':truncated}


def select_daily(db,cfg,run,now):
    rows=db.execute('''SELECT * FROM files WHERE seen=? AND size<=? AND
        (state='pending' OR (state='clean' AND last_checked<?) OR (state IN ('error','detected') AND last_attempt<?))
        AND NOT EXISTS(SELECT 1 FROM queue q WHERE q.path=files.path AND q.fp=files.fp AND q.state!='resolved')
        ORDER BY last_checked,priority,last_attempt,path''',(run,cfg['daily']['max_file_mib']*2**20,now-cfg['recheck_days']*86400,now-86400))
    selected=[];total=0;eligible=0
    for row in rows:
        eligible+=1
        if len(selected)>=cfg['daily']['max_files'] or total+row['size']>cfg['daily']['input_mib']*2**20:continue
        selected.append(dict(row));total+=row['size']
    return selected,eligible


def seed_report(db,state,roots):
    key='legacy_report_imported'
    if db.execute('SELECT 1 FROM meta WHERE key=?',(key,)).fetchone():return 0
    try:
        item=json.loads((state/'last-scan.json').read_text());report=Path(item['report'])
        if report.parent!=state or report.is_symlink() or not re.fullmatch(r'scan-\d{8}-\d{6}\.log',report.name):return 0
        text=report.read_text(errors='replace')
    except (OSError,ValueError,KeyError):return 0
    added=0
    for line in text.splitlines():
        m=re.match(r'^(.*): (Heuristics\.Limits\.Exceeded[^ ]*) FOUND$',line)
        if not m:continue
        p=Path(m[1])
        if p.suffix.lower() not in DOCS:continue
        try:fp,_=valid(p,roots)
        except (OSError,ValueError):continue
        queue_file(db,p,fp,m[2]);added+=1
    db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,str(item['report'])));db.commit();return added


def select_targets(db,cfg,roots,now):
    selected=[];blocked=Counter()
    rows=db.execute('SELECT * FROM queue ORDER BY next_try,path').fetchall()
    # Prefer smaller documents so bounded batches make progress before large ones.
    def order(row):
        try:size=Path(row['path']).lstat().st_size
        except OSError:size=0
        return row['next_try'],size,row['path']
    rows.sort(key=order)
    for row in rows:
        path=Path(row['path'])
        try:fp,size=valid(path,roots)
        except (OSError,ValueError) as e:
            db.execute('UPDATE queue SET state=?,last_result=? WHERE path=?',('unavailable',str(e),str(path)));blocked['unavailable']+=1;continue
        if fp!=row['fp']:
            queue_file(db,path,fp,'File changed since previous attempt');row=db.execute('SELECT * FROM queue WHERE path=?',(str(path),)).fetchone()
        if size>cfg['rescan']['max_file_mib']*2**20:
            db.execute('UPDATE queue SET state=?,last_result=? WHERE path=?',('blocked_size','Larger than bounded rescan size limit',str(path)));blocked['size']+=1;continue
        if row['state'] in ('resolved','needs_review','blocked_size','unavailable'):continue
        if row['attempts']>=cfg['rescan']['max_attempts']:
            db.execute('UPDATE queue SET state=? WHERE path=?',('needs_review',str(path)));continue
        if row['next_try']>now or len(selected)>=cfg['rescan']['max_files']:continue
        selected.append({'path':str(path),'fp':fp,'size':size,'attempts':row['attempts']})
    db.commit();return selected,dict(blocked)


def command(cfg,mode,listing,temp):
    p=cfg[mode]
    return [cfg['clamscan'],'--stdout','--no-summary','--cross-fs=no','--follow-dir-symlinks=0','--follow-file-symlinks=0',
            '--max-filesize='+str(p['max_file_mib'])+'M','--max-scansize='+str(p['max_scan_mib'])+'M',
            '--max-scantime='+str(p['file_seconds']*1000),'--max-files='+str(p['container_files']),
            '--max-recursion=17','--alert-exceeds-max=yes','--fail-if-cvd-older-than=3',
            '--tempdir='+str(temp),'--file-list='+str(listing)]


def parse_lines(text,paths):
    outcomes={};unknown=[];paths=sorted(paths,key=len,reverse=True)
    for line in text.splitlines():
        if not (line.endswith(' OK') or line.endswith(' FOUND') or line.endswith(' ERROR')):continue
        path=next((p for p in paths if line.startswith(p+': ')),None)
        if path is None:unknown.append(line);continue
        value=line[len(path)+2:]
        state='clean' if value=='OK' else 'limits' if value.startswith('Heuristics.Limits.Exceeded') and value.endswith(' FOUND') else 'detected' if value.endswith(' FOUND') else 'error'
        # A later OK line can never erase a limit, error or detection.
        rank={'clean':0,'limits':1,'error':2,'detected':3}
        if path not in outcomes or rank[state]>=rank[outcomes[path][0]]:outcomes[path]=(state,value)
    return outcomes,unknown


def on_ac():
    battery=False
    for p in Path('/sys/class/power_supply').iterdir():
        try:
            kind=(p/'type').read_text().strip();battery|=kind=='Battery'
            if kind!='Battery' and (p/'online').read_text().strip()=='1':return True
        except OSError:pass
    return not battery


def run_batch(cfg,mode,rows,state,deadline,stop,report):
    with tempfile.TemporaryDirectory(prefix='extract-',dir=state) as td:
        temp=Path(td);listing=temp/'files.txt';listing.write_text(''.join(r['path']+'\n' for r in rows))
        log=temp/'output.log'
        with log.open('w') as stream:
            child=subprocess.Popen(command(cfg,mode,listing,temp),stdout=stream,stderr=subprocess.STDOUT)
            reason=None
            while child.poll() is None:
                if stop[0] or not on_ac() or time.monotonic()>=deadline:
                    reason='interrupted' if stop[0] else 'battery' if not on_ac() else 'job_budget'
                    child.terminate()
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
                    break
                time.sleep(.5)
        text=log.read_text(errors='replace')
        with report.open('a') as out:out.write(text)
        outcomes,unknown=parse_lines(text,[r['path'] for r in rows])
        if unknown or child.returncode not in (0,1) and reason is None:
            # Database/init errors cannot be turned into a successful clean batch.
            outcomes={p:(s,v) for p,(s,v) in outcomes.items() if s!='clean'}
        return outcomes,reason,child.returncode,len(unknown)


def apply_outcomes(db,rows,outcomes,mode,cfg,now):
    counts=Counter()
    for row in rows:
        path=row['path'];state,detail=outcomes.get(path,('error','No complete result for this file'))
        try:fp,_=fingerprint(Path(path))
        except (OSError,ValueError):fp=None
        if fp!=row['fp']:state,detail='changed','File changed or disappeared during scanning'
        counts[state]+=1
        if mode=='rescan':
            db.execute('INSERT OR IGNORE INTO files VALUES(?,?,?,?,?,?,0,0)',(path,row['fp'],row['size'],0,'targeted','pending'))
        db.execute('UPDATE files SET state=?,last_attempt=?,last_checked=CASE WHEN ?=? THEN ? ELSE last_checked END WHERE path=? AND fp=?',
                   (state,now,state,'clean',now,path,row['fp']))
        if mode=='daily' and state=='limits' and Path(path).suffix.lower() in DOCS:queue_file(db,Path(path),row['fp'],detail,renew=True)
        if mode=='rescan':
            attempts=row.get('attempts',0)+1
            qstate='resolved' if state=='clean' else 'needs_review' if attempts>=cfg['rescan']['max_attempts'] else 'pending'
            if state=='detected':qstate='needs_review'
            db.execute('UPDATE queue SET state=?,attempts=?,next_try=?,last_result=? WHERE path=? AND fp=?',
                       (qstate,attempts,now+cfg['rescan']['retry_hours']*3600,detail,path,row['fp']))
    db.commit();return counts


def queue_counts(db):return dict(db.execute('SELECT state,count(*) FROM queue GROUP BY state').fetchall())


def notify(cfg,state,result):
    counts=result.get('results',{});threats=counts.get('detected',0)
    message=(f'Possible threats: {threats}. ' if threats else 'No new malware detections. ')
    if result.get('status')=='deferred':return
    if counts.get('limits'):message+=f"{counts['limits']} files hit processing limits; not fully scanned. "
    if result.get('eligible_remaining'):message+=f"{result['eligible_remaining']} eligible files remain for later runs. "
    if result.get('known_unresolved',{}).get('limits'):message+=f"{result['known_unresolved']['limits']} files still have unresolved processing limits. "
    if result.get('oversized_files'):message+=f"{result['oversized_files']} files exceed daily size policy (not malware detections). "
    q=result.get('queue',{});unresolved=sum(v for k,v in q.items() if k!='resolved')
    if unresolved:message+=f'{unresolved} document rescans pending/unresolved. '
    if result.get('known_unresolved',{}).get('detected'):message+='Previously detected files still need review. '
    if result.get('status') not in ('completed','gaps'):message+='Scan stopped or encountered errors; coverage incomplete. '
    message+='No source files changed. Report: '+result['report']
    item={'message':message,'urgency':'critical' if threats else 'normal'}
    save(state/'pending-notification.json',item)
    notify_pending(cfg,state)


def notify_pending(cfg,state):
    p=state/'pending-notification.json'
    if not p.exists():return
    if subprocess.run(['/usr/bin/systemctl','--user','is-active','--quiet','dunst.service']).returncode:return
    item=json.loads(p.read_text())
    try:
        r=subprocess.run([cfg['notify'],'--app-name=ClamAV','--urgency='+item['urgency'],'Antivirus coverage',item['message']],timeout=5)
        if r.returncode==0:p.unlink()
    except (OSError,subprocess.SubprocessError):pass


def execute(cfg,mode,state,db,force=False,plan=False):
    roots=list(map(Path,cfg['roots']));now=time.time();run=uuid.uuid4().hex
    seeded=seed_report(db,state,roots)
    previous=state/('daily-last.json' if mode=='daily' else 'rescan-last.json')
    if not plan:
        if not on_ac():return {'status':'deferred','reason':'battery'}
        if shutil.disk_usage(state).free<(2*cfg[mode]['max_scan_mib']+512)*2**20:return {'status':'deferred','reason':'insufficient encrypted extraction space'}
        if mode=='daily' and not force and not previous.exists():
            try:legacy=json.loads((state/'last-scan.json').read_text())
            except (OSError,ValueError):legacy={}
            if now-legacy.get('finished_epoch',0)<86400:return {'status':'deferred','reason':'existing daily cadence retained during migration'}
        if mode=='daily' and not force and previous.exists():
            old=json.loads(previous.read_text())
            interval=86400 if old.get('status') in ('completed','gaps','detections','job_budget') else 6*3600 if old.get('status')=='engine_error' else 0
            if now-old.get('finished_epoch',0)<interval:return {'status':'deferred','reason':'daily gate'}
    inventory_result={};blocked={}
    if mode=='daily':
        inventory_result=inventory(db,cfg,run);rows,eligible=select_daily(db,cfg,run,now)
    else:rows,blocked=select_targets(db,cfg,roots,now);eligible=len(rows)
    if plan:return {'mode':mode,'selected_files':len(rows),'selected_mib':round(sum(r['size'] for r in rows)/2**20,2),'eligible':eligible,'queue':queue_counts(db),'newly_queued_from_legacy_report':seeded,'blocked':blocked,**inventory_result}
    started=time.time();deadline=time.monotonic()+cfg[mode]['job_seconds'];stop=[False]
    def stopping(signum,frame):stop[0]=True
    signal.signal(signal.SIGTERM,stopping);signal.signal(signal.SIGINT,stopping)
    report=state/(mode+'-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
    report.write_text('Bounded '+mode+' scan. File results follow; omitted/deferred files are not declared clean.\n')
    save(state/(mode+'-attempt.json'),{'status':'running','started_epoch':started,'report':str(report),'pid':os.getpid()})
    counts=Counter();processed=0;reason=None;unknown=0
    batch_size=cfg[mode].get('batch_size',1)
    for start in range(0,len(rows),batch_size):
        if stop[0] or not on_ac() or time.monotonic()>=deadline:reason='interrupted' if stop[0] else 'battery' if not on_ac() else 'job_budget';break
        batch=[]
        for row in rows[start:start+batch_size]:
            try:fp,_=valid(Path(row['path']),roots)
            except (OSError,ValueError):counts['unavailable']+=1;continue
            if fp!=row['fp']:counts['changed']+=1;continue
            batch.append(row)
        if not batch:continue
        outcomes,reason,code,unparsed=run_batch(cfg,mode,batch,state,deadline,stop,report)
        if mode=='rescan' and code not in (0,1) and not outcomes and reason is None:
            for row in batch:db.execute('UPDATE queue SET next_try=?,last_result=? WHERE path=?',(time.time()+cfg['rescan']['retry_hours']*3600,'Engine/database failure; attempt not consumed',row['path']))
            db.commit();counts['error']+=len(batch)
        else:counts.update(apply_outcomes(db,batch,outcomes,mode,cfg,time.time()))
        processed+=len(batch);unknown+=unparsed
        if code not in (0,1) and not reason:reason='engine_error'
        save(state/(mode+'-attempt.json'),{'status':'running','started_epoch':started,'progress_epoch':time.time(),'attempted_files':processed,'results':dict(counts),'queue':queue_counts(db),'report':str(report),'pid':os.getpid()})
        if reason:break
    oversized=db.execute('SELECT count(*) FROM files WHERE seen=? AND state=?',(run,'oversized')).fetchone()[0] if mode=='daily' else 0
    known_unresolved=dict(db.execute("SELECT state,count(*) FROM files WHERE seen=? AND state!='clean' GROUP BY state",(run,)).fetchall()) if mode=='daily' else {}
    unresolved_queue=any(k!='resolved' and v for k,v in queue_counts(db).items())
    gaps=bool(unresolved_queue or known_unresolved or eligible>processed or oversized or counts.get('limits') or counts.get('error') or counts.get('changed') or counts.get('unavailable') or inventory_result.get('inventory_truncated') or inventory_result.get('inventory_errors'))
    result={'mode':mode,'started_epoch':started,'finished_epoch':time.time(),'elapsed_seconds':round(time.time()-started),'status':reason or ('detections' if counts.get('detected') else 'gaps' if gaps else 'completed'),
            'results':dict(counts),'attempted_files':processed,'eligible_remaining':max(0,eligible-processed),'oversized_files':oversized,'queue':queue_counts(db),'report':str(report),'policy':cfg[mode],'unknown_result_lines':unknown,'known_unresolved':known_unresolved,**inventory_result}
    save(previous,result);save(state/(mode+'-attempt.json'),result)
    if mode=='daily' or processed or reason or blocked:notify(cfg,state,result)
    # Keep reports only; never delete, move or quarantine scanned sources.
    for prefix in ('daily','rescan'):
        for p in sorted(state.glob(prefix+'-????????-??????.log'),reverse=True)[cfg['retain_reports']:]:p.unlink()
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True,type=Path)
    modes=p.add_mutually_exclusive_group();modes.add_argument('--now',action='store_true');modes.add_argument('--status',action='store_true');modes.add_argument('--plan',action='store_true');modes.add_argument('--rescan',action='store_true');modes.add_argument('--rescan-plan',action='store_true')
    a=p.parse_args();cfg=json.loads(a.config.read_text());state=Path(cfg['state_directory']);os.umask(0o077)
    if not Path('/vault').is_mount():print('Deferred: encrypted /vault is not mounted.');return
    state.mkdir(mode=0o700,exist_ok=True)
    s=state.lstat()
    if not stat.S_ISDIR(s.st_mode) or state.is_symlink() or s.st_uid!=os.getuid() or s.st_mode&0o077:raise SystemExit('Unsafe private scanner state directory')
    if a.status:
        value={'queue':{}}
        if (state/'inventory.sqlite').exists():
            db=sqlite3.connect('file:'+str(state/'inventory.sqlite')+'?mode=ro',uri=True)
            try:value['queue']=queue_counts(db)
            finally:db.close()
        for mode in ['daily','rescan']:
            for suffix in ['last','attempt']:
                f=state/(mode+'-'+suffix+'.json');value[mode+'_'+suffix]=json.loads(f.read_text()) if f.exists() else None
        print(json.dumps(value,indent=2));return
    with (state/'scan.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('Another scan owns the shared lock; deferred.');return
        db=connect(state)
        try:
            try:notify_pending(cfg,state)
            except (OSError,ValueError,subprocess.SubprocessError):pass
            result=execute(cfg,'rescan' if a.rescan or a.rescan_plan else 'daily',state,db,force=a.now,plan=a.plan or a.rescan_plan)
            print(json.dumps(result,indent=2))
        finally:db.close()

if __name__=='__main__':main()
