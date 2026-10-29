"""Check actual generated profiles and isolated XRandR save/blank/restore."""
from pathlib import Path
import configparser,json,os,shlex,subprocess,sys,tempfile

def check(p):
 h=p['hardware']
 assert p['graphicsWrapper']==h['graphicsWrapper']
 bar=configparser.ConfigParser(interpolation=None,strict=False);bar.read(p['bar'])
 assert bar['bar/main']['monitor']=='${env:MONITOR:'+str(h['displayOutput'] or '')+'}'
 assert int(bar['bar/main']['height'])==44*h['scale']
 assert ('battery' in bar['bar/main']['modules-right'].split())==(h['battery'] is not None)
 assert ('network' in bar['bar/main']['modules-right'].split())==(h['wifiInterface'] is not None)
 if h['battery']:
  assert bar['module/battery']['battery']==h['battery'] and bar['module/battery']['adapter']==h['acAdapter']
 else:assert 'module/battery' not in bar
 if h['wifiInterface']:assert bar['module/network']['interface']==h['wifiInterface']
 else:assert 'module/network' not in bar
 assert p['codiumVersion']=='1.140.06880'
 assert ('--force-device-scale-factor='+str(h['scale'])).encode() in Path(p['codium']).read_bytes()
 assert p['dpi']==h['dpi'] and p['cursorSize']==h['cursorSize']
 assert p['xsettings']['Gdk/WindowScalingFactor']==h['scale']
 assert p['xsettings']['Xft/DPI']==h['dpi']*1024
 assert p['healthDevices']==h['nvmeDevices']
 assert p['health']==bool(h['battery'] or h['nvmeDevices'])
 assert p['vnc']==bool(h['backlightDevice'] and h['displayOutput'])
 lines=Path(p['keyboard']).read_text().splitlines()
 xkb=next(shlex.split(line) for line in lines if line.lstrip().startswith('setxkbmap '))
 assert xkb[xkb.index('-layout')+1]==h['keyboardLayout']
 remaps=[shlex.split(line)[2] for line in lines if line.lstrip().startswith('xmodmap -e ')]
 assert remaps==h['keyboardRemaps']
 assert ('xsetwacom set' in '\n'.join(lines))==(h['tablet'] is not None)
 assert '@keyboard' not in '\n'.join(lines)

settings=json.loads(Path(sys.argv[1]).read_text())
for profile in settings.values():check(profile)
vm=settings['virtual']
assert not any(vm[k] for k in ['health','vnc','backup','scan'])
assert vm['hardware']['displayOutput']=='Virtual-1'
assert vm['hardware']['keyboardLayout']=='us'
assert settings['physical']['hardware']['displayOutput']=='eDP-1'
assert settings['physical']['hardware']['keyboardLayout']=='br'
with tempfile.TemporaryDirectory() as temporary:
 socket=str(Path(temporary)/'tmux.sock')
 env=dict(os.environ,HOME=temporary,TERM='xterm-256color')
 try:
  subprocess.run(['tmux','-S',socket,'-f',vm['tmuxConfig'],'new-session','-d','-s','fixture'],env=env,check=True)
  actual=subprocess.check_output(['tmux','-S',socket,'show-options','-gv','prefix'],env=env,text=True).strip()
  assert actual==';','Virtual keyboard prefix is unavailable'
 finally:
  subprocess.run(['tmux','-S',socket,'kill-server'],env=env,capture_output=True)
with tempfile.TemporaryDirectory() as root:
 root=Path(root);before=root/'before';after=root/'after'
 def run(helper,action,path):return subprocess.run([helper,action,str(path)],capture_output=True,text=True)
 for action in ['save','blank','restore']:
  r=run(sys.argv[2],action,before);assert r.returncode==0,r.stderr
 r=run(sys.argv[2],'save',after);assert r.returncode==0,r.stderr
 assert before.read_bytes()==after.read_bytes(),('Gamma restoration was not exact',len(before.read_bytes()),len(after.read_bytes()),sum(a!=b for a,b in zip(before.read_bytes(),after.read_bytes())))
 r=run(sys.argv[3],'save',root/'wrong');assert r.returncode!=0
 assert not (root/'wrong').exists(),'Wrong output created recovery data'
print(json.dumps({'physical_profile':'passed','vm_profile':'passed','no_physical_hardware_services_in_vm':True,'non_edp_output_gamma_round_trip':'passed','unconfigured_output_refused':True},indent=2))
