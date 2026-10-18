import hashlib, json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HP = os.path.join(HERE, 'hpupdate.py')


def make_remote(root, version, files):
    os.makedirs(root, exist_ok=True)
    manifest = {'files': []}
    for rel, body in files.items():
        src = 'payload-%s' % rel.replace('/', '_')
        with open(os.path.join(root, src), 'wb') as f:
            f.write(body)
        manifest['files'].append({'path': rel, 'source': src,
                                  'sha256': hashlib.sha256(body).hexdigest()})
    mname = 'manifest-%s.json' % version
    with open(os.path.join(root, mname), 'w') as f:
        json.dump(manifest, f)
    with open(os.path.join(root, 'system-version.json'), 'w') as f:
        json.dump({'version': version, 'manifest': mname}, f)


class TestHpUpdate(unittest.TestCase):
    def setUp(self):
        self.remote = tempfile.mkdtemp()
        self.root = tempfile.mkdtemp()
        self.env = dict(os.environ, HPUPDATE_REMOTE=self.remote,
                        HPUPDATE_ROOT=self.root)

    def run_hp(self, *args):
        return subprocess.run(['python3', HP] + list(args),
                              capture_output=True, text=True, env=self.env)

    def test_up_to_date(self):
        make_remote(self.remote, '1', {})
        os.makedirs(os.path.join(self.root, 'etc/homepi'))
        json.dump({'version': '1'}, open(os.path.join(self.root, 'etc/homepi/system-version.json'), 'w'))
        r = self.run_hp('--check')
        self.assertIn('up to date', r.stdout)

    def test_applies_new_files_and_backs_up(self):
        make_remote(self.remote, '2', {'usr/bin/homepi': b'NEW-LAUNCHER\n'})
        old = os.path.join(self.root, 'usr/bin')
        os.makedirs(old)
        open(os.path.join(old, 'homepi'), 'w').write('OLD-LAUNCHER')
        r = self.run_hp('--auto')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(os.path.join(old, 'homepi')).read(), 'NEW-LAUNCHER\n')
        backups = []
        for dp, _, fns in os.walk(os.path.join(self.root, 'var/backups')):
            backups += [os.path.join(dp, f) for f in fns]
        self.assertEqual(len(backups), 1)
        self.assertEqual(open(backups[0]).read(), 'OLD-LAUNCHER')
        v = json.load(open(os.path.join(self.root, 'etc/homepi/system-version.json')))
        self.assertEqual(v['version'], '2')

    def test_protected_files_never_touched(self):
        make_remote(self.remote, '3', {'etc/homepi/auth.json': b'{"evil": 1}',
                                       'etc/homepi/vault.enc': b'{"evil": 2}',
                                       'root/notes.txt': b'evil'})
        os.makedirs(os.path.join(self.root, 'etc/homepi'))
        open(os.path.join(self.root, 'etc/homepi/auth.json'), 'w').write('{"real": 1}')
        r = self.run_hp('--auto')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(os.path.join(self.root, 'etc/homepi/auth.json')).read(),
                         '{"real": 1}')
        self.assertFalse(os.path.exists(os.path.join(self.root, 'etc/homepi/vault.enc')))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'root/notes.txt')))
        self.assertIn('protected', r.stdout)

    def test_checksum_mismatch_aborts(self):
        make_remote(self.remote, '4', {'usr/bin/fanctl.py': b'good'})
        m = json.load(open(os.path.join(self.remote, 'manifest-4.json')))
        m['files'][0]['sha256'] = '0' * 64
        json.dump(m, open(os.path.join(self.remote, 'manifest-4.json'), 'w'))
        r = self.run_hp('--auto')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('checksum mismatch', r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, 'usr/bin/fanctl.py')))

    def test_check_does_not_apply(self):
        make_remote(self.remote, '5', {'usr/bin/qr.py': b'x'})
        r = self.run_hp('--check')
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.root, 'usr/bin/qr.py')))


if __name__ == '__main__':
    unittest.main()
