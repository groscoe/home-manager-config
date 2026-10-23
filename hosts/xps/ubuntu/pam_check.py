"""Exercise declared PAM control flow using libpam and isolated synthetic policies.

pam_start_confdir selects temporary service files; absolute includes keep older
Ubuntu libpam versions inside the same temporary directory as well.
Only synthetic pam_exec modules run; no real password or biometric is used.
"""

import argparse
import ctypes as c
import json
import pathlib
import re
import sys
import tempfile

HOST_LIBRARY = '/lib/x86_64-linux-gnu/libpam.so.0'
HOST_MODULES = '/lib/x86_64-linux-gnu/security'


def verify(files, library=HOST_LIBRARY, modules=HOST_MODULES, only=None, candidate=None):
    lib = c.CDLL(str(library))
    callback = c.CFUNCTYPE(c.c_int, c.c_int, c.c_void_p, c.c_void_p, c.c_void_p)

    @callback
    def conversation(*args):
        return 19  # Refuse any unexpected credential prompt.

    class Conversation(c.Structure):
        _fields_ = [('conv', callback), ('appdata_ptr', c.c_void_p)]

    conv = Conversation(conversation, None)
    lib.pam_start_confdir.argtypes = [c.c_char_p, c.c_char_p, c.POINTER(Conversation), c.c_char_p, c.POINTER(c.c_void_p)]
    for name in ['pam_authenticate', 'pam_acct_mgmt', 'pam_end']:
        getattr(lib, name).argtypes = [c.c_void_p, c.c_int]
    # maintenance, root, password, fingerprint, original, account, success, steps
    cases = [
        ('password', 0, 0, 0, 1, 0, 0, True, ['maintenance', 'root', 'password', 'original', 'gnome-keyring', 'kwallet', 'account']),
        ('original-auth-rejects', 0, 0, 0, 1, 1, 0, False, ['maintenance', 'root', 'password', 'original']),
        ('fingerprint', 0, 0, 1, 0, 1, 0, True, ['maintenance', 'root', 'password', 'fingerprint', 'account']),
        ('scanner-rejects-password-fallback', 0, 0, 1, 1, 0, 0, True, ['maintenance', 'root', 'password', 'fingerprint', 'original', 'gnome-keyring', 'kwallet', 'account']),
        ('both-reject', 0, 0, 1, 1, 1, 0, False, ['maintenance', 'root', 'password', 'fingerprint', 'original']),
        ('maintenance-rejects', 1, 0, 0, 0, 0, 0, False, ['maintenance']),
        ('root-password-rejected', 0, 1, 0, 0, 0, 0, False, ['maintenance', 'root', 'password', 'original', 'gnome-keyring', 'kwallet']),
        ('root-fingerprint-rejected', 0, 1, 1, 0, 1, 0, False, ['maintenance', 'root', 'password', 'fingerprint', 'original']),
        ('scanner-unavailable-password-fallback', 0, 0, 1, None, 0, 0, True, ['maintenance', 'root', 'password', 'original', 'gnome-keyring', 'kwallet', 'account']),
        ('account-rejects-fingerprint', 0, 0, 1, 0, 1, 1, False, ['maintenance', 'root', 'password', 'fingerprint', 'account']),
    ]
    passed = []
    with tempfile.TemporaryDirectory(prefix='xps-host-pam-') as directory:
        root = pathlib.Path(directory)
        steps = root / 'steps'
        script = root / 'step.py'
        script.write_text('import pathlib,sys\nwith pathlib.Path(sys.argv[1]).open("a") as f: f.write(sys.argv[2]+"\\n")\nraise SystemExit(int(sys.argv[3]))\n')

        def stub(label, status):
            if status is None:
                return str(root / 'missing-module.so')
            return f'{modules}/pam_exec.so quiet {sys.executable} -I {script} {steps} {label} {status}'

        for service in ['i3lock', 'sddm']:
            if only and service != only:
                continue
            text = (candidate or files / (service + '.pam')).read_text()
            for name, maintenance, root_status, password, fingerprint, original, account, success, expected in cases:
                if service == 'i3lock' and (root_status or account):
                    continue
                statuses = dict(maintenance=maintenance, root=root_status, password=password,
                                fingerprint=fingerprint, original=original, account=account,
                                **{'gnome-keyring': 0, 'kwallet': 0})
                module_labels = {'pam_nologin.so': 'maintenance', 'pam_succeed_if.so': 'root',
                                 'pam_unix.so': 'password', 'pam_fprintd.so': 'fingerprint',
                                 'pam_gnome_keyring.so': 'gnome-keyring', 'pam_kwallet5.so': 'kwallet'}
                reviewed_options = {'pam_nologin.so': '',
                                    'pam_succeed_if.so': 'user != root quiet_success',
                                    'pam_unix.so': 'nodelay',
                                    'pam_fprintd.so': 'max-tries=3 timeout=10',
                                    'pam_gnome_keyring.so': '', 'pam_kwallet5.so': ''}
                transformed = []
                for raw in text.splitlines():
                    line = raw.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith('@include '):
                        if line not in ['@include common-auth', '@include common-account',
                                        '@include common-session', '@include common-password']:
                            raise ValueError(f'Unreviewed PAM include: {line}')
                        if line in ['@include common-auth', '@include common-account']:
                            group = 'auth' if line.endswith('common-auth') else 'account'
                            # Debian's @include is an extension; use equivalent
                            # typed includes for these single-group test stacks.
                            transformed.append(f'{group} include {root / line.split()[1]}')
                        continue
                    match = re.fullmatch(r'(-?\w+)\s+(\[[^\]]+\]|\S+)\s+(\S+)(?:\s+(.*))?', line)
                    if not match:
                        raise ValueError(f'Unrecognized PAM line: {line}')
                    kind, control, module, options = match.groups()
                    if kind.lstrip('-') not in ['auth', 'account', 'session', 'password']:
                        raise ValueError(f'Unreviewed PAM group: {kind}')
                    if kind.lstrip('-') not in ['auth', 'account']:
                        continue
                    if control == 'include' and module == 'login':
                        transformed.append(f'{kind} {control} {root / "login"}')
                        continue
                    if module not in module_labels:
                        raise ValueError(f'Unreviewed PAM module: {module}')
                    if ' '.join((options or '').split()) != reviewed_options[module]:
                        raise ValueError(f'PAM options need review: {line}')
                    label = module_labels[module]
                    transformed.append(f'{kind} {control} {stub(label, statuses[label])}')
                (root / service).write_text('\n'.join(transformed) + '\n')
                (root / 'login').write_text(f'auth requisite {stub("original", original)}\n')
                (root / 'common-auth').write_text(f'auth requisite {stub("original", original)}\n')
                (root / 'common-account').write_text(f'account requisite {stub("account", account)}\n')
                (root / 'other').write_text(f'auth requisite {modules}/pam_deny.so\n')
                steps.write_text('')
                handle = c.c_void_p()
                result = lib.pam_start_confdir(service.encode(), b'groscoe', c.byref(conv), str(root).encode(), c.byref(handle))
                if result:
                    raise ValueError(f'PAM could not parse the synthetic {service} candidate: {result}')
                try:
                    result = lib.pam_authenticate(handle, 0)
                    if result == 0 and service == 'sddm':
                        result = lib.pam_acct_mgmt(handle, 0)
                finally:
                    lib.pam_end(handle, result)
                actual = steps.read_text().splitlines()
                wanted = expected if service == 'sddm' else [s for s in expected if s not in ['root', 'gnome-keyring', 'kwallet', 'account']]
                if (result == 0) != success or actual != wanted:
                    raise ValueError(f'{service}/{name}: PAM status {result}, steps {actual}, expected success={success}, steps={wanted}')
                passed.append(f'{service}/{name}')
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', default=HOST_LIBRARY)
    parser.add_argument('--modules', default=HOST_MODULES)
    parser.add_argument('--policy', choices=['i3lock', 'sddm'])
    parser.add_argument('--candidate', type=pathlib.Path)
    args = parser.parse_args()
    print(json.dumps({'passed': verify(pathlib.Path(__file__).parent / 'files', args.library,
                                      args.modules, args.policy, args.candidate)}, indent=2))
