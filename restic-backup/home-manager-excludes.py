#!/usr/bin/env python3
"""Exclude only currently installed Home Manager symlinks; read no file contents."""
import argparse
import os
from pathlib import Path
import tempfile


def managed_paths(home):
    generations = [
        home / '.local/state/home-manager/gcroots/current-home/home-files',
        home / '.local/state/nix/profiles/home-manager/home-files',
        Path('/nix/var/nix/profiles/per-user') / home.name / 'home-manager/home-files',
    ]
    managed = set()
    for generation in generations:
        if not generation.is_dir():
            continue
        for directory, dirs, files in os.walk(generation, followlinks=False):
            for name in list(dirs):
                if (Path(directory) / name).is_symlink():
                    dirs.remove(name)
                    files.append(name)
            for name in files:
                source = Path(directory) / name
                actual = home / source.relative_to(generation)
                try:
                    # A regular file replacing a managed link is local user data.
                    # Do not exclude it, or a symlink pointing to a different file.
                    if actual.is_symlink() and actual.samefile(source):
                        managed.add(str(actual))
                except OSError:
                    continue
    return sorted(managed)


def literal_pattern(path):
    # Restic expands environment variables in exclude files and interprets globs.
    return ''.join('$$' if c == '$' else '\\' + c if c in '\\*?[' else c for c in path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = [p for p in managed_paths(args.home) if '\n' not in p and '\r' not in p]
    content = '# Generated before each backup from installed Home Manager symlinks.\n'
    content += '# Edit Home Manager sources, not this generated list.\n'
    content += ''.join(literal_pattern(p) + '\n' for p in paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=args.output.parent, delete=False) as temp:
        temp.write(content)
        temporary = temp.name
    os.replace(temporary, args.output)
    print(f'Home Manager: excluding {len(paths)} currently managed paths.')


if __name__ == '__main__':
    main()
