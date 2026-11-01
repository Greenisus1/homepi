#!/usr/bin/env python3
"""Home Pi first-boot wizard + login gate (fullscreen curses).
First boot: username (Enter = root) -> password rules + warning -> confirm you
know it -> wifi/ethernet -> link GitHub by QR. The password also DERIVES the
vault key: data is only viable when logged in. The GitHub link stores a
recovery secret (secret gist) so a forgotten password can be reset WITHOUT
losing the encrypted data (the owner's call). Later boots: login (unlocks vault),
or forgot -> GitHub QR same account -> fetch recovery secret -> new password,
old data kept. Last resort only: ERASE-and-reset."""
import curses, os, subprocess, sys, time

import authlib, ghlink, qr, vaultlib

VERSION = '1.1.0'
DEMO = os.environ.get('HOMEPI_DEMO') == '1'
ROOT = os.environ.get('HOMEPI_DEMO_ROOT', '/tmp/homepi-demo') if DEMO else '/'


def prompt(scr, y, label, secret=False):
    curses.echo(0 if secret else 1)
    scr.addstr(y, 2, label)
    scr.refresh()
    win = curses.newwin(1, 40, y, 2 + len(label))
    win.refresh()
    text = ''
    while True:
        k = win.getch()
        if k in (10, 13, curses.KEY_ENTER):
            break
        if k in (27,):
            curses.noecho()
            return None
        if k in (curses.KEY_BACKSPACE, 127, 8):
            text = text[:-1]
        elif 32 <= k < 127:
            text += chr(k)
        win.erase()
        win.addstr(0, 0, ('*' * len(text)) if secret else text)
        win.refresh()
    curses.noecho()
    return text


def draw_qr(scr, y0, text):
    matrix = qr.encode(text)
    for i, row in enumerate(matrix):
        line = ''.join('██' if v else '  ' for v in row)
        if y0 + i < scr.getmaxyx()[0] - 1:
            scr.addstr(y0 + i, 4, line)


def new_password_flow(scr, y0):
    '''Ask for a rule-compliant password twice. Returns the password.'''
    while True:
        pw = prompt(scr, y0, 'new password: ', secret=True)
        if pw is None:
            continue
        problems = authlib.check_password_rules(pw)
        if problems:
            scr.addstr(y0 + 1, 2, 'Missing: ' + ', '.join(problems) + '   ')
            scr.refresh()
            time.sleep(1.5)
            scr.move(y0 + 1, 0)
            scr.clrtoeol()
            continue
        pw2 = prompt(scr, y0 + 2, 'repeat it: ', secret=True)
        if pw != pw2:
            scr.addstr(y0 + 3, 2, 'Did not match, try again.   ')
            scr.refresh()
            time.sleep(1.2)
            scr.move(y0 + 3, 0)
            scr.clrtoeol()
            continue
        return pw


def github_verify(scr, y0):
    '''QR device flow. Returns (login, token) or (None, None).
    The token is used for the immediate calls and then discarded - never stored.'''
    if DEMO:
        return ghlink.link_login(fake='Greenisus1'), 'demo-token'
    code = ghlink.request_code()
    scr.addstr(y0, 2, 'Code: %s   (or open %s)' % (code['user_code'], code['verification_uri']))
    draw_qr(scr, y0 + 1, code['verification_uri'])
    scr.refresh()
    token = ghlink.poll_token(code['device_code'], code['interval'], code['expires_in'])
    if not token:
        return None, None
    return ghlink.whoami(token), token


def save_recovery(scr, y, token, recovery_secret):
    '''Upload the recovery secret to the user's GitHub (secret gist).'''
    payload = vaultlib.recovery_payload(recovery_secret)
    if DEMO:
        ghlink.demo_store(payload)
        scr.addstr(y, 2, '[DEMO] recovery secret saved (gist simulated).   ')
        return
    ok = ghlink.upload_recovery(token, payload)
    scr.addstr(y, 2, ('Recovery secret saved to your GitHub (secret gist).   '
                      if ok else
                      'WARNING: recovery upload failed - reset will NOT work.   '))


def wizard(scr):
    scr.erase()
    scr.addstr(1, 2, 'Welcome to Home Pi - first boot setup', curses.A_BOLD)
    scr.addstr(3, 2, 'Choose a username. Press Enter for the default: root')
    u = prompt(scr, 4, 'username [root]: ')
    username = (u or '').strip() or 'root'
    while True:
        scr.addstr(6, 2, 'Password rules: 8+ chars, 1 capital, 1 number, 1 special.')
        scr.addstr(7, 2, 'It also ENCRYPTS your data: only this password unlocks it.',
                   curses.A_BOLD)
        pw = new_password_flow(scr, 8)
        scr.addstr(12, 2, 'Do you KNOW it by heart? If you forget it, only the')
        scr.addstr(13, 2, 'GitHub QR override (same account) can reset it.')
        scr.addstr(14, 2, '[y]es I know it  /  [c]hange it ')
        scr.refresh()
        k = scr.getch()
        if k in (ord('y'), ord('Y')):
            break
    master, kek, salt, recovery_secret = vaultlib.create_vault(ROOT, pw)
    authlib.save_auth(ROOT, username, pw, salt_hex=salt.hex())
    scr.addstr(16, 2, 'Saved. Password = salted verifier only; data vault encrypted.')
    scr.addstr(18, 2, 'Network: [w]i-fi setup  /  [e]thernet (skip) ')
    scr.refresh()
    k = scr.getch()
    if k in (ord('w'), ord('W')):
        ssid = prompt(scr, 19, 'wifi name (SSID): ')
        wpw = prompt(scr, 20, 'wifi password: ', secret=True)
        if ssid and not DEMO:
            conf = ('network={\n  ssid="%s"\n  psk="%s"\n}\n'
                    % (ssid.replace('"', ''), (wpw or '').replace('"', '')))
            try:
                with open('/etc/wpa_supplicant.conf', 'w') as f:
                    f.write(conf)
                subprocess.run(['wpa_supplicant', '-B', '-i', 'wlan0',
                                '-c', '/etc/wpa_supplicant.conf'], check=False)
                subprocess.run(['udhcpc', '-i', 'wlan0', '-q'], check=False)
            except Exception:
                pass
        scr.addstr(21, 2, 'wifi: attempting connection to %s   ' % (ssid or '?'))
    else:
        scr.addstr(19, 2, 'ethernet: nothing to do.   ')
    scr.addstr(23, 2, 'Last step: link your GitHub - the reset override if you')
    scr.addstr(24, 2, 'forget the password. Keeps your data. [s]kip ')
    scr.refresh()
    if DEMO:
        login, token = github_verify(scr, 25)
        authlib.set_github_login(ROOT, login)
        save_recovery(scr, 25, token, recovery_secret)
        scr.refresh()
        time.sleep(1)
    else:
        k = scr.getch()
        if k not in (ord('s'), ord('S')):
            login, token = github_verify(scr, 25)
            if login:
                authlib.set_github_login(ROOT, login)
                save_recovery(scr, 25, token, recovery_secret)
                scr.addstr(26, 2, 'Linked GitHub: %s   ' % login)
            else:
                scr.addstr(25, 2, 'No link made; reset will NOT be available.   ')
            scr.refresh()
            time.sleep(1.5)
    scr.addstr(scr.getmaxyx()[0] - 2, 2, 'Setup done - press any key for the Home screen')
    scr.refresh()
    scr.getch()
    return 0


def login(scr, rec):
    limiter = authlib.RateLimiter()
    while True:
        scr.erase()
        scr.addstr(1, 2, 'Home Pi - log in', curses.A_BOLD)
        if limiter.blocked():
            scr.addstr(4, 2, 'Too many tries. Wait %ds.   ' % limiter.blocked_seconds())
            scr.refresh()
            time.sleep(1)
            continue
        u = prompt(scr, 3, 'username: ')
        if u is None:
            return 2
        p = prompt(scr, 4, 'password: ', secret=True)
        kek = (authlib.check_and_kek(p or '', rec['salt'], rec['hash'])
               if u == rec['username'] else None)
        limiter.record(kek is not None)
        if kek is not None:
            blob = vaultlib.load_blob(ROOT)
            master = vaultlib.unwrap_key(blob['wrap_pw'], kek) if blob else None
            if master is None or vaultlib.vault_decrypt(master, blob['vault']) is None:
                scr.addstr(6, 2, 'VAULT DAMAGED: integrity check failed. Data unreadable.   ')
                scr.refresh()
                time.sleep(3)
                return 3
            return 0
        scr.addstr(6, 2, 'Wrong login. [enter] retry, [f]orgot password ')
        scr.refresh()
        k = scr.getch()
        if k in (ord('f'), ord('F')):
            rc = forgot(scr, rec)
            if rc is not None:
                rec = rc
    return 2


def forgot(scr, rec):
    '''GitHub override: same linked account -> recovery secret -> new password,
    data KEPT. Last resort: type ERASE to wipe data and start fresh.
    Returns the refreshed auth record after reset, or None.'''
    if rec.get('linux_account'):
        scr.addstr(7, 2, 'Use sudo password to change Linux, disk and vault passwords together.')
        scr.refresh()
        time.sleep(3)
        return None
    if not rec.get('github_login'):
        scr.addstr(7, 2, 'No GitHub override was linked at setup. Cannot reset.   ')
        scr.refresh()
        time.sleep(2)
        return None
    scr.addstr(7, 2, 'Verify with GitHub: scan the QR with the LINKED account.   ')
    scr.refresh()
    login_name, token = github_verify(scr, 8)
    if not (login_name and login_name.lower() == rec['github_login'].lower()):
        scr.addstr(8, 2, 'That was not the linked GitHub account. No reset.   ')
        scr.refresh()
        time.sleep(2)
        return None
    scr.erase()
    scr.addstr(1, 2, 'GitHub verified: %s' % login_name, curses.A_BOLD)
    scr.addstr(3, 2, 'Fetching your recovery secret from GitHub...   ')
    scr.refresh()
    if DEMO:
        payload = ghlink.demo_fetch()
        secret = vaultlib.secret_from_payload(payload) if payload else None
    else:
        secret = ghlink.fetch_recovery_secret(token)
    if secret:
        master = vaultlib.unlock_with_recovery_secret(ROOT, secret)
    else:
        master = None
    if master is not None:
        scr.addstr(3, 2, 'Recovery OK. Your data is KEPT. Set a new password.   ')
        scr.refresh()
        npw = new_password_flow(scr, 5)
        salt = os.urandom(16)
        vaultlib.rewrap_new_password(ROOT, master, npw, salt=salt)
        authlib.save_auth(ROOT, rec['username'], npw, rec.get('github_login'),
                          salt_hex=salt.hex())
        rec = authlib.load_auth(ROOT)
        scr.addstr(9, 2, 'Password changed. Old data kept. Log in.   ')
        scr.refresh()
        time.sleep(1.5)
        return rec
    scr.addstr(3, 2, 'Recovery secret NOT available (no network / gist gone).   ')
    scr.addstr(4, 2, 'Last resort: ERASE the old encrypted data and start fresh.', curses.A_BOLD)
    scr.addstr(6, 2, 'Type ERASE to wipe everything, or esc to cancel: ')
    scr.refresh()
    win = curses.newwin(1, 10, 7, 2)
    win.refresh()
    confirm = ''
    while True:
        k = win.getch()
        if k in (10, 13, curses.KEY_ENTER):
            break
        if k in (27,):
            return None
        if k in (curses.KEY_BACKSPACE, 127, 8):
            confirm = confirm[:-1]
        elif 32 <= k < 127:
            confirm += chr(k)
        win.erase()
        win.addstr(0, 0, confirm)
        win.refresh()
    if confirm != 'ERASE':
        scr.addstr(9, 2, 'Cancelled. Nothing erased.   ')
        scr.refresh()
        time.sleep(1.5)
        return None
    npw = new_password_flow(scr, 9)
    salt = os.urandom(16)
    _, _, _, new_secret = vaultlib.wipe_vault(ROOT, npw, salt=salt)
    authlib.save_auth(ROOT, rec['username'], npw, rec.get('github_login'),
                      salt_hex=salt.hex())
    save_recovery(scr, 13, token, new_secret)   # fresh gist for the new vault
    rec = authlib.load_auth(ROOT)
    scr.addstr(14, 2, 'Reset done. Old data erased. Log in with the new password.   ')
    scr.refresh()
    time.sleep(2)
    return rec


def main():
    if '--version' in sys.argv:
        print(VERSION)
        return 0
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.stderr.write('homepiauth: needs a real terminal; stdin/stdout is not a TTY.\n')
        return 2
    rec = authlib.load_auth(ROOT)
    try:
        if rec is None:
            return curses.wrapper(wizard)
        return curses.wrapper(login, rec)
    except curses.error as e:
        sys.stderr.write('homepiauth: terminal error: %s\n' % e)
        return 2
    except KeyboardInterrupt:
        return 2


if __name__ == '__main__':
    sys.exit(main())
