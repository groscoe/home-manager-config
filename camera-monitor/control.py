"""Fixed built-in-camera control backend. Root-owned config; no arbitrary targets."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

CONFIG = Path('/usr/local/libexec/camera-monitor/controller.json')
STATE = Path('/var/lib/camera-monitor-control')
MARKER = STATE / 'blocked.json'
OVERRIDE = 'camera-privacy-blocked'


def validate(config):
    patterns = {'address': r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]',
                'driver': r'[A-Za-z0-9_-]+', 'vendor': r'0x[0-9a-f]{4}',
                'device': r'0x[0-9a-f]{4}', 'virtualCameraName': r'[A-Za-z0-9 ._-]+'}
    if set(config) != set(patterns) or any(not isinstance(config[k], str) or
            not re.fullmatch(pattern, config[k]) for k, pattern in patterns.items()):
        raise ValueError('Invalid camera controller configuration')
    return config


def trusted_json(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError('Untrusted camera control metadata: ' + str(path))
    return json.loads(path.read_text())


def save_marker(path, value):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode='w') as stream:
        tmp = Path(stream.name)
        os.fchmod(stream.fileno(), 0o644)
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


class VirtualCamera:
    """Restrict only root-owned virtual nodes carrying the configured relay label."""
    def __init__(self, label, sysfs=Path('/sys'), dev=Path('/dev'), run=None):
        self.label, self.sysfs, self.dev = label, sysfs, dev
        self.run = run or Controller.command

    def nodes(self):
        nodes = []
        for node in (self.sysfs / 'devices/virtual/video4linux').glob('video[0-9]*'):
            if (node / 'name').read_text().strip() != self.label: continue
            target = self.dev / node.name
            info = target.lstat()
            major, minor = map(int, (node / 'dev').read_text().strip().split(':'))
            if not stat.S_ISCHR(info.st_mode) or info.st_uid != 0 or info.st_rdev != os.makedev(major, minor):
                raise RuntimeError('Virtual camera identity or device ownership changed')
            nodes.append(target)
        return nodes

    def snapshot(self):
        nodes = self.nodes()
        if not nodes: raise RuntimeError('Configured virtual camera is absent')
        result = []
        for target in nodes:
            info = target.lstat()
            acl = subprocess.check_output(['/usr/bin/getfacl','-cnp','--',str(target)],text=True)
            result.append({'node':target.name,'uid':info.st_uid,'gid':info.st_gid,
                           'mode':stat.S_IMODE(info.st_mode),'acl':acl})
        return result

    def trigger(self, nodes):
        for target in nodes:
            self.run('/bin/udevadm','trigger','--action=change','--subsystem-match=video4linux',
                     '--sysname-match='+target.name)
        if nodes: self.run('/bin/udevadm','settle','--timeout=5')

    def restrict(self, saved, boot=False):
        nodes = self.nodes()
        if not nodes and not boot: raise RuntimeError('Virtual camera disappeared before blocking')
        for target in nodes: os.chmod(target,0)
        # The installed rule removes uaccess before seat-late can regrant ACLs.
        self.trigger(nodes)
        for target in nodes: os.chmod(target,0)
        if not self.blocked(): raise RuntimeError('Virtual camera access remains enabled')

    def restore(self, saved):
        nodes = self.nodes()
        if not saved: raise RuntimeError('Missing saved virtual camera permissions')
        self.trigger(nodes)  # Marker has been removed: restore normal udev/uaccess tags.
        for target in nodes:
            previous = next((item for item in saved if item['node']==target.name),saved[0])
            os.chown(target,previous['uid'],previous['gid'])
            subprocess.run(['/usr/bin/setfacl','--set-file=-','--',str(target)],
                           input=previous['acl'],text=True,check=True)
            os.chmod(target,previous['mode'])

    def blocked(self):
        return all(stat.S_IMODE(target.lstat().st_mode)==0 for target in self.nodes())


class Controller:
    def __init__(self, config, state=STATE, sysfs=Path('/sys'), run=None, write=None, permissions=None):
        self.config = validate(config)
        self.state = state
        self.marker = state / 'blocked.json'
        self.device = sysfs / 'bus/pci/devices' / config['address']
        self.driver = sysfs / 'bus/pci/drivers' / config['driver']
        self.run = run or self.command
        self.write = write or (lambda path, value: path.write_text(value))
        self.permissions = permissions or VirtualCamera(config['virtualCameraName'],sysfs,run=self.run)

    @staticmethod
    def command(*args):
        return subprocess.run(args, check=True, timeout=25, stdout=subprocess.DEVNULL)

    def inspect(self, allow_missing=False):
        if not self.device.exists():
            if allow_missing: return None
            raise RuntimeError('Configured camera controller is absent')
        for key in ('vendor', 'device'):
            if (self.device / key).read_text().strip() != self.config[key]:
                raise RuntimeError('Camera hardware identity changed; refusing to act')
        link = self.device / 'driver'
        current = link.resolve().name if link.exists() else None
        if current not in (None, self.config['driver']):
            raise RuntimeError('Camera is bound to an unexpected driver')
        return current

    def existing(self):
        if not self.marker.exists(): return None
        value = trusted_json(self.marker)
        if value.get('controller') != self.config or value.get('original_override') != '':
            raise RuntimeError('Saved block state does not match this controller')
        if not isinstance(value.get('relay_active'), bool):
            raise RuntimeError('Invalid saved relay state')
        return value

    def block(self, boot=False):
        saved = self.existing()
        if boot and saved is None: return
        bound = self.inspect(allow_missing=boot)
        if saved is None and bound != self.config['driver']:
            raise RuntimeError('Camera was not initially attached; refusing to change its policy')
        if self.device.exists():
            override = (self.device / 'driver_override').read_text().strip()
            if override not in ('', '(null)', OVERRIDE if saved else ''):
                raise RuntimeError('Camera has an unexpected driver override')
        if saved is None:
            override = (self.device / 'driver_override').read_text().strip()
            if override not in ('', '(null)'):
                raise RuntimeError('Controller has an existing driver override; refusing to replace it')
            active = subprocess.run(['/bin/systemctl', 'is-active', '--quiet', 'v4l2-relayd.service'],
                                    stdout=subprocess.DEVNULL).returncode == 0
            saved = {'controller': self.config, 'original_override': '', 'relay_active': active, 'virtual': self.permissions.snapshot()}
            save_marker(self.marker, saved)
        self.permissions.restrict(saved['virtual'],boot=boot)
        # Keep the marker on failure: the UI must show unverified/failed, not blocked.
        if not boot:
            self.run('/bin/systemctl', 'stop', 'v4l2-relayd.service')
        if self.device.exists():
            self.write(self.device / 'driver_override', OVERRIDE + '\n')
            if bound is not None:
                self.write(self.driver / 'unbind', self.config['address'] + '\n')
            if self.inspect() is not None:
                raise RuntimeError('Camera controller remains bound; blocking is unverified')
            if (self.device / 'driver_override').read_text().strip() != OVERRIDE:
                raise RuntimeError('Camera driver override was not applied')

    def unblock(self):
        saved = self.existing()
        if saved is None:
            if self.inspect() != self.config['driver'] or (self.device / 'driver_override').read_text().strip() not in ('', '(null)'):
                raise RuntimeError('No saved block; camera policy is unexpected and will not be overwritten')
            return  # Never modify somebody else's driver override.
        self.inspect()
        try:
            self.write(self.device / 'driver_override', '\n')
            if self.inspect() is None:
                self.write(self.driver / 'bind', self.config['address'] + '\n')
            if self.inspect() != self.config['driver']:
                raise RuntimeError('Camera driver did not reattach')
            self.marker.unlink()
            self.permissions.restore(saved['virtual'])
            if saved['relay_active']:
                self.run('/bin/systemctl', 'start', 'v4l2-relayd.service')
        except BaseException:
            save_marker(self.marker, saved)
            try: self.block()
            except Exception: pass
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['block', 'unblock', 'enforce'])
    args = parser.parse_args()
    if os.geteuid() != 0: raise SystemExit('Camera controls require the installed privileged helper.')
    os.umask(0o077)
    config = validate(trusted_json(CONFIG))
    info = STATE.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise SystemExit('Unsafe camera state directory')
    with (STATE / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        c = Controller(config)
        if args.action == 'unblock': c.unblock()
        else: c.block(boot=args.action == 'enforce')
    print('Camera control:', args.action, 'completed')


if __name__ == '__main__':
    main()
