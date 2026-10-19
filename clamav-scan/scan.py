"""Daily, unprivileged ClamAV scans. Reports and extraction stay on encrypted /vault."""
from pathlib import Path
import datetime
import fcntl
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time

ROOTS = [Path.home() / 'Downloads', Path.home() / 'Desktop', Path('/vault')]
STATE = Path('/vault/.clamav-scan')
CACHE_RE = r'(^|/)(\.cache|cache|caches|Cache|Caches|__pycache__|\.npm|\.pnpm-store)(/|$)'
EXCLUDES = [CACHE_RE, r'^/vault/(lost\+found|\.clamav-scan)(/|$)']
LIMITS = '256 MiB per file; 512 MiB expanded per container; 120 seconds per file; no symlinks/submounts'


def file_coverage(roots):
    """Record predictable size omissions separately from the engine's return code."""
    oversized = []
    errors = []
    def error(exc):
        errors.append(str(exc))
    for root in roots:
        device = root.stat().st_dev
        for base, dirs, files in os.walk(root, followlinks=False, onerror=error):
            kept = []
            for name in dirs:
                path = Path(base) / name
                if any(re.search(pattern, str(path)) for pattern in EXCLUDES):
                    continue
                try:
                    s = path.lstat()
                    if stat.S_ISDIR(s.st_mode) and s.st_dev == device:
                        kept.append(name)
                except OSError as exc:
                    error(exc)
            dirs[:] = kept
            for name in files:
                path = Path(base) / name
                try:
                    s = path.lstat()
                    if stat.S_ISREG(s.st_mode) and s.st_size > 256 * 1024 * 1024:
                        oversized.append(str(path))
                except OSError as exc:
                    error(exc)
    return oversized, errors


def on_ac():
    supplies = Path('/sys/class/power_supply')
    battery = False
    for p in supplies.iterdir():
        try:
            kind = (p / 'type').read_text().strip()
            battery |= kind == 'Battery'
            if kind != 'Battery' and (p / 'online').read_text().strip() == '1':
                return True
        except OSError:
            pass
    return not battery


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.chmod(0o600)
    tmp.replace(path)


def notify_pending():
    pending = STATE / 'pending-notification.json'
    if not pending.exists():
        return
    # Do not activate a desktop notification server in a logged-out session.
    if subprocess.run(['/usr/bin/systemctl', '--user', 'is-active', '--quiet', 'dunst.service']).returncode:
        return
    item = json.loads(pending.read_text())
    p = subprocess.run(['/usr/bin/notify-send', '--app-name=ClamAV', '--urgency=' + item['urgency'],
                        'Antivirus scan', item['message']], timeout=15)
    if p.returncode == 0:
        pending.unlink()


def command(roots, temp):
    return ['/usr/bin/clamscan', '--recursive', '--infected', '--cross-fs=no',
            '--follow-dir-symlinks=0', '--follow-file-symlinks=0',
            '--max-dir-recursion=128', '--max-filesize=256M', '--max-scansize=512M',
            '--max-scantime=120000', '--alert-exceeds-max=yes', '--fail-if-cvd-older-than=3',
            '--tempdir=' + str(temp)] + ['--exclude-dir=' + p for p in EXCLUDES] + [str(p) for p in roots]


def self_test():
    # EICAR is an inert antivirus test string, never executed.
    with tempfile.TemporaryDirectory(prefix='self-test-', dir=STATE) as tmp:
        root = Path(tmp)
        (root / 'clean.txt').write_text('A harmless scanner smoke test.\n')
        test = bytes.fromhex('58354f2150254041505b345c505a58353428505e2937434329377d2445494341522d5354414e444152442d414e544956495255532d544553542d46494c452124482b482a')
        cache = root / '.cache'
        cache.mkdir()
        (cache / 'excluded-test.txt').write_bytes(test)
        (root / 'outside.txt').write_bytes(test)
        (root / 'link.txt').symlink_to(root / 'outside.txt')
        p = subprocess.run(command([root / 'clean.txt', cache, root / 'link.txt'], root), capture_output=True, text=True)
        assert p.returncode == 0 and 'FOUND' not in p.stdout, 'Clean/cache/symlink test failed'
        p = subprocess.run(command([root / 'outside.txt'], root), capture_output=True, text=True)
        assert p.returncode == 1 and 'Eicar' in p.stdout and (root / 'outside.txt').exists(), 'Detection/preservation test failed'
        print('Self-test passed: clean file, cache exclusion, symlink exclusion, detection and file preservation.')


def main():
    args = sys.argv[1:]
    assert args in [[], ['--now'], ['--status'], ['--self-test']]
    os.umask(0o077)
    if not Path('/vault').is_mount():
        print('Deferred: encrypted /vault is not mounted.')
        return 0
    STATE.mkdir(mode=0o700, exist_ok=True)
    s = STATE.lstat()
    assert not STATE.is_symlink() and s.st_uid == os.getuid() and s.st_mode & 0o077 == 0, 'Unsafe report directory'
    if args == ['--status']:
        p = STATE / 'last-scan.json'
        print(p.read_text() if p.exists() else 'No completed scan yet.')
        return 0
    with (STATE / 'scan.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('A scan is already running.')
            return 0
        if args == ['--self-test']:
            self_test()
            return 0
        try:
            notify_pending()
        except (OSError, subprocess.SubprocessError):
            pass  # Keep pending notice; a notification failure must not prevent scanning.
        previous = STATE / 'last-scan.json'
        old = json.loads(previous.read_text()) if previous.exists() else {}
        interval = 24 * 3600
        if not args and time.time() - old.get('finished_epoch', 0) < interval:
            return 0
        if not args and not on_ac():
            print('Deferred until plugged in; next hourly check will retry.')
            return 0
        assert all(p.is_dir() and not p.is_symlink() for p in ROOTS), 'A scan root is missing or symlinked'
        started = time.time()
        report = STATE / ('scan-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.log')
        interrupted = [False]
        def stop(signum, frame):
            interrupted[0] = True
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        with tempfile.TemporaryDirectory(prefix='extract-', dir=STATE) as temp, report.open('w') as log:
            log.write('Scope: Downloads, Desktop, /vault; common cache directories excluded.\nLimits: ' + LIMITS + '\n')
            oversized, coverage_errors = file_coverage(ROOTS)
            for path in oversized:
                log.write('File-size limit (not a malware detection): ' + json.dumps(path) + '\n')
            for error in coverage_errors:
                log.write('Coverage error: ' + json.dumps(error) + '\n')
            log.flush()
            p = subprocess.Popen(command(ROOTS, temp), stdout=log, stderr=subprocess.STDOUT)
            while p.poll() is None:
                if interrupted[0] or (not args and not on_ac()):
                    interrupted[0] = True
                    p.terminate()
                    try:
                        p.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait()
                    break
                time.sleep(10)
            code = p.returncode
        text = report.read_text(errors='replace')
        found = [line for line in text.splitlines() if line.endswith(' FOUND')]
        limited = [line for line in found if re.search(r': Heuristics\.Limits\.Exceeded[^ ]* FOUND$', line)]
        detections = len(found) - len(limited)
        result = {'started_epoch': started, 'finished_epoch': time.time(), 'elapsed_seconds': round(time.time() - started),
                  'exit_code': code, 'detections': detections, 'limit_alerts': len(limited),
                  'oversized_files': len(oversized), 'coverage_errors': len(coverage_errors), 'report': str(report),
                  'status': 'interrupted' if interrupted[0] else (
                      ('incomplete' if code == 2 and (limited or oversized) else 'error') if code not in (0, 1) else (
                      'incomplete' if coverage_errors else ('detections' if detections else ('limits' if limited or oversized else 'completed')))),
                  'scope': [str(p) for p in ROOTS], 'limits': LIMITS}
        if interrupted[0]:
            # Preserve a report, but retry when awake/on AC instead of delaying a day.
            save(STATE / 'last-interrupted.json', result)
            print('Scan interrupted; will retry when awake and plugged in. Report:', report)
            return 0
        save(previous, result)
        if detections or result['status'] in ('error', 'incomplete') or ((limited or oversized) and (old.get('limit_alerts'), old.get('oversized_files')) != (len(limited), len(oversized))):
            message = ('Possible threats: ' + str(detections) + '. ' if detections else '')
            message += ('Scan failed or incomplete. ' if result['status'] in ('error', 'incomplete') else '')
            message += (str(len(limited)) + ' files/containers reached safety limits. ' if limited else '')
            message += (str(len(oversized)) + ' oversized files were skipped. ' if oversized else '')
            message += 'Review ' + str(report) + '. No files were changed.'
            save(STATE / 'pending-notification.json', {'message': message, 'urgency': 'critical' if detections else 'normal'})
            try:
                notify_pending()
            except (OSError, subprocess.SubprocessError):
                pass
        # Retain 14 reports produced by this scanner, never touch scanned input.
        for p in sorted(STATE.glob('scan-????????-??????.log'), reverse=True)[14:]:
            if p != report:
                p.unlink()
        print(json.dumps(result))
        return 2 if result['status'] == 'error' else 0


if __name__ == '__main__':
    sys.exit(main())
