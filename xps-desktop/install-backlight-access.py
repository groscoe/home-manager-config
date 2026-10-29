"""One-time permission for this user's built-in LCD brightness attribute only."""
import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import tempfile


RULE_PATH = Path('/etc/udev/rules.d/99-xps-desktop-backlight.rules')
def device_path(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
        raise RuntimeError('Invalid backlight device name')
    return Path('/sys/class/backlight') / name / 'brightness'


def rule_for(group, device):
    device_path(device)
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', group):
        raise RuntimeError('Unsupported private group name')
    return ('# XPS Desktop: this private group may change only LCD brightness.\n'
            'ACTION=="add", SUBSYSTEM=="backlight", KERNEL=="' + device + '", '
            'RUN+="/usr/bin/chgrp ' + group + ' /sys%p/brightness", '
            'RUN+="/usr/bin/chmod g+w /sys%p/brightness"\n')


def check_rule(path, expected):
    if path.is_symlink():
        raise RuntimeError('Refusing a symlink at the protected rule path')
    if path.exists() and path.read_text() != expected:
        raise RuntimeError('An unrelated rule already exists at ' + str(path))


def preflight(username, device):
    target = device_path(device)
    account = pwd.getpwnam(username)
    group = grp.getgrgid(account.pw_gid)
    others = {p.pw_name for p in pwd.getpwall() if p.pw_gid == group.gr_gid} | set(group.gr_mem)
    if others != {username}:
        raise RuntimeError('The target group is not private to this account')
    if account.pw_uid == 0:
        raise RuntimeError('A normal desktop account is required')
    if not target.resolve().is_relative_to('/sys/devices'):
        raise RuntimeError('Unexpected backlight device path')
    s = target.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o002:
        raise RuntimeError('Unexpected brightness attribute ownership/type/permissions')
    expected = rule_for(group.gr_name, device)
    check_rule(RULE_PATH, expected)
    if RULE_PATH.exists():
        st = RULE_PATH.stat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            raise RuntimeError('Unexpected protected rule permissions')
    for path in (RULE_PATH.parent, Path('/var/backups')):
        st = path.stat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            raise RuntimeError('Unexpected protected directory permissions: ' + str(path))
    return account, group, expected, s, target


ROLLBACK = '''import json,os,stat,subprocess
from pathlib import Path
if os.geteuid()!=0: raise SystemExit('Run this rollback with sudo')
root=Path(__file__).resolve().parent
m=json.loads((root/'metadata.json').read_text())
if Path('/run/user/'+str(m['uid'])+'/xps-desktop/backlight-state.json').exists():
 raise SystemExit('Stop xps-desktop.service before rolling back backlight permissions')
rule=Path(m['rule']);device=Path(m['device'])
if rule.is_symlink() or (rule.exists() and rule.read_text()!=m['rule_text']):
 raise SystemExit('The rule changed after installation; inspect it before rollback')
if rule.exists() and not m['rule_existed']: rule.unlink()
s=device.stat()
if not stat.S_ISREG(s.st_mode) or s.st_uid!=0: raise SystemExit('Unexpected brightness file')
os.chown(device,m['owner'],m['group']);os.chmod(device,m['mode'])
subprocess.run(['/usr/bin/udevadm','control','--reload-rules'],check=True)
print('Backlight permission rollback complete; brightness value was not changed.')
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    account, group, expected, before, target = preflight(args.user, args.device)
    if args.check:
        print(json.dumps({'preflight': 'passed', 'device': str(target),
                          'private_group': group.gr_name, 'only_added_permission': 'group write to this brightness attribute',
                          'rule': str(RULE_PATH)}))
        return
    if os.geteuid() != 0:
        raise SystemExit('Run the installer with sudo')
    if RULE_PATH.exists() and before.st_gid == group.gr_gid and before.st_mode & 0o020:
        print('XPS_BACKLIGHT_ACCESS_ALREADY_INSTALLED')
        return
    backup = Path(tempfile.mkdtemp(prefix='xps-backlight-access-', dir='/var/backups'))
    metadata = {'uid': account.pw_uid, 'device': str(target), 'owner': before.st_uid,
                'group': before.st_gid, 'mode': stat.S_IMODE(before.st_mode),
                'rule': str(RULE_PATH), 'rule_text': expected, 'rule_existed': RULE_PATH.exists()}
    (backup / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (backup / 'rollback.py').write_text(ROLLBACK)
    value_before = target.read_text()
    temporary = None
    try:
        if not RULE_PATH.exists():
            fd, name = tempfile.mkstemp(prefix='.xps-backlight-', dir=RULE_PATH.parent)
            temporary = Path(name)
            with os.fdopen(fd, 'w') as f:
                f.write(expected);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(), 0o644)
            os.replace(temporary, RULE_PATH)
        os.chown(target, before.st_uid, group.gr_gid)
        os.chmod(target, stat.S_IMODE(before.st_mode) | 0o020)
        subprocess.run(['/usr/bin/udevadm', 'control', '--reload-rules'], check=True)
        after = target.stat()
        assert after.st_uid == before.st_uid and after.st_gid == group.gr_gid
        assert stat.S_IMODE(after.st_mode) == stat.S_IMODE(before.st_mode) | 0o020
        assert target.read_text() == value_before, 'Brightness changed during permission installation'
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if not metadata['rule_existed'] and RULE_PATH.exists() and RULE_PATH.read_text() == expected:
            RULE_PATH.unlink()
        os.chown(target, before.st_uid, before.st_gid)
        os.chmod(target, stat.S_IMODE(before.st_mode))
        subprocess.run(['/usr/bin/udevadm', 'control', '--reload-rules'], check=False)
        raise
    print('Backup: ' + str(backup))
    print('Rollback: sudo /usr/bin/python3 -I ' + str(backup / 'rollback.py'))
    print('Only built-in LCD brightness access changed; brightness itself is unchanged.')
    print('XPS_BACKLIGHT_ACCESS_INSTALLED')


if __name__ == '__main__':
    main()
