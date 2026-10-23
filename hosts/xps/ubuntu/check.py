"""Read-only host inspection and candidate SSH validation for xps-host."""

import argparse
import difflib
import json
import importlib.util
import pathlib
import platform
import stat
import subprocess
import sys
import tempfile

SOURCE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('xps_pam_check', SOURCE / 'pam_check.py')
pam_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pam_check)
STARTUP_SPEC = importlib.util.spec_from_file_location('xps_nix_startup', SOURCE / 'nix_startup.py')
nix_startup = importlib.util.module_from_spec(STARTUP_SPEC)
STARTUP_SPEC.loader.exec_module(nix_startup)


def policies(source=SOURCE):
    return json.loads((source / 'policies.json').read_text())


def guarded_path(path, uid=0):
    """Refuse symlink traversal and writable/untrusted ancestors."""
    for entry in reversed([path, *path.parents]):
        if not entry.exists() and not entry.is_symlink():
            continue
        metadata = entry.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f'Refusing symlink: {entry}')
        if metadata.st_uid != uid or metadata.st_mode & 0o022:
            raise ValueError(f'Unexpected owner or writable path: {entry}')
    if path.exists() and not path.is_file():
        raise ValueError(f'Expected a regular file: {path}')


def compare(source=SOURCE, root=pathlib.Path('/'), uid=0, gid=0, guard=True):
    result = []
    for item in policies(source):
        target = root / item['path'].lstrip('/')
        if guard:
            guarded_path(target, uid)
        expected = (source / 'files' / item['source']).read_bytes()
        actual = target.read_bytes() if target.exists() else None
        metadata = target.stat() if target.exists() else None
        mode = stat.S_IMODE(metadata.st_mode) if metadata else None
        match = actual == expected and mode == int(item['mode'], 8)
        match = match and metadata.st_uid == uid and metadata.st_gid == gid
        diff = ''
        if actual != expected:
            try:
                diff = ''.join(difflib.unified_diff(
                    (actual or b'').decode().splitlines(keepends=True),
                    expected.decode().splitlines(keepends=True),
                    fromfile=item['path'], tofile=item['path'] + ' (declared)',
                ))
            except UnicodeDecodeError:
                diff = 'Binary asset differs from the declared file.\n'
        result.append({
            'path': item['path'], 'matches': bool(match), 'exists': actual is not None,
            'mode': f'{mode:04o}' if mode is not None else None,
            'diff': diff,
        })
    return result


def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True).stdout


def ssh_preflight(source=SOURCE):
    main = pathlib.Path('/etc/ssh/sshd_config')
    guarded_path(main)
    text = main.read_text()
    include = 'Include /etc/ssh/sshd_config.d/*.conf'
    if text.count(include) != 1:
        raise ValueError('Expected one Ubuntu SSH drop-in Include; review this host first')
    with tempfile.TemporaryDirectory(prefix='xps-host-ssh-') as scratch:
        directory = pathlib.Path(scratch)
        key = directory / 'host-key'
        run('/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key))
        includes = directory / 'sshd_config.d'
        includes.mkdir()
        for path in pathlib.Path('/etc/ssh/sshd_config.d').glob('*.conf'):
            guarded_path(path)
            (includes / path.name).write_bytes(path.read_bytes())
        policy = next(p for p in policies(source) if p['name'] == 'ssh')
        (includes / pathlib.Path(policy['path']).name).write_bytes(
            (source / 'files' / policy['source']).read_bytes())
        candidate = directory / 'sshd_config'
        candidate.write_text(text.replace(include, 'Include ' + str(includes / '*.conf')))

        def effective(config):
            output = run('/usr/sbin/sshd', '-T', '-f', str(config), '-h', str(key))
            return dict(line.split(' ', 1) for line in output.splitlines())

        before = effective(main)
        after = effective(candidate)
        if after != dict(before, x11forwarding='no'):
            raise ValueError('Candidate changes SSH policy beyond X11 forwarding; review required')
        return {key: after[key] for key in [
            'port', 'permitrootlogin', 'passwordauthentication',
            'kbdinteractiveauthentication', 'allowagentforwarding',
            'allowtcpforwarding', 'x11forwarding',
        ]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    release = {}
    for line in pathlib.Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            release[key] = value.strip('"')
    if release.get('ID') != 'ubuntu' or release.get('VERSION_ID') != '22.04' or platform.machine() != 'x86_64':
        raise ValueError('This profile is reviewed for Ubuntu 22.04 on x86_64; review before extending it')
    result = compare()
    effective = ssh_preflight()
    authentication = authentication_preflight()
    startup = nix_startup.inspect()
    startup['validation'] = nix_startup.native_validation()
    print(json.dumps({'files': result, 'ssh_candidate_policy': effective,
                      'authentication': authentication, 'nix_startup': startup}, indent=2))
    if not args.preflight and (any(not item['matches'] for item in result) or startup['would_change']):
        raise SystemExit(1)


def authentication_preflight(source=SOURCE):
    requirements = json.loads((source / 'authentication-packages.json').read_text())
    installed = {}
    for package in requirements:
        value = run('/usr/bin/dpkg-query', '-W', '-f=${db:Status-Status}\t${Version}', package)
        state, version = value.split('\t')
        if state != 'installed':
            raise ValueError(f'Install the documented prerequisite first: {package}')
        installed[package] = version
    for name in ['login', 'common-auth', 'common-account', 'common-session', 'common-password']:
        path = pathlib.Path('/etc/pam.d') / name
        guarded_path(path)
        if not path.is_file():
            raise ValueError(f'Missing standard PAM include: {path}')
    module = pathlib.Path('/lib/x86_64-linux-gnu/security/pam_fprintd.so')
    # /lib is Ubuntu's normal usr-merge symlink; guard its resolved location.
    guarded_path(module.resolve())
    if not module.is_file():
        raise ValueError('libpam-fprintd must provide pam_fprintd.so')
    cases = pam_check.verify(source / 'files')
    return {'packages': installed, 'synthetic_pam_cases_passed': cases,
            'biometric_enrollment': 'not read or changed; enroll separately with fprintd-enroll'}


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        print('xps-host: native validation failed: ' + error.stderr.strip(), file=sys.stderr)
        raise SystemExit(2)
    except (OSError, ValueError) as error:
        print('xps-host: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
