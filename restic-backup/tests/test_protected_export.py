import importlib.util
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'protected-export.py'
spec = importlib.util.spec_from_file_location('protected_export', SCRIPT)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


@unittest.skipUnless(Path('/proc/self/fd').is_dir(), 'Linux descriptor paths required')
class ProtectedExportTests(unittest.TestCase):
    def test_archive_roundtrip_reuse_and_refresh(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / 'source'
            source.mkdir()
            (source / 'identity').write_bytes(b'synthetic identity')
            (source / 'cache').mkdir()
            (source / 'cache/data').write_bytes(b'disposable')
            output = root / 'output'
            output.mkdir(mode=0o750)
            config = {'directory': str(output), 'gid': os.getgid(), 'sources': [
                {'path': str(source), 'name': 'state', 'directory': True, 'ignore': ['cache']}
            ]}
            exporter.export(config)
            manifest = json.loads((output / 'manifest.json').read_text())
            with tarfile.open(output / 'state.tar') as archive:
                member = str(source / 'identity').lstrip('/')
                self.assertEqual(archive.extractfile(member).read(), b'synthetic identity')
                self.assertFalse(any('/cache' in p for p in archive.getnames()))
            exporter.export(config)
            self.assertEqual((output / 'state.tar').stat().st_mtime_ns, manifest['sources'][0]['mtime_ns'])
            (source / 'identity').write_bytes(b'updated synthetic identity')
            exporter.export(config)
            self.assertNotEqual((output / 'state.tar').stat().st_mtime_ns, manifest['sources'][0]['mtime_ns'])

    def test_symlink_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'original').write_bytes(b'synthetic')
            (root / 'link').symlink_to(root / 'original')
            with self.assertRaises(OSError):
                exporter.open_path(root / 'link')

    def test_running_database_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / 'out'
            output.mkdir(mode=0o750)
            config = {'directory': str(output), 'gid': os.getgid(), 'sources': [
                {'path': '/unused', 'name': 'db', 'stoppedContainer': 'synthetic-postgis'}
            ]}
            with patch.object(exporter.subprocess, 'run') as command:
                command.return_value.stdout = 'true\n'
                with self.assertRaisesRegex(RuntimeError, 'container is running'):
                    exporter.export(config)
            self.assertFalse((output / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
