#!/usr/bin/env python3
"""Home Pi backup to GitHub (opt-in): backs up chosen folders to a PRIVATE
repo (homepi-backup) on the owner's GitHub.
- QR device-flow login (scope: repo - needed to create/push the private repo).
- Token lives in memory for the run only; never written to .git/config,
  remote URLs, or any file.
- Files bigger than the split cap (default 95M, GitHub rejects >100M blobs)
  are stored as numbered parts + a reassemble.sh, never rejected.
- Add-only: backup never deletes remote content and never force-pushes.
Demo/tests: HOMEPI_DEMO=1 skips the QR and pushes to a local bare repo at
$HOMEPI_DEMO_ROOT/backup-remote.git (no network)."""
import json, os, subprocess, sys, urllib.request

import ghlink

VERSION = '1.0.0'
DEMO = os.environ.get('HOMEPI_DEMO') == '1'
ROOT = os.environ.get('HOMEPI_DEMO_ROOT', '/tmp/homepi-demo') if DEMO else '/'
REPO_NAME = 'homepi-backup'
SPLIT_BYTES = int(os.environ.get('HPBACKUP_SPLIT_MB', '95')) * 1024 ** 2
WORK = os.path.join(ROOT, 'root/.homepi-backup/repo') if DEMO else '/root/.homepi-backup/repo'
DEFAULT_PATHS = ['/root/apps', '/etc/homepi']


def _git(args, cwd, token=None):
    cmd = ['git']
    if token:
        cmd += ['-c', 'http.extraHeader=Authorization: Bearer %s' % token]
    cmd += args
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('hpbackup: git %s failed: %s' % (args[0], r.stderr.strip()))
    return r.stdout.strip()


def ensure_repo(login, token):
    """Create the private repo if missing (real mode only)."""
    req = urllib.request.Request('https://api.github.com/user/repos',
                                 data=json.dumps({'name': REPO_NAME, 'private': True}).encode(),
                                 headers={'Authorization': 'Bearer %s' % token,
                                          'Accept': 'application/json',
                                          'User-Agent': 'homepi'})
    try:
        urllib.request.urlopen(req, timeout=15)      # 201 created
    except urllib.error.HTTPError as e:
        if e.code != 422:                            # 422 = already exists
            raise


def stage(paths):
    """Copy paths into the working repo; split oversized files. Never deletes."""
    os.makedirs(WORK, exist_ok=True)
    staged = 0
    for src in paths:
        if not os.path.exists(src):
            print('hpbackup: skip missing %s' % src)
            continue
        base = os.path.basename(src.rstrip('/'))
        dest = os.path.join(WORK, base)
        if os.path.isdir(src):
            subprocess.run(['cp', '-r', src, dest + '.tmp'], check=True)
            subprocess.run(['rm', '-rf', dest], check=False)
            os.replace(dest + '.tmp', dest)
        else:
            subprocess.run(['cp', src, dest], check=True)
        staged += 1
    for dirpath, _, files in os.walk(WORK):
        if '.git' in dirpath.split(os.sep):
            continue
        for fn in files:
            fp = os.path.join(dirpath, fn)
            if os.path.getsize(fp) > SPLIT_BYTES and not fn.endswith('.part'):
                split_file(fp)
    return staged


def split_file(fp):
    parts_dir = fp + '.parts'
    os.makedirs(parts_dir, exist_ok=True)
    n, total = 0, os.path.getsize(fp)
    with open(fp, 'rb') as src:
        while True:
            block = src.read(SPLIT_BYTES)
            if not block:
                break
            n += 1
            with open(os.path.join(parts_dir, '%04d.part' % n), 'wb') as out:
                out.write(block)
    with open(os.path.join(parts_dir, 'reassemble.sh'), 'w') as f:
        base = os.path.basename(fp)
        f.write('#!/bin/sh\ncat "$(dirname "$0")"/*.part > "%s"\n'
                'echo reassembled %s (%d bytes)\n' % (base, base, total))
    os.chmod(os.path.join(parts_dir, 'reassemble.sh'), 0o755)
    os.unlink(fp)
    print('hpbackup: split %s into %d parts' % (fp, n))


def run_backup(paths, login, token):
    staged = stage(paths)
    if not staged:
        print('hpbackup: nothing to back up.')
        return 1
    if not os.path.isdir(os.path.join(WORK, '.git')):
        _git(['init', '-q'], WORK)
        _git(['config', 'user.email', 'homepi@local'], WORK)
        _git(['config', 'user.name', 'Home Pi'], WORK)
    _git(['add', '-A'], WORK)
    status = _git(['status', '--porcelain'], WORK)
    if not status:
        print('hpbackup: already up to date.')
        return 0
    _git(['commit', '-q', '-m', 'Home Pi backup'], WORK)
    if DEMO:
        remote = os.path.join(ROOT, 'backup-remote.git')
        if not os.path.isdir(remote):
            subprocess.run(['git', 'init', '-q', '--bare', remote], check=True)
        _git(['push', '-q', remote, 'HEAD:main'], WORK)
    else:
        url = 'https://github.com/%s/%s.git' % (login, REPO_NAME)
        ensure_repo(login, token)
        _git(['push', '-q', url, 'HEAD:main'], WORK, token=token)
    print('hpbackup: pushed to %s (%s)' % (REPO_NAME, 'demo' if DEMO else 'private repo'))
    return 0


def main():
    if '--version' in sys.argv:
        print(VERSION)
        return 0
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args or args[0] != 'backup':
        print('usage: hpbackup backup [path...]   (default: %s)' % ' '.join(DEFAULT_PATHS))
        return 2
    paths = args[1:] or [p if not DEMO else os.path.join(ROOT, p.lstrip('/'))
                         for p in DEFAULT_PATHS]
    if DEMO:
        login, token = 'Greenisus1', 'demo-token'
    else:
        code = ghlink.request_code(scope='read:user repo')
        print('Approve this backup login: %s   (code %s)'
              % (code['verification_uri'], code['user_code']))
        token = ghlink.poll_token(code['device_code'], code['interval'],
                                  code['expires_in'])
        if not token:
            print('hpbackup: login not approved; nothing backed up.')
            return 1
        login = ghlink.whoami(token)
    return run_backup(paths, login, token)


if __name__ == '__main__':
    sys.exit(main())
