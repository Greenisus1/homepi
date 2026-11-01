"""Integration test on a disposable regular file; never opens a host block device."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / 'security'))
import accounts
import disk


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('HOMEPI_RUN_LUKS_TESTS') == '1',
                     'opt-in Linux cryptsetup test')
class LuksTests(unittest.TestCase):
    def test_key_rotation_retires_old_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            device = str(Path(tmp) / 'test-volume.luks')
            with open(device, 'wb') as volume:
                volume.truncate(32 * 1024 * 1024)
            disk.run(['luksFormat', '--type', 'luks2', '--batch-mode', '--pbkdf', 'pbkdf2', '--iter-time', '10', device], 'OldPass1!')
            class Store:
                journal = Path(tmp) / 'journal'
                finished = False
                def stage(self, updates, pending):
                    tx = dict(files=updates, disk=pending)
                    self.journal.write_text(json.dumps(tx))
                    return tx
                def finish(self, tx):
                    self.finished = True
                    self.journal.unlink()
            store = Store()
            with patch.object(disk, 'config', return_value={'device': device}), patch.object(disk, 'DEVICE', device):
                disk.change_password(store, {}, 'OldPass1!', 'NewPass2!')
            self.assertTrue(store.finished)
            self.assertFalse(any(disk.accepts(device, 'OldPass1!', slot) for slot in disk.slots(device)))
            self.assertTrue(any(disk.accepts(device, 'NewPass2!', slot) for slot in disk.slots(device)))
            hashed = accounts.shadow_hash('NewPass2!')
            self.assertTrue(accounts.check_password('NewPass2!', hashed))
            self.assertFalse(accounts.check_password('OldPass1!', hashed))


if __name__ == '__main__':
    unittest.main()
