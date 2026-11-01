#!/usr/bin/python3 -I
"""Root-only HomePi account operations. Never invoke a shell or persist passwords."""
import copy
import ctypes
import fcntl
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile
import time
import warnings

# Installed dependencies live in the same root-owned directory, not cwd/PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import authlib
import vaultlib

NAME = re.compile(r'[a-z_][a-z0-9_-]{0,31}\Z')
FILES = ('etc/passwd', 'etc/shadow', 'etc/group', 'etc/gshadow',
         'etc/homepi/auth.json', 'etc/homepi/vault.enc')


def crypt_password(password, salt):
    if '\x00' in password:
        raise ValueError('NUL is not allowed in a password')
    lib = None
    for name in ('libcrypt.so.2', 'libcrypt.so.1', 'libc.so.6'):
        try:
            candidate = ctypes.CDLL(name)
            candidate.crypt
            lib = candidate
            break
        except (OSError, AttributeError):
            continue
    if lib is None:
        raise ValueError('Linux crypt library is required')
    lib.crypt.argtypes = (ctypes.c_char_p, ctypes.c_char_p)
    lib.crypt.restype = ctypes.c_char_p
    result = lib.crypt(password.encode(), salt.encode())
    if not result or result.startswith(b'*'):
        raise ValueError('unsupported Linux password hash')
    return result.decode()


def shadow_hash(password):
    return crypt_password(password, '$6$rounds=200000$' + secrets.token_hex(8) + '$')


def check_password(password, encoded):
    return bool(encoded and not encoded.startswith(('!', '*')) and
                hmac.compare_digest(crypt_password(password, encoded), encoded))


def atomic(path, body, mode, uid=0, gid=0):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.homepi-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        if os.geteuid() == 0:
            os.fchown(fd, uid, gid)
        with os.fdopen(fd, 'w') as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        d = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(d)
        finally:
            os.close(d)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Accounts:
    def __init__(self, root='/'):
        self.root = Path(root)
        self.directory = self.root / 'etc/homepi'
        self.journal = self.directory / 'account-transaction.json'

    def __enter__(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.fd = os.open(self.directory / 'accounts.lock',
                          os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        # Also honor the conventional Linux account database lock.
        self.pwlock = os.open(self.root / 'etc/.pwd.lock',
                              os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.lockf(self.pwlock, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        os.close(self.pwlock)
        os.close(self.fd)

    def read(self, rel):
        path = self.root / rel
        if path.is_symlink():
            raise ValueError('account file symlinks are unsupported')
        return path.read_text()

    def entry(self, rel, name):
        rows = [r.split(':') for r in self.read(rel).splitlines()]
        matches = [r for r in rows if r[0] == name]
        if len(matches) != 1:
            raise ValueError('account is missing or ambiguous: ' + name)
        return matches[0]

    def caller(self):
        # sudo overwrites SUDO_UID; never accept a target username from argv.
        uid = int(os.environ.get('SUDO_UID', os.getuid()))
        rows = [r.split(':') for r in self.read('etc/passwd').splitlines()]
        matches = [r for r in rows if int(r[2]) == uid]
        if len(matches) != 1 or uid == 0:
            raise ValueError('run through sudo from the non-root HomePi administrator account')
        name = matches[0][0]
        rec = authlib.load_auth(str(self.root))
        if rec is not None and rec['username'] != name:
            raise ValueError('Linux and HomePi account names differ; migration is required')
        return name

    def verify(self, name, password):
        if not check_password(password, self.entry('etc/shadow', name)[1]):
            raise ValueError('incorrect current Linux password')
        rec = authlib.load_auth(str(self.root))
        if not rec or not authlib.verify_password(password, rec['salt'], rec['hash']):
            raise ValueError('current HomePi password does not match; migration is required')
        blob = vaultlib.load_blob(str(self.root))
        master, _ = vaultlib.unlock_with_password(str(self.root), password)
        if master is None or vaultlib.vault_decrypt(master, blob['vault']) is None:
            raise ValueError('vault authentication failed; no files changed')
        return rec, blob, master

    def replacement(self, rel, old, new, field=None, value=None):
        rows = self.read(rel).splitlines()
        found = False
        for i, line in enumerate(rows):
            row = line.split(':')
            if row[0] == old:
                found = True
                row[0] = new
                if field is not None:
                    row[field] = value
            if rel in ('etc/group', 'etc/gshadow'):
                for j in ([3] if rel == 'etc/group' else [2, 3]):
                    row[j] = ','.join(new if n == old else n for n in row[j].split(','))
            rows[i] = ':'.join(row)
        if not found and rel in ('etc/passwd', 'etc/shadow'):
            raise ValueError('account missing')
        return '\n'.join(rows) + '\n'

    def new_shadow(self, name, password):
        rows = self.replacement('etc/shadow', name, name, 1, shadow_hash(password)).splitlines()
        for i, line in enumerate(rows):
            row = line.split(':')
            if row[0] == name:
                row[2] = str(int(time.time() // 86400))
                rows[i] = ':'.join(row)
        return '\n'.join(rows) + '\n'

    def prepare_password(self, name, old, new):
        rec, blob, master = self.verify(name, old)
        problems = authlib.check_password_rules(new)
        if problems or any(c in new for c in ('\n', '\r', '\x00')):
            raise ValueError('new password requirements: ' + ', '.join(problems or ['no control characters']))
        if old == new:
            raise ValueError('new password must be different')
        salt = os.urandom(16)
        kek = vaultlib.derive_kek(new, salt)
        rec = copy.deepcopy(rec)
        rec.update(salt=salt.hex(), hash=vaultlib.verifier_from_kek(kek), linux_account=True)
        blob = copy.deepcopy(blob)
        blob.update(salt_pw=vaultlib._b64(salt), wrap_pw=vaultlib.wrap_key(master, kek))
        return {'etc/shadow': self.new_shadow(name, new),
                'etc/homepi/auth.json': json.dumps(rec),
                'etc/homepi/vault.enc': json.dumps(blob)}

    def prepare_rename(self, name, password, new):
        rec, blob, master = self.verify(name, password)
        if not NAME.fullmatch(new) or new == 'root':
            raise ValueError('use a lowercase Linux username (1–32 letters, digits, _ or -)')
        if any(r.split(':')[0] == new for r in self.read('etc/passwd').splitlines()):
            raise ValueError('username already exists')
        # Explicit username rules and scheduled jobs cannot safely be rewritten blindly.
        for path in [self.root / 'etc/sudoers'] + list((self.root / 'etc/sudoers.d').glob('*')):
            if path.is_file():
                for line in path.read_text().splitlines():
                    if not line.lstrip().startswith('#') and re.search(r'(?<![\w%-])' + re.escape(name) + r'(?![\w-])', line):
                        raise ValueError('username-specific sudo policy requires administrator migration')
        if (self.root / 'var/spool/cron/crontabs' / name).exists() or (self.root / 'var/spool/cron' / name).is_file():
            raise ValueError('user crontab must be migrated before renaming')
        updates = {rel: self.replacement(rel, name, new) for rel in
                   ('etc/passwd', 'etc/shadow', 'etc/group', 'etc/gshadow') if (self.root / rel).exists()}
        rec = dict(rec, username=new, linux_account=True)
        updates['etc/homepi/auth.json'] = json.dumps(rec)
        return updates

    def stage(self, updates, disk=None):
        if self.journal.exists():
            raise ValueError('pending account transaction; restart to recover')
        records = {}
        for rel, body in updates.items():
            if rel not in FILES:
                raise ValueError('invalid account path')
            path = self.root / rel
            if path.exists():
                st = path.lstat()
                if not stat.S_ISREG(st.st_mode):
                    raise ValueError('account path must be a regular file')
                mode, uid, gid = stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid
            else:
                mode, uid, gid = 0o600, 0, 0
            records[rel] = dict(body=body, mode=mode, uid=uid, gid=gid)
        data = dict(files=records, disk=disk)
        atomic(self.journal, json.dumps(data), 0o600)
        return data

    def finish(self, transaction):
        for rel, record in transaction['files'].items():
            if rel not in FILES:
                raise ValueError('invalid recovery path')
            atomic(self.root / rel, **record)
        self.journal.unlink()
        d = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(d)
        finally:
            os.close(d)

    def setup(self, name, password):
        # Called only in the encrypted image's local early-boot provisioner.
        if (self.root / 'etc/homepi/auth.json').exists() or (self.root / 'etc/homepi/vault.enc').exists():
            raise ValueError('existing account/vault must never be replaced by first boot setup')
        self.entry('etc/passwd', name)
        problems = authlib.check_password_rules(password)
        if problems:
            raise ValueError(', '.join(problems))
        salt = os.urandom(16)
        master = secrets.token_bytes(32)
        kek = vaultlib.derive_kek(password, salt)
        blob = dict(version=2, salt_pw=vaultlib._b64(salt), wrap_pw=vaultlib.wrap_key(master, kek),
                    vault=vaultlib.vault_encrypt(master, {'secrets': {}}))
        rec = dict(version=2, username=name, salt=salt.hex(), hash=vaultlib.verifier_from_kek(kek),
                   linux_account=True, github_login=None)
        updates = {'etc/shadow': self.new_shadow(name, password),
                   'etc/homepi/auth.json': json.dumps(rec),
                   'etc/homepi/vault.enc': json.dumps(blob)}
        self.finish(self.stage(updates))


def main(command=None):
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError('requires normal sudo authorization')
    command = sys.argv[1:] if command is None else command
    if not command or command[0] not in ('password', 'user'):
        raise ValueError('usage: sudo password [OLD NEW] | sudo user [PASSWORD NEWNAME]')
    action, args = command[0], command[1:]
    warnings.simplefilter('error', getpass.GetPassWarning)
    if not args and not sys.stdin.isatty():
        raise ValueError('hidden password prompts need a terminal')
    if args and len(args) != 2:
        raise ValueError('supply two arguments or omit both for hidden password prompts')
    if args:
        print('Warning: command-line passwords can appear in history and process listings.', file=sys.stderr)
    with Accounts() as account:
        name = account.caller()
        old = args[0] if args else getpass.getpass('Current password: ')
        new = args[1] if args else (getpass.getpass('New password: ') if action == 'password' else input('New username: '))
        if not args and action == 'password' and new != getpass.getpass('Repeat new password: '):
            raise ValueError('passwords do not match')
        if action == 'user':
            updates = account.prepare_rename(name, old, new)
            account.finish(account.stage(updates))
            print('Account renamed. UID, home directory, files and encryption key are unchanged. Log out and reconnect with the new username.')
        else:
            updates = account.prepare_password(name, old, new)
            import disk
            disk.change_password(account, updates, old, new)
            print('Password change complete; existing encrypted data preserved.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('homepi account: ' + str(exc), file=sys.stderr)
        sys.exit(1)
