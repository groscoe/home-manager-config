"""Switch the boot-time headless daemon to X only when a session becomes available."""
from pathlib import Path
import subprocess
import sys


def start(systemctl):
    subprocess.run([systemctl, '--user', 'start', 'kdeconnect.service'], check=True)
    pid = subprocess.check_output([systemctl, '--user', 'show', 'kdeconnect.service', '-p', 'MainPID', '--value'], text=True).strip()
    if pid.isdecimal() and int(pid):
        try:
            environment = Path('/proc', pid, 'environ').read_bytes().split(b'\0')
        except FileNotFoundError:
            return  # systemd supervises a daemon that exits during this check
        if b'QT_QPA_PLATFORM=offscreen' in environment:
            subprocess.run([systemctl, '--user', 'restart', 'kdeconnect.service'], check=True)


if __name__ == '__main__':
    start(sys.argv[1])
