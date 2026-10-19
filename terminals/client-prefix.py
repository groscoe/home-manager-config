"""Cache SSH origin per attached tmux client, never from a shared pane/session."""
from pathlib import Path
import fcntl
import os
import stat
import subprocess
import sys


def main():
    assert len(sys.argv) in (3, 4)
    server_pid = int(sys.argv[1])
    socket = Path(sys.argv[2])
    initialize = sys.argv[3:] == ['--initialize']
    assert len(sys.argv) == 3 or initialize
    assert socket.is_absolute()
    # Use the running server's binary, including after a profile upgrade.
    command = ['/proc/' + str(server_pid) + '/exe', '-S', str(socket)]

    def tmux(*args):
        return subprocess.run(command + list(args), capture_output=True, text=True, check=True).stdout.strip()

    lock = socket.with_name(socket.name + '.prefix.lock')
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as stream:
        s = os.fstat(stream.fileno())
        assert stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid()
        # Simultaneous attach/detach hooks must publish a fresh complete snapshot.
        fcntl.flock(stream, fcntl.LOCK_EX)
        remote = []
        for value in tmux('list-clients', '-F', '#{client_pid}').splitlines():
            pid = int(value)
            try:
                entries = (Path('/proc') / str(pid) / 'environ').read_bytes().split(b'\0')
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
            if any(entry.startswith((b'SSH_CONNECTION=', b'SSH_CLIENT=', b'SSH_TTY='))
                   and entry.split(b'=', 1)[1] for entry in entries):
                remote.append(pid)
        value = '|' + '|'.join(str(pid) for pid in sorted(remote)) + '|' if remote else ''
        tmux('set-option', '-sq', '@xps-remote-clients', value)
        if initialize:
            # Migrate old per-session overrides; future sessions inherit prefix=None.
            p = subprocess.run(command + ['list-sessions', '-F', '#{session_id}'], capture_output=True, text=True)
            if p.returncode == 0:
                for session in p.stdout.splitlines():
                    tmux('set-option', '-qu', '-t', session, 'prefix')
                    tmux('set-option', '-qu', '-t', session, 'prefix2')


if __name__ == '__main__':
    try:
        main()
    except (FileNotFoundError, ProcessLookupError, subprocess.CalledProcessError):
        # A detach hook may outlive its server. Do not print client environments.
        pass
