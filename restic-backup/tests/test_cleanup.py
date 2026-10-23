import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('cleanup', BASE / 'cleanup.py')
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


class CleanupPolicyTests(unittest.TestCase):
    def test_archive_protection_cannot_be_removed(self):
        args = cleanup.parser().parse_args(['--config', '/unused', '--keep-last', '1'])
        with self.assertRaisesRegex(ValueError, 'archive'):
            cleanup.command({'restic': 'restic', 'retentionKeepTags': []}, args)

    def test_extra_tags_use_or_semantics_and_preview_is_default(self):
        args = cleanup.parser().parse_args(['--config', '/unused', '--keep-last', '1'])
        cmd = cleanup.command({'restic': 'restic', 'retentionKeepTags': ['archive', 'important']}, args)
        self.assertEqual(cmd.count('--keep-tag'), 2)
        self.assertIn('--dry-run', cmd)

    def test_raw_snapshot_ids_and_override_flags_are_rejected(self):
        for tail in [('deadbeef',), ('--unsafe-allow-remove-all',), ('--keep-last', '-1')]:
            with self.subTest(tail=tail), self.assertRaises(SystemExit):
                cleanup.parser().parse_args(['--config', '/unused', *tail])


@unittest.skipUnless(shutil.which('restic'), 'requires native restic')
class ArchiveRetentionTests(unittest.TestCase):
    def test_cleanup_prunes_ordinary_snapshot_but_archive_remains_restorable(self):
        with tempfile.TemporaryDirectory(prefix='restic-archive-test-') as temp:
            root = Path(temp)
            home = root / 'source'
            home.mkdir()
            password = root / 'password'
            password.write_text('synthetic-local-test-password')
            password.chmod(0o600)
            envfile = root / 'env'
            envfile.write_text(f'export RESTIC_REPOSITORY={root / "repo"}\n'
                               f'export RESTIC_PASSWORD_FILE={password}\n')
            envfile.chmod(0o600)
            config = {'restic': shutil.which('restic'), 'bash': shutil.which('bash'),
                      'stateDirectory': str(root / 'state'), 'environmentFile': str(envfile),
                      'retentionKeepTags': ['archive']}
            (root / 'state').mkdir()
            env = cleanup.environment(config)
            env = {k:v for k,v in env.items() if not k.startswith(('AWS_', 'B2_'))}
            def restic(*args):
                return subprocess.run([config['restic'], *args], env=env, check=True,
                                      capture_output=True, text=True).stdout
            restic('init')
            ids = []
            for day, value in [(1, 'archived phone photo'), (2, 'ordinary old data'), (3, 'latest data')]:
                (home / 'phone.txt').write_text(value)
                args = ['backup', '--host', 'synthetic-host', '--time', f'2020-01-0{day} 12:00:00']
                if day == 1:
                    args += ['--tag', 'archive', '--tag', 'archive-backup-s22-bem']
                restic(*args, str(home))
                ids.append(json.loads(restic('snapshots', '--json'))[-1]['id'])
            options = cleanup.parser().parse_args(['--config', '/unused', '--keep-last', '1'])
            subprocess.run(cleanup.command(config, options), env=env, check=True, capture_output=True)
            self.assertEqual(len(json.loads(restic('snapshots', '--json'))), 3)
            options.apply = True
            subprocess.run(cleanup.command(config, options), env=env, check=True, capture_output=True)
            remaining = {s['id'] for s in json.loads(restic('snapshots', '--json'))}
            self.assertEqual(remaining, {ids[0], ids[2]})
            self.assertEqual(restic('dump', ids[0], str(home / 'phone.txt')), 'archived phone photo')


if __name__ == '__main__':
    unittest.main()
