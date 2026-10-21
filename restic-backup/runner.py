"""One guarded Restic workflow for interactive use, systemd and launchd."""
from pathlib import Path
import argparse
import fcntl
import grp
import importlib.util
import json
import os
import pwd
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load_module('backup_guard', 'backup-guard.py')
managed = load_module('managed_excludes', 'home-manager-excludes.py')


def save(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.write('\n')
    temporary.replace(path)


def read_json(path):
    return json.loads(path.read_text()) if path.exists() else {}


def on_ac():
    if sys.platform == 'darwin':
        result = subprocess.run(['/usr/bin/pmset', '-g', 'batt'], capture_output=True, text=True)
        return result.returncode == 0 and "'AC Power'" in result.stdout
    battery = False
    for supply in Path('/sys/class/power_supply').iterdir():
        try:
            kind = (supply / 'type').read_text().strip()
            battery |= kind == 'Battery'
            if kind != 'Battery' and (supply / 'online').read_text().strip() == '1':
                return True
        except OSError:
            pass
    return not battery


def private_credential(path):
    path = Path(path).expanduser()
    s = path.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid not in (0, os.getuid()) or s.st_mode & 0o027:
        raise RuntimeError('Credential file must be owned by root or this user, without public access or group write: ' + str(path))
    if not os.access(path, os.R_OK):
        raise RuntimeError('Credential file is not readable by the backup user: ' + str(path))
    if s.st_mode & 0o040:
        group = grp.getgrgid(s.st_gid)
        readers = set(group.gr_mem) | {p.pw_name for p in pwd.getpwall() if p.pw_gid == s.st_gid}
        allowed = {pwd.getpwuid(os.getuid()).pw_name, 'root'}
        if not readers <= allowed:
            raise RuntimeError('Credential file has group access beyond this user/root: ' + str(path))


def environment(config):
    private_credential(config['environmentFile'])
    # Values stay inside this process and the native Restic process environment.
    # They are never embedded in Nix, command arguments, status files or output.
    result = subprocess.run([config['bash'], '-c',
        'set +x; set -e; set -a; source "$1"; exec /usr/bin/env -0',
        'restic-environment', config['environmentFile']], capture_output=True)
    if result.returncode:
        raise RuntimeError('Cannot load the existing credential environment (values not displayed).')
    values = {}
    for entry in result.stdout.split(b'\0'):
        if entry:
            key, value = entry.split(b'=', 1)
            values[os.fsdecode(key)] = os.fsdecode(value)
    if values.get('RESTIC_PASSWORD_FILE'):
        private_credential(values['RESTIC_PASSWORD_FILE'])
    values['RESTIC_CACHE_DIR'] = str(Path(config['stateDirectory']) / 'repository-cache')
    return values


def notify(config, state, message):
    record = read_json(state / 'last-notification.json')
    if record.get('message') == message and time.time() - record.get('epoch', 0) < 86400:
        return
    if sys.platform == 'darwin':
        command = ['/usr/bin/osascript', '-e',
            'on run argv\ndisplay notification (item 1 of argv) with title "Restic backup"\nend run', message]
    else:
        if subprocess.run(['/usr/bin/systemctl', '--user', 'is-active', '--quiet', 'dunst.service']).returncode:
            return
        command = [config['notifySend'], '--app-name=Restic', 'Backup needs attention', message]
    try:
        result = subprocess.run(command, capture_output=True, timeout=15)
        if result.returncode == 0:
            save(state / 'last-notification.json', {'message': message, 'epoch': time.time()})
    except (OSError, subprocess.SubprocessError):
        pass


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def protected_paths(config):
    export = config.get('protectedExport')
    if not export:
        return []
    directory = Path(export['directory'])
    s = directory.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
        raise RuntimeError('Protected export directory has unsafe ownership/permissions.')
    manifest = directory / 'manifest.json'
    private_credential(manifest)
    if manifest.lstat().st_uid != 0 or manifest.is_symlink():
        raise RuntimeError('Protected export manifest must be a regular root-owned file.')
    record = json.loads(manifest.read_text())
    age = time.time() - record['epoch']
    if not 0 <= age <= 26 * 3600:
        raise RuntimeError('Protected export is stale. Check restic-protected-export.timer/service.')
    if {r['path'] for r in record['sources']} != set(export['sources']):
        raise RuntimeError('Protected export does not cover the configured source list.')
    for source in record['sources']:
        name = source['archive']
        if Path(name).name != name or not name.endswith('.tar'):
            raise RuntimeError('Invalid protected archive name.')
        archive = directory / name
        private_credential(archive)
        s = archive.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_size != source['bytes'] or s.st_mtime_ns != source['mtime_ns']:
            raise RuntimeError('Protected archive changed or is incomplete. Retry after the export finishes.')
    return export['sources']


def run_backup(config, args, state):
    started = time.time()
    env = environment(config)
    host = config.get('hostname') or env.get('RESTIC_HOST') or socket.gethostname()
    for path in config['requiredMounts']:
        if not Path(path).is_mount():
            print('Deferred: required backup volume is not mounted:', path, flush=True)
            return 0
    protected = protected_paths(config)
    with tempfile.TemporaryDirectory(prefix='restic-managed-excludes-') as temp:
        rules = Path(temp) / 'managed.txt'
        paths = managed.managed_paths(Path(config['homeDirectory'])) + protected
        rules.write_text(''.join(managed.literal_pattern(p) + '\n' for p in paths if '\n' not in p and '\r' not in p))
        command = [sys.executable, str(Path(__file__).with_name('backup-guard.py')),
                   '--restic', config['restic'], '--host', host,
                   '--threshold-gb', str(args.threshold_gb or config['thresholdGB'])]
        for path in config['paths']:
            command += ['--source', path]
        for tag in config['tags']:
            command += ['--tag', tag]
        for path in config['excludeFiles'] + [str(rules)]:
            command += ['--exclude-file', path]
        real = args.run or args.scheduled
        command += ['--run' if real else '--dry-run']
        process = subprocess.Popen(command, env=env,
            stdin=subprocess.DEVNULL if args.scheduled else None,
            start_new_session=args.scheduled)
        try:
            while process.poll() is None:
                if args.scheduled and config['requireAC'] and not on_ac():
                    stop_group(process)
                    save(state / 'last-attempt.json', {'status': 'interrupted-on-battery', 'epoch': time.time()})
                    print('Stopped after switching to battery; a later hourly check will retry.', flush=True)
                    return 0
                time.sleep(1)
        except BaseException:
            if args.scheduled:
                stop_group(process)
            else:
                if process.poll() is None:
                    process.terminate()
                    process.wait()
            raise
        code = process.returncode
    if not real:
        return code
    status = 'needs-confirmation' if code == 75 else ('completed' if code == 0 else 'error')
    result = {'status': status, 'epoch': time.time(), 'exit_code': code,
              'hostname': host, 'paths': config['paths']}
    if code == 0:
        # Confirm a new snapshot covering every configured root actually exists.
        previous = os.environ.copy()
        try:
            os.environ.clear()
            os.environ.update(env)
            snapshot = guard.choose_parent(config['restic'], config['paths'], host)
        finally:
            os.environ.clear()
            os.environ.update(previous)
        if not snapshot or set(snapshot['paths']) != set(config['paths']):
            raise RuntimeError('Restic returned success but no snapshot covers all configured paths.')
        timestamp = guard.snapshot_time(snapshot['time']).timestamp()
        if timestamp < started - 5:
            raise RuntimeError('Restic returned success but the verified snapshot is older than this run.')
        result.update(snapshot_id=snapshot['id'], snapshot_time=snapshot['time'])
        save(state / 'last-success.json', result)
    save(state / 'last-attempt.json', result)
    if args.scheduled and code:
        message = ('Changes exceed the confirmation limit. Run restic-backup --run in a terminal.'
                   if code == 75 else 'The backup failed or was incomplete. Review restic-backup --status and its private log.')
        notify(config, state, message)
    return 0 if args.scheduled and code == 75 else code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--run', action='store_true', help='Back up after the guarded preview.')
    modes.add_argument('--dry-run', action='store_true', help='Preview only; this is the default.')
    modes.add_argument('--scheduled', action='store_true', help='Run once daily while awake/on AC, without bypassing the guard.')
    modes.add_argument('--status', action='store_true')
    parser.add_argument('--threshold-gb', type=guard.threshold_bytes)
    args = parser.parse_args()
    if args.scheduled:
        def stop(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
    # Keep decimal GB at the CLI boundary; backup-guard applies the same parser.
    if args.threshold_gb is not None:
        args.threshold_gb = str(args.threshold_gb / guard.GB)
    config = json.loads(args.config.read_text())
    assert config['paths'] and all(Path(p).is_absolute() for p in config['paths'])
    config['paths'] = guard.source_list(config['paths'])
    os.umask(0o077)
    state = Path(config['stateDirectory'])
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = state.lstat()
    assert stat.S_ISDIR(s.st_mode) and s.st_uid == os.getuid() and not s.st_mode & 0o077
    if args.status:
        print(json.dumps({'last_success': read_json(state / 'last-success.json'),
                          'last_attempt': read_json(state / 'last-attempt.json'),
                          'log': str(state / 'scheduled.log'), 'paths': config['paths']}, indent=2))
        return 0
    fd = os.open(state / 'run.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        assert os.fstat(lock.fileno()).st_uid == os.getuid()
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another backup command is running; skipping overlap.')
            return 0
        if args.scheduled:
            success = read_json(state / 'last-success.json')
            attempt = read_json(state / 'last-attempt.json')
            if time.time() - success.get('epoch', 0) < config['intervalHours'] * 3600:
                return 0
            if attempt.get('status') == 'needs-confirmation' and time.time() - attempt.get('epoch', 0) < 86400:
                return 0
            if config['requireAC'] and not on_ac():
                print('Deferred until AC power is connected.')
                return 0
            log = state / 'scheduled.log'
            if log.exists() and log.stat().st_size > 5 * 1024 * 1024:
                log.replace(state / 'scheduled.previous.log')
            stream = log.open('a', buffering=1)
            os.dup2(stream.fileno(), 1)
            os.dup2(stream.fileno(), 2)
        try:
            return run_backup(config, args, state)
        except KeyboardInterrupt:
            save(state / 'last-attempt.json', {'status': 'interrupted', 'epoch': time.time()})
            return 0 if args.scheduled else 130
        except (OSError, ValueError, RuntimeError, guard.PreflightError) as exc:
            save(state / 'last-attempt.json', {'status': 'error', 'epoch': time.time(), 'error': str(exc)})
            print('Backup stopped:', str(exc), file=sys.stderr, flush=True)
            if args.scheduled:
                notify(config, state, 'Backup could not run. Review restic-backup --status and its private log.')
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
