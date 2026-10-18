import os, tempfile, unittest

import vaultlib as V


class TestKekAndVerifier(unittest.TestCase):
    def test_derive_and_verifier(self):
        salt = os.urandom(16)
        v = V.verifier_from_kek(V.derive_kek('Bear!2026x', salt))
        self.assertEqual(V.verifier_from_kek(V.derive_kek('Bear!2026x', salt)), v)
        self.assertNotEqual(V.verifier_from_kek(V.derive_kek('Wrong!123', salt)), v)


class TestVaultLifecycle(unittest.TestCase):
    def test_create_unlock_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            master, kek, salt, secret = V.create_vault(root, 'Bear!2026x')
            self.assertEqual(len(master), 32)
            self.assertEqual(V.unlock_with_password(root, 'Bear!2026x')[0], master)
            self.assertEqual(V.unlock_with_recovery_secret(root, secret), master)

    def test_wrong_password_and_secret_fail(self):
        with tempfile.TemporaryDirectory() as root:
            V.create_vault(root, 'Bear!2026x')
            self.assertEqual(V.unlock_with_password(root, 'Bear!2026y'), (None, None))
            self.assertIsNone(V.unlock_with_recovery_secret(root, 'AAAA'))

    def test_payload_roundtrip(self):
        master, _, _, secret = V.create_vault(tempfile.mkdtemp(), 'Bear!2026x')
        payload = V.recovery_payload(secret)
        self.assertEqual(V.secret_from_payload(payload), secret)
        self.assertIsNone(V.secret_from_payload({'nope': 1}))

    def test_vault_contents_roundtrip_and_tamper(self):
        with tempfile.TemporaryDirectory() as root:
            master, _, _, _ = V.create_vault(root, 'Bear!2026x')
            V.reset_vault(root, master, {'secrets': {'token': 'x9'}, 'created': 1})
            blob = V.load_blob(root)
            self.assertEqual(V.vault_decrypt(master, blob['vault'])['secrets']['token'], 'x9')
            blob['vault']['ct'] = blob['vault']['ct'][:-4] + 'AAAA'   # tamper
            self.assertIsNone(V.vault_decrypt(master, blob['vault']))

    def test_recovery_reset_keeps_data(self):
        '''the owner's rule: GitHub recovery replaces the password, KEEPS the data.'''
        with tempfile.TemporaryDirectory() as root:
            master, _, _, secret = V.create_vault(root, 'Bear!2026x')
            V.reset_vault(root, master, {'secrets': {'game': 'save'}, 'created': 1})
            m2 = V.unlock_with_recovery_secret(root, secret)
            self.assertEqual(m2, master)
            V.rewrap_new_password(root, m2, 'Goose!2026y')
            self.assertEqual(V.unlock_with_password(root, 'Bear!2026x'), (None, None))
            m3, _ = V.unlock_with_password(root, 'Goose!2026y')
            self.assertEqual(m3, master)
            data = V.vault_decrypt(m3, V.load_blob(root)['vault'])
            self.assertEqual(data['secrets']['game'], 'save')        # data kept

    def test_wipe_last_resort(self):
        with tempfile.TemporaryDirectory() as root:
            old_master, _, _, old_secret = V.create_vault(root, 'Bear!2026x')
            new_master, _, _, new_secret = V.wipe_vault(root, 'Goose!2026y')
            self.assertNotEqual(new_master, old_master)
            self.assertNotEqual(new_secret, old_secret)
            self.assertEqual(V.unlock_with_password(root, 'Bear!2026x'), (None, None))
            self.assertEqual(V.unlock_with_password(root, 'Goose!2026y')[0], new_master)
            self.assertIsNone(V.unlock_with_recovery_secret(root, old_secret))
            self.assertEqual(V.unlock_with_recovery_secret(root, new_secret), new_master)
            data = V.vault_decrypt(new_master, V.load_blob(root)['vault'])
            self.assertEqual(data['secrets'], {})                    # old data gone

    def test_no_plaintext_on_disk(self):
        with tempfile.TemporaryDirectory() as root:
            V.create_vault(root, 'Bear!2026x')
            raw = open(V.vault_path(root)).read()
            self.assertNotIn('Bear', raw)
            self.assertEqual(os.stat(V.vault_path(root)).st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
