import contextlib
import io
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import predict


class PredictTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = patch.object(predict.pwd, 'getpwuid', return_value=SimpleNamespace(pw_dir=self.tmp.name))
        self.home.start()
        self.addCleanup(self.home.stop)
        self.env = patch.dict(os.environ)
        self.env.start()
        os.environ.pop('SUDO_UID', None)
        self.addCleanup(self.env.stop)

    def run_predict(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = predict.main(list(args))
        return code, output.getvalue()

    def suggest(self, *args):
        with patch.object(predict, 'candidates', return_value=['echo', 'ls']):
            return self.run_predict('suggest', *args)

    def test_suggestion_and_literal_execution_once(self):
        payload = '$(touch /tmp/PREDICT-INJECTION); *'
        code, output = self.suggest('ehco', payload)
        self.assertEqual(code, 127)
        self.assertIn('did you mean echo', output)
        with patch.object(predict.shutil, 'which', return_value='/bin/echo'), patch.object(predict.subprocess, 'run', return_value=SimpleNamespace(returncode=7)) as run:
            self.assertEqual(self.run_predict('use')[0], 7)
            run.assert_called_once_with(['/bin/echo', payload], shell=False)
        with self.assertRaises(ValueError):
            self.run_predict('use')

    def test_learning_reload_reset(self):
        self.suggest('ehco', 'old')
        self.run_predict('wrong', 'echo')
        self.run_predict('reload')
        self.assertIn('echo new', self.suggest('ehco', 'new')[1])
        self.run_predict('reset')
        with predict.State() as state:
            self.assertEqual(state.load(), {})
        self.assertTrue(os.path.isdir(self.tmp.name))

    def test_sudo_only_wraps_selected_argv(self):
        self.suggest('ehco', 'hello')
        with patch.object(predict.os, 'getuid', return_value=123), patch.object(predict.os, 'geteuid', return_value=123), patch.object(predict.os, 'fstat', return_value=SimpleNamespace(st_uid=123, st_mode=0o40700)), patch.object(predict.shutil, 'which', side_effect=['/bin/echo', '/usr/bin/sudo']), patch.object(predict.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            self.run_predict('--sudo-use')
            run.assert_called_once_with(['/usr/bin/sudo', '--', '/bin/echo', 'hello'], shell=False)
        with patch.dict(os.environ, {'SUDO_UID': '123'}), self.assertRaises(ValueError):
            self.run_predict('use')

    def test_symlink_directory_rejected(self):
        os.symlink(self.tmp.name, self.tmp.name + '/.homepi-predict')
        with self.assertRaises(OSError):
            self.run_predict('reset')

    def test_corrupt_state_recovery(self):
        self.run_predict('reset')
        with open(self.tmp.name + '/.homepi-predict/state.json', 'w') as f:
            f.write('broken')
        with self.assertRaises(ValueError):
            self.run_predict('use')
        self.run_predict('reset')
        self.run_predict('reload')

    def test_no_match_clears_stale_suggestion(self):
        self.suggest('ehco')
        self.suggest('zzzzzzzz')
        with self.assertRaises(ValueError):
            self.run_predict('use')

    def test_reject_paths_controls_and_recursive_predict(self):
        for argv in [['/tmp/evil'], ['echo', '\n'], ['predict'], ['../echo']]:
            self.assertFalse(predict.valid(argv))


if __name__ == '__main__':
    unittest.main()
