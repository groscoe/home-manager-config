#!/usr/bin/env python3
"""Rofi front end to KDE Connect; no shell interpolation or saved pairing data."""
import re
from pathlib import Path
import subprocess


def run(*args, check=True):
    result = subprocess.run(args, text=True, capture_output=True, timeout=20)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f'{args[0]} failed')
    return result.stdout.strip()


def choose(prompt, rows):
    if not rows:
        return None
    result = subprocess.run(['rofi', '-dmenu', '-i', '-no-custom', '-format', 'i', '-p', prompt],
                            input='\n'.join(rows), text=True, capture_output=True)
    if result.returncode:
        return None
    try:
        value = int(result.stdout.strip())
        return value if 0 <= value < len(rows) else None
    except ValueError:
        return None


def ask(prompt):
    result = subprocess.run(['rofi', '-dmenu', '-p', prompt], input='', text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else ''


def devices():
    paired = set(run('kdeconnect-cli', '--list-available', '--id-only').splitlines())
    result = []
    for line in run('kdeconnect-cli', '--list-devices', '--id-name-only').splitlines():
        # The CLI emits "id name"; split once so spaces in device names survive.
        if re.fullmatch(r'\d+ devices? found', line):
            continue
        bits = line.split(' ', 1)
        if len(bits) == 2:
            result.append((bits[0], bits[1], bits[0] in paired))
    return result


def notify(message):
    run('notify-send', 'KDE Connect', message, check=False)


def device_menu(device):
    ident, name, available = device
    actions = [('Ping device', '--ping'), ('Ring / find device', '--ring'),
               ('Send clipboard', '--send-clipboard'), ('Share file…', 'file'),
               ('Share URL or text…', 'text'), ('Request pairing', '--pair'),
               ('Open KDE Connect settings', 'settings'), ('Back', 'back')]
    if not available:
        actions = [a for a in actions if a[1] in ('--pair', 'settings', 'back')]
    choice = choose(name + ('' if available else ' · not connected'), [a[0] for a in actions])
    if choice is None or actions[choice][1] == 'back':
        return
    action = actions[choice][1]
    if action == 'settings':
        subprocess.Popen(['kdeconnect-app'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    args = ['kdeconnect-cli', '--device', ident]
    if action == 'file':
        value = ask('Full file path')
        if not value:
            return
        path = Path(value).expanduser()
        if not path.is_file():
            raise RuntimeError('Choose an existing regular file.')
        args += ['--share', str(path.resolve())]
    elif action == 'text':
        value = ask('URL or text to share')
        if not value:
            return
        args += ['--share' if value.startswith(('https://', 'http://')) else '--share-text', value]
    else:
        args += [action]
    run(*args)
    notify('Request sent to ' + name)


def main():
    run('systemctl', '--user', 'start', 'kdeconnect.service')
    while True:
        known = devices()
        rows = [f'{name}  ·  {"connected" if online else "not connected"}' for _, name, online in known]
        extras = ['Refresh devices', 'Open KDE Connect settings', 'Restart KDE Connect', 'Close']
        choice = choose('KDE Connect', rows + extras)
        if choice is None or choice == len(known) + 3:
            return
        try:
            if choice < len(known):
                device_menu(known[choice])
            elif choice == len(known):
                run('kdeconnect-cli', '--refresh')
            elif choice == len(known) + 1:
                subprocess.Popen(['kdeconnect-app'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            else:
                run('systemctl', '--user', 'restart', 'kdeconnect.service')
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            notify(str(error))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        notify(str(error))
        raise SystemExit(1)
