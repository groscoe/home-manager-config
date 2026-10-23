"""Exercise real Ansible dry-run, convergence, metadata repair and backups."""

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile

SOURCE = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('host_check', SOURCE / 'check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def snapshot(root):
    return {
        str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode & 0o777)
        for p in root.rglob('*') if p.is_file()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ansible', required=True)
    parser.add_argument('--python', required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='xps-host-test-', dir='/tmp') as directory:
        root = pathlib.Path(directory)
        variables = {
            'xps_fixture': True, 'xps_root': str(root),
            'xps_owner': str(os.getuid()), 'xps_group': str(os.getgid()),
            'ansible_python_interpreter': args.python,
        }
        calls = []

        def ansible(*flags, success=True):
            proc = subprocess.run([
                args.ansible, '--inventory', 'localhost,', '--connection', 'local',
                '--extra-vars', json.dumps(variables), str(SOURCE / 'playbook.yml'), *flags,
            ], text=True, capture_output=True, timeout=120)
            calls.append({'flags': list(flags), 'returncode': proc.returncode})
            if success and proc.returncode:
                raise AssertionError(proc.stdout + proc.stderr)
            return proc.stdout + proc.stderr

        ansible('--syntax-check')
        for item in check.policies():
            target = root / item['path'].lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('X11Forwarding yes\n' if item['name'] == 'ssh' else '[Journal]\nSystemMaxUse=5G\n')
            target.chmod(0o600)
        before = snapshot(root)
        dry_run = ansible('--check', '--diff')
        assert snapshot(root) == before, 'Dry-run changed fixture files or made backups'
        assert 'X11Forwarding no' in dry_run and 'SystemMaxUse=1G' in dry_run, dry_run
        assert 'pam_fprintd.so' in dry_run and 'Use fingerprint' in dry_run, dry_run
        assert any(not p['matches'] for p in check.compare(root=root, uid=os.getuid(), gid=os.getgid(), guard=False))

        first = ansible('--diff')
        assert 'changed=0' not in first, first
        assert all(p['matches'] for p in check.compare(root=root, uid=os.getuid(), gid=os.getgid(), guard=False))

        for item in check.policies():
            target = root / item['path'].lstrip('/')
            backups = list(target.parent.glob(target.name + '.[0-9]*.*~'))
            assert len(backups) == 1, (target, backups)
            assert hashlib.sha256(backups[0].read_bytes()).hexdigest() == before[str(target.relative_to(root))][0]
        converged = snapshot(root)
        second = ansible()
        assert 'changed=0' in second, second
        assert snapshot(root) == converged, 'Second application changed files or generated new backups'
        image = next(p for p in check.policies() if p['source'].endswith('Mountain.jpg'))
        target = root / image['path'].lstrip('/')
        target.write_bytes(b'not the wallpaper')
        changed = next(p for p in check.compare(root=root, uid=os.getuid(), gid=os.getgid(), guard=False) if p['path'] == image['path'])
        assert not changed['matches'] and 'Binary asset differs' in changed['diff']
        ansible()
        assert all(p['matches'] for p in check.compare(root=root, uid=os.getuid(), gid=os.getgid(), guard=False))
        one = root / check.policies()[0]['path'].lstrip('/')
        one.chmod(0o600)
        ansible()
        assert one.stat().st_mode & 0o777 == 0o644
        assert all(p['matches'] for p in check.compare(root=root, uid=os.getuid(), gid=os.getgid(), guard=False))

        variables['xps_root'] = '/etc'
        invalid = ansible(success=False)
        assert 'Assertion failed' in invalid or 'assertion' in invalid.lower(), invalid
        assert calls[-1]['returncode'] != 0, calls
        print(json.dumps({
            'syntax': 'passed', 'dry_run_no_mutation': 'passed',
            'convergence': 'passed', 'backups_match_originals': 'passed',
            'second_run_unchanged': 'passed', 'permission_repair': 'passed',
            'fixture_escape_rejected': 'passed', 'calls': calls,
            'binary_theme_drift_and_repair': 'passed',
        }, indent=2))


if __name__ == '__main__':
    main()
