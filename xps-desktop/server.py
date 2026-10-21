"""Share an existing local i3 session; never start another X server."""
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time


def private_password(path):
    p = Path(path)
    s = p.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise RuntimeError('The VNC password file must be owned by you with mode 0600')
    if s.st_size not in (8, 16):
        raise RuntimeError('The VNC password file is invalid; run xps-desktop-control password')
    return p


def i3_environment(proc=Path('/proc')):
    found = []
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            if p.stat().st_uid != os.getuid() or (p / 'comm').read_text().strip() != 'i3':
                continue
            env = {}
            for entry in (p / 'environ').read_bytes().split(b'\0'):
                key, sep, value = entry.partition(b'=')
                if sep and key in (b'DISPLAY', b'XAUTHORITY'):
                    env[key.decode()] = value.decode()
            if env.get('DISPLAY', '').startswith(':'):
                env.setdefault('XAUTHORITY', str(Path.home() / '.Xauthority'))
                found.append(env)
        except (OSError, UnicodeError):
            continue
    if len(found) != 1:
        raise RuntimeError('Log into one local i3 session on xps first; no unique running session was found')
    auth = Path(found[0]['XAUTHORITY'])
    s = auth.stat()
    if s.st_uid != os.getuid() or not stat.S_ISREG(s.st_mode) or not os.access(auth, os.R_OK):
        raise RuntimeError('The running i3 session has no accessible user-owned Xauthority file')
    return found[0]


def runtime_directory():
    p = Path('/run/user') / str(os.getuid()) / 'xps-desktop'
    p.mkdir(mode=0o700, exist_ok=True)
    s = p.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise RuntimeError('The VNC runtime directory must be private and owned by you')
    return p


def wait_socket(path, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            s = path.lstat()
            if not stat.S_ISSOCK(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
                raise RuntimeError('The VNC socket has unexpected ownership or permissions')
            with socket.socket(socket.AF_UNIX) as c:
                c.settimeout(1)
                c.connect(str(path))
                if c.recv(12).startswith(b'RFB 003.'):
                    return
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
            pass
        time.sleep(.15)
    raise RuntimeError('The desktop service did not become ready; inspect systemctl --user status xps-desktop')


def active_vnc_clients(pid, socket_path, proc=Path('/proc')):
    p = proc / str(pid)
    if (p / 'comm').read_text().strip() != 'x0vncserver':
        raise RuntimeError('Unexpected desktop service process')
    inodes = set()
    for f in (p / 'fd').iterdir():
        try:
            target = os.readlink(f)
            if target.startswith('socket:['):
                inodes.add(target[8:-1])
        except FileNotFoundError:
            continue
    clients = 0
    for line in (p / 'net/unix').read_text().splitlines()[1:]:
        fields = line.split(maxsplit=7)
        if len(fields) == 8 and fields[6] in inodes and fields[4:6] == ['0001', '03'] and fields[7] == str(socket_path):
            clients += 1
    return clients


def display_power(cfg, env, *args):
    return subprocess.run([cfg['xset'], *args], env=env, check=True,
                          capture_output=True, text=True, timeout=5).stdout


def backlight_device(cfg, base=Path('/sys/class/backlight')):
    name = cfg['backlightDevice']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise RuntimeError('Invalid built-in backlight name')
    return base / name


def set_backlight(cfg, value, base=Path('/sys/class/backlight')):
    device = backlight_device(cfg, base)
    if not isinstance(value, int) or not 0 <= value <= int((device / 'max_brightness').read_text()):
        raise RuntimeError('Invalid requested backlight brightness')
    (device / 'brightness').write_text(str(value) + '\n')
    if int((device / 'brightness').read_text()) != value:
        raise RuntimeError('The backlight did not accept the requested brightness')


def prepare_backlight(cfg, state_file, base=Path('/sys/class/backlight')):
    device = backlight_device(cfg, base)
    if state_file.exists():
        return  # Retain the original brightness and any deliberate manual override.
    maximum = int((device / 'max_brightness').read_text())
    previous = int((device / 'brightness').read_text())
    if not 0 <= previous <= maximum or maximum <= 0:
        raise RuntimeError('Invalid backlight brightness range')
    if not os.access(device / 'brightness', os.W_OK):
        raise RuntimeError('Run install-xps-backlight-access once on xps to enable hardware backlight control')
    state = {'device': str(device.resolve()), 'maximum': maximum, 'previous': previous}
    state_file.write_text(json.dumps(state))
    state_file.chmod(0o600)
    # Save recovery first: ExecStopPost can restore this even if X11 startup fails.
    set_backlight(cfg, 0, base)


def restore_backlight(cfg, state_file, base=Path('/sys/class/backlight'), brightness_before_cleanup=None):
    if not state_file.exists():
        return
    s = state_file.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise RuntimeError('Unexpected backlight recovery state file')
    state = json.loads(state_file.read_text())
    device = backlight_device(cfg, base)
    maximum = int((device / 'max_brightness').read_text())
    if str(device.resolve()) != state['device'] or maximum != state['maximum']:
        raise RuntimeError('The backlight device changed; refusing to apply saved brightness')
    if not isinstance(state['previous'], int) or not 0 <= state['previous'] <= maximum:
        raise RuntimeError('Invalid saved backlight brightness')
    # DPMS changes can reset the hardware level. Decide whether the user made a
    # manual adjustment from the value captured before any display-power cleanup.
    current = int((device / 'brightness').read_text()) if brightness_before_cleanup is None else brightness_before_cleanup
    set_backlight(cfg, state['previous'] if current == 0 else current, base)
    state_file.unlink()


def compositor_bus(cfg, env, destination, method, *args):
    return subprocess.run([cfg['dbusSend'], '--session', '--print-reply', '--type=method_call',
                           '--dest=' + destination, '/com/github/chjj/compton' if
                           destination.startswith(':') else '/org/freedesktop/DBus',
                           method, *args], env=env, check=True, capture_output=True,
                          text=True, timeout=3).stdout


def compositor_owner(cfg, env):
    name = 'com.github.chjj.compton.' + re.sub(r'[^A-Za-z0-9]', '_', env['DISPLAY'])
    try:
        output = compositor_bus(cfg, env, 'org.freedesktop.DBus',
                                'org.freedesktop.DBus.GetNameOwner', 'string:' + name)
    except subprocess.CalledProcessError as e:
        if 'org.freedesktop.DBus.Error.NameHasNoOwner' in e.stderr:
            return None  # Picom is not running; do not start it merely for VNC.
        raise
    match = re.search(r'\bstring "(:[0-9]+\.[0-9]+)"', output)
    if not match:
        raise RuntimeError('Unexpected Picom bus owner')
    return match[1]


def compositor_mode(cfg, env, owner, mode=None):
    method = 'com.github.chjj.compton.opts_' + ('get' if mode is None else 'set')
    args = ['string:redirected_force'] + ([] if mode is None else ['uint32:' + str(mode)])
    output = compositor_bus(cfg, env, owner, method, *args)
    if mode is not None:
        if not re.search(r'\bboolean true\b', output):
            raise RuntimeError('Picom refused the compositor toggle')
        return
    match = re.search(r'\buint32 ([012])\b', output)
    if not match:
        raise RuntimeError('Unexpected Picom redirection mode')
    return int(match[1])


def prepare_compositor(cfg, env, state_file):
    env = dict(env, DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/' + str(os.getuid()) + '/bus')
    owner = compositor_owner(cfg, env)
    if not owner:
        return
    if state_file.exists():
        prior = json.loads(state_file.read_text())
        if prior['owner'] == owner:
            return  # Preserve the original snapshot and any deliberate manual override.
    state = {'owner': owner, 'previous': compositor_mode(cfg, env, owner),
             'environment': {k: env[k] for k in ('DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS')}}
    state_file.write_text(json.dumps(state))
    state_file.chmod(0o600)
    # Picom v9: OFF=0, ON=1, UNSET=2. Unredirect while retaining the daemon.
    compositor_mode(cfg, env, owner, 0)


def restore_compositor(cfg, state_file):
    if not state_file.exists():
        return
    s = state_file.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise RuntimeError('Unexpected compositor recovery state file')
    state = json.loads(state_file.read_text())
    if state['previous'] not in (0, 1, 2):
        raise RuntimeError('Invalid saved compositor mode')
    env = dict(os.environ, **state['environment'])
    # Leave a restarted compositor or a manual mode change alone.
    if compositor_owner(cfg, env) == state['owner'] and compositor_mode(cfg, env, state['owner']) == 0:
        compositor_mode(cfg, env, state['owner'], state['previous'])
    state_file.unlink()


def prepare_display(cfg, env, state_file):
    """Keep the graphics pipeline awake; X11 idle locking is left intact."""
    status = display_power(cfg, env, 'q')
    enabled = re.search(r'DPMS is (Enabled|Disabled)', status)
    monitor = re.search(r'Monitor is (On|Standby|Suspend|Off)', status)
    if not enabled or (enabled[1] == 'Enabled' and not monitor):
        raise RuntimeError('Cannot safely preserve the existing display power state')
    state = {'environment': {k: env[k] for k in ('DISPLAY', 'XAUTHORITY')},
             'enabled': enabled[1] == 'Enabled', 'monitor': monitor[1] if monitor else 'On', 'prepared': False}
    state_file.write_text(json.dumps(state))
    state_file.chmod(0o600)
    gamma = state_file.with_name('panel-gamma.bin')
    subprocess.run([cfg['panelGamma'], 'save', str(gamma)], env=env, check=True, timeout=5)
    # DPMS-off stalls graphical updates on this laptop even when VNC is active.
    if state['enabled']:
        display_power(cfg, env, 'dpms', 'force', 'on')
    display_power(cfg, env, '-dpms')
    subprocess.run([cfg['panelGamma'], 'blank', str(gamma)], env=env, check=True, timeout=5)
    state['prepared'] = True
    state_file.write_text(json.dumps(state))


def restore_display(cfg, state_file):
    if not state_file.exists():
        return
    s = state_file.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise RuntimeError('Unexpected display recovery state file')
    state = json.loads(state_file.read_text())
    env = os.environ.copy()
    env.update(state['environment'])
    current = display_power(cfg, env, 'q')
    # A manual change to DPMS during sharing takes precedence over our old state.
    if not state['prepared'] or 'DPMS is Disabled' in current:
        display_power(cfg, env, '+dpms' if state['enabled'] else '-dpms')
        if state['enabled']:
            level = state['monitor'].lower()
            if level not in ('on', 'standby', 'suspend', 'off'):
                raise RuntimeError('Invalid saved monitor state')
            display_power(cfg, env, 'dpms', 'force', level)
    gamma = state_file.with_name('panel-gamma.bin')
    if gamma.exists():
        subprocess.run([cfg['panelGamma'], 'restore', str(gamma)], env=env, check=True, timeout=5)
        gamma.unlink()
    state_file.unlink()


def main():
    cfg = json.loads(Path(sys.argv[1]).read_text())
    action = sys.argv[2] if len(sys.argv) > 2 else 'status'
    if action == 'restore-display':
        directory = runtime_directory()
        brightness_before = None
        try:
            if (directory / 'backlight-state.json').exists():
                brightness_before = int((backlight_device(cfg) / 'brightness').read_text())
        finally:
            try:
                try:
                    restore_display(cfg, directory / 'display-state.json')
                finally:
                    restore_compositor(cfg, directory / 'compositor-state.json')
            finally:
                restore_backlight(cfg, directory / 'backlight-state.json', brightness_before_cleanup=brightness_before)
        return
    if action == 'refresh-display':
        directory = runtime_directory()
        if (directory / 'display-state.json').exists():
            env = os.environ.copy()
            env.update(i3_environment())
            prepare_backlight(cfg, directory / 'backlight-state.json')
            display_power(cfg, env, '+dpms')
            display_power(cfg, env, 'dpms', 'force', 'on')
            display_power(cfg, env, '-dpms')
            # HiDPI activation can wake the display and reset its cached PWM.
            set_backlight(cfg, 0)
            subprocess.run([cfg['panelGamma'], 'blank', str(directory / 'panel-gamma.bin')],
                           env=env, check=True, timeout=5)
            prepare_compositor(cfg, env, directory / 'compositor-state.json')
        return
    if action == 'password':
        p = Path(cfg['passwordFile'])
        p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if p.parent.stat().st_mode & 0o077:
            raise RuntimeError('The password directory must be private (mode 0700)')
        os.execv(cfg['vncpasswd'], [cfg['vncpasswd'], str(p)])
    if action == 'serve':
        private_password(cfg['passwordFile'])
        env = os.environ.copy()
        env.update(i3_environment())
        path = runtime_directory() / 'desktop.sock'
        if path.exists():
            s = path.lstat()
            if not stat.S_ISSOCK(s.st_mode) or s.st_uid != os.getuid():
                raise RuntimeError('Refusing to replace an unexpected runtime file')
            path.unlink()
        args = [cfg['vnc'], '-display=' + env['DISPLAY'], '-rfbport=-1',
                '-rfbunixpath=' + str(path), '-rfbunixmode=0600',
                '-SecurityTypes=VncAuth', '-PasswordFile=' + cfg['passwordFile'],
                '-AlwaysShared=1', '-DisconnectClients=0', '-AcceptSetDesktopSize=0',
                # Screen Sharing sends Command as Alt and Option as Meta.
                '-RemapKeys=0xffe9->0xffeb,0xffea->0xffec,0xffe7->0xffe9,0xffe8->0xffea',
                '-FrameRate=30', '-CompareFB=1', '-MaxDisconnectionTime=300',
                '-SetPrimary=0', '-SendPrimary=0']
        prepare_backlight(cfg, path.parent / 'backlight-state.json')
        prepare_display(cfg, env, path.parent / 'display-state.json')
        # The Intel driver can restore its previous PWM level on DPMS wake.
        set_backlight(cfg, 0)
        prepare_compositor(cfg, env, path.parent / 'compositor-state.json')
        os.execve(cfg['vnc'], args, env)
    if action == 'start':
        private_password(cfg['passwordFile'])
        env = i3_environment()
        subprocess.run([cfg['systemctl'], '--user', 'reset-failed', 'xps-desktop.service'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([cfg['systemctl'], '--user', 'start', 'xps-desktop.service'], check=True, timeout=15)
        path = runtime_directory() / 'desktop.sock'
        wait_socket(path)
        print(json.dumps({'ready': True, 'socket': str(path), 'display': env['DISPLAY']}))
    elif action == 'stop-if-unused':
        r = subprocess.run([cfg['systemctl'], '--user', 'show', 'xps-desktop.service',
                            '-p', 'MainPID', '--value'], capture_output=True, text=True, check=True, timeout=5)
        pid = int(r.stdout.strip())
        if pid and active_vnc_clients(pid, runtime_directory() / 'desktop.sock') == 0:
            subprocess.run([cfg['systemctl'], '--user', 'stop', 'xps-desktop.service'], check=True, timeout=15)
    elif action in ('status', 'stop'):
        os.execv(cfg['systemctl'], [cfg['systemctl'], '--user', action, 'xps-desktop.service'])
    else:
        raise RuntimeError('Use start, stop, status or password')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        print('XPS Desktop: ' + str(e), file=sys.stderr)
        raise SystemExit(1)
