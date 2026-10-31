import importlib.util
import sys
import types
import unittest
from unittest.mock import patch

# The launcher only needs the library when drawing/discovering entries.
sys.modules.setdefault('homepilib', types.ModuleType('homepilib'))
spec = importlib.util.spec_from_file_location('launcher', 'homepi.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

class UpdatePrivileges(unittest.TestCase):
    def run_update(self, uid):
        with patch.object(launcher.curses, 'endwin'), patch('builtins.input'), patch.object(launcher.os, 'geteuid', return_value=uid), patch.object(launcher.subprocess, 'run') as run:
            run.return_value.returncode = 0
            launcher.run_command(None, 'hpupdate --auto')
            return run.call_args

    def test_regular_user_gets_password_prompt_via_sudo(self):
        self.assertEqual(self.run_update(1001).args, (['sudo', '--', 'hpupdate', '--auto'],))
        self.assertEqual(self.run_update(1001).kwargs, {})

    def test_root_does_not_require_sudo(self):
        self.assertEqual(self.run_update(0).args, (['hpupdate', '--auto'],))

    def test_update_failure_is_visible(self):
        with patch.object(launcher.curses, 'endwin'), patch('builtins.input'), patch.object(launcher.os, 'geteuid', return_value=1001), patch.object(launcher.subprocess, 'run') as run, patch('builtins.print') as output:
            run.return_value.returncode = 1
            launcher.run_command(None, 'hpupdate --auto')
            output.assert_any_call('Command failed (exit 1).')

if __name__ == '__main__':
    unittest.main()
