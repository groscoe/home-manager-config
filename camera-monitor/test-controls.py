"""Root-run live test of installed controls; discards all video to /dev/null."""
import argparse
import sys
sys.dont_write_bytecode = True
import importlib.util
import json
import os
from pathlib import Path
import pwd
import subprocess
import tempfile
import time


def wait_snapshot(path, timeout=12, ready=lambda value: True):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = json.loads(path.read_text())
            if (value.get('coverage') == 'system' and
                    0 <= time.time() - value['time'] < 8 and ready(value)):
                return value
        except (OSError, ValueError, KeyError, TypeError):
            pass
        time.sleep(.1)
    raise RuntimeError('Camera collector did not publish a fresh, ready system snapshot')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--user',required=True);args=p.parse_args()
    if os.geteuid()!=0:raise SystemExit('Root is required for the controlled live test')
    spec=importlib.util.spec_from_file_location('control','/usr/local/libexec/camera-monitor/control.py')
    cmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(cmod)
    c=cmod.Controller(cmod.validate(cmod.trusted_json(cmod.CONFIG)))
    if c.marker.exists():raise SystemExit('Camera is already blocked; self-test will not enable it.')
    before=c.inspect()
    if before!=c.config['driver']:raise SystemExit('Camera was not initially attached; refusing live test')
    reading=wait_snapshot(Path('/run/camera-monitor/status.json'), ready=lambda value: bool(value.get('holders')))
    if any(not h.get('infrastructure') for h in reading['holders']):
        raise SystemExit('A camera application is active; close it before running the self-test.')
    nodes={d for h in reading['holders'] if h.get('infrastructure') for d in h['devices'] if d.startswith('video')}
    if len(nodes)!=1:raise SystemExit('Cannot identify one virtual relay camera for the live test')
    capture='/dev/'+nodes.pop()
    account=pwd.getpwnam(args.user)
    env={'PATH':'/usr/bin:/bin','HOME':account.pw_dir,'LANG':'C'}
    client=None;blocked=False;result={'frames_saved':False}
    with tempfile.TemporaryDirectory(prefix='camera-privacy-test-') as td:
        logpath=Path(td)/'stream.log'
        def client_start(count,log):
            return subprocess.Popen(['/usr/bin/v4l2-ctl','--device='+capture,'--stream-mmap=3',
                 '--stream-count='+str(count),'--stream-to=/dev/null'],user=account.pw_uid,
                 group=account.pw_gid,extra_groups=[],env=env,stdout=log,stderr=log)
        try:
            with logpath.open('w') as log:
                client=client_start(1800,log)
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    snapshot=wait_snapshot(Path('/run/camera-monitor/status.json'))
                    if any(h['pid']==client.pid for h in snapshot['holders']):break
                    if client.poll() is not None:raise RuntimeError('Initial camera stream failed')
                    time.sleep(.25)
                else:raise RuntimeError('Monitor did not observe the test stream')
                result['initial_stream_detected']=True
                c.block();blocked=True
                assert c.inspect() is None
                assert (c.device/'driver_override').read_text().strip()==cmod.OVERRIDE
                time.sleep(1);size=logpath.stat().st_size;time.sleep(2)
                result['existing_stream_stopped_producing']=client.poll() is not None or logpath.stat().st_size==size
                assert result['existing_stream_stopped_producing'],'Existing stream still produces frame reports'
            if client.poll() is None:client.terminate();client.wait(timeout=3)
            with (Path(td)/'blocked.log').open('w') as log:
                attempted=client_start(1,log)
                try:code=attempted.wait(timeout=4)
                except subprocess.TimeoutExpired:attempted.terminate();attempted.wait(timeout=3);code='timed-out-without-frame'
                assert code!=0,'A new camera stream succeeded while blocked'
                result['new_stream_denied']=code
            # Reapplying the same block and the boot enforcement path are idempotent.
            c.block();c.block(boot=True);assert c.inspect() is None
            result['reapply_and_boot_enforce_passed']=True
        finally:
            if client is not None and client.poll() is None:
                client.terminate()
                try:client.wait(timeout=3)
                except subprocess.TimeoutExpired:client.kill();client.wait()
            if c.marker.exists():c.unblock()
        assert c.inspect()==before and not c.marker.exists()
        restored_at=time.time();deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            fresh_status=wait_snapshot(Path('/run/camera-monitor/status.json'))
            if fresh_status['time']>=restored_at and any(h.get('infrastructure') and h['uid']==0 for h in fresh_status['holders']):break
            time.sleep(.25)
        else:raise RuntimeError('Restored relay did not become ready for capture')
        with (Path(td)/'restored.log').open('w') as log:
            fresh=client_start(90,log)
            try:code=fresh.wait(timeout=15)
            except subprocess.TimeoutExpired:fresh.kill();fresh.wait();raise RuntimeError('Restored camera stream timed out')
            if code!=0:raise RuntimeError('Restored camera stream failed: '+(Path(td)/'restored.log').read_text()[-1200:])
        result['fresh_stream_after_unblock']=True
        result['original_state_restored']=True
    cmod.save_marker(cmod.STATE/'last-test.json',result)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
