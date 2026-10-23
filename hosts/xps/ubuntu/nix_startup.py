"""Restore the selected Nix systemd definitions without depending on Nix itself."""

import argparse
import base64
import hashlib
import json
import os
import pathlib
import platform
import shutil
import stat
import subprocess
import sys
import tempfile

SOURCE = pathlib.Path(__file__).resolve().parent
PATHS = {
    '/etc/systemd/system/nix-daemon.service',
    '/etc/systemd/system/nix-daemon.socket',
    '/etc/systemd/system/sockets.target.wants/nix-daemon.socket',
    '/etc/systemd/system/custom-start-nix-in-other-partition.service',
    '/etc/systemd/system/multi-user.target.wants/custom-start-nix-in-other-partition.service',
}


def scope(root, fixture):
    root = pathlib.Path(root)
    if fixture:
        if root.parent != pathlib.Path('/tmp') or not root.name.startswith('xps-nix-test-'):
            raise ValueError('Fixture must be a disposable /tmp/xps-nix-test-* directory')
        return root, os.getuid(), os.getgid()
    if root != pathlib.Path('/'):
        raise ValueError('Unexpected host root')
    return root, 0, 0


def manifest():
    items = json.loads((SOURCE / 'nix-startup.json').read_text())
    if {p['path'] for p in items} != PATHS or len(items) != len(PATHS):
        raise ValueError('Unexpected Nix startup scope')
    return items


def trusted_directory(path, root, uid, gid):
    if root not in [path, *path.parents]:
        raise ValueError('Path escapes the selected root')
    entries = []
    while True:
        entries.append(path)
        if path == root:
            break
        path = path.parent
    for entry in reversed(entries):
        if not entry.exists() and not entry.is_symlink():
            continue
        info = entry.lstat()
        if not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid) != (uid, gid) or info.st_mode & 0o022:
            raise ValueError(f'Untrusted directory: {entry}')


def snapshot(path, uid, gid):
    if not path.exists() and not path.is_symlink():
        return None
    info = path.lstat()
    if (info.st_uid, info.st_gid) != (uid, gid):
        raise ValueError(f'Unexpected ownership: {path}')
    metadata = {'uid': uid, 'gid': gid, 'mode': stat.S_IMODE(info.st_mode)}
    if stat.S_ISLNK(info.st_mode):
        return dict(metadata, kind='link', target=os.readlink(path))
    if not stat.S_ISREG(info.st_mode) or info.st_size > 262144:
        raise ValueError(f'Unexpected file type or size: {path}')
    return dict(metadata, kind='file', data=base64.b64encode(path.read_bytes()).decode())


def ensure_directory(path, root, uid, gid):
    trusted_directory(path, root, uid, gid)
    if path.exists():
        return
    ensure_directory(path.parent, root, uid, gid)
    path.mkdir(mode=0o755)
    os.chmod(path, 0o755)
    os.chown(path, uid, gid)


def desired(root, uid, gid):
    result = {}
    for item in manifest():
        name = item['path']
        if item['kind'] == 'file':
            payload = (SOURCE / 'nix-units' / item['source']).read_bytes()
            result[name] = {'kind': 'file', 'uid': uid, 'gid': gid, 'mode': 0o644,
                            'data': base64.b64encode(payload).decode()}
        elif item['kind'] == 'link':
            result[name] = {'kind': 'link', 'uid': uid, 'gid': gid, 'mode': 0o777,
                            'target': str(root / item['target'].lstrip('/'))}
        else:
            result[name] = None
    return result


def current(root, uid, gid, review=True):
    result = {}
    for item in manifest():
        name = item['path']
        path = root / name.lstrip('/')
        trusted_directory(path.parent, root, uid, gid)
        state = snapshot(path, uid, gid)
        if review and state is not None:
            if state['kind'] == 'link':
                targets = list(item.get('legacy_targets', []))
                if item['kind'] == 'link':
                    targets.append(item['target'])
                # Prefix expected absolute targets inside disposable fixtures.
                allowed = {str(root / target.lstrip('/')) for target in targets}
                if state['target'] not in allowed:
                    raise ValueError(f'Unreviewed symlink target: {path}')
            elif item['kind'] == 'link':
                raise ValueError(f'Expected an enablement symlink: {path}')
            elif item['kind'] == 'absent':
                digest = hashlib.sha256(base64.b64decode(state['data'], validate=True)).hexdigest()
                if digest != item.get('legacy_sha256'):
                    raise ValueError(f'Unreviewed obsolete unit: {path}')
        result[name] = state
    return result


def inspect(root=pathlib.Path('/'), fixture=False):
    root, uid, gid = scope(root, fixture)
    before, after = current(root, uid, gid), desired(root, uid, gid)
    return {'files': [{'path': name, 'matches': before[name] == after[name],
                       'existing_kind': before[name]['kind'] if before[name] else None,
                       'desired_kind': after[name]['kind'] if after[name] else None}
                      for name in sorted(PATHS)],
            'would_change': before != after, 'changed': False}


def native_validation():
    release = pathlib.Path('/etc/os-release').read_text()
    if '\nID=ubuntu\n' not in '\n' + release or 'VERSION_ID="22.04"' not in release or platform.machine() != 'x86_64':
        raise ValueError('Review Nix startup policies before using another OS/architecture')
    executable = pathlib.Path('/nix/var/nix/profiles/default/bin/nix-daemon')
    resolved = executable.resolve(strict=True)
    info = resolved.stat()
    if info.st_uid != 0 or info.st_mode & 0o022 or not os.access(resolved, os.X_OK):
        raise ValueError('Install a trusted multi-user Nix profile first')
    with tempfile.TemporaryDirectory(prefix='xps-nix-verify-') as directory:
        units = []
        for name in ['nix-daemon.service', 'nix-daemon.socket']:
            path = pathlib.Path(directory) / name
            path.write_bytes((SOURCE / 'nix-units' / name).read_bytes())
            units.append(str(path))
        proc = subprocess.run(['/usr/bin/systemd-analyze', 'verify', '--man=no', *units],
                              text=True, capture_output=True, check=True)
    return {'systemd_analyze_verify': 'passed', 'diagnostics': proc.stdout + proc.stderr}


def write_state(path, state, root, uid, gid):
    trusted_directory(path.parent, root, uid, gid)
    if state is None:
        path.unlink(missing_ok=True)
        return
    ensure_directory(path.parent, root, uid, gid)
    fd, temporary = tempfile.mkstemp(prefix='.xps-nix-', dir=path.parent)
    try:
        if state['kind'] == 'file':
            with os.fdopen(fd, 'wb') as stream:
                stream.write(base64.b64decode(state['data'], validate=True))
                os.fchmod(stream.fileno(), state['mode'])
                os.fchown(stream.fileno(), state['uid'], state['gid'])
                stream.flush()
                os.fsync(stream.fileno())
        else:
            os.close(fd)
            os.unlink(temporary)
            os.symlink(state['target'], temporary)
            os.chown(temporary, state['uid'], state['gid'], follow_symlinks=False)
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def reload_systemd(fixture):
    if not fixture:
        subprocess.run(['/usr/bin/systemctl', 'daemon-reload'], check=True, capture_output=True, text=True)


def restore_states(states, root, uid, gid):
    # Restore definitions before enablement links.
    for name in sorted(PATHS, key=lambda n: ('.wants/' in n, n)):
        write_state(root / name.lstrip('/'), states[name], root, uid, gid)


def validate_record(states, uid, gid):
    if set(states) != PATHS:
        raise ValueError('Unexpected rollback scope')
    for item in states.values():
        if item is None:
            continue
        if (item.get('uid'), item.get('gid')) != (uid, gid):
            raise ValueError('Unexpected rollback ownership')
        if item.get('kind') == 'file':
            payload = base64.b64decode(item['data'], validate=True)
            if len(payload) > 262144 or not isinstance(item['mode'], int) or not 0 <= item['mode'] <= 0o777:
                raise ValueError('Invalid rollback file')
        elif item.get('kind') == 'link':
            if not isinstance(item.get('target'), str) or not item['target'].startswith('/') or '\0' in item['target']:
                raise ValueError('Invalid rollback link')
        else:
            raise ValueError('Unexpected rollback file type')


def apply(root=pathlib.Path('/'), fixture=False):
    root, uid, gid = scope(root, fixture)
    if not fixture and os.geteuid() != 0:
        raise ValueError('Use sudo for Nix startup application')
    before, after = current(root, uid, gid), desired(root, uid, gid)
    if before == after:
        return dict(inspect(root, fixture), backup=None)
    backups = root / 'var/backups'
    trusted_directory(backups, root, uid, gid)
    ensure_directory(backups, root, uid, gid)
    backup = pathlib.Path(tempfile.mkdtemp(prefix='xps-nix-startup-', dir=backups))
    record = {'before': before, 'after': after}
    (backup / 'state.json').write_text(json.dumps(record, indent=2) + '\n')
    (backup / 'state.json').chmod(0o600)
    shutil.copyfile(__file__, backup / 'nix_startup.py')
    (backup / 'nix_startup.py').chmod(0o600)
    assert json.loads((backup / 'state.json').read_text()) == record
    assert current(root, uid, gid) == before, 'Nix startup files changed during backup'
    try:
        restore_states(after, root, uid, gid)
        assert current(root, uid, gid) == after, 'Nix startup convergence failed'
        reload_systemd(fixture)
    except BaseException:
        restore_states(before, root, uid, gid)
        reload_systemd(fixture)
        raise
    return dict(inspect(root, fixture), changed=True, backup=str(backup),
                rollback=f'sudo /usr/bin/python3 -I {backup}/nix_startup.py rollback {backup}')


def rollback(backup, root=pathlib.Path('/'), fixture=False):
    root, uid, gid = scope(root, fixture)
    if not fixture and os.geteuid() != 0:
        raise ValueError('Use sudo for rollback')
    backup = pathlib.Path(backup)
    trusted_directory(backup, root, uid, gid)
    record_path = backup / 'state.json'
    if record_path.is_symlink() or not record_path.is_file() or record_path.stat().st_mode & 0o077 or (record_path.stat().st_uid, record_path.stat().st_gid) != (uid, gid):
        raise ValueError('Use the private backup record')
    record = json.loads(record_path.read_text())
    validate_record(record['before'], uid, gid)
    validate_record(record['after'], uid, gid)
    # Reject a rollback over subsequent administrator changes.
    live = {}
    for name in PATHS:
        path = root / name.lstrip('/')
        trusted_directory(path.parent, root, uid, gid)
        live[name] = snapshot(path, uid, gid)
    if live != record['after']:
        raise ValueError('Startup state changed since this backup; review before rollback')
    restore_states(record['before'], root, uid, gid)
    reload_systemd(fixture)
    return {'restored': True, 'backup': str(backup)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['check', 'plan', 'apply', 'rollback'], nargs='?', default='check')
    parser.add_argument('backup', nargs='?', type=pathlib.Path)
    args = parser.parse_args()
    if args.mode == 'rollback':
        if args.backup is None:
            parser.error('rollback requires its printed backup directory')
        result = rollback(args.backup)
    else:
        validation = native_validation()
        result = apply() if args.mode == 'apply' else inspect()
        result['validation'] = validation
    print(json.dumps(result, indent=2))
    if args.mode == 'check' and result['would_change']:
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, AssertionError, subprocess.CalledProcessError) as error:
        print(f'xps-nix-startup: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        raise SystemExit(2)
