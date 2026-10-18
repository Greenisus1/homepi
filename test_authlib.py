import json, os, tempfile, unittest

import authlib as A


class TestRules(unittest.TestCase):
    def test_good(self):
        self.assertEqual(A.check_password_rules('Bear!2026x'), [])

    def test_each_rule(self):
        self.assertIn('at least 8 characters', A.check_password_rules('Aa1!'))
        self.assertIn('one capital letter', A.check_password_rules('bear!2026x'))
        self.assertIn('one number', A.check_password_rules('Bear!cubxy'))
        self.assertIn('one special character', A.check_password_rules('Bear2026x'))

    def test_empty(self):
        self.assertEqual(len(A.check_password_rules('')), 4)


class TestHash(unittest.TestCase):
    def test_roundtrip(self):
        salt, digest = A.hash_password('Bear!2026x')
        self.assertTrue(A.verify_password('Bear!2026x', salt, digest))
        self.assertFalse(A.verify_password('bear!2026x', salt, digest))
        self.assertFalse(A.verify_password('Bear!2026y', salt, digest))

    def test_unique_salts(self):
        s1, _ = A.hash_password('SamePass1!')
        s2, _ = A.hash_password('SamePass1!')
        self.assertNotEqual(s1, s2)


class TestStore(unittest.TestCase):
    def test_roundtrip_and_update(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(A.load_auth(root))          # first boot
            rec = A.save_auth(root, 'root', 'Bear!2026x', 'Greenisus1')
            back = A.load_auth(root)
            self.assertEqual(back['username'], 'root')
            self.assertEqual(back['github_login'], 'Greenisus1')
            self.assertTrue(A.verify_password('Bear!2026x', back['salt'], back['hash']))
            self.assertNotIn('Bear!2026x', json.dumps(back))   # never plaintext
            mode = os.stat(A.auth_path(root)).st_mode & 0o777
            self.assertEqual(mode, 0o600)
            A.set_github_login(root, 'Other')
            self.assertEqual(A.load_auth(root)['github_login'], 'Other')

    def test_corrupt_file_is_first_boot(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, 'etc/homepi'))
            with open(A.auth_path(root), 'w') as f:
                f.write('not json')
            self.assertIsNone(A.load_auth(root))


class TestRateLimiter(unittest.TestCase):
    def test_lockout_and_recovery(self):
        t = [1000.0]
        rl = A.RateLimiter(now=lambda: t[0])
        self.assertFalse(rl.blocked())
        for _ in range(3):
            rl.record(False)
        self.assertTrue(rl.blocked())
        self.assertGreater(rl.blocked_seconds(), 0)
        t[0] += 31
        self.assertFalse(rl.blocked())
        rl.record(False); rl.record(False); rl.record(False)
        self.assertTrue(rl.blocked())
        self.assertGreaterEqual(rl.blocked_seconds(), 59)   # doubled
        t[0] += 120
        rl.record(True)
        self.assertEqual(rl.rounds, 0)


if __name__ == '__main__':
    unittest.main()
