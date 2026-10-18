'''Home Pi auth: password rules, salted hashing, store, rate limiting.
Launcher-level lock for a single-user appliance - NOT a boundary against
someone who can mount the SD card (see README).'''
import hashlib, hmac, json, os, time

APP = 'homepi'
ITERATIONS = 200_000
MIN_LEN = 8
ATTEMPTS_BEFORE_LOCK = 3
LOCK_SECONDS = 30


def check_password_rules(pw):
    '''Returns list of unmet rules (empty = ok).'''
    problems = []
    if len(pw) < MIN_LEN:
        problems.append('at least %d characters' % MIN_LEN)
    if not any(c.isupper() for c in pw):
        problems.append('one capital letter')
    if not any(c.isdigit() for c in pw):
        problems.append('one number')
    if not any(not c.isalnum() for c in pw):
        problems.append('one special character')
    return problems


def hash_password(pw, salt=None):
    '''Returns (salt_hex, verifier_hex). The verifier is HMAC(kek, domain):
    proof of the password WITHOUT storing the vault key itself (v2).'''
    import vaultlib
    if salt is None:
        salt = os.urandom(16)
    kek = vaultlib.derive_kek(pw, salt)
    return salt.hex(), vaultlib.verifier_from_kek(kek)


def verify_password(pw, salt_hex, digest_hex):
    _, candidate = hash_password(pw, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, digest_hex)


def check_and_kek(pw, salt_hex, verifier_hex):
    '''Returns the vault KEK when the password matches, else None.'''
    import vaultlib
    kek = vaultlib.derive_kek(pw, bytes.fromhex(salt_hex))
    if hmac.compare_digest(vaultlib.verifier_from_kek(kek), verifier_hex):
        return kek
    return None


def auth_path(root='/'):
    return os.path.join(root, 'etc/homepi/auth.json')


def load_auth(root='/'):
    try:
        with open(auth_path(root)) as f:
            d = json.load(f)
        if d.get('version') in (1, 2) and d.get('username') and d.get('hash'):
            return d
    except Exception:
        pass
    return None


def save_auth(root, username, pw, github_login=None, salt_hex=None):
    if salt_hex is not None:
        salt, digest = hash_password(pw, bytes.fromhex(salt_hex))
    else:
        salt, digest = hash_password(pw)
    rec = {'version': 2, 'username': username, 'salt': salt, 'hash': digest,
           'github_login': github_login, 'created': time.time()}
    path = auth_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(rec, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return rec


def set_github_login(root, login):
    rec = load_auth(root)
    rec['github_login'] = login
    path = auth_path(root)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(rec, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


class RateLimiter:
    '''Lock out after ATTEMPTS_BEFORE_LOCK failures; lock time doubles each round.'''
    def __init__(self, now=None):
        self.fails = 0
        self.locked_until = 0.0
        self.rounds = 0
        self.now = now or time.time

    def blocked(self):
        return self.now() < self.locked_until

    def blocked_seconds(self):
        return max(0, int(self.locked_until - self.now()))

    def record(self, ok):
        if ok:
            self.fails = 0
            self.rounds = 0
            return
        self.fails += 1
        if self.fails >= ATTEMPTS_BEFORE_LOCK:
            self.rounds += 1
            self.locked_until = self.now() + LOCK_SECONDS * (2 ** (self.rounds - 1))
            self.fails = 0
