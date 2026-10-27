"""Run project-owned regression suites with synthetic data and no live session."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SUITES = ('restic-backup/tests', 'xps-desktop/tests', 'hosts/xps/tests', 'hardware-health/tests')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    for key in list(os.environ):
        if key.startswith(('RESTIC_', 'AWS_', 'B2_', 'RCLONE_')) or key in (
            'SSH_AUTH_SOCK', 'DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
            'WAYLAND_DISPLAY',
        ):
            del os.environ[key]
    for executable in ('bash', 'restic'):
        if not shutil.which(executable):
            parser.error(f'{executable} is required; integration tests must not silently skip')
    results = []
    success = True
    for relative in SUITES:
        path = ROOT / relative
        suite = unittest.TestLoader().discover(str(path), top_level_dir=str(path))
        if suite.countTestCases() == 0:
            raise RuntimeError(f'No tests discovered in {relative}')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        unexpected_skips = [
            (test.id(), reason) for test, reason in result.skipped
            if not (sys.platform == 'darwin'
                    and test.id().startswith('test_protected_export.ProtectedExportTests.')
                    and reason == 'Linux descriptor paths required')
        ]
        passed = result.wasSuccessful() and not unexpected_skips
        results.append({
            'suite': relative,
            'tests': result.testsRun,
            'skips': [{'test': test.id(), 'reason': reason} for test, reason in result.skipped],
            'failures': len(result.failures),
            'errors': len(result.errors),
            'unexpectedSkips': unexpected_skips,
            'passed': passed,
        })
        success = success and passed
    args.report.write_text(json.dumps({
        'platform': sys.platform,
        'python': sys.version.split()[0],
        'suites': results,
        'passed': success,
    }, indent=2) + '\n')
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
