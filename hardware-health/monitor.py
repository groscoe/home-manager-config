"""Monthly, read-only battery/NVMe trends and durable desktop notifications."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

UTC = dt.timezone.utc
SMART_ARGS = ['-i', '-H', '-A', '-j']


def stamp(now):
    return now.astimezone(UTC).isoformat()


def identity(*parts):
    return hashlib.sha256('\0'.join(map(str, parts)).encode()).hexdigest()[:24]


def number(value, name, low=0, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'Invalid {name}: {value!r}')
    if value < low or (high is not None and value > high):
        raise ValueError(f'Out-of-range {name}: {value!r}')
    return value


def run_json(command, timeout=45):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                            env={**os.environ, 'LC_ALL': 'C', 'LANG': 'C'})
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        # Avoid writing raw controller output/serials into notification history.
        raise RuntimeError(f'{Path(command[0]).name} returned no valid JSON (exit {result.returncode})') from exc
    return result.returncode, data


def linux_batteries(root=Path('/sys/class/power_supply')):
    batteries = []
    for path in sorted(root.iterdir()):
        def read(name, default=None):
            try:
                return (path / name).read_text().strip()
            except FileNotFoundError:
                return default
        if read('type') != 'Battery' or read('present', '1') == '0':
            continue
        kind = next((k for k in ('energy', 'charge')
                     if (path / f'{k}_full').exists() and (path / f'{k}_full_design').exists()), None)
        if kind is None:
            raise ValueError(f'{path.name}: battery full/design capacity unavailable')
        full = number(float(read(f'{kind}_full')), 'full capacity', low=1)
        design = number(float(read(f'{kind}_full_design')), 'design capacity', low=1)
        health = number(100 * full / design, 'battery health', high=150)
        model, serial = read('model_name', path.name), read('serial_number', '')
        cycles = int(read('cycle_count', '0'))
        batteries.append({'id': identity(read('manufacturer', ''), model, serial, design),
                          'name': model, 'capacity_percent': round(health, 3),
                          'source': f'linux-{kind}-full/design', 'cycle_count': cycles or None,
                          'full': full, 'design': design, 'unit': 'uWh' if kind == 'energy' else 'uAh',
                          'condition': read('health'), 'state_of_charge': read('capacity')})
    if not batteries:
        raise ValueError('No present battery found; configure battery monitoring off for a desktop/VM')
    return batteries


def mac_batteries(data):
    batteries = []
    for item in data.get('SPPowerDataType', []):
        info = item.get('sppower_battery_health_info')
        if not info:
            continue
        value = info.get('sppower_battery_health_maximum_capacity')
        if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+)?%', value):
            raise ValueError('macOS maximum battery capacity unavailable; normalized MaxCapacity is not health')
        model = item.get('sppower_battery_model_info', {})
        serial = model.get('sppower_battery_serial_number')
        if not serial:
            raise ValueError('macOS battery identity unavailable')
        batteries.append({'id': identity(serial), 'name': model.get('sppower_battery_device_name', 'Battery'),
                          'capacity_percent': number(float(value[:-1]), 'battery health', high=150),
                          'source': 'macos-system-profiler-maximum-capacity',
                          'cycle_count': info.get('sppower_battery_cycle_count'),
                          'condition': info.get('sppower_battery_health')})
    if not batteries:
        raise ValueError('macOS returned no battery health information')
    return batteries


def nvme_snapshot(data, returncode, device):
    # smartctl's upper exit bits represent real health warnings: retain them.
    # Command/open/read failures in the low bits must never become a healthy zero.
    if returncode < 0 or returncode & 7:
        raise ValueError(f'SMART query failed for {device} (exit {returncode}); check read permission')
    log = data.get('nvme_smart_health_information_log')
    if not isinstance(log, dict) or not isinstance(data.get('smart_status', {}).get('passed'), bool):
        raise ValueError(f'{device}: complete NVMe health counters unavailable')
    serial, model = data.get('serial_number'), data.get('model_name')
    if not serial or not model:
        raise ValueError(f'{device}: controller identity unavailable')
    fields = ('critical_warning', 'percentage_used', 'available_spare', 'available_spare_threshold',
              'media_errors', 'num_err_log_entries', 'data_units_written', 'power_on_hours',
              'unsafe_shutdowns', 'temperature')
    result = {name: number(log.get(name), name) for name in fields}
    for name, maximum in [('critical_warning', 255), ('percentage_used', 255),
                          ('available_spare', 100), ('available_spare_threshold', 100)]:
        number(result[name], name, high=maximum)
    result.update({'id': identity(model, serial), 'name': model, 'device': device,
                   'passed': data['smart_status']['passed'], 'firmware': data.get('firmware_version')})
    return result


def collect(config, now):
    snapshot = {'timestamp': stamp(now), 'batteries': [], 'ssds': [], 'errors': {}}
    if config['battery']:
        try:
            if config['platform'] == 'darwin':
                code, data = run_json(['/usr/sbin/system_profiler', 'SPPowerDataType', '-json'])
                if code:
                    raise RuntimeError(f'system_profiler exited with {code}')
                snapshot['batteries'] = mac_batteries(data)
            else:
                snapshot['batteries'] = linux_batteries()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            snapshot['errors']['battery'] = str(exc)
    for device in config['devices']:
        try:
            command = [config['smartctl'], *SMART_ARGS, device]
            if config['sudoSmartctl']:
                command = ['/usr/bin/sudo', '-n', *command]
            code, data = run_json(command)
            snapshot['ssds'].append(nvme_snapshot(data, code, device))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            snapshot['errors'][device] = str(exc)
    return snapshot


def prior_devices(history, section, current, now, days=None):
    found = []
    for snapshot in history:
        age = (now - dt.datetime.fromisoformat(snapshot['timestamp'])).total_seconds() / 86400
        if age <= 0 or (days is not None and age > days):
            continue
        for item in snapshot[section]:
            if item['id'] == current['id']:
                found.append((age, item))
    return found


def evaluate(snapshot, history, limits):
    now = dt.datetime.fromisoformat(snapshot['timestamp'])
    alerts = {f'collection:{key}': f'Health reading unavailable: {message}'
              for key, message in snapshot['errors'].items()}
    for battery in snapshot['batteries']:
        prefix = f'battery:{battery["id"]}'
        if str(battery.get('condition', '')).lower() in ('poor', 'fair', 'service recommended', 'check battery', 'replace now', 'replace soon'):
            alerts[prefix + ':condition'] = f'Battery reports {battery["condition"]}.'
        for days, threshold in [(45, limits['batteryMonthlyPoints']), (105, limits['batteryQuarterlyPoints'])]:
            previous = prior_devices(history, 'batteries', battery, now, days)
            # Different reporting sources are separate measurement series.
            drops = [(old['capacity_percent'] - battery['capacity_percent'], age)
                     for age, old in previous if old['source'] == battery['source']]
            if drops:
                drop, age = max(drops)
                if drop + 1e-6 >= threshold:
                    alerts[prefix + ':decline'] = (f'Battery capacity estimate fell {drop:.1f} percentage points '
                        f'in {age:.0f} days, to {battery["capacity_percent"]:.1f}%. Confirm the trend with another reading; estimates can vary.')
    for ssd in snapshot['ssds']:
        prefix = f'ssd:{ssd["id"]}'
        if not ssd['passed'] or ssd['critical_warning']:
            alerts[prefix + ':critical'] = f'{ssd["name"]}: SMART warning 0x{ssd["critical_warning"]:02x}; overall passed={ssd["passed"]}.'
        if ssd['available_spare'] <= ssd['available_spare_threshold']:
            alerts[prefix + ':spare-low'] = f'{ssd["name"]}: spare capacity {ssd["available_spare"]}% is at/below threshold {ssd["available_spare_threshold"]}%.'
        if ssd['percentage_used'] >= 90:
            alerts[prefix + ':endurance'] = f'{ssd["name"]}: estimated endurance consumed is {ssd["percentage_used"]}%.'
        old_items = prior_devices(history, 'ssds', ssd, now)
        previous = min(old_items, default=None, key=lambda pair: pair[0])
        if previous:
            age, old = previous
            if ssd['media_errors'] > old['media_errors']:
                alerts[prefix + ':media'] = f'{ssd["name"]}: media/data integrity errors increased from {old["media_errors"]} to {ssd["media_errors"]}.'
            if old['available_spare'] - ssd['available_spare'] >= limits['ssdSparePoints']:
                alerts[prefix + ':spare-change'] = f'{ssd["name"]}: available spare fell from {old["available_spare"]}% to {ssd["available_spare"]}%.'
            if ssd['num_err_log_entries'] - old['num_err_log_entries'] >= limits['ssdErrorEntries']:
                alerts[prefix + ':error-log'] = f'{ssd["name"]}: controller error-log count grew by {ssd["num_err_log_entries"] - old["num_err_log_entries"]}. Inspect the log; this count alone does not establish media failure.'
            if any(ssd[k] < old[k] for k in ('percentage_used', 'media_errors', 'num_err_log_entries', 'data_units_written', 'power_on_hours')):
                alerts[prefix + ':counter-reset'] = f'{ssd["name"]}: a cumulative counter decreased. Review a possible firmware/reporting reset before interpreting the trend.'
        elif ssd['media_errors']:
            alerts[prefix + ':media'] = f'{ssd["name"]}: baseline already reports {ssd["media_errors"]} media/data integrity errors.'
        for days, threshold in [(45, limits['ssdMonthlyPoints']), (105, limits['ssdQuarterlyPoints'])]:
            previous = prior_devices(history, 'ssds', ssd, now, days)
            if previous:
                delta, age = max((ssd['percentage_used'] - old['percentage_used'], age) for age, old in previous)
                if delta >= threshold:
                    alerts[prefix + ':wear'] = f'{ssd["name"]}: estimated endurance consumed rose {delta} points in {age:.0f} days, to {ssd["percentage_used"]}%.'
    return alerts


def atomic_json(path, data):
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def notify(config, title, message):
    if config['platform'] == 'darwin':
        command = ['/usr/bin/osascript', '-e',
                   'on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run',
                   title, message]
    else:
        command = [config['notifySend'], '--app-name=Hardware health', '--urgency=normal', title, message]
    try:
        result = subprocess.run(command, capture_output=True, timeout=15)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def remote_alerts(config, state, now):
    alerts = {}
    cache = state.setdefault('remote_cache', {})
    for remote in config.get('remoteReports', []):
        name = remote['name']
        try:
            code, report = run_json(['/usr/bin/ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                '-o', 'ConnectionAttempts=1', '-p', str(remote['port']), remote['host'], remote['command'], '--status', '--json'], timeout=15)
            if code or report.get('version') != 1 or report.get('host') != name:
                raise ValueError('Unexpected health report')
            if not isinstance(report.get('alerts'), dict) or not all(isinstance(k, str) and isinstance(v, str)
                    and len(v) < 2000 for k, v in report['alerts'].items()) or len(report['alerts']) > 50:
                raise ValueError('Invalid remote alerts')
            # Retain a single status report, not remote raw device data.
            cache[name] = {'timestamp': report.get('last_success'), 'alerts': report['alerts'], 'seen': stamp(now)}
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            # An offline laptop is normal. A stale known report is still actionable.
            pass
        cached = cache.get(name)
        if cached:
            alerts.update({f'remote:{name}:{key}': f'{name}: {value}' for key, value in cached['alerts'].items()})
            date = cached.get('timestamp') or cached['seen']
            try:
                if (now - dt.datetime.fromisoformat(date)).days > 62:
                    alerts[f'remote:{name}:stale'] = f'{name}: no successful hardware reading for over two months. Check the monthly job.'
            except (TypeError, ValueError):
                alerts[f'remote:{name}:invalid-date'] = f'{name}: health report contains an invalid reading date.'
    return alerts


def deliver(config, state, alerts, now):
    delivered = state.setdefault('delivered', {})
    pending = state['pending'] = {}
    for key, message in alerts.items():
        signature = identity(message)
        if delivered.get(key) == signature:
            continue
        if notify(config, f'{config["host"]}: hardware health', message):
            delivered[key] = signature
        else:
            pending[key] = message
    # Persistent warnings are not repeated. Cleared conditions can alert again.
    state['delivered'] = {key: value for key, value in delivered.items() if key in alerts}
    state['notification_attempt'] = stamp(now)


def load_state(path):
    if not path.exists():
        return {'version': 1, 'history': [], 'alerts': {}, 'pending': {}}
    data = json.loads(path.read_text())
    if data.get('version') != 1 or not isinstance(data.get('history'), list) or not isinstance(data.get('alerts'), dict):
        raise ValueError('Invalid health history; preserve it for inspection instead of resetting the baseline')
    return data


def process(config, state, now, force=False):
    month = now.strftime('%Y-%m')
    due = force or state.get('last_complete_month') != month
    if due:
        snapshot = collect(config, now)
        alerts = evaluate(snapshot, state['history'], config['thresholds'])
        # Preserve prior warnings for components that could not be read.
        if snapshot['errors']:
            for key, value in state['alerts'].items():
                if not key.startswith(('collection:', 'remote:')):
                    alerts.setdefault(key, value)
        state.update({'latest': snapshot, 'alerts': alerts, 'last_attempt': stamp(now)})
        if not snapshot['errors']:
            state['history'].append(snapshot)
            state['history'] = state['history'][-240:]
            state['last_success'] = stamp(now)
            state['last_complete_month'] = month
    alerts = {key: value for key, value in state['alerts'].items() if not key.startswith('remote:')}
    alerts.update(remote_alerts(config, state, now))
    state['alerts'] = alerts
    deliver(config, state, alerts, now)
    return 1 if state.get('latest', {}).get('errors') else 0


def report(config, state):
    return {'version': 1, 'host': config['host'], 'last_success': state.get('last_success'),
            'last_attempt': state.get('last_attempt'), 'latest': state.get('latest'),
            'alerts': state.get('alerts', {}), 'pending': state.get('pending', {}),
            'samples': len(state.get('history', []))}


def failure_notice(config, directory, now, exc):
    path = directory / 'failure.json'
    previous = {}
    try:
        previous = json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    message = str(exc)
    accepted = previous.get('error') == message and previous.get('notification_accepted', False)
    if not accepted:
        accepted = notify(config, f'{config["host"]}: hardware tracking failed',
                          'Could not read or update health history. Run hardware-health --status and inspect the job log.')
    atomic_json(path, {'timestamp': stamp(now), 'error': message, 'notification_accepted': accepted})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--scheduled', action='store_true')
    modes.add_argument('--record', action='store_true', help='Take a reading now, regardless of the monthly gate')
    modes.add_argument('--status', action='store_true', help='Read saved status without accessing hardware')
    modes.add_argument('--test-notification', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    now = dt.datetime.now(UTC)
    directory = Path(config['stateDirectory'])
    if args.test_notification:
        ok = notify(config, f'{config["host"]}: hardware health', 'Test notification: monthly battery and SSD tracking is configured.')
        print('Notification command accepted.' if ok else 'Notification unavailable; check the graphical session/notification permission.')
        return 0 if ok else 1
    os.umask(0o077)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_path = directory / 'history.json'
    with (directory / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another hardware reading is running.', file=sys.stderr)
            return 0
        try:
            state = load_state(state_path)
            code = 0
            if not args.status:
                code = process(config, state, now, force=args.record)
                atomic_json(state_path, state)
                (directory / 'failure.json').unlink(missing_ok=True)
            data = report(config, state)
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                print(f'{config["host"]}: last successful reading {data["last_success"] or "none"}; {data["samples"]} saved samples')
                for item in (data['latest'] or {}).get('batteries', []):
                    print(f'Battery: {item["capacity_percent"]:.1f}% capacity; cycles {item.get("cycle_count") or "unavailable"}')
                for item in (data['latest'] or {}).get('ssds', []):
                    print(f'{item["name"]}: {item["percentage_used"]}% endurance consumed; {item["media_errors"]} media errors; {item["temperature"]} C')
                for message in data['alerts'].values():
                    print('ATTENTION:', message)
                if data['pending']:
                    print('Desktop notification pending; it will be retried by the scheduled job.')
            return code
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f'Hardware tracking failed: {exc}', file=sys.stderr)
            # Leave existing history intact, keep an inspectable failure record,
            # and report it without claiming a new successful measurement.
            failure_notice(config, directory, now, exc)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
