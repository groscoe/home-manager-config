"""PulseAudio controls and an event-driven state service; never records audio."""
import argparse
from contextlib import contextmanager
import fcntl
import html
import json
import math
import os
from pathlib import Path
import selectors
import struct
import subprocess
import tempfile
import time
import wave


def safe(text):
    return str(text).replace('\n',' ').replace('\r',' ').replace('%{','?{')[:160]


def run(*args):
    p=subprocess.run(args,text=True,capture_output=True,timeout=10)
    if p.returncode:raise RuntimeError(safe(p.stderr.strip() or p.stdout.strip() or 'Audio command failed'))
    return p.stdout.strip()


class Audio:
    def __init__(self,cfg):
        self.cfg=cfg
        self.root=Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'xps-audio'
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
    def pa(self,*args):return run(self.cfg['pactl'],*map(str,args))
    def listing(self,kind):return json.loads(self.pa('-f','json','list',kind))
    def prefs(self):
        try:return json.loads((self.root/'preferences.json').read_text())
        except (OSError,ValueError):return {}
    def save(self,name,value):
        fd,tmp=tempfile.mkstemp(dir=self.root,prefix='.'+name)
        try:
            with os.fdopen(fd,'w') as f:json.dump(value,f)
            os.replace(tmp,self.root/name)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    @contextmanager
    def lock(self):
        with (self.root/'lock').open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX);yield
    def inventory(self):
        return self.listing('sinks'),[s for s in self.listing('sources') if not monitor(s)]
    def default(self,kind):return self.pa('get-default-'+('sink' if kind=='output' else 'source'))
    def notice(self,title,body=''):
        try:subprocess.run([self.cfg['notify'],'--app-name=XPS audio','--hint=string:x-dunst-stack-tag:xps-audio','--expire-time=2000',title,html.escape(body)],timeout=2,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except (OSError,subprocess.TimeoutExpired):pass
    def switch(self,kind,name,remember=True):
        noun='sink' if kind=='output' else 'source'
        devices=self.listing('sinks' if kind=='output' else 'sources')
        chosen=next((d for d in devices if d['name']==name and available(d) and (kind=='output' or not monitor(d))),None)
        if not chosen:raise RuntimeError('The selected device is no longer available')
        self.pa('set-default-'+noun,name)
        # Explicit output/input switching moves existing streams, not just new ones.
        for stream in self.listing('sink-inputs' if kind=='output' else 'source-outputs'):
            try:self.pa('move-'+('sink-input' if kind=='output' else 'source-output'),stream['index'],name)
            except RuntimeError:pass # A stream can exit or disallow moving.
        prefs=self.prefs()
        if kind=='input' and prefs.get('mic_muted') and not chosen['mute']:self.pa('set-source-mute',name,'1')
        if remember:
            prefs[kind]=name;self.save('preferences.json',prefs)
        return chosen
    def adjust(self,kind,delta):
        noun='sink' if kind=='output' else 'source'
        name=self.default(kind)
        values=self.listing('sinks' if kind=='output' else 'sources')
        d=next(d for d in values if d['name']==name)
        volumes=[str(max(0,min(65536,int(v['value'])+round(delta*65536/100)))) for v in d['volume'].values()]
        self.pa('set-'+noun+'-volume',name,*volumes)
        self.notice(('Output volume' if kind=='output' else 'Microphone gain'),str(round(max(map(int,volumes))*100/65536))+'% · '+safe(d['description']))
    def mute_output(self):
        self.pa('set-sink-mute','@DEFAULT_SINK@','toggle')
        self.notice('Output mute toggled')
    def mute_mics(self):
        _,sources=self.inventory()
        if not sources:raise RuntimeError('No microphone available')
        target=not all(s['mute'] for s in sources)
        for s in sources:self.pa('set-source-mute',s['name'],'1' if target else '0')
        prefs=self.prefs();prefs['mic_muted']=target;self.save('preferences.json',prefs)
        self.notice('All microphones muted' if target else 'Microphones unmuted')
    def reconcile(self,previous=None):
        previous=previous or {};prefs=self.prefs();sinks,sources=self.inventory()
        for kind,devices in [('output',sinks),('input',sources)]:
            usable={d['name']:d for d in devices if available(d)}
            if not usable:continue
            current=self.default(kind);preferred=prefs.get(kind)
            returned=preferred in usable and preferred not in previous.get(kind+'_devices',list(usable))
            if returned or current not in usable:
                target=preferred if preferred in usable else max(usable,key=lambda n:priority(usable[n]))
                self.switch(kind,target,remember=False)
        if prefs.get('mic_muted'):
            for s in sources:
                if not s['mute']:self.pa('set-source-mute',s['name'],'1')
        sinks,sources=self.inventory()
        out=self.default('output');inp=self.default('input')
        output=next((d for d in sinks if d['name']==out),None)
        source=next((d for d in sources if d['name']==inp),None)
        real_indices={s['index'] for s in sources}
        recording=any(s.get('source') in real_indices and not s.get('corked',False) for s in self.listing('source-outputs'))
        state={'time':time.time(),'connected':True,'output':output,'input':source,
               'output_devices':[d['name'] for d in sinks if available(d)],'input_devices':[d['name'] for d in sources if available(d)],
               'all_mics_muted':bool(sources) and all(d['mute'] for d in sources),'recording':recording}
        self.save('status.json',state);return state
    def choose_device(self,kind):
        devices=self.listing('sinks' if kind=='output' else 'sources')
        devices=[d for d in devices if available(d) and (kind=='output' or not monitor(d))]
        current=self.default(kind)
        rows=[('● ' if d['name']==current else '  ')+safe(d['description'])+(' · muted' if d['mute'] else '') for d in devices]
        choice=choose(self.cfg,'Output · move playback' if kind=='output' else 'Microphone · move capture',rows)
        if choice is not None:
            with self.lock():d=self.switch(kind,devices[choice]['name'])
            self.notice('Audio '+kind+' selected',safe(d['description']))
    def profiles(self):
        cards=[c for c in self.listing('cards') if c.get('properties',{}).get('device.bus')=='bluetooth' or c['name'].startswith('bluez_card')]
        entries=[]
        for c in cards:
            profiles=c['profiles']
            if isinstance(profiles,list):profiles={p['name']:p for p in profiles}
            for name,p in profiles.items():
                if name=='off' or p.get('available') in (False,'no','not available'):continue
                entries.append((c,name,p))
        choice=choose(self.cfg,'Bluetooth · music / headset profiles',[safe(c.get('properties',{}).get('device.description',c['name']))+' · '+safe(p['description'])+(' · selected' if name==c['active_profile'] else '') for c,name,p in entries])
        if choice is not None:
            c,name,p=entries[choice]
            if ('headset' in name or 'head_unit' in name) and choose(self.cfg,'Headset microphone can reduce playback quality',['Cancel','Use headset profile'])!=1:return
            with self.lock():self.pa('set-card-profile',c['name'],name)
            self.notice('Bluetooth profile selected',safe(p['description']))
    def test(self):
        target=self.default('output')
        if 'yes' in self.pa('get-sink-mute',target).lower():raise RuntimeError('Output is muted. Unmute it explicitly before playing the test.')
        with tempfile.TemporaryDirectory(prefix='xps-audio-') as td:
            path=Path(td)/'left-right.wav'
            with wave.open(str(path),'wb') as wav:
                wav.setparams((2,2,24000,0,'NONE','not compressed'))
                for side in [0,1]:
                    frames=[]
                    for n in range(36000):
                        envelope=max(0,min(1,n/1200,(24000-n)/1200))
                        value=int(8000*envelope*math.sin(2*math.pi*(440 if side==0 else 660)*n/24000)) if n<24000 else 0
                        frames.append(struct.pack('<hh',value if side==0 else 0,value if side else 0))
                    wav.writeframes(b''.join(frames))
            run(self.cfg['paplay'],'--device='+target,'--stream-name=XPS left-right test','--volume=65536',str(path))


def monitor(d):return d.get('properties',{}).get('device.class')=='monitor' or d['name'].endswith('.monitor')
def available(d):
    ports=d.get('ports') or []
    active=next((p for p in ports if p['name']==d.get('active_port')),None)
    return active.get('availability') not in ('not available','no') if active else not ports or any(p.get('availability') not in ('not available','no') for p in ports)
def priority(d):return (int(any(p.get('type')=='Speaker' for p in d.get('ports',[]))),int(d.get('properties',{}).get('device.bus')!='bluetooth'))
def percent(d):return round(max((v['value'] for v in d.get('volume',{}).values()),default=0)*100/65536)
def choose(cfg,prompt,rows):
    if not rows:
        subprocess.run([cfg['notify'],'XPS audio','No matching devices available'],check=False);return None
    p=subprocess.run([cfg['rofi'],'-dmenu','-i','-no-custom','-format','i','-p',prompt],input='\n'.join(rows),text=True,capture_output=True)
    try:
        n=int(p.stdout.strip());return n if p.returncode==0 and 0<=n<len(rows) else None
    except ValueError:return None


def menu(a):
    actions=[('Connect / pair Bluetooth headphones…','bluetooth'),('Choose output…','output'),('Choose microphone…','input'),('Bluetooth music / headset profiles…','profiles'),('Output volume +5%','up'),('Output volume −5%','down'),('Toggle output mute','mute'),('Toggle mute on all microphones','mic-mute'),('Microphone gain +5%','mic-up'),('Microphone gain −5%','mic-down'),('Quiet test · left then right tone','test'),('Full application mixer…','mixer')]
    while True:
        sinks,sources=a.inventory();default=a.default('output');source=a.default('input')
        out=next((d for d in sinks if d['name']==default),None);mic=next((d for d in sources if d['name']==source),None)
        header='Output: '+(safe(out['description'])+f" · {percent(out)}%"+(' · MUTED' if out['mute'] else '') if out else 'none')
        header+='\nMic: '+(safe(mic['description'])+f" · {percent(mic)}%"+(' · MUTED' if mic['mute'] else ' · ready') if mic else 'none')
        p=subprocess.run([a.cfg['rofi'],'-dmenu','-i','-no-custom','-format','i','-p','Audio','-mesg',html.escape(header)],input='\n'.join(x[0] for x in actions),text=True,capture_output=True)
        try:n=int(p.stdout.strip())
        except ValueError:return
        if p.returncode or not 0<=n<len(actions):return
        try:execute(a,actions[n][1])
        except (RuntimeError,subprocess.TimeoutExpired) as e:a.notice('Audio action failed',str(e))
        if actions[n][1]=='mixer':return


def execute(a,action):
    if action in ('output','input'):a.choose_device(action)
    elif action=='bluetooth':subprocess.run([a.cfg['bluetooth']],check=True)
    elif action=='profiles':a.profiles()
    elif action=='test':a.test()
    elif action=='mixer':subprocess.Popen([a.cfg['mixer']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:
        with a.lock():
            if action in ('up','down','mic-up','mic-down'):a.adjust('input' if action.startswith('mic-') else 'output',5 if action.endswith('up') else -5)
            elif action=='mute':a.mute_output()
            elif action=='mic-mute':a.mute_mics()
            else:raise RuntimeError('Unknown audio action')


def watch(a):
    p=subprocess.Popen([a.cfg['pactl'],'subscribe'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    selector=selectors.DefaultSelector();selector.register(p.stdout,selectors.EVENT_READ)
    buf=b'';dirty=True;due=0.;last={};heartbeat=0.
    try:
        while True:
            now=time.monotonic()
            if p.poll() is not None:raise RuntimeError('PulseAudio event subscription ended')
            if dirty and now>=due:
                with a.lock():last=a.reconcile(last)
                dirty=False;heartbeat=now+5
            if now>=heartbeat:
                last['time']=time.time();a.save('status.json',last);heartbeat=now+5
            timeout=max(0,min(heartbeat-now,due-now if dirty else 5))
            if selector.select(timeout):
                chunk=os.read(p.stdout.fileno(),65536)
                if not chunk:raise RuntimeError('PulseAudio disconnected')
                buf+=chunk
                while b'\n' in buf:
                    line,buf=buf.split(b'\n',1)
                    if any(b'on '+kind in line for kind in [b'sink ',b'source ',b'server ',b'card ',b'sink-input ',b'source-output ']):
                        if not dirty:due=time.monotonic()+.12
                        dirty=True
    finally:
        selector.close();p.terminate()
        try:p.wait(timeout=2)
        except subprocess.TimeoutExpired:p.kill();p.wait()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    p.add_argument('action',nargs='?',default='menu',choices=['menu','output','input','profiles','up','down','mic-up','mic-down','mute','mic-mute','test','mixer','watch','status','mic-status','json'])
    args=p.parse_args();a=Audio(json.loads(args.config.read_text()))
    try:
        if args.action=='watch':watch(a)
        elif args.action in ('status','mic-status','json'):
            try:state=json.loads((a.root/'status.json').read_text())
            except (OSError,ValueError):state={}
            if args.action=='json':print(json.dumps(state));return
            if not state.get('connected') or time.time()-state.get('time',0)>15:print('Audio ?' if args.action=='status' else 'Mic ?');return
            if args.action=='mic-status':print('Mic —' if not state.get('input') else 'Mic muted' if state['all_mics_muted'] else 'Mic LIVE' if state['recording'] else 'Mic ready')
            else:
                d=state.get('output');print('Audio —' if not d else 'Muted' if d['mute'] else f'Audio {percent(d)}%')
        elif args.action=='menu':menu(a)
        else:execute(a,args.action)
    except (OSError,RuntimeError,subprocess.TimeoutExpired,StopIteration) as e:
        if args.action=='watch':a.save('status.json',{'connected':False,'time':time.time(),'error':safe(e)});raise
        a.notice('Audio unavailable',str(e));raise SystemExit(1)

if __name__=='__main__':main()
