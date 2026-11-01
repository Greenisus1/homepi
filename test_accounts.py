import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / 'security'))
import accounts
import disk
import vaultlib

OLD = 'OldPassword1!'
NEW = 'NewPassword2!'


def fake_hash(pw):
    return 'testhash-' + pw


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'etc').mkdir()
        self.hashing = patch.object(accounts, 'shadow_hash', side_effect=fake_hash)
        self.verifying = patch.object(accounts, 'check_password', side_effect=lambda p, h: h == fake_hash(p))
        self.hashing.start()
        self.verifying.start()
        self.addCleanup(self.hashing.stop)
        self.addCleanup(self.verifying.stop)
        (self.root / 'etc/passwd').write_text('root:x:0:0:root:/root:/bin/sh\nhomepi:x:1000:1000:HomePi:/home/homepi:/bin/bash\n')
        (self.root / 'etc/shadow').write_text('root:!:0:0:99999:7:::\nhomepi:*:0:0:99999:7:::\n')
        (self.root / 'etc/group').write_text('homepi:x:1000:\nsudo:x:27:homepi\n')
        (self.root / 'etc/gshadow').write_text('homepi:!::\nsudo:!::homepi\n')
        self.a = accounts.Accounts(self.root)
        with self.a:
            self.a.setup('homepi', OLD)
        self.before = vaultlib.load_blob(str(self.root))
        self.master, _ = vaultlib.unlock_with_password(str(self.root), OLD)
        blob = self.before
        blob['vault'] = vaultlib.vault_encrypt(self.master, {'important': 'keep me'})
        vaultlib._save(str(self.root), blob)
        self.before = vaultlib.load_blob(str(self.root))

    def test_password_preserves_ciphertext_and_master(self):
        with self.a:
            self.a.finish(self.a.stage(self.a.prepare_password('homepi', OLD, NEW)))
        after = vaultlib.load_blob(str(self.root))
        self.assertEqual(after['vault'], self.before['vault'])
        master, _ = vaultlib.unlock_with_password(str(self.root), NEW)
        self.assertEqual(master, self.master)
        self.assertEqual(vaultlib.vault_decrypt(master, after['vault']), {'important': 'keep me'})
        self.assertEqual(vaultlib.unlock_with_password(str(self.root), OLD), (None, None))
        self.assertEqual(self.a.entry('etc/shadow', 'homepi')[1], fake_hash(NEW))

    def test_wrong_password_changes_nothing(self):
        before = {p: (self.root / p).read_bytes() for p in accounts.FILES}
        with self.a, self.assertRaises(ValueError):
            self.a.prepare_password('homepi', 'wrong', NEW)
        self.assertEqual(before, {p: (self.root / p).read_bytes() for p in accounts.FILES})

    def test_rename_keeps_ids_home_and_vault(self):
        before = self.a.entry('etc/passwd', 'homepi')[2:]
        with self.a:
            self.a.finish(self.a.stage(self.a.prepare_rename('homepi', OLD, 'liam')))
        self.assertEqual(before, self.a.entry('etc/passwd', 'liam')[2:])
        self.assertIn('sudo:x:27:liam', self.a.read('etc/group'))
        self.assertIn('sudo:!::liam', self.a.read('etc/gshadow'))
        self.assertEqual(self.before, vaultlib.load_blob(str(self.root)))
        self.assertEqual(accounts.authlib.load_auth(str(self.root))['username'], 'liam')

    def test_reject_invalid_and_existing_names(self):
        for name in ('root', 'homepi', '-o', '../root', 'a:b', 'name\nroot'):
            with self.a, self.assertRaises(ValueError):
                self.a.prepare_rename('homepi', OLD, name)

    def test_setup_never_overwrites_existing_vault(self):
        with self.a, self.assertRaises(ValueError):
            self.a.setup('homepi', NEW)
        self.assertEqual(self.before, vaultlib.load_blob(str(self.root)))

    def test_interrupted_account_commit_rolls_forward(self):
        with self.a:
            tx = self.a.stage(self.a.prepare_password('homepi', OLD, NEW))
            first, record = next(iter(tx['files'].items()))
            accounts.atomic(self.root / first, **record)
        with self.a:
            disk.recover(self.a, NEW)
        self.assertFalse(self.a.journal.exists())
        self.a.verify('homepi', NEW)

    def test_pending_disk_change_requires_new_password(self):
        with self.a:
            tx = self.a.stage(self.a.prepare_password('homepi', OLD, NEW),
                              {'device': '/dev/mmcblk0p2', 'oldslots': [0], 'newslot': 1})
            with patch.object(disk, 'slots', return_value=[0, 1]), self.assertRaises(ValueError):
                disk.recover(self.a, OLD)
            self.assertTrue(self.a.journal.exists())
            with patch.object(disk, 'slots', return_value=[0, 1]), patch.object(disk, 'finish_rotation') as finish:
                disk.recover(self.a, NEW)
                finish.assert_called_once()
        self.a.verify('homepi', NEW)

    def test_explicit_username_sudo_policy_blocks_rename(self):
        (self.root / 'etc/sudoers').write_text('homepi ALL=(ALL) ALL\n')
        with self.a, self.assertRaises(ValueError):
            self.a.prepare_rename('homepi', OLD, 'liam')


class HistoryTests(unittest.TestCase):
    def test_clear_retains_four_complete_entries_in_memory_and_on_disk(self):
        self.check_history(False)

    def test_multiline_history_on_bash5(self):
        version = subprocess.check_output(['bash', '-c', 'echo "${BASH_VERSINFO[0]}"'], text=True)
        if int(version) < 5:
            self.skipTest('encrypted image uses Bash 5; host Bash is older')
        self.check_history(True)

    def check_history(self, multiline):
        source = Path('security/history.sh').resolve()
        with tempfile.TemporaryDirectory() as tmp:
            script = '''
set -o history
HISTFILE="$1/history"
HISTFILESIZE=100
HISTSIZE=100
history -c
set +o history
. "$2"
history -r "$1/seed"
clear() { :; }
# Reload production function, then override only the external screen-clearing executable.
. "$2"
PATH="$1:$PATH"
clear
history -w "$HISTFILE"
history -c
history -r "$HISTFILE"
history
'''
            seed = ''.join('#1700000000\n' + name + '\n' for name in ['first', 'second', 'third', 'fourth', 'fifth', 'sixth' + ('\ncontinued' if multiline else '')])
            (Path(tmp) / 'seed').write_text(seed)
            if not multiline:
                script = script.replace('history -r \"$1/seed\"', 'for item in first second third fourth fifth sixth; do history -s \"$item\"; done')
            clear = Path(tmp) / 'clear'
            clear.write_text('#!/bin/sh\nexit 0\n')
            clear.chmod(0o755)
            r = subprocess.run(['bash', '--norc', '-i', '-c', script, 'test', tmp, str(source)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            saved = (Path(tmp) / 'history').read_text()
            self.assertNotIn('first', saved)
            self.assertNotIn('second', saved)
            self.assertEqual([line for line in saved.splitlines() if not line.startswith('#')], ['third', 'fourth', 'fifth', 'sixth'] + (['continued'] if multiline else []))
            if multiline:
                self.assertEqual(sum(line.startswith('#') for line in saved.splitlines()), 4)


if __name__ == '__main__':
    unittest.main()
