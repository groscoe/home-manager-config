import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'backup-guard.py'
spec = importlib.util.spec_from_file_location('guard', SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ThresholdTests(unittest.TestCase):
    def test_restic_nanoseconds_work_on_older_python(self):
        value = guard.snapshot_time('2026-02-21T22:24:37.163243819-03:00')
        self.assertEqual(value.microsecond, 163243)
        self.assertEqual(str(value.utcoffset()), '-1 day, 21:00:00')

    def test_parent_selection_requires_exact_host_and_source(self):
        rows = [
            dict(id='correct', hostname='this-mac', paths=['/home/test'], time='2025-01-01T00:00:00Z'),
            dict(id='other-host', hostname='other-mac', paths=['/home/test'], time='2025-02-01T00:00:00Z'),
            dict(id='extra-path', hostname='this-mac', paths=['/home/test', '/other'], time='2025-03-01T00:00:00Z'),
            dict(id='future', hostname='this-mac', paths=['/home/test'], time='2999-01-01T00:00:00Z'),
        ]
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps(rows))
        with patch.object(guard.subprocess, 'run', return_value=result):
            self.assertEqual(guard.choose_parent('restic', '/home/test', 'this-mac')['id'], 'correct')

    def test_decimal_gb_and_invalid_values(self):
        self.assertEqual(guard.threshold_bytes('20'), 20_000_000_000)
        self.assertEqual(guard.threshold_bytes('0.25'), 250_000_000)
        for value in ('-1', 'nan', 'Infinity', 'abc'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                guard.threshold_bytes(value)

    def test_multiple_roots_prefer_exact_parent_and_allow_old_home_only(self):
        rows = [
            dict(id='old-home', hostname='xps', paths=['/home/test'], time='2025-03-01T00:00:00Z'),
            dict(id='both', hostname='xps', paths=['/vault', '/home/test'], time='2025-02-01T00:00:00Z'),
            dict(id='other-host', hostname='mac', paths=['/home/test', '/vault'], time='2025-04-01T00:00:00Z'),
            dict(id='unrelated', hostname='xps', paths=['/etc'], time='2025-05-01T00:00:00Z'),
        ]
        with patch.object(guard.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(rows))):
            self.assertEqual(guard.choose_parent('restic', ['/home/test', '/vault'], 'xps')['id'], 'both')
        rows = [row for row in rows if row['id'] != 'both']
        with patch.object(guard.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(rows))):
            self.assertEqual(guard.choose_parent('restic', ['/home/test', '/vault'], 'xps')['id'], 'old-home')

    def test_directions_are_separate_and_boundary_is_strict(self):
        self.assertFalse(guard.exceeds_threshold(dict(added=20, removed=20, new_repository_data=20), 20))
        for key in ('added', 'removed', 'new_repository_data'):
            delta = dict(added=0, removed=0, new_repository_data=0)
            delta[key] = 21
            self.assertTrue(guard.exceeds_threshold(delta, 20))
        self.assertTrue(guard.exceeds_threshold(dict(added=30, removed=30, new_repository_data=0), 20))

    def test_confirmation_and_noninteractive_refusal(self):
        delta = dict(added=21, removed=0, new_repository_data=0)
        with redirect_stdout(io.StringIO()), patch.object(guard.sys.stdin, 'isatty', return_value=True):
            for response, expected in (('yes', True), ('YES', True), ('', False), ('no', False), ('y', False)):
                with patch('builtins.input', return_value=response):
                    self.assertEqual(guard.confirm(delta, 20), expected)
            with patch('builtins.input', side_effect=EOFError):
                self.assertFalse(guard.confirm(delta, 20))
        with redirect_stdout(io.StringIO()), patch.object(guard.sys.stdin, 'isatty', return_value=False), \
                patch('builtins.input') as ask:
            self.assertFalse(guard.confirm(delta, 20))
            ask.assert_not_called()


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inventory = guard.Inventory(self.root / 'parent.sqlite')

    def tearDown(self):
        self.inventory.db.close()
        self.temp.cleanup()

    def old_file(self, name, size):
        self.inventory.parent_node({'type': 'file', 'path': str(self.root / name), 'size': size})

    def current_file(self, name, size, action):
        path = self.root / name
        path.write_bytes(b'x' * size)
        self.inventory.preview_event({'message_type': 'verbose_status', 'action': action, 'item': str(path)})

    def summary(self, count, size):
        self.inventory.preview_event(dict(message_type='summary', dry_run=True,
                                          total_files_processed=count, total_bytes_processed=size,
                                          data_added=7, data_added_packed=5))

    def test_add_growth_shrink_and_absent_files(self):
        self.old_file('grown', 10)
        self.old_file('shrunk', 100)
        self.old_file('missing_or_excluded', 200)
        self.old_file('same', 5)
        self.current_file('new', 50, 'new')
        self.current_file('grown', 30, 'modified')
        self.current_file('shrunk', 40, 'modified')
        self.current_file('same', 5, 'unchanged')
        self.summary(4, 125)
        result = self.inventory.finish()
        self.assertEqual(result['added'], 70)
        self.assertEqual(result['removed'], 260)

    def test_missing_summary_and_incomplete_inventory_stop_backup(self):
        with self.assertRaises(guard.PreflightError):
            self.inventory.finish()
        self.summary(2, 100)
        with self.assertRaises(guard.PreflightError):
            self.inventory.finish()

    def test_current_size_changes_are_detected(self):
        self.current_file('new', 10, 'new')
        self.summary(1, 11)
        with self.assertRaises(guard.PreflightError):
            self.inventory.finish()

    def test_bad_json_and_source_errors_stop_backup(self):
        with self.assertRaises(guard.PreflightError):
            self.inventory.preview_event({'message_type': 'error'})
        with self.assertRaises(guard.PreflightError):
            self.inventory.preview_event({'message_type': 'verbose_status', 'action': 'unknown', 'item': 'file'})

    def test_nonzero_preflight_never_launches_real_backup(self):
        args = argparse.Namespace(source=str(self.root), host='test', restic='not-executed',
                                  exclude_file=[], run=True, threshold_gb=20_000_000_000)
        for code in (1, 3):
            with self.subTest(code=code), patch.object(guard, 'choose_parent', return_value=None), \
                    patch.object(guard, 'stream_json', return_value=code), \
                    patch.object(guard.subprocess, 'call') as upload, redirect_stdout(io.StringIO()):
                with self.assertRaises(guard.PreflightError):
                    guard.execute(args)
                upload.assert_not_called()


@unittest.skipUnless(shutil.which('restic'), 'requires local restic executable')
class ResticIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='restic-guard-test-')
        cls.base = Path(cls.temp.name)
        cls.repo = cls.base / 'repo'
        cls.restic = shutil.which('restic')
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith(('RESTIC_', 'AWS_', 'B2_'))}
        cls.env.update(RESTIC_REPOSITORY=str(cls.repo), RESTIC_PASSWORD='public-local-test-password',
                       RESTIC_CACHE_DIR=str(cls.base / 'cache'))
        cls.command(['init'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def command(cls, args):
        return subprocess.run([cls.restic] + args, env=cls.env, capture_output=True, text=True, check=True).stdout

    def setUp(self):
        self.source = self.base / self._testMethodName
        self.source.mkdir()
        self.host = self._testMethodName
        self.rules = self.base / (self.host + '.excludes')
        self.rules.write_text('')

    def initial_backup(self):
        self.command(['backup', '--host', self.host, str(self.source)])

    def snapshots(self):
        return json.loads(self.command(['snapshots', '--json', '--host', self.host]))

    def run_guard(self, *extra):
        return subprocess.run(['python3', str(SCRIPT), '--restic', self.restic,
                               '--source', str(self.source), '--host', self.host,
                               '--exclude-file', str(self.rules), *extra],
                              env=self.env, capture_output=True, text=True)

    def test_preview_tracks_equal_additions_and_removals_without_writes(self):
        (self.source / 'keep').write_text('keep')
        (self.source / 'old').write_bytes(b'o' * 10000)
        (self.source / 'empty').touch()
        self.initial_backup()
        (self.source / 'old').unlink()
        (self.source / 'new').write_bytes(b'n' * 10000)
        (self.source / 'link').symlink_to('keep')
        result = self.run_guard('--threshold-gb', '0.000005')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Added/new or grown files:  0.000 GB (10,000 bytes)', result.stdout)
        self.assertIn('Removed or shrunk files:  0.000 GB (10,000 bytes)', result.stdout)
        self.assertIn('would require confirmation', result.stdout)
        self.assertEqual(len(self.snapshots()), 1)

    def test_small_run_creates_snapshot(self):
        (self.source / 'keep').write_text('keep')
        self.initial_backup()
        (self.source / 'new').write_text('new')
        result = self.run_guard('--run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.snapshots()), 2)

    def test_adding_root_reuses_home_parent_and_restores_both_roots(self):
        (self.source / 'keep').write_text('home data')
        self.initial_backup()
        old = self.snapshots()[0]['id']
        second = self.base / (self.host + '-vault')
        second.mkdir()
        (second / 'vault.txt').write_text('vault data')
        result = self.run_guard('--source', str(second), '--run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        latest = max(self.snapshots(), key=lambda row: row['time'])
        self.assertEqual(latest['parent'], old)
        self.assertEqual(set(latest['paths']), {str(self.source), str(second)})
        target = self.base / (self.host + '-restored')
        self.command(['restore', latest['id'], '--target', str(target)])
        self.assertEqual((target / str(second).lstrip('/') / 'vault.txt').read_text(), 'vault data')
        self.assertEqual((target / str(self.source).lstrip('/') / 'keep').read_text(), 'home data')

    def test_interactive_approval_creates_snapshot_with_selected_parent(self):
        (self.source / 'keep').write_text('keep')
        self.initial_backup()
        parent_id = self.snapshots()[0]['id']
        (self.source / 'new').write_bytes(b'approved-new-content' * 2000)
        args = argparse.Namespace(source=str(self.source), host=self.host, restic=self.restic,
                                  exclude_file=[str(self.rules)], run=True, threshold_gb=5000)
        with patch.dict(os.environ, self.env, clear=True), redirect_stdout(io.StringIO()), \
                patch.object(guard.sys.stdin, 'isatty', return_value=True), \
                patch('builtins.input', return_value='yes') as ask:
            self.assertEqual(guard.execute(args), 0)
            ask.assert_called_once()
        snapshots = self.snapshots()
        self.assertEqual(len(snapshots), 2)
        latest = max(snapshots, key=lambda s: s['time'])
        self.assertEqual(latest['parent'], parent_id)

    def test_removed_by_new_exclusion_requires_confirmation(self):
        (self.source / 'large').write_bytes(b'x' * 20000)
        (self.source / 'keep').write_text('keep')
        self.initial_backup()
        self.rules.write_text('large\n')
        result = self.run_guard('--run', '--threshold-gb', '0.000005')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Removed or shrunk files:  0.000 GB (20,000 bytes)', result.stdout)
        self.assertIn('Interactive confirmation is required', result.stderr)
        self.assertEqual(len(self.snapshots()), 1)

    def test_large_first_backup_is_not_automatically_started(self):
        (self.source / 'new').write_bytes(b'x' * 20000)
        result = self.run_guard('--run', '--threshold-gb', '0.000005')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No matching parent', result.stdout)
        self.assertEqual(len(self.snapshots()), 0)

    def test_same_size_rewrite_triggers_new_repository_data_check(self):
        (self.source / 'file').write_bytes(b'x' * 20000)
        self.initial_backup()
        (self.source / 'file').write_bytes(b'y' * 20000)
        result = self.run_guard('--run', '--threshold-gb', '0.000005')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Added/new or grown files:  0.000 GB (0 bytes)', result.stdout)
        self.assertIn('Removed or shrunk files:  0.000 GB (0 bytes)', result.stdout)
        self.assertIn('Interactive confirmation is required', result.stderr)
        self.assertEqual(len(self.snapshots()), 1)


if __name__ == '__main__':
    unittest.main()
