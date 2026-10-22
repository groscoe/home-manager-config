"""Restore the pre-NixGL environment before executing a terminal child."""
import json
import os
import sys

MARKER = 'XPS_ALACRITTY_ORIGINAL_GL_ENV'
GRAPHICS_VARIABLES = {
    'GBM_BACKENDS_PATH', 'LIBGL_DRIVERS_PATH', 'LIBVA_DRIVERS_PATH',
    '__EGL_VENDOR_LIBRARY_FILENAMES', 'LD_LIBRARY_PATH',
}

environment = os.environ.copy()
original = json.loads(environment.pop(MARKER, '{}'))
assert isinstance(original, dict) and set(original) <= GRAPHICS_VARIABLES
for key, value in original.items():
    assert value is None or isinstance(value, str)
    if value is None:
        environment.pop(key, None)
    else:
        environment[key] = value
if len(sys.argv) < 2:
    raise SystemExit('Missing terminal child command')
os.execvpe(sys.argv[1], sys.argv[1:], environment)
