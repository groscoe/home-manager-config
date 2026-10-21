#!/usr/bin/env python3
"""Preview restic changes and gate large backups on interactive confirmation."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
import re
from pathlib import Path
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

GB = 1_000_000_000


def snapshot_time(value):
    # Restic emits nanoseconds; Python 3.10 accepts at most microseconds.
    return datetime.fromisoformat(re.sub(r'(\.\d{6})\d+', r'\1', value).replace('Z', '+00:00'))


class PreflightError(Exception):
    pass


def threshold_bytes(value):
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError('threshold must be a nonnegative number of GB') from exc
    if not number.is_finite() or number < 0:
        raise argparse.ArgumentTypeError('threshold must be a nonnegative finite number of GB')
    return int(number * GB)


def human_size(value):
    return f'{value / GB:,.3f} GB ({value:,} bytes)'


def integer(data, key):
    value = data.get(key)
    if type(value) is not int or value < 0:
        raise PreflightError(f'Missing or invalid restic field: {key}')
    return value


def stream_json(command, callback):
    # Let restic report its own errors, but never display environment variables.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    try:
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise PreflightError('Could not parse restic output; backup will not start.') from exc
            if not isinstance(event, dict):
                raise PreflightError('Unexpected restic JSON output.')
            callback(event)
        return process.wait()
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def source_list(source):
    values = [source] if isinstance(source, str) else source
    return sorted(set(os.path.abspath(value) for value in values))


def choose_parent(restic, source, hostname):
    sources = set(source_list(source))
    result = subprocess.run(
        [restic, 'snapshots', '--json', '--no-lock', '--host', hostname],
        stdout=subprocess.PIPE, text=True, check=False)
    if result.returncode:
        raise PreflightError('Could not read snapshot history; backup will not start.')
    try:
        snapshots = json.loads(result.stdout)
        if not isinstance(snapshots, list):
            raise ValueError('expected snapshot list')
        now = datetime.now(timezone.utc)
        exact = []
        compatible = []
        for snapshot in snapshots:
            paths = set(snapshot['paths'])
            if snapshot['hostname'] != hostname or not paths or not paths <= sources:
                continue
            timestamp = snapshot_time(snapshot['time'])
            if timestamp <= now:
                if paths == sources:
                    exact.append((timestamp, snapshot))
                else:
                    compatible.append((len(paths), timestamp, snapshot))
        if exact:
            return max(exact, key=lambda item: item[0])[1]
        # Adding /vault can reuse this host's old home snapshot. New roots still
        # count as additions; unrelated paths or another host are never inferred.
        return max(compatible, key=lambda item: item[:2])[2] if compatible else None
    except (ValueError, KeyError, TypeError) as exc:
        raise PreflightError('Invalid snapshot history; backup will not start.') from exc


class Inventory:
    """Disk-backed parent inventory, so large backups do not exhaust RAM."""
    def __init__(self, filename):
        self.db = sqlite3.connect(filename)
        self.db.execute('CREATE TABLE files (path TEXT PRIMARY KEY, size INTEGER, seen INTEGER DEFAULT 0)')
        self.added = 0
        self.shrunk = 0
        self.files = 0
        self.total_size = 0
        self.summary = None
        self.last_progress = time.monotonic()

    def parent_node(self, event):
        if event.get('type') == 'file':
            self.db.execute('INSERT INTO files(path,size) VALUES (?,?)',
                            (event['path'], integer(event, 'size')))

    def preview_event(self, event):
        message_type = event.get('message_type')
        if message_type == 'summary':
            if self.summary is not None:
                raise PreflightError('Multiple preflight summaries received.')
            self.summary = event
            return
        if message_type == 'error':
            raise PreflightError('Restic reported a source read error during preflight.')
        if message_type != 'verbose_status':
            return
        action = event.get('action')
        if action == 'scan_finished':
            print(f"Scan: {integer(event, 'total_files'):,} files, "
                  f"{human_size(integer(event, 'data_size'))} selected.", flush=True)
            return
        path = event.get('item')
        if action not in ('new', 'modified', 'unchanged') or not isinstance(path, str) or not path:
            raise PreflightError('Unrecognized restic item event.')
        # Restic 0.18+ identifies directory events with a trailing slash.
        # Symlinks have no file-data bytes and do not emit these file events.
        if path.endswith('/'):
            return
        row = self.db.execute('SELECT size,seen FROM files WHERE path=?', (path,)).fetchone()
        if row and row[1]:
            raise PreflightError(f'Duplicate file event during preflight: {path}')
        try:
            current = os.lstat(path)
        except OSError as exc:
            raise PreflightError(f'File changed or became unreadable during preflight: {path}') from exc
        if not stat.S_ISREG(current.st_mode):
            raise PreflightError(f'File type changed during preflight: {path}')
        size = current.st_size
        if action == 'unchanged' and (row is None or row[0] != size):
            raise PreflightError(f'Parent/preflight file mismatch: {path}')
        if row is None:
            self.added += size
        else:
            previous = row[0]
            self.added += max(size - previous, 0)
            self.shrunk += max(previous - size, 0)
            self.db.execute('UPDATE files SET seen=1 WHERE path=?', (path,))
        self.files += 1
        self.total_size += size
        if time.monotonic() - self.last_progress >= 15:
            print(f'Preflight: compared {self.files:,} files...', flush=True)
            self.last_progress = time.monotonic()

    def finish(self):
        if self.summary is None or self.summary.get('dry_run') is not True:
            raise PreflightError('No complete dry-run summary was received.')
        if integer(self.summary, 'total_files_processed') != self.files:
            raise PreflightError('Incomplete file inventory; backup will not start.')
        if integer(self.summary, 'total_bytes_processed') != self.total_size:
            raise PreflightError('File sizes changed during preflight; rerun the command.')
        missing = self.db.execute('SELECT COALESCE(SUM(size),0) FROM files WHERE seen=0').fetchone()[0]
        return {
            'added': self.added,
            'removed': missing + self.shrunk,
            'new_repository_data': integer(self.summary, 'data_added'),
            'stored_estimate': integer(self.summary, 'data_added_packed'),
            'files': self.files,
            'total_size': self.total_size,
        }


def exceeds_threshold(delta, threshold):
    return any(delta[key] > threshold for key in ('added', 'removed', 'new_repository_data'))


def confirm(delta, threshold):
    if not exceeds_threshold(delta, threshold):
        return True
    print(f'Change exceeds the {human_size(threshold)} confirmation threshold.', flush=True)
    if not sys.stdin.isatty():
        print('Interactive confirmation is required. Run this command in a terminal; backup canceled.',
              file=sys.stderr)
        return False
    try:
        reply = input('Type yes to start the backup, or press Enter to cancel: ')
    except EOFError:
        return False
    return reply.strip().lower() == 'yes'


def execute(args):
    sources = source_list(args.source)
    for source in sources:
        if not os.path.isdir(source) or os.path.islink(source):
            raise PreflightError(f'Backup source is not an accessible real directory: {source}')
    if not sources:
        raise PreflightError('At least one backup directory is required.')
    hostname = args.host or os.environ.get('RESTIC_HOST') or socket.gethostname()
    parent = choose_parent(args.restic, sources, hostname)
    parent_id = parent['id'] if parent else None
    if parent_id:
        print(f"Comparing with snapshot {parent_id[:8]} ({parent['time']}, {hostname}).", flush=True)
    else:
        print('No matching parent snapshot: all selected file data will count as added.', flush=True)

    # Keep temporary state outside the home directory being backed up.
    with tempfile.TemporaryDirectory(prefix='restic-preflight-') as temp:
        temporary = Path(temp)
        common = [args.restic, 'backup', '--host', hostname,
                  '--one-file-system', '--exclude-caches']
        for tag in getattr(args, 'tag', None) or ['macos' if sys.platform == 'darwin' else 'linux', 'home']:
            common += ['--tag', tag]
        for number, filename in enumerate(args.exclude_file):
            copy = temporary / f'excludes-{number}.txt'
            shutil.copyfile(filename, copy)
            common += ['--exclude-file', str(copy)]
        if parent_id:
            common += ['--parent', parent_id]
        inventory = Inventory(temporary / 'parent.sqlite')
        try:
            if parent_id:
                code = stream_json([args.restic, 'ls', '--json', '--no-lock', parent_id],
                                   inventory.parent_node)
                if code:
                    raise PreflightError('Could not list the parent snapshot; backup will not start.')
            print('Running a read-only preflight with the backup exclusions...', flush=True)
            code = stream_json(common + ['--dry-run', '--no-lock', '--json', '--verbose=2'] + sources,
                               inventory.preview_event)
            if code:
                raise PreflightError(f'Preflight exited with status {code}. Resolve any source read errors '
                                     'and rerun; no real backup was started.')
            delta = inventory.finish()
        finally:
            inventory.db.close()

        print(f"Added/new or grown files:  {human_size(delta['added'])}")
        print(f"Removed or shrunk files:  {human_size(delta['removed'])}")
        print(f"New repository data:      {human_size(delta['new_repository_data'])} before compression")
        print(f"Estimated stored data:    {human_size(delta['stored_estimate'])}")
        print(f"Selected: {delta['files']:,} files, {human_size(delta['total_size'])}.")
        print('Removed means omitted from the next snapshot; previous snapshots are not deleted.')
        if not args.run:
            result = 'would require confirmation' if exceeds_threshold(delta, args.threshold_gb) else 'is below the threshold'
            print(f'Dry run complete: a real backup {result}. No backup was created.')
            return 0
        if not confirm(delta, args.threshold_gb):
            print('Backup canceled. No backup was created.')
            return 75 if exceeds_threshold(delta, args.threshold_gb) and not sys.stdin.isatty() else 1
        print('Starting backup...', flush=True)
        return subprocess.call(common + sources)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restic', required=True)
    parser.add_argument('--source', required=True, action='append', help='Repeat for multiple directories.')
    parser.add_argument('--host')
    parser.add_argument('--tag', action='append')
    parser.add_argument('--exclude-file', action='append', default=[])
    parser.add_argument('--threshold-gb', type=threshold_bytes, default='20',
                        help='Prompt if either direction exceeds this many decimal GB (default: 20).')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--run', action='store_true')
    modes.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        return execute(args)
    except KeyboardInterrupt:
        print('\nInterrupted.', file=sys.stderr)
        return 130
    except (PreflightError, OSError, sqlite3.Error) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
