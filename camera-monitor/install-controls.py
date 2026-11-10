"""Install fixed camera controls; preserve the camera's current state by default."""
import argparse
import sys
sys.dont_write_bytecode = True
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import tempfile

LIB = Path('/usr/local/libexec/camera-monitor')
STATE = Path('/var/lib/camera-monitor-control')
UNIT = Path('/etc/systemd/system/camera-privacy.service')
RULE = Path('/etc/udev/rules.d/72-camera-privacy.rules')
DROPIN = Path('/etc/systemd/system/v4l2-relayd.service.d/90-camera-privacy.conf')
SUDOERS = Path('/etc/sudoers.d/camera-privacy')


def policy(user):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', user): raise ValueError('Invalid account name')
    base = '/usr/bin/python3 -I /usr/local/libexec/camera-monitor/control.py '
    return f'{user} ALL=(root) NOPASSWD: {base}block, {base}unblock\n'


def unit():
    return '''[Unit]
Description=Reapply saved built-in camera privacy block
After=systemd-udev-trigger.service
Before=v4l2-relayd.service
ConditionPathExists=/var/lib/camera-monitor-control/blocked.json

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I /usr/local/libexec/camera-monitor/control.py enforce
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
'''


def rule(config):
    return ('ACTION=="add", SUBSYSTEM=="pci", KERNEL=="'+config['address']+'", '
            'ATTR{vendor}=="'+config['vendor']+'", ATTR{device}=="'+config['device']+'", '
            'TEST=="/var/lib/camera-monitor-control/blocked.json", '
            'ATTR{driver_override}="camera-privacy-blocked"\n'
            'ACTION=="add|change", SUBSYSTEM=="video4linux", DEVPATH=="/devices/virtual/video4linux/*", '
            'ATTR{name}=="'+config['virtualCameraName']+'", TEST=="/var/lib/camera-monitor-control/blocked.json", '
            'TAG-="uaccess", MODE="0000"\n')


def safe(path, directory=False):
    if not path.exists() and not path.is_symlink(): return
    s = path.lstat()
    if s.st_uid != 0 or s.st_mode & 0o022 or not (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)):
        raise RuntimeError('Unsafe protected destination: '+str(path))


def atomic(path, content, mode=0o644):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp=Path(f.name);f.write(content);os.fchmod(f.fileno(),mode);os.fchown(f.fileno(),0,0)
    tmp.replace(path)


def source(path):
    p=path.resolve(strict=True);s=p.stat()
    if not str(p).startswith('/nix/store/') or s.st_uid != 0 or s.st_mode & 0o022:
        raise RuntimeError('Sources must be immutable root-owned Nix store files')
    return p


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['control','config','monitor','test']:p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--user',required=True)
    p.add_argument('--check',action='store_true')
    p.add_argument('--self-test',action='store_true')
    args=p.parse_args()
    files={k:source(getattr(args,k)) for k in ['control','config','monitor','test']}
    account=pwd.getpwnam(args.user)
    spec=importlib.util.spec_from_file_location('camera_control',files['control']);control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
    config=control.validate(json.loads(files['config'].read_text()))
    control.Controller(config).inspect()
    for k in ['control','monitor','test']:compile(files[k].read_text(),str(files[k]),'exec')
    payloads={LIB/'control.py':files['control'].read_bytes(), LIB/'controller.json':files['config'].read_bytes(),
              LIB/'test-controls.py':files['test'].read_bytes(),
              UNIT:unit().encode(), RULE:rule(config).encode(),
              DROPIN:b'[Unit]\nConditionPathExists=!/var/lib/camera-monitor-control/blocked.json\n',
              SUDOERS:policy(args.user).encode()}
    with tempfile.TemporaryDirectory(prefix='camera-privacy-check-') as td:
        check=Path(td)/'sudoers';check.write_bytes(payloads[SUDOERS]);check.chmod(0o440)
        subprocess.run(['/usr/sbin/visudo','-cf',str(check)],check=True)
        check=Path(td)/UNIT.name;check.write_bytes(payloads[UNIT])
        subprocess.run(['/bin/systemd-analyze','verify',str(check)],check=True)
    if args.check:
        print('Camera identity, sources, sudo policy and boot unit passed read-only preflight.');return
    if os.geteuid()!=0:raise SystemExit('Use install-camera-controls; sudo is required.')
    for directory in [LIB,STATE,UNIT.parent,RULE.parent,DROPIN.parent,SUDOERS.parent]:
        safe(directory,True)
        safe(directory.parent,True)
    for dest in payloads:safe(dest)
    # Do not silently retarget controls while a saved block exists.
    if (STATE/'blocked.json').exists():
        existing=json.loads((STATE/'blocked.json').read_text())
        if existing.get('controller')!=config:raise RuntimeError('Existing block belongs to another camera')
    backup=Path(tempfile.mkdtemp(prefix='camera-privacy-',dir='/var/backups'))
    manifest={}
    for i,dest in enumerate(payloads):
        if dest.exists():shutil.copy2(dest,backup/str(i));manifest[str(dest)]=str(i)
        else:manifest[str(dest)]=None
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
    enabled=subprocess.run(['/bin/systemctl','is-enabled','--quiet',UNIT.name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    try:
        for dest,content in payloads.items():
            dest.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
            atomic(dest,content,0o440 if dest==SUDOERS else 0o644)
        STATE.mkdir(mode=0o755,exist_ok=True)
        subprocess.run(['/usr/sbin/visudo','-cf',str(SUDOERS)],check=True)
        subprocess.run(['/bin/systemctl','daemon-reload'],check=True)
        subprocess.run(['/bin/udevadm','control','--reload-rules'],check=True)
        # Enabling adds the boot guard, without running it or changing camera state.
        subprocess.run(['/bin/systemctl','enable',UNIT.name],check=True)
    except BaseException:
        for dest,old in manifest.items():
            if old is None:Path(dest).unlink(missing_ok=True)
            else:shutil.copy2(backup/old,dest)
        subprocess.run(['/bin/systemctl','daemon-reload'])
        subprocess.run(['/bin/udevadm','control','--reload-rules'])
        subprocess.run(['/bin/systemctl','enable' if enabled else 'disable',UNIT.name])
        raise
    print('Camera controls backup:',backup,flush=True)
    print('Installed fixed block/unblock commands for',args.user,'; camera state unchanged.',flush=True)
    print('Unblock/recovery: sudo /usr/bin/python3 -I /usr/local/libexec/camera-monitor/control.py unblock',flush=True)
    if args.self_test:
        subprocess.run(['/usr/bin/python3','-I',str(LIB/'test-controls.py'),'--user',args.user],check=True)


if __name__=='__main__':main()
