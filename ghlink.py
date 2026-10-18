'''GitHub device-flow link for Home Pi recovery. Public client id only;
the token is used for one whoami call and NEVER stored.'''
import json, time, urllib.parse, urllib.request

CLIENT_ID = 'Ov23liE4ISwOOwp2coRn'   # fetchwing OAuth app, public id, device flow
DEVICE_URL = 'https://github.com/login/device/code'
TOKEN_URL = 'https://github.com/login/oauth/access_token'
USER_URL = 'https://api.github.com/user'
SCOPE = 'read:user gist'   # gist scope stores the recovery secret


def _post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def request_code(scope=None):
    d = _post(DEVICE_URL, {'client_id': CLIENT_ID, 'scope': scope or SCOPE})
    return {'device_code': d['device_code'], 'user_code': d['user_code'],
            'verification_uri': d['verification_uri'],
            'expires_in': d.get('expires_in', 900), 'interval': d.get('interval', 5)}


def poll_token(device_code, interval=5, expires_in=900):
    '''Returns the token string, or None on timeout/denial.'''
    deadline = time.time() + expires_in
    while time.time() < deadline:
        d = _post(TOKEN_URL, {'client_id': CLIENT_ID, 'device_code': device_code,
                              'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'})
        if 'access_token' in d:
            return d['access_token']
        err = d.get('error')
        if err == 'authorization_pending':
            time.sleep(interval)
            continue
        if err == 'slow_down':
            interval += 5
            time.sleep(interval)
            continue
        return None
    return None


def whoami(token):
    req = urllib.request.Request(USER_URL, headers={
        'Authorization': 'Bearer %s' % token, 'Accept': 'application/json',
        'User-Agent': 'homepi'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()).get('login')


def link_login(fake=None):
    '''Full flow: returns github login string or None. fake=(login) for demo/tests.'''
    if fake is not None:
        return fake
    code = request_code()
    token = poll_token(code['device_code'], code['interval'], code['expires_in'])
    if not token:
        return None
    return whoami(token)   # token discarded here, never stored


GIST_DESC = 'Home Pi recovery (do not share)'
GIST_FILE = 'homepi-recovery.json'
GISTS_URL = 'https://api.github.com/gists'
def _fake_gist_path():
    import os as _os
    root = _os.environ.get('HOMEPI_DEMO_ROOT', '/tmp/homepi-demo')
    return _os.path.join(root, 'tmp', 'homepi-fake-gist.json')


def upload_recovery(token, payload):
    """Create a secret gist holding the recovery payload. Returns True/False.
    Secret gists are UNLISTED, not fully private - README states this."""
    import json as _j, urllib.request as _u
    body = _j.dumps({'description': GIST_DESC, 'public': False,
                     'files': {GIST_FILE: {'content': _j.dumps(payload)}}}).encode()
    req = _u.Request(GISTS_URL, data=body, headers={
        'Authorization': 'Bearer %s' % token, 'Accept': 'application/json',
        'User-Agent': 'homepi'})
    try:
        with _u.urlopen(req, timeout=15) as r:
            return r.status in (200, 201)
    except Exception:
        return False


def fetch_recovery_secret(token):
    """Find the recovery gist and return the stored secret b64, or None."""
    import json as _j, urllib.request as _u
    req = _u.Request(GISTS_URL, headers={
        'Authorization': 'Bearer %s' % token, 'Accept': 'application/json',
        'User-Agent': 'homepi'})
    try:
        with _u.urlopen(req, timeout=15) as r:
            gists = _j.loads(r.read())
        for g in gists:
            if GIST_FILE in (g.get('files') or {}):
                url = g['files'][GIST_FILE].get('raw_url')
                if not url:
                    continue
                req2 = _u.Request(url, headers={
                    'Authorization': 'Bearer %s' % token, 'User-Agent': 'homepi'})
                with _u.urlopen(req2, timeout=15) as r2:
                    import vaultlib
                    return vaultlib.secret_from_payload(_j.loads(r2.read()))
    except Exception:
        pass
    return None


def demo_store(payload):
    """DEMO/test: persist the recovery payload in the demo root (survives
    across processes, like a real gist survives across boots)."""
    import json as _j, os as _os
    path = _fake_gist_path()
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        _j.dump(payload, f)
    _os.chmod(path, 0o600)


def demo_fetch():
    import json as _j
    try:
        with open(_fake_gist_path()) as f:
            return _j.load(f)
    except Exception:
        return None
