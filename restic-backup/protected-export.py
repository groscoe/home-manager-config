"""Export selected protected files locally; never connect to a backup repository."""
from pathlib import Path
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import tarfile
import time


def open_path(path, directory=False):
    """Pin every directory component without following user-controlled symlinks."""
    p = Path(path)
    assert p.is_absolute() and '..' not in p.parts
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for i, part in enumerate(p.parts[1:]):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if i < len(p.parts) - 2 or directory:
                flags |= os.O_DIRECTORY
            new = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = new
        return fd
    except BaseException:
        os.close(fd)
        raise


def inventory(fd, source):
    base = '/proc/self/fd/' + str(fd)
    items = []
    ignored = set(source.get('ignore', []))
    def add(p, relative):
        s = os.lstat(p)
        items.append((relative, s.st_mode, s.st_uid, s.st_gid, s.st_size,
                      s.st_mtime_ns, s.st_ctime_ns,
                      os.readlink(p) if stat.S_ISLNK(s.st_mode) else None))
    if stat.S_ISDIR(os.fstat(fd).st_mode):
        add(base + '/.', '.')
        def fail(error):
            raise error
        for directory, dirs, files in os.walk(base + '/.', followlinks=False, onerror=fail):
            relative = os.path.relpath(directory, base + '/.')
            for name in dirs[:]:
                if os.path.normpath(os.path.join(relative, name)) in ignored:
                    dirs.remove(name)
            for name in sorted(dirs + files):
                r = os.path.normpath(os.path.join(relative, name))
                if r not in ignored:
                    add(os.path.join(directory, name), r)
    else:
        s = os.fstat(fd)
        assert stat.S_ISREG(s.st_mode)
        items.append(('.', s.st_mode, s.st_uid, s.st_gid, s.st_size, s.st_mtime_ns, s.st_ctime_ns, None))
    return hashlib.sha256(json.dumps(sorted(items)).encode()).hexdigest()


def archive(fd, source, stream):
    name = source['path'].lstrip('/')
    ignored = set(source.get('ignore', []))
    def selected(member):
        relative = os.path.relpath(member.name, name)
        if relative in ignored or not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            return None
        return member
    with tarfile.open(fileobj=stream, mode='w', dereference=False) as tar:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            tar.add('/proc/self/fd/' + str(fd) + '/.', arcname=name, filter=selected)
        else:
            s = os.fstat(fd)
            assert stat.S_ISREG(s.st_mode)
            member = tarfile.TarInfo(name)
            member.size, member.mode = s.st_size, stat.S_IMODE(s.st_mode)
            member.uid, member.gid, member.mtime = s.st_uid, s.st_gid, s.st_mtime
            with os.fdopen(os.dup(fd), 'rb') as data:
                os.lseek(data.fileno(), 0, os.SEEK_SET)
                tar.addfile(member, data)


def write_atomic(directory, name, gid, writer):
    temporary = '.' + name + '.' + secrets.token_hex(8)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            writer(stream)
            stream.flush()
            os.fchown(stream.fileno(), os.geteuid(), gid)
            os.fchmod(stream.fileno(), 0o640)
            os.fsync(stream.fileno())
        os.rename(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def export(config):
    directory = open_path(config['directory'], directory=True)
    try:
        s = os.fstat(directory)
        assert s.st_uid == os.geteuid() and s.st_gid == config['gid'] and stat.S_IMODE(s.st_mode) == 0o750
        try:
            fd = os.open('manifest.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            with os.fdopen(fd) as stream:
                assert os.fstat(stream.fileno()).st_uid == os.geteuid()
                previous = json.load(stream)
        except FileNotFoundError:
            previous = {}
        records = []
        for source in config['sources']:
            if source.get('stoppedContainer'):
                result = subprocess.run(['/usr/bin/docker', 'inspect', '--format', '{{.State.Running}}',
                                         source['stoppedContainer']], capture_output=True, text=True, check=True)
                if result.stdout.strip() != 'false':
                    raise RuntimeError('Database container is running; a cold file archive is unsafe. Set up a database dump first.')
            fd = open_path(source['path'], directory=source.get('directory', False))
            try:
                fingerprint = inventory(fd, source)
                name = source['name'] + '.tar'
                old = next((r for r in previous.get('sources', []) if r['path'] == source['path']), {})
                try:
                    existing = os.stat(name, dir_fd=directory, follow_symlinks=False)
                    reusable = (stat.S_ISREG(existing.st_mode) and existing.st_uid == os.geteuid()
                                and existing.st_size == old.get('bytes') and existing.st_mtime_ns == old.get('mtime_ns')
                                and fingerprint == old.get('fingerprint'))
                except FileNotFoundError:
                    reusable = False
                if not reusable:
                    write_atomic(directory, name, config['gid'], lambda stream: archive(fd, source, stream))
                    if inventory(fd, source) != fingerprint:
                        raise RuntimeError('Protected source changed during export; retry before backing up.')
                current = os.stat(name, dir_fd=directory, follow_symlinks=False)
                records.append({'path': source['path'], 'archive': name, 'fingerprint': fingerprint,
                                'bytes': current.st_size, 'mtime_ns': current.st_mtime_ns})
            finally:
                os.close(fd)
        manifest = {'epoch': time.time(), 'sources': records}
        content = (json.dumps(manifest, indent=2) + '\n').encode()
        write_atomic(directory, 'manifest.json', config['gid'], lambda stream: stream.write(content))
        print('Protected export complete:', len(records), 'archives;', sum(r['bytes'] for r in records), 'bytes. No upload performed.')
    finally:
        os.close(directory)


if __name__ == '__main__':
    assert os.geteuid() == 0, 'Run through the protected system service.'
    config_path = Path('/etc/restic-protected-export.json')
    s = config_path.lstat()
    assert stat.S_ISREG(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022
    export(json.loads(config_path.read_text()))
