"""Copy for the initiating Linux tmux client, using its own SSH/display environment."""
from pathlib import Path
import os
import shutil
import subprocess
import sys


def main():
    # Use the running server's binary and explicit socket, including after upgrades.
    server, socket, client_pid, client, pane = sys.argv[1:6]
    flags = set(sys.argv[6:])
    assert flags <= {'--buffer', '--append', '--no-newline', '--paste', '--path'}
    command = ['/proc/' + str(int(server)) + '/exe', '-S', socket]

    def tmux(*args, data=None, check=True):
        return subprocess.run(command + list(args), input=data, capture_output=True,
                              check=check).stdout

    clients = tmux('list-clients', '-F', '#{client_pid}\t#{client_name}').decode().splitlines()
    assert str(int(client_pid)) + '\t' + client in clients, 'Originating tmux client has detached'
    # Do not use the pane/session environment: it is shared by local and SSH clients.
    entries = Path('/proc', str(int(client_pid)), 'environ').read_bytes().split(b'\0')
    env = {k.decode(): v.decode(errors='surrogateescape') for e in entries
           if b'=' in e for k, v in [e.split(b'=', 1)]}
    remote = any(env.get(k) for k in ['SSH_CONNECTION', 'SSH_CLIENT', 'SSH_TTY'])
    if '--path' in flags:
        data = tmux('display-message', '-p', '-t', pane, '#{pane_current_path}').rstrip(b'\n')
    elif '--buffer' in flags:
        data = tmux('save-buffer', '-')
    else:
        data = sys.stdin.buffer.read()
    if '--no-newline' in flags:
        data = data.replace(b'\n', b'')
    if '--append' in flags:
        data = tmux('save-buffer', '-', check=False) + data
    if not data:
        return
    if remote:
        # Native -w targets this terminal only; ordinary copy commands broadcast.
        tmux('load-buffer', '-w', '-t', client, '-', data=data)
        message = 'Clipboard sent to remote terminal'
    else:
        # VTE/Guake on Ubuntu 22.04 does not implement OSC 52. Keep a tmux buffer
        # and use the physical client's X11 display, never the last SSH session's.
        tmux('load-buffer', '-', data=data)
        if not env.get('DISPLAY'):
            raise RuntimeError('No local display; selection is saved in the tmux buffer')
        display_env = dict(os.environ)
        for key in ['DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR']:
            display_env.pop(key, None)
            if env.get(key):
                display_env[key] = env[key]
        xclip = shutil.which('xclip')
        assert xclip, 'xclip is unavailable; selection is saved in the tmux buffer'
        # xclip forks to own the X11 selection. Do not leave captured output pipes
        # open in that child; otherwise tmux's copy job can appear to hang.
        subprocess.run([xclip, '-selection', 'clipboard'], input=data, env=display_env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=5)
        message = 'Copied to xps desktop clipboard'
    if '--paste' in flags:
        tmux('paste-buffer', '-t', pane)
    tmux('display-message', '-d', '1000', '-c', client, message, check=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Selection bytes and environment values must never appear in diagnostics.
        try:
            server, socket, _pid, client, _pane = sys.argv[1:6]
            subprocess.run(['/proc/' + str(int(server)) + '/exe', '-S', socket,
                            'display-message', '-c', client,
                            'Clipboard copy failed; use prefix+w to retry'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        print('Clipboard copy failed (' + type(exc).__name__ + ')', file=sys.stderr)
        sys.exit(1)
