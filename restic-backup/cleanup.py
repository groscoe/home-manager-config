"""Policy-based cleanup that always retains archive-tagged snapshots.

No scheduler calls this command today. Future cleanup jobs must use this entry
point rather than invoking restic forget directly.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from runner import environment

PERIODS = ('last', 'hourly', 'daily', 'weekly', 'monthly', 'yearly')


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('retention counts must be positive')
    return number


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--config', type=Path, required=True)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Actually forget/prune ordinary snapshots.')
    mode.add_argument('--dry-run', action='store_true', help='Preview only (the default).')
    for period in PERIODS:
        result.add_argument('--keep-' + period, type=positive)
    return result


def command(config, args):
    # Fail closed if a future configuration accidentally drops the archive rule.
    if 'archive' not in config.get('retentionKeepTags', []):
        raise ValueError('Cleanup requires retentionKeepTags to include archive.')
    policy = []
    for period in PERIODS:
        count = getattr(args, 'keep_' + period)
        if count is not None:
            policy.extend(['--keep-' + period, str(count)])
    if not policy:
        raise ValueError('Specify at least one positive --keep-* count.')
    result = [config['restic'], 'forget', '--prune']
    # Separate --keep-tag arguments mean OR. A comma would mean AND, which could
    # accidentally require another tag in addition to archive.
    for tag in config['retentionKeepTags']:
        if not tag or ',' in tag:
            raise ValueError('Retention tags must be single, nonempty tags.')
        result.extend(['--keep-tag', tag])
    result.extend(policy)
    if not args.apply:
        result.append('--dry-run')
    return result


def main():
    cli = parser()
    args = cli.parse_args()
    config = json.loads(args.config.read_text())
    try:
        cmd = command(config, args)
        env = environment(config)
    except (ValueError, RuntimeError, OSError) as exc:
        cli.error(str(exc))
    print('Archive-tagged snapshots are always retained. ' +
          ('Applying cleanup.' if args.apply else 'Preview only; no snapshots will be removed.'), flush=True)
    return subprocess.run(cmd, env=env).returncode


if __name__ == '__main__':
    sys.exit(main())
