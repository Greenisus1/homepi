#!/usr/bin/env python3
"""Home Pi self-update from the owner's GitHub repo.
Checks the repo's system-version.json; when the remote is newer, downloads
the overlay manifest, verifies each file's sha256, backs up what it replaces
to /var/backups/homepi-update/, and installs. NEVER touches auth.json,
vault.enc, fan.conf, watchdog.conf, or anything under /root (user data).
Scope: this updates the Home Pi system scripts/config (the python tools,
launcher, store). It cannot update the kernel or rootfs base - that is a
reflash, said plainly in the README.
--check: report only. --auto: apply when different (used by cron).
--force: reinstall the published manifest even if the installed version matches.
DEMO/tests: HPUPDATE_REMOTE=<local dir> acts as the repo raw content."""
import argparse
import hashlib, json, os, shutil, sys, tempfile, time, urllib.request

VERSION = '1.1.9'
RAW = 'https://raw.githubusercontent.com/Greenisus1/homepi/main'
REMOTE = os.environ.get('HPUPDATE_REMOTE')           # dir path = demo mode
LOCAL_VER = '/etc/homepi/system-version.json'
BACKUP = '/var/backups/homepi-update'
PROTECTED = ('etc/homepi/auth.json', 'etc/homepi/vault.enc',
             'etc/homepi/fan.conf', 'etc/homepi/watchdog.conf')
if os.environ.get('HPUPDATE_ROOT'):                  # tests
    _r = os.environ['HPUPDATE_ROOT']
    LOCAL_VER = os.path.join(_r, LOCAL_VER.lstrip('/'))
    BACKUP = os.path.join(_r, BACKUP.lstrip('/'))


def read_remote(path):
    if REMOTE:
        with open(os.path.join(REMOTE, path)) as f:
            return f.read()
    with urllib.request.urlopen('%s/%s' % (RAW, path), timeout=15) as r:
        return r.read().decode('utf-8')


def remote_bytes(path):
    if REMOTE:
        with open(os.path.join(REMOTE, path), 'rb') as f:
            return f.read()
    with urllib.request.urlopen('%s/%s' % (RAW, path), timeout=30) as r:
        return r.read()


def local_version():
    try:
        with open(LOCAL_VER) as f:
            return json.load(f).get('version', '0')
    except Exception:
        return '0'


def check():
    remote = json.loads(read_remote('system-version.json'))
    return remote, remote.get('version', '0') != local_version()


def apply(remote):
    root = os.environ.get('HPUPDATE_ROOT', '/')
    manifest = json.loads(read_remote(remote['manifest']))
    installed, skipped = [], []
    backup_run = None
    for entry in manifest['files']:
        rel, want = entry['path'], entry['sha256']
        if rel in PROTECTED or rel.startswith('root/'):
            skipped.append(rel)
            continue
        body = remote_bytes(entry['source'])
        if hashlib.sha256(body).hexdigest() != want:
            raise SystemExit('hpupdate: checksum mismatch on %s - aborted' % rel)
        dest = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            if backup_run is None:
                os.makedirs(BACKUP, exist_ok=True)
                backup_run = tempfile.mkdtemp(prefix=time.strftime('%Y%m%d-%H%M%S-'), dir=BACKUP)
            backup = os.path.join(backup_run, rel)
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copy2(dest, backup)
        with open(dest, 'wb') as f:
            f.write(body)
        os.chmod(dest, entry.get('mode', 0o755))
        installed.append(rel)
    os.makedirs(os.path.dirname(LOCAL_VER), exist_ok=True)
    with open(LOCAL_VER, 'w') as f:
        json.dump({'version': remote['version'], 'updated': time.time()}, f)
    return installed, skipped


def main():
    parser = argparse.ArgumentParser(description='Update HomePi system tools from the published manifest.')
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--check', action='store_true', help='report only; never install files')
    parser.add_argument('--auto', action='store_true', help='apply published updates (cron/menu compatibility)')
    parser.add_argument('--force', action='store_true', help='reinstall even when the version matches; checksums and protections still apply')
    args = parser.parse_args()
    try:
        remote, newer = check()
    except Exception as e:
        print('hpupdate: cannot reach repo: %s' % e)
        return 1
    if not newer and not args.force:
        print('hpupdate: up to date (version %s)' % local_version())
        return 0
    if not newer:
        print('hpupdate: reinstalling version %s (--force)' % remote['version'])
    else:
        print('hpupdate: version %s -> %s' % (local_version(), remote['version']))
    if args.check:
        return 0
    installed, skipped = apply(remote)
    for rel in installed:
        print('updated: %s' % rel)
    for rel in skipped:
        print('protected, untouched: %s' % rel)
    print('hpupdate: done. Replaced files backed up under %s' % BACKUP)
    return 0


if __name__ == '__main__':
    sys.exit(main())
