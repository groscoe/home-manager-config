"""Scope NixGL to Alacritty while preserving its PTY commands' environment."""
import json
import os
import sys

MARKER = 'XPS_ALACRITTY_ORIGINAL_GL_ENV'
GRAPHICS_VARIABLES = (
    'GBM_BACKENDS_PATH', 'LIBGL_DRIVERS_PATH', 'LIBVA_DRIVERS_PATH',
    '__EGL_VENDOR_LIBRARY_FILENAMES', 'LD_LIBRARY_PATH',
)
VALUE_OPTIONS = {
    '-T', '--title', '--class', '--config-file', '--socket',
    '--working-directory', '--embed', '--tabbing-identifier', '-o', '--option',
}


def wrap_command(arguments, helper):
    """The command flag consumes all remaining arguments; keep those literal."""
    index = 0
    while index < len(arguments):
        value = arguments[index]
        if value == '--':
            break
        if value in VALUE_OPTIONS:
            index += 2
            continue
        if value in ('-e', '--command') and index + 1 < len(arguments):
            return arguments[:index + 1] + [helper] + arguments[index + 1:]
        if value.startswith('--command=') and value != '--command=':
            return arguments[:index] + ['--command', helper, value.split('=', 1)[1]] + arguments[index + 1:]
        if value.startswith('-e') and not value.startswith('--') and len(value) > 2:
            return arguments[:index] + ['-e', helper, value[2:]] + arguments[index + 1:]
        index += 1
    return arguments


def main():
    helper = '@cleanChild@'
    environment = os.environ.copy()
    environment[MARKER] = json.dumps({key: environment.get(key) for key in GRAPHICS_VARIABLES})
    # The host already uses Fish. Declare its Nix implementation for the
    # default PTY as well as restoring explicit -e/--command invocations.
    defaults = [
        '--option', 'terminal.shell={ program=' + json.dumps(helper)
        + ', args=' + json.dumps(['@fish@', '--login']) + ' }',
    ]
    arguments = sys.argv[1:]
    # --option takes multiple values. A leading positional subcommand would
    # otherwise be swallowed as another option value (e.g. msg create-window).
    if arguments and not arguments[0].startswith('-'):
        defaults = []
    binary = '@wrappedAlacritty@'
    os.execve(binary, [binary, *defaults, *wrap_command(arguments, helper)], environment)


if __name__ == '__main__':
    main()
