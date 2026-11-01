"""LUKS2 password rotation; keep an unlockable key throughout interrupted changes."""
import contextlib
import json
import os
from pathlib import Path
import stat
import subprocess

DEVICE = '/dev/mmcblk0p2'


def binary():
    for p in ('/usr/sbin/cryptsetup', '/sbin/cryptsetup'):
        if Path(p).is_file():
            return p
    raise ValueError('cryptsetup is required')


@contextlib.contextmanager
def secret_fd(password):
    fd = os.memfd_create('homepi-key', os.MFD_CLOEXEC)
    try:
        os.write(fd, password.encode())
        os.lseek(fd, 0, os.SEEK_SET)
        yield fd
    finally:
        os.close(fd)


def run(args, password=None, new=None, check=True):
    with contextlib.ExitStack() as stack:
        fds = []
        if password is not None:
            fd = stack.enter_context(secret_fd(password))
            args += ['--key-file', '/proc/self/fd/' + str(fd)]
            fds.append(fd)
        if new is not None:
            fd = stack.enter_context(secret_fd(new))
            args += ['--new-keyfile', '/proc/self/fd/' + str(fd)]
            fds.append(fd)
        result = subprocess.run([binary()] + args, pass_fds=fds, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if check and result.returncode:
            raise ValueError('encrypted-disk operation failed; no password is logged. If a transaction is pending, reboot to recover.')
        return result


def slots(device):
    return sorted(int(n) for n in json.loads(run(['luksDump', '--dump-json-metadata', device]).stdout)['keyslots'])


def accepts(device, password, slot):
    return run(['open', '--test-passphrase', '--key-slot', str(slot), device], password, check=False).returncode == 0


def config(root='/'):
    path = Path(root) / 'etc/homepi/disk.json'
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    # Image layout is fixed. Never turn an arbitrary config path into a formatting target.
    if data != {'device': '/dev/mmcblk0p2', 'mapper': 'homepi-root', 'version': 1}:
        raise ValueError('unsupported encrypted image layout')
    if not stat.S_ISBLK(os.stat(data['device']).st_mode):
        raise ValueError('encrypted root device is not a block device')
    return data


def change_password(account, updates, old, new):
    settings = config()
    if settings is None:
        # Existing installations can synchronize native login and the HomePi vault.
        # Do not imply this encrypts an existing unencrypted installation.
        account.finish(account.stage(updates))
        print('This installation has no HomePi encrypted root; only Linux and vault passwords changed.')
        return
    device = settings['device']
    current = slots(device)
    oldslots = [n for n in current if accepts(device, old, n)]
    if not oldslots:
        raise ValueError('current password does not unlock the encrypted disk')
    free = next((n for n in range(32) if n not in current), None)
    if free is None:
        raise ValueError('no free encryption key slot')
    transaction = account.stage(updates, dict(device=device, oldslots=oldslots, newslot=free))
    try:
        run(['luksAddKey', '--key-slot', str(free), device], old, new)
        if not accepts(device, new, free):
            raise ValueError('new disk key verification failed; reboot for recovery')
        finish_rotation(transaction['disk'], new)
        account.finish(transaction)
    except Exception:
        # If the new slot was never created, the old state is fully intact.
        if free not in slots(device):
            account.journal.unlink()
        raise


def finish_rotation(pending, password):
    device = pending['device']
    if device != DEVICE or not accepts(device, password, pending['newslot']):
        raise ValueError('use the NEW password to finish the interrupted password change')
    for slot in pending['oldslots']:
        if slot in slots(device):
            run(['luksKillSlot', device, str(slot)], password)


def recover(account, password):
    if not account.journal.exists():
        return
    transaction = json.loads(account.journal.read_text())
    pending = transaction.get('disk')
    if pending:
        if pending['newslot'] not in slots(pending['device']):
            account.journal.unlink()  # Power loss before adding the new key.
            return
        # Do not commit new login hashes after unlocking with an obsolete key.
        import authlib
        rec = json.loads(transaction['files']['etc/homepi/auth.json']['body'])
        if not authlib.verify_password(password, rec['salt'], rec['hash']):
            raise ValueError('pending password change: enter the NEW password')
        finish_rotation(pending, password)
    account.finish(transaction)
