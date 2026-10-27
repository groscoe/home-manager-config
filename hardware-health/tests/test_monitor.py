import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


m = module('health_monitor', 'monitor.py')
access = module('health_access', 'install-access.py')
NOW = dt.datetime(2026, 10, 27, 12, tzinfo=dt.timezone.utc)
LIMITS = {'batteryMonthlyPoints': 5, 'batteryQuarterlyPoints': 10,
          'ssdMonthlyPoints': 5, 'ssdQuarterlyPoints': 10, 'ssdSparePoints': 1,
          'ssdErrorEntries': 100}


def battery(capacity=73, ident='battery-one'):
    return {'id': ident, 'capacity_percent': capacity, 'source': 'fixture', 'name': 'Battery'}


def drive(**changes):
    value = dict(id='ssd-one', name='SSD', passed=True, critical_warning=0,
                 percentage_used=7, available_spare=100, available_spare_threshold=50,
                 media_errors=0, num_err_log_entries=0, data_units_written=1000,
                 power_on_hours=1000, unsafe_shutdowns=0, temperature=35)
    value.update(changes)
    return value


def sample(days=0, bat=None, ssd=None, errors=None):
    return {'timestamp': m.stamp(NOW - dt.timedelta(days=days)),
            'batteries': [bat or battery()], 'ssds': [ssd or drive()], 'errors': errors or {}}


class HealthTests(unittest.TestCase):
    def test_linux_charge_and_energy_units_are_not_mixed(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            b = root / 'BAT0'
            b.mkdir()
            for key, value in {'type': 'Battery', 'present': '1', 'charge_full': '3422000',
                               'charge_full_design': '4687000', 'cycle_count': '0', 'capacity': '76'}.items():
                (b / key).write_text(value)
            result = m.linux_batteries(root)[0]
            self.assertAlmostEqual(result['capacity_percent'], 73.010, places=3)
            self.assertIsNone(result['cycle_count'])
            self.assertEqual(result['unit'], 'uAh')
            for key, value in {'energy_full': '40000000', 'energy_full_design': '50000000'}.items():
                (b / key).write_text(value)
            self.assertEqual(m.linux_batteries(root)[0]['capacity_percent'], 80)

    def test_macos_uses_health_not_charge_or_normalized_max(self):
        data = {'SPPowerDataType': [{'sppower_battery_health_info': {
            'sppower_battery_health_maximum_capacity': '95%', 'sppower_battery_cycle_count': 45,
            'sppower_battery_health': 'Good'}, 'sppower_battery_model_info': {
            'sppower_battery_serial_number': 'private-fixture-serial'}}]}
        result = m.mac_batteries(data)[0]
        self.assertEqual(result['capacity_percent'], 95)
        self.assertNotIn('private-fixture-serial', json.dumps(result))
        del data['SPPowerDataType'][0]['sppower_battery_health_info']['sppower_battery_health_maximum_capacity']
        with self.assertRaises(ValueError):
            m.mac_batteries(data)

    def test_nvme_health_failure_exit_bit_is_kept(self):
        data = {'model_name': 'SSD', 'serial_number': 'serial', 'smart_status': {'passed': False},
                'nvme_smart_health_information_log': drive(critical_warning=4)}
        result = m.nvme_snapshot(data, 8, '/dev/nvme0')
        self.assertFalse(result['passed'])
        for code in [1, 2, 4, -9]:
            with self.assertRaises(ValueError):
                m.nvme_snapshot(data, code, '/dev/nvme0')
        del data['nvme_smart_health_information_log']['media_errors']
        with self.assertRaises(ValueError):
            m.nvme_snapshot(data, 0, '/dev/nvme0')

    def test_battery_small_variation_does_not_alert(self):
        self.assertFalse(m.evaluate(sample(), [sample(30, battery(75))], LIMITS))

    def test_monthly_and_quarterly_battery_decline(self):
        for days, old in [(30, 78), (90, 83)]:
            self.assertTrue(any(k.endswith(':decline') for k in m.evaluate(sample(), [sample(days, battery(old))], LIMITS)))
        self.assertFalse(m.evaluate(sample(), [sample(150, battery(100))], LIMITS))

    def test_replacement_is_a_new_baseline(self):
        previous = sample(30, battery(100, 'old-battery'), drive(id='old-ssd', percentage_used=1))
        self.assertFalse(m.evaluate(sample(), [previous], LIMITS))

    def test_reporting_source_change_is_not_battery_decline(self):
        old = sample(30, battery(100))
        old['batteries'][0]['source'] = 'different-tool'
        self.assertFalse(m.evaluate(sample(), [old], LIMITS))

    def test_new_media_errors_and_critical_warning_alert_immediately(self):
        current = sample(ssd=drive(media_errors=1, critical_warning=4, passed=False))
        alerts = m.evaluate(current, [sample(30)], LIMITS)
        self.assertTrue(any(k.endswith(':media') for k in alerts))
        self.assertTrue(any(k.endswith(':critical') for k in alerts))

    def test_baseline_existing_media_errors_are_not_silent(self):
        self.assertTrue(any(k.endswith(':media') for k in m.evaluate(sample(ssd=drive(media_errors=2)), [], LIMITS)))

    def test_ssd_wear_and_spare_changes(self):
        alerts = m.evaluate(sample(ssd=drive(percentage_used=12, available_spare=99)), [sample(30)], LIMITS)
        self.assertTrue(any(k.endswith(':wear') for k in alerts))
        self.assertTrue(any(k.endswith(':spare-change') for k in alerts))
        self.assertFalse(any(k.endswith(':wear') for k in m.evaluate(sample(ssd=drive(percentage_used=12)), [sample(200)], LIMITS)))

    def test_generic_error_counts_are_separate_from_media_errors(self):
        self.assertFalse(m.evaluate(sample(ssd=drive(num_err_log_entries=1)), [sample(30)], LIMITS))
        self.assertTrue(any(k.endswith(':error-log') for k in m.evaluate(sample(ssd=drive(num_err_log_entries=100)), [sample(30)], LIMITS)))

    def test_counter_reset_and_unsafe_shutdown_are_distinguished(self):
        self.assertFalse(m.evaluate(sample(ssd=drive(unsafe_shutdowns=1)), [sample(30)], LIMITS))
        alerts = m.evaluate(sample(ssd=drive(data_units_written=1)), [sample(30)], LIMITS)
        self.assertTrue(any(k.endswith(':counter-reset') for k in alerts))

    def test_failed_reads_do_not_create_successful_baseline(self):
        config = {'host': 'fixture', 'thresholds': LIMITS, 'remoteReports': []}
        state = {'history': [sample(30)], 'alerts': {}, 'version': 1}
        failed = sample(errors={'/dev/nvme0': 'permission denied'})
        with patch.object(m, 'collect', return_value=failed), patch.object(m, 'notify', return_value=False):
            self.assertEqual(m.process(config, state, NOW), 1)
        self.assertEqual(len(state['history']), 1)
        self.assertNotIn('last_success', state)
        self.assertTrue(state['pending'])

    def test_retry_success_then_monthly_gate_and_catchup(self):
        config = {'thresholds': LIMITS, 'remoteReports': []}
        state = {'history': [], 'alerts': {}, 'version': 1}
        with patch.object(m, 'collect', return_value=sample()) as collect:
            m.process(config, state, NOW)
            m.process(config, state, NOW + dt.timedelta(days=1))
            self.assertEqual(collect.call_count, 1)
            m.process(config, state, NOW + dt.timedelta(days=70))
            self.assertEqual(collect.call_count, 2)
        self.assertEqual(len(state['history']), 2)

    def test_notification_retry_deduplication_and_recurrence(self):
        state = {}
        config = {'host': 'fixture'}
        with patch.object(m, 'notify', side_effect=[False, True, True]) as notify:
            m.deliver(config, state, {'issue': 'problem'}, NOW)
            self.assertEqual(state['pending'], {'issue': 'problem'})
            m.deliver(config, state, {'issue': 'problem'}, NOW)
            m.deliver(config, state, {'issue': 'problem'}, NOW)
            self.assertEqual(notify.call_count, 2)
            m.deliver(config, state, {}, NOW)
            m.deliver(config, state, {'issue': 'problem'}, NOW)
            self.assertEqual(notify.call_count, 3)

    def test_remote_delivery_cached_through_normal_outage_and_stale_report(self):
        config = {'remoteReports': [{'name': 'xps', 'host': 'fixture', 'port': 2222, 'command': '/home/u/bin/health'}]}
        remote = {'version': 1, 'host': 'xps', 'last_success': m.stamp(NOW), 'alerts': {'ssd:media': 'new media error'}}
        state = {}
        with patch.object(m, 'run_json', return_value=(0, remote)):
            alerts = m.remote_alerts(config, state, NOW)
            self.assertEqual(alerts['remote:xps:ssd:media'], 'xps: new media error')
        with patch.object(m, 'run_json', side_effect=RuntimeError('offline')):
            self.assertEqual(m.remote_alerts(config, state, NOW + dt.timedelta(days=1)), alerts)
            self.assertIn('remote:xps:stale', m.remote_alerts(config, state, NOW + dt.timedelta(days=70)))

    def test_wrong_remote_host_is_not_accepted(self):
        config = {'remoteReports': [{'name': 'xps', 'host': 'fixture', 'port': 2222, 'command': '/h'}]}
        with patch.object(m, 'run_json', return_value=(0, {'version': 1, 'host': 'other', 'alerts': {}})):
            state = {}
            self.assertFalse(m.remote_alerts(config, state, NOW))
            self.assertFalse(state['remote_cache'])

    def test_atomic_private_history_and_corruption_preservation(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'history.json'
            m.atomic_json(path, {'version': 1, 'history': [], 'alerts': {}})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(m.load_state(path)['version'], 1)
            path.write_text('broken history')
            with self.assertRaises(ValueError):
                m.load_state(path)
            self.assertEqual(path.read_text(), 'broken history')

    def test_access_rule_has_exact_read_only_arguments(self):
        text = access.policy({'user': 'groscoe', 'smartctl': '/usr/sbin/smartctl', 'devices': ['/dev/nvme0']})
        self.assertIn('NOPASSWD: /usr/sbin/smartctl -i -H -A -j /dev/nvme0\n', text)
        for config in [
            {'user': 'user ALL', 'smartctl': '/usr/sbin/smartctl', 'devices': ['/dev/nvme0']},
            {'user': 'user', 'smartctl': '/home/user/bin/smartctl', 'devices': ['/dev/nvme0']},
            {'user': 'user', 'smartctl': '/usr/sbin/smartctl', 'devices': ['/dev/nvme*']},
            {'user': 'user', 'smartctl': '/usr/sbin/smartctl', 'devices': ['/dev/nvme0 -s on']},
        ]:
            with self.assertRaises(ValueError):
                access.policy(config)

    def test_corrupt_history_failure_notification_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as t, patch.object(m, 'notify', return_value=True) as notify:
            root = Path(t)
            m.failure_notice({'host': 'fixture'}, root, NOW, ValueError('corrupt history'))
            m.failure_notice({'host': 'fixture'}, root, NOW, ValueError('corrupt history'))
            self.assertEqual(notify.call_count, 1)


if __name__ == '__main__':
    unittest.main()
