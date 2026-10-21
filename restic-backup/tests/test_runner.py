import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'runner.py'
spec = importlib.util.spec_from_file_location('runner', SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@unittest.skipUnless(shutil.which('restic'), 'requires native restic')
class ScheduledBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='restic-schedule-test-')
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.vault = self.root / 'vault'
        self.state = self.root / 'state'
        for path in (self.home, self.vault, self.state):
            path.mkdir(mode=0o700)
        (self.home / 'notes.txt').write_text('home notes')
        (self.vault / 'work.txt').write_text('vault work')
        password = self.root / 'password'
        password.write_text('public-synthetic-test-password')
        password.chmod(0o600)
        self.envfile = self.root / 'environment'
        self.envfile.write_text('export RESTIC_REPOSITORY=' + str(self.root / 'repo') + '\n'
                               'export RESTIC_PASSWORD_FILE=' + str(password) + '\n')
        self.envfile.chmod(0o600)
        rules = self.root / 'exclude.txt'
        rules.write_text('.cache\n')
        self.config = {
            'restic': shutil.which('restic'), 'bash': '/bin/bash',
            'environmentFile': str(self.envfile), 'homeDirectory': str(self.home),
            'stateDirectory': str(self.state), 'paths': [str(self.home), str(self.vault)],
            'requiredMounts': [], 'hostname': 'synthetic-host', 'tags': ['test'],
            'excludeFiles': [str(rules)], 'thresholdGB': '20', 'requireAC': False,
            'intervalHours': 24,
        }
        self.env = runner.environment(self.config)
        subprocess.run([self.config['restic'], 'init'], env=self.env, check=True, capture_output=True)
        self.args = argparse.Namespace(run=False, scheduled=True, threshold_gb=None)

    def tearDown(self):
        self.temp.cleanup()

    def snapshots(self):
        return json.loads(subprocess.run([self.config['restic'], 'snapshots', '--json'],
            env=self.env, check=True, capture_output=True, text=True).stdout)

    def test_scheduled_backup_verifies_snapshot_of_all_roots(self):
        with patch.object(runner, 'notify') as notice:
            self.assertEqual(runner.run_backup(self.config, self.args, self.state), 0)
            notice.assert_not_called()
        result = json.loads((self.state / 'last-success.json').read_text())
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(set(self.snapshots()[0]['paths']), set(self.config['paths']))
        self.assertEqual(result['snapshot_id'], self.snapshots()[0]['id'])

    def test_unattended_threshold_refuses_upload_and_keeps_success_unset(self):
        self.config['thresholdGB'] = '0'
        with patch.object(runner, 'notify') as notice:
            self.assertEqual(runner.run_backup(self.config, self.args, self.state), 0)
            notice.assert_called_once()
        self.assertFalse((self.state / 'last-success.json').exists())
        self.assertEqual(json.loads((self.state / 'last-attempt.json').read_text())['status'], 'needs-confirmation')
        self.assertEqual(self.snapshots(), [])

    def test_missing_required_mount_does_not_create_snapshot(self):
        self.config['requiredMounts'] = [str(self.vault)]
        self.assertEqual(runner.run_backup(self.config, self.args, self.state), 0)
        self.assertEqual(self.snapshots(), [])
        self.assertFalse((self.state / 'last-success.json').exists())

    def test_public_credential_permissions_are_rejected(self):
        self.envfile.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'Credential file'):
            runner.environment(self.config)

    def test_missing_protected_export_stops_before_upload(self):
        self.config['protectedExport'] = {'directory': str(self.root / 'missing-export'),
                                           'sources': [str(self.home / 'protected')]}
        with self.assertRaises(FileNotFoundError):
            runner.run_backup(self.config, self.args, self.state)
        self.assertEqual(self.snapshots(), [])
        self.assertFalse((self.state / 'last-success.json').exists())


if __name__ == '__main__':
    unittest.main()
