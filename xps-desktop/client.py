"""Open the existing XPS desktop through an SSH-owned local VNC tunnel."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shlex
import socket
import stat
import subprocess
import sys
import time


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = path.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise RuntimeError('The launcher cache directory must be private and owned by you')
    return path


def ssh_base(cfg):
    return [cfg['ssh'], '-p', str(cfg['sshPort']), '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=8', '-o', 'ForwardAgent=no', '-o', 'ForwardX11=no',
            '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3']


def tunnel_check(cfg, control):
    p = subprocess.run(ssh_base(cfg) + ['-S', str(control), '-O', 'check', cfg['sshHost']],
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=3)
    return p.returncode == 0


def local_port_free(port):
    with socket.socket() as s:
        # Match SSH's listener behavior: recently closed connections can leave
        # TIME_WAIT sockets even though no process is listening on this port.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def banner_ready(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1) as s:
            return s.recv(12).startswith(b'RFB 003.')
    except OSError:
        return False


def established_clients(pid, port):
    p = subprocess.run(['/usr/sbin/lsof', '-nP', '-a', '-p', str(pid),
                        '-iTCP:' + str(port), '-sTCP:ESTABLISHED', '-Ff'],
                       capture_output=True, timeout=5)
    return any(line.startswith(b'f') for line in p.stdout.splitlines())


def worker(cfg, directory):
    os.umask(0o077)
    with (directory / 'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(3)
        control = directory / 'ssh.sock'
        state = directory / 'ready.json'
        error = directory / 'error.txt'
        state.unlink(missing_ok=True)
        error.unlink(missing_ok=True)
        tunnel = None
        try:
            if not local_port_free(cfg['localPort']):
                raise RuntimeError('Local port ' + str(cfg['localPort']) + ' is already in use; refusing to connect to an unrelated listener')
            cmd = ssh_base(cfg) + ['-o', 'ControlMaster=no', '-o', 'ControlPath=none',
                                  cfg['sshHost'], 'exec ' + shlex.quote(cfg['remoteControl']) + ' start']
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=25)
            if r.returncode:
                raise RuntimeError('SSH desktop startup failed: ' + (r.stderr.strip() or r.stdout.strip())[-1500:])
            remote = json.loads(r.stdout)
            if not remote.get('ready') or remote.get('socket') != cfg['remoteSocket']:
                raise RuntimeError('The remote service reported an unexpected socket')
            control.unlink(missing_ok=True)
            args = ssh_base(cfg) + ['-M', '-S', str(control), '-o', 'ControlMaster=yes',
                                    '-o', 'ControlPersist=no', '-o', 'ExitOnForwardFailure=yes',
                                    '-N', '-L', '127.0.0.1:' + str(cfg['localPort']) + ':' + cfg['remoteSocket'],
                                    cfg['sshHost']]
            with (directory / 'ssh.log').open('w') as log:
                tunnel = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                          stderr=log, close_fds=True)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if tunnel.poll() is not None:
                        raise RuntimeError('The SSH tunnel stopped; see ~/Library/Caches/xps-desktop/ssh.log')
                    if control.exists() and tunnel_check(cfg, control) and banner_ready(cfg['localPort']):
                        break
                    time.sleep(.15)
                else:
                    raise RuntimeError('The SSH tunnel did not become ready')
                ready = state.with_suffix('.new')
                ready.write_text(json.dumps({'pid': os.getpid(), 'ssh_pid': tunnel.pid,
                                             'host': cfg['sshHost'], 'port': cfg['localPort']}))
                os.replace(ready, state)
                seen = False
                last = time.monotonic()
                while tunnel.poll() is None:
                    active = established_clients(tunnel.pid, cfg['localPort'])
                    if active:
                        seen = True
                        last = time.monotonic()
                    elif time.monotonic() - last > (30 if seen else 300):
                        break
                    time.sleep(2)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
            error.write_text(str(e))
            raise SystemExit(1)
        finally:
            state.unlink(missing_ok=True)
            if tunnel is not None and tunnel.poll() is None:
                tunnel.terminate()
                try:
                    tunnel.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    tunnel.kill()
                    tunnel.wait()
            control.unlink(missing_ok=True)
            if tunnel is not None:
                # Restore the panel promptly, while leaving other viewers connected.
                try:
                    subprocess.run(ssh_base(cfg) + ['-o', 'ControlMaster=no', '-o', 'ControlPath=none',
                                                   cfg['sshHost'], 'exec ' + shlex.quote(cfg['remoteControl']) + ' stop-if-unused'],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=15)
                except (OSError, subprocess.SubprocessError):
                    pass  # The server's idle timeout is the offline fallback.


def launch(cfg, directory):
    control = directory / 'ssh.sock'
    state = directory / 'ready.json'
    if state.exists() and tunnel_check(cfg, control) and banner_ready(cfg['localPort']):
        ready = json.loads(state.read_text())
        if ready.get('host') != cfg['sshHost']:
            raise RuntimeError('A desktop connection to a different host is already open; disconnect it first')
    else:
        # The worker's flock serializes concurrent Finder/CLI launches.
        with (directory / 'worker.log').open('a') as log:
            p = subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()),
                                  sys.argv[1], '--worker', '--host', cfg['sshHost']],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True, close_fds=True)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if state.exists() and tunnel_check(cfg, control) and banner_ready(cfg['localPort']):
                break
            if p.poll() is not None and p.returncode != 3:
                error = directory / 'error.txt'
                raise RuntimeError(error.read_text() if error.exists() else 'The desktop tunnel could not start')
            time.sleep(.2)
        else:
            raise RuntimeError('Timed out preparing the desktop tunnel')
    if json.loads(state.read_text()).get('host') != cfg['sshHost']:
        raise RuntimeError('A desktop connection to a different host is already open; disconnect it first')
    subprocess.run([cfg['open'], '-a', cfg['viewer'], 'vnc://127.0.0.1:' + str(cfg['localPort'])],
                   check=True, timeout=10)
    print('Opened XPS Desktop. Close its viewer window to disconnect.')


def main():
    cfg = json.loads(Path(sys.argv[1]).read_text())
    parser = argparse.ArgumentParser(description='Open the existing XPS desktop over SSH')
    parser.add_argument('--host', help='SSH host override, e.g. the personal Tailscale address')
    parser.add_argument('--disconnect', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--gui', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(sys.argv[2:])
    if args.host:
        if args.host.startswith('-') or any(c.isspace() for c in args.host):
            raise RuntimeError('Invalid SSH host')
        cfg['sshHost'] = args.host
    directory = private_directory(Path.home() / 'Library/Caches/xps-desktop')
    os.umask(0o077)
    if args.worker:
        worker(cfg, directory)
    elif args.disconnect:
        r = subprocess.run(ssh_base(cfg) + ['-S', str(directory / 'ssh.sock'), '-O', 'exit', cfg['sshHost']],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
        print('Desktop tunnel closed.' if r.returncode == 0 else 'No active desktop tunnel.')
    elif args.status:
        print('Connected' if tunnel_check(cfg, directory / 'ssh.sock') else 'Disconnected')
    else:
        try:
            launch(cfg, directory)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
            if args.gui:
                # Open a text report without scripting or controlling another app.
                report = directory / 'connection-error.txt'
                report.write_text('XPS Desktop could not connect.\n\n' + str(e) + '\n')
                subprocess.run([cfg['open'], '-t', str(report)], check=False)
            raise


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
        print('XPS Desktop: ' + str(e), file=sys.stderr)
        raise SystemExit(1)
