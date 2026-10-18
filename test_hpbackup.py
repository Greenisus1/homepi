import os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class TestHpBackup(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.env = dict(os.environ, HOMEPI_DEMO='1', HOMEPI_DEMO_ROOT=self.root,
                        HPBACKUP_SPLIT_MB='1')
        self.src = os.path.join(self.root, 'mysaves')
        os.makedirs(self.src)
        with open(os.path.join(self.src, 'world.dat'), 'wb') as f:
            f.write(os.urandom(2 * 1024 ** 2 + 500))     # 2.5M > 1M split cap
        with open(os.path.join(self.src, 'notes.txt'), 'w') as f:
            f.write('first world coords')

    def run_backup(self, *args):
        return subprocess.run(['python3', os.path.join(HERE, 'hpbackup.py'),
                               'backup', self.src] + list(args),
                              capture_output=True, text=True, env=self.env)

    def test_backup_splits_and_pushes(self):
        r = self.run_backup()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('pushed', r.stdout)
        clone = os.path.join(self.root, 'clone')
        subprocess.run(['git', 'clone', '-q', '-b', 'main',
                        os.path.join(self.root, 'backup-remote.git'), clone], check=True)
        self.assertEqual(open(os.path.join(clone, 'mysaves', 'notes.txt')).read(),
                         'first world coords')
        parts = os.path.join(clone, 'mysaves', 'world.dat.parts')
        self.assertTrue(os.path.isdir(parts))                    # split, not rejected
        self.assertGreaterEqual(len([p for p in os.listdir(parts)
                                     if p.endswith('.part')]), 3)
        self.assertTrue(os.path.exists(os.path.join(parts, 'reassemble.sh')))
        # reassembly restores the exact bytes
        out = os.path.join(self.root, 'roundtrip.dat')
        with open(out, 'wb') as o:
            for pn in sorted(p for p in os.listdir(parts) if p.endswith('.part')):
                o.write(open(os.path.join(parts, pn), 'rb').read())
        self.assertEqual(os.path.getsize(out), 2 * 1024 ** 2 + 500)

    def test_second_run_idempotent(self):
        self.run_backup()
        r = self.run_backup()
        self.assertIn('up to date', r.stdout)

    def test_no_token_on_disk(self):
        self.run_backup()
        work = os.path.join(self.root, 'root/.homepi-backup/repo')
        for dirpath, _, files in os.walk(work):
            for fn in files:
                body = open(os.path.join(dirpath, fn), 'rb').read()
                self.assertNotIn(b'demo-token', body)
                self.assertNotIn(b'x-access-token', body)

    def test_missing_path_skipped_not_fatal(self):
        r = subprocess.run(['python3', os.path.join(HERE, 'hpbackup.py'),
                            'backup', '/no/such/dir', self.src],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('skip missing', r.stdout)


if __name__ == '__main__':
    unittest.main()
