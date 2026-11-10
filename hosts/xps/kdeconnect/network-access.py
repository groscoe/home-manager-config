#!/usr/bin/python3
"""One-time Ubuntu/xps KDE Connect firewall migration; pairing data is not read."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

BASE = '8683ce6b042f60c7e7b8371f84a15abba59b33e0aabf453aa2eba2e9a63dce82'
TARGET = Path('/usr/local/sbin/xps-host-firewall')


def candidate(source):
    if hashlib.sha256(source.encode()).hexdigest() != BASE:
        raise RuntimeError('The host firewall changed. Review it before applying this migration.')
    for chain, rest in [('$personal', ''), ('$input', '-i $lan_interface -s $prefix ')]:
        if chain == '$personal':
            anchor = '   printf \'%s\\n\' "-A $personal -p tcp -m multiport --dports 2222,8096,9443,9999 -j RETURN"'
            rules = ''.join(f'   printf \'%s\\n\' "-A $personal -p {proto} --dport 1714:1764 -j RETURN"\n' for proto in ('tcp','udp'))
        else:
            anchor = '    printf \'%s\\n\' "-A $input -i $lan_interface -s $prefix -p tcp --dport 2222 -j ACCEPT"'
            rules = ''.join(f'    printf \'%s\\n\' "-A $input -i $lan_interface -s $prefix -p {proto} --dport 1714:1764 -j ACCEPT"\n' for proto in ('tcp','udp'))
        assert source.count(anchor) == 1
        source = source.replace(anchor, rules + anchor)
    return source


def command(*args):
    subprocess.run(args, check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    source=TARGET.read_text()
    if '--dport 1714:1764' in source:
        raise SystemExit('KDE Connect host-guard rules already present; inspect UFW before reapplying.')
    changed=candidate(source)
    command('/bin/bash','-n','-c',changed)
    if not args.apply:
        print('Preflight passed: four scoped rules; existing firewall source matches reviewed baseline.')
        return
    if os.geteuid()!=0:
        raise SystemExit('Run with sudo to apply the reviewed root-owned firewall changes.')
    os.umask(0o077)
    backup=Path(tempfile.mkdtemp(prefix='xps-kdeconnect-',dir='/var/backups'))
    with tarfile.open(backup/'before.tar','w') as archive:
        for path in ['/etc/ufw','/usr/local/sbin/xps-host-firewall']:
            archive.add(path,arcname=path.lstrip('/'))
    # Validate regular-file bytes and ownership/modes before modifying anything.
    with tarfile.open(backup/'before.tar') as archive:
        for item in archive:
            path=Path('/')/item.name
            st=path.lstat()
            assert (st.st_uid,st.st_gid,st.st_mode & 0o7777)==(item.uid,item.gid,item.mode)
            if item.isfile():
                assert archive.extractfile(item).read()==path.read_bytes()
    rollback=backup/'rollback.sh'
    rollback.write_text('#!/bin/bash\nset -euo pipefail\n/bin/tar -xpf '+str(backup/'before.tar')+' -C /\n/usr/sbin/ufw reload\n/usr/local/sbin/xps-host-firewall\n')
    rollback.chmod(0o700)
    print('Backup:',backup,flush=True)
    print('Rollback: sudo /bin/bash',rollback,flush=True)
    try:
        # Atomic replacement preserves the root-owned executable's metadata.
        tmp=TARGET.with_name('.xps-host-firewall.kdeconnect')
        with tmp.open('x') as stream:stream.write(changed)
        shutil.copystat(TARGET,tmp)
        os.chown(tmp,0,0)
        os.replace(tmp,TARGET)
        for proto in ['tcp','udp']:
            command('/usr/sbin/ufw','allow','in','on','wlp0s20f3','from','192.168.1.0/24','to','any','port','1714:1764','proto',proto,'comment','KDE Connect home LAN')
        command(str(TARGET))
        for tool,family in [('/usr/sbin/iptables','4'),('/usr/sbin/ip6tables','6')]:
            for proto in ['tcp','udp']:
                command(tool,'-w','10','-C','XPS-PERSONAL'+family,'-p',proto,'--dport','1714:1764','-j','RETURN')
        print('KDECONNECT_NETWORK_ACCESS_INSTALLED',flush=True)
    except BaseException:
        command('/bin/bash',str(rollback))
        raise


if __name__=='__main__':main()
