"""Run with python3 -m unittest discover -s hosts/xps/tests."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('alacritty_launcher', ROOT / 'alacritty-launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class AlacrittyLauncherTests(unittest.TestCase):
    def test_command_forms_keep_arguments_literal(self):
        for flag in ['-e', '--command', '-e/bin/echo', '--command=/bin/echo']:
            with self.subTest(flag=flag):
                args = [flag, '/bin/echo'] if flag in ['-e', '--command'] else [flag]
                args += ['space in argument', '--literal', '; no shell expansion']
                actual = launcher.wrap_command(args, 'child-helper')
                self.assertEqual(actual[-5:], ['child-helper', '/bin/echo', 'space in argument', '--literal', '; no shell expansion'])

    def test_value_options_and_double_dash_are_not_commands(self):
        args = ['--title', '-e', '--class', 'example', '-e', '/bin/echo', 'hello']
        self.assertEqual(launcher.wrap_command(args, 'helper'), args[:5] + ['helper'] + args[5:])
        args = ['--', '-e', 'literal']
        self.assertEqual(launcher.wrap_command(args, 'helper'), args)

    def invoke(self, *args):
        with patch.object(sys, 'argv', ['alacritty', *args]), patch.object(launcher.os, 'execve') as execute:
            launcher.main()
            return execute.call_args.args

    def test_subcommand_is_not_swallowed_by_variadic_option(self):
        _, args, _ = self.invoke('msg', 'create-window', '--help')
        self.assertEqual(args[1:], ['msg', 'create-window', '--help'])

    def test_default_shell_is_one_atomic_option(self):
        _, args, _ = self.invoke('--title', 'test')
        self.assertEqual(args.count('--option'), 1)
        self.assertIn('program=', args[2])
        self.assertIn('args=', args[2])

    def test_ipc_explicit_command_is_wrapped(self):
        _, args, _ = self.invoke('msg', 'create-window', '-e', '/bin/echo', 'a b')
        self.assertEqual(args[1:], ['msg', 'create-window', '-e', '@cleanChild@', '/bin/echo', 'a b'])

    def test_child_restores_set_unset_and_empty_values(self):
        original = {name: None for name in launcher.GRAPHICS_VARIABLES}
        original['LD_LIBRARY_PATH'] = '/custom path:/another'
        original['LIBVA_DRIVERS_PATH'] = ''
        env = os.environ.copy()
        env.update({name: 'injected-by-nixgl' for name in original})
        env[launcher.MARKER] = json.dumps(original)
        env['ALACRITTY_TEST_UNRELATED'] = 'preserved'
        code = 'import os,json; print(json.dumps({k:os.environ.get(k) for k in ' + repr([*original, launcher.MARKER, 'ALACRITTY_TEST_UNRELATED']) + '}))'
        actual = json.loads(subprocess.check_output([sys.executable, str(ROOT / 'alacritty-child-env.py'), sys.executable, '-c', code], env=env, text=True))
        self.assertEqual({k: actual[k] for k in original}, original)
        self.assertIsNone(actual[launcher.MARKER])
        self.assertEqual(actual['ALACRITTY_TEST_UNRELATED'], 'preserved')


if __name__ == '__main__':
    unittest.main()
