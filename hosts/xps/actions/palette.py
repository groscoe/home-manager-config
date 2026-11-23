"""A fixed action registry; typed text is search, never a shell command."""
import argparse
import json
import subprocess
from pathlib import Path


def select(cfg,entries):
    rows=[e['label'] for e in entries]
    result=subprocess.run([cfg['rofi'],'-dmenu','-i','-no-custom','-format','i','-p','XPS actions',
                           '-mesg','Sound · Connections · Privacy · Desktop · System'],input='\n'.join(rows),text=True,capture_output=True)
    try:
        n=int(result.stdout.strip())
        return entries[n] if result.returncode==0 and 0<=n<len(entries) else None
    except ValueError:return None


def launch(cfg,entry):
    argv=entry['argv']
    if not argv or not Path(argv[0]).is_absolute():raise ValueError('Action must use an absolute executable path')
    if entry.get('terminal'):argv=[cfg['terminal'],'--hold','-e',*argv]
    # No shell, eval, interpolated arguments or direct privileged operations.
    subprocess.Popen(argv,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--list',action='store_true');args=p.parse_args()
    cfg=json.loads(args.config.read_text())
    if args.list:print(json.dumps(cfg['entries'],indent=2));return
    entry=select(cfg,cfg['entries'])
    if entry is None:return
    try:launch(cfg,entry)
    except (OSError,ValueError) as e:
        subprocess.run([cfg['notify'],'XPS action unavailable',str(e)],check=False)
        raise SystemExit(1)

if __name__=='__main__':main()
