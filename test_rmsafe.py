import os, pty, subprocess, sys, tempfile, time, unittest, fcntl, termios, struct, select

HERE = os.path.dirname(os.path.abspath(__file__))
RMSAFE = os.path.join(HERE, 'rmsafe.py')


class TestRmSafe(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.trash = os.path.join(self.root, '.trash')
        self.env = dict(os.environ, RMSAFE_TRASH=self.trash)
        self.victim = os.path.join(self.root, 'world-save.txt')
        open(self.victim, 'w').write('precious')

    def test_yes_flag_moves_to_trash(self):
        r = subprocess.run(['python3', RMSAFE, '--yes', self.victim],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.victim))
        self.assertEqual(open(os.path.join(self.trash, 'world-save.txt')).read(), 'precious')

    def test_non_interactive_without_yes_refuses(self):
        r = subprocess.run(['python3', RMSAFE, self.victim],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertTrue(os.path.exists(self.victim))      # NOT deleted

    def test_missing_file(self):
        r = subprocess.run(['python3', RMSAFE, '--yes', '/no/such/file'],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn('no such file', r.stderr)

    def test_restore(self):
        subprocess.run(['python3', RMSAFE, '--yes', self.victim],
                       capture_output=True, env=self.env)
        r = subprocess.run(['python3', RMSAFE, '--restore', 'world-save.txt'],
                           capture_output=True, text=True, env=self.env, cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(self.victim).read(), 'precious')

    def test_name_collision_gets_suffix(self):
        subprocess.run(['python3', RMSAFE, '--yes', self.victim],
                       capture_output=True, env=self.env)
        open(self.victim, 'w').write('second')
        subprocess.run(['python3', RMSAFE, '--yes', self.victim],
                       capture_output=True, env=self.env)
        self.assertTrue(os.path.exists(os.path.join(self.trash, 'world-save.txt.2')))

    def test_interactive_confirm_via_pty(self):
        master, slave = pty.openpty()
        p = subprocess.Popen(['python3', RMSAFE, self.victim],
                             stdin=slave, stdout=slave, stderr=slave,
                             env=self.env, close_fds=True)
        os.close(slave)
        time.sleep(1)
        os.write(master, b'n\n')                          # decline
        p.wait(timeout=10)
        self.assertEqual(p.returncode, 2)
        self.assertTrue(os.path.exists(self.victim))      # declined: kept
        master, slave = pty.openpty()
        p = subprocess.Popen(['python3', RMSAFE, self.victim],
                             stdin=slave, stdout=slave, stderr=slave,
                             env=self.env, close_fds=True)
        os.close(slave)
        time.sleep(1)
        os.write(master, b'y\n')                          # confirm
        p.wait(timeout=10)
        self.assertEqual(p.returncode, 0)
        self.assertFalse(os.path.exists(self.victim))
        os.close(master)


if __name__ == '__main__':
    unittest.main()
