"""Observe camera handles without opening cameras or collecting command lines."""
import argparse
import ctypes
import datetime
import html
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import time


def clean(value):
    # Process names are untrusted; never allow Polybar markup or extra Rofi rows.
    return re.sub(r'[^\w .+:/()@-]', '?', value)[:120]


def discover(root=Path('/sys/class')):
    devices = {}
    for cls in ('video4linux', 'media'):
        folder = root / cls
        if not folder.exists():
            continue
        for node in folder.iterdir():
            try:
                major, minor = map(int, (node / 'dev').read_text().strip().split(':'))
                devices[(major, minor)] = node.name
            except (OSError, ValueError):
                continue
    # Older Ubuntu IPU6 kernels expose media controllers outside /sys/class.
    if root == Path('/sys/class'):
        for node in Path('/dev').glob('media[0-9]*'):
            try:
                info = node.stat()
                if stat.S_ISCHR(info.st_mode):
                    devices[(os.major(info.st_rdev), os.minor(info.st_rdev))] = node.name
            except OSError:
                continue
    return devices


def scan(proc=Path('/proc'), devices=None, uid=None):
    devices = discover() if devices is None else devices
    uid = os.getuid() if uid is None else uid
    holders, unreadable = [], []
    for process in proc.iterdir():
        if not process.name.isdigit():
            continue
        try:
            owner = process.stat().st_uid
            if uid >= 0 and owner != uid:
                continue
            # The final ')' delimits comm, which can itself contain parentheses.
            raw = (process / 'stat').read_text()
            start = raw[raw.rfind(')') + 2:].split()[19]
            name = clean((process / 'comm').read_text().strip())
            found = set()
            for fd in (process / 'fd').iterdir():
                try:
                    info = fd.stat()
                    key = (os.major(info.st_rdev), os.minor(info.st_rdev))
                    if stat.S_ISCHR(info.st_mode) and key in devices:
                        found.add(devices[key])
                except FileNotFoundError:
                    pass  # A descriptor closed during sampling.
            if found:
                try:
                    executable = clean(os.readlink(process / 'exe'))
                except OSError:
                    executable = 'unavailable'
                holders.append({'uid': owner, 'pid': int(process.name), 'start': start,
                                'name': name, 'executable': executable,
                                'devices': sorted(found),
                                'broker': name.startswith(('pipewire', 'v4l2-relay'))})
        except (FileNotFoundError, ProcessLookupError):
            pass  # Process exited during sampling.
        except PermissionError:
            unreadable.append(int(process.name))
        except (OSError, ValueError, IndexError):
            unreadable.append(int(process.name))
    virtual = set()
    for node in Path('/sys/class/video4linux').glob('*'):
        if '/devices/virtual/' in str(node.resolve()):
            virtual.add(node.name)
    for p in holders:
        # A virtual-camera producer alone does not imply a consuming application.
        p['infrastructure'] = p['name'].startswith('v4l2-relay') and set(p['devices']) <= virtual
    access = [p for p in holders if not p['infrastructure']]
    holders.sort(key=lambda p: p['pid'])
    return {'time': time.time(), 'devices': sorted(set(devices.values())),
            'holders': holders, 'unreadable': sorted(unreadable),
            'scope': ('All users, including system relay.' if uid < 0 else
                      'Current user only; root/system users are not inspected.'),
            'coverage': 'system' if uid < 0 else 'user',
            'state': 'access' if access else ('partial' if unreadable else
                     ('clear' if devices else 'absent'))}


def identity(holder):
    return holder['pid'], holder['start']


def changes(before, after):
    old = {identity(p): p for p in before.get('holders', []) if not p.get('infrastructure')}
    new = {identity(p): p for p in after['holders'] if not p.get('infrastructure')}
    return [('opened', p) for k, p in new.items() if k not in old] + [
        ('closed', p) for k, p in old.items() if k not in new and p['pid'] not in after.get('unreadable', [])
        and not (before.get('coverage') == 'system' and after.get('coverage') == 'user')]


def save(path, value, mode=0o600):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as f:
        os.chmod(tmp, mode)
        json.dump(value, f, ensure_ascii=False)
    tmp.replace(path)


def read_status(path):
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or time.time() - value['time'] > 8:
            raise ValueError('stale')
        return value
    except (OSError, ValueError, KeyError, TypeError):
        return {'state': 'unavailable', 'holders': [], 'unreadable': [], 'devices': []}


def label(value):
    state = value['state']
    control = value.get('control') or {}
    if control.get('mode') == 'blocked':
        return 'Cam BLOCKED' + (' + access' if state == 'access' else '')
    if control.get('mode') == 'failed':
        return 'Cam BLOCK ?'
    if state == 'access':
        return 'Cam ACCESS' + (' ?' if value.get('unreadable') or (value.get('trace') or {}).get('lost') or (value.get('trace') or {}).get('ui_lost') else '')
    if value.get('coverage') == 'user' and state == 'clear':
        return 'Cam — (user)'
    return {'clear': 'Cam —', 'partial': 'Cam ?', 'absent': 'No cam',
            'unavailable': 'Cam !'}.get(state, 'Cam !')


def details(value):
    rows = ['Camera access · ' + label(value),
            ('Scope: all processes, including system/root.' if value.get('coverage') == 'system'
             else 'Scope: your processes only; system/root activity is not visible.'),
            'Open handles indicate access, not proof of streaming or recording.']
    control = value.get('control')
    if control:
        rows.append('Built-in camera control: ' + control['mode'])
        if control.get('message'):
            rows.append(control['message'])
    if value['state'] == 'unavailable':
        rows.append('Monitor stopped or status stale; coverage unavailable.')
    elif not value['devices']:
        rows.append('No camera/media devices detected.')
    elif not value['holders']:
        rows.append('No camera handles observed in inspectable user processes.')
    for p in value['holders']:
        role = (' · relay producer (virtual output only)' if p.get('infrastructure') else
                (' · broker; downstream app may differ' if p['broker'] else ''))
        rows += [f"{p['name']} · PID {p['pid']} · UID {p.get('uid', '?')}{role}",
                 '    ' + p['executable'], '    /dev/' + ', /dev/'.join(p['devices'])]
    if value['unreadable']:
        rows.append('Uninspectable PIDs: ' + ', '.join(map(str, value['unreadable'])))
    trace = value.get('trace') or {}
    if trace.get('backend') == 'ebpf':
        rows.append('Kernel events: ' + ('active' if trace.get('ready') else 'unavailable'))
        if trace.get('error'):
            rows.append('Tracing error: ' + clean(trace['error']))
        if trace.get('lost') or trace.get('ui_lost'):
            rows.append('Warning: events were lost; history is incomplete.')
        rows.append('Current holders: event-triggered scans + 60-second reconciliation.')
        recent = [e for e in value.get('events', []) if not e.get('infrastructure') and e.get('known')][-8:]
        if recent:
            rows.append('Recent kernel events (including brief accesses):')
            for e in recent:
                rows.append(clean(e['time']) + ' · ' + clean(e['action']) + ' · ' + clean(e['name']) + ' · PID ' + str(e['pid']) + ' · ' + ', '.join(map(clean, e['devices'])))
    else:
        rows.append('Fallback sampling only; brief access can be missed.')
    rows.append('Esc closes.')
    return rows



def control_status(expected):
    if expected is None:
        return None
    try:
        def trusted(path):
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError('Untrusted control metadata')
            return json.loads(path.read_text())
        config = trusted(Path('/usr/local/libexec/camera-monitor/controller.json'))
        if config != expected or not re.fullmatch(r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]', config['address']):
            return {'mode': 'uninstalled', 'message': 'Install camera controls for the selected hardware profile.'}
        device = Path('/sys/bus/pci/devices') / config['address']
        if any((device / k).read_text().strip() != config[k] for k in ('vendor', 'device')):
            raise ValueError('Camera identity changed')
        marker = Path('/var/lib/camera-monitor-control/blocked.json')
        requested = marker.exists()
        if requested and trusted(marker).get('controller') != config:
            raise ValueError('Saved block belongs to different hardware')
        link = device / 'driver'
        bound = link.resolve().name if link.exists() else None
        override = (device / 'driver_override').read_text().strip()
        if requested:
            virtual_denied = True
            for node in Path('/sys/devices/virtual/video4linux').glob('video[0-9]*'):
                if (node / 'name').read_text().strip() == config['virtualCameraName']:
                    info = (Path('/dev') / node.name).lstat()
                    virtual_denied = virtual_denied and stat.S_ISCHR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0
            mode = 'blocked' if bound is None and override == 'camera-privacy-blocked' and virtual_denied else 'failed'
        else:
            mode = 'allowed' if bound == config['driver'] and override in ('', '(null)') else 'failed'
        return {'mode': mode, 'address': config['address'], 'driver': bound}
    except FileNotFoundError:
        return {'mode': 'uninstalled', 'message': 'Camera controls are not installed or configured hardware is absent.'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'mode': 'failed', 'message': 'Cannot verify the built-in camera block; inspect control state.'}


def observed(controller=None):
    path = Path('/run/camera-monitor/status.json')
    try:
        info = path.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('unsafe collector file')
        value = read_status(path)
        if value.get('coverage') == 'system' and (value['state'] != 'unavailable' or value.get('trace')):
            value['control'] = control_status(controller)
            return value
    except (OSError, ValueError):
        pass
    value = scan()
    value['control'] = control_status(controller)
    return value


class StatusWake:
    """Sleep on atomic status replacements; no camera device is opened."""
    def __init__(self):
        self.lib = ctypes.CDLL(None, use_errno=True)
        self.fd = self.lib.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), 'inotify_init1')
        self.watched = False

    def arm(self):
        if not self.watched:
            # Includes directory invalidation so a restarted collector can be
            # watched again after systemd recreates its runtime directory.
            self.watched = self.lib.inotify_add_watch(self.fd, b'/run/camera-monitor', 0x80 | 0x100 | 0x400 | 0x800) >= 0

    def wait(self):
        if select.select([self.fd], [], [], 3)[0]:
            os.read(self.fd, 65536)
            self.watched = False  # re-arm also handles IN_IGNORED/replacement

    def close(self):
        os.close(self.fd)


def journal_batch(value, cursor, existing):
    trace = value.get('trace') or {}
    stream = trace.get('stream')
    if not stream:
        return [], cursor, False
    same = cursor.get('stream') == stream
    previous = cursor.get('seq', 0) if same else 0
    records = value.get('events', [])
    gap = bool((cursor.get('stream') and not same) or (records and records[0]['seq'] > previous + 1))
    seen = {e.get('event_id') for e in existing}
    fresh = []
    for raw in records:
        if raw['seq'] <= previous:
            continue
        event = {**raw, 'event_id': stream + ':' + str(raw['seq'])}
        if event['event_id'] not in seen and event.get('known') and not event.get('infrastructure'):
            fresh.append(event)
    return fresh, {'stream': stream, 'seq': records[-1]['seq'] if records else previous}, gap


def notify_batch(cfg, events):
    if not events:
        return
    opened = [e for e in events if e['action'] in ('opened', 'observed')]
    chosen = opened or events
    body = '\n'.join(html.escape(f"{p['name']} (PID {p['pid']}) · " + ', '.join(p['devices'])) for p in chosen[:4])
    if len(chosen) > 4:
        body += f"\n…and {len(chosen) - 4} more; see Camera access."
    title = 'Camera handle opened' if opened else 'Camera handle released'
    try:
        subprocess.run([cfg['notify'], '--app-name=Camera monitor', '--icon=camera-web', '--expire-time=8000', title, body],
                       timeout=1, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass


def watch(cfg, status, history):
    before = {'holders': []}
    cursor_path = history.with_name('cursor.json')
    try:
        events = json.loads(history.read_text())
        events = events[-200:] if isinstance(events, list) else []
    except (OSError, ValueError):
        events = []
    try:
        cursor = json.loads(cursor_path.read_text())
    except (OSError, ValueError):
        cursor = {}
    wake = StatusWake()
    ui_lost = False
    try:
        while True:
            wake.arm()
            value = observed(cfg.get('controller'))
            if value.get('trace'):
                batch, next_cursor, gap = journal_batch(value, cursor, events)
                ui_lost = ui_lost or gap
                value['trace']['ui_lost'] = ui_lost
                if ui_lost and value['state'] == 'clear':
                    value['state'] = 'partial'
            else:
                batch = [{'time': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'action': action, 'source': 'sample', **p}
                         for action, p in changes(before, value)]
                next_cursor = cursor
            save(status, value)
            if batch:
                events = (events + batch)[-200:]
                save(history, events)
                notify_batch(cfg, batch)
            if next_cursor != cursor:
                save(cursor_path, next_cursor)
                cursor = next_cursor
            before = {**value, 'holders': value['holders'] + [p for p in before.get('holders', []) if p['pid'] in value['unreadable']]}
            wake.wait()
    finally:
        wake.close()


def choose(cfg, title, rows):
    result = subprocess.run([cfg['rofi'], '-dmenu', '-i', '-no-custom', '-format', 'i', '-p', title,
                             '-mesg', 'Built-in camera controls · process details below',
                             '-theme-str', 'window { width: 90%; } entry { placeholder: "Filter camera details…"; }'],
                            input='\n'.join(rows), text=True, capture_output=True, check=False)
    try:
        return int(result.stdout.strip()) if result.returncode == 0 else None
    except ValueError:
        return None


def operate(cfg, action):
    if cfg.get('controller') is None or (control_status(cfg['controller']) or {}).get('mode') == 'uninstalled':
        raise SystemExit('Install the Home Manager camera controls for this hardware first.')
    try:
        result = subprocess.run(['/usr/bin/sudo', '-n', '/usr/bin/python3', '-I',
                                 '/usr/local/libexec/camera-monitor/control.py', action],
                                capture_output=True, text=True, timeout=45)
        ok = result.returncode == 0
        expected = 'blocked' if action == 'block' else 'allowed'
        ok = ok and (control_status(cfg['controller']) or {}).get('mode') == expected
        message = ('Built-in camera blocked' if action == 'block' else 'Built-in camera allowed') if ok else 'Camera control failed; block state is unverified'
    except subprocess.TimeoutExpired:
        ok = False
        message = 'Camera control timed out; inspect block state before relying on it'
    subprocess.run([cfg['notify'], '--app-name=Camera monitor', '--icon=camera-web',
                    message], check=False)
    if not ok:
        raise SystemExit(message)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('action', choices=['watch', 'status', 'json', 'details', 'menu', 'probe', 'block', 'unblock'])
    args = parser.parse_args()
    if not args.config:
        parser.error('--config is required')
    cfg = json.loads(args.config.read_text())
    state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'camera-monitor'
    status = state / 'status.json'
    history = state / 'events.json'
    if args.action == 'watch':
        watch(cfg, status, history)
        return
    value = observed(cfg.get('controller')) if args.action == 'probe' else read_status(status)
    if args.action in ('block', 'unblock'):
        operate(cfg, args.action)
    elif args.action in ('json', 'probe'):
        print(json.dumps(value, ensure_ascii=False))
    elif args.action == 'status':
        # Only fixed strings go to Polybar, never process-controlled text.
        print(label(value))
    elif args.action == 'details':
        print('\n'.join(details(value)))
    elif args.action == 'menu':
        action = 'unblock' if (value.get('control') or {}).get('mode') == 'blocked' else 'block'
        title = 'Allow built-in camera' if action == 'unblock' else 'Block built-in camera'
        installed = cfg.get('controller') is not None and (value.get('control') or {}).get('mode') in ('allowed', 'blocked', 'failed')
        rows = ([title + '…'] if installed else []) + details(value)
        if choose(cfg, 'Camera access', rows) == 0 and installed:
            if choose(cfg, title + '?', ['Cancel', title]) == 1:
                operate(cfg, action)



if __name__ == '__main__':
    main()
