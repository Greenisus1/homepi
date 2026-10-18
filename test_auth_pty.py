'''Event-driven PTY test: wizard (vault+recovery), login, GitHub keep-data reset.'''
import fcntl, os, pty, re, select, struct, subprocess, sys, tempfile, termios, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BUF = bytearray()


def wait_out(fd, patterns, timeout=20):
    need = {p: False for p in patterns}
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if fd in r:
            try:
                BUF.extend(os.read(fd, 65536))
            except OSError:
                pass
        text = BUF.decode('utf-8', 'replace')
        for p in need:
            if not need[p] and re.search(p, text):
                need[p] = True
        if all(need.values()):
            return
    raise SystemExit('TIMEOUT waiting for %s' % [p for p, v in need.items() if not v])


def spawn(home):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 120, 0, 0))
    env = dict(os.environ, TERM='xterm-256color', HOMEPI_DEMO='1',
               HOMEPI_DEMO_ROOT=home, HOME=home)
    p = subprocess.Popen(['python3', os.path.join(HERE, 'homepiauth.py')],
                         stdin=slave, stdout=slave, stderr=slave, env=env,
                         close_fds=True)
    os.close(slave)
    fcntl.fcntl(master, fcntl.F_SETFL, os.O_NONBLOCK)
    return p, master


def type_text(fd, text):
    os.write(fd, text.encode())
    time.sleep(0.3)


def wait_exit(p, code=0, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline and p.poll() is None:
        time.sleep(0.1)
    if p.poll() is None:
        p.kill()
        raise SystemExit('FAIL: process did not exit')
    if p.returncode != code:
        raise SystemExit('FAIL: exit %s, wanted %s' % (p.returncode, code))


def main():
    global BUF
    home = tempfile.mkdtemp()
    # ---- run 1: first-boot wizard ----
    p, m = spawn(home)
    try:
        wait_out(m, [r'first boot setup', r'username \[root\]'])
        type_text(m, '\r')
        wait_out(m, [r'Password rules', r'ENCRYPTS your data'])
        type_text(m, 'weak\r')
        wait_out(m, [r'Missing:'])
        type_text(m, 'Bear!2026x\r')
        wait_out(m, [r'repeat it'])
        type_text(m, 'Bear!2026x\r')
        wait_out(m, [r'Do you KNOW it by heart\?', r'GitHub QR override'])
        type_text(m, 'c')
        wait_out(m, [r'new password'])
        type_text(m, 'Goose!2026y\r')
        wait_out(m, [r'repeat it'])
        type_text(m, 'Goose!2026y\r')
        wait_out(m, [r'Do you KNOW it by heart\?'])
        type_text(m, 'y')
        wait_out(m, [r'vault encrypted', r'\[w\]i-fi setup'])
        type_text(m, 'e')
        wait_out(m, [r'reset override', r'\[DEMO\] recovery secret saved'])
        type_text(m, 'x')
        wait_exit(p)
    finally:
        if p.poll() is None:
            p.kill()
        os.close(m)
    # plant a secret in the vault, as if the user had stored data
    import vaultlib, ghlink
    master, _ = vaultlib.unlock_with_password(home, 'Goose!2026y')
    assert master, 'vault should unlock with wizard password'
    vaultlib.reset_vault(home, master, {'secrets': {'game': 'save1'}, 'created': 1})
    # ---- run 2: login wrong then right ----
    BUF = bytearray()
    p, m = spawn(home)
    try:
        wait_out(m, [r'Home Pi - log in'])
        type_text(m, 'root\r')
        type_text(m, 'Wrong!123\r')
        wait_out(m, [r'Wrong login'])
        type_text(m, '\r')
        wait_out(m, [r'username:'])
        type_text(m, 'root\r')
        type_text(m, 'Goose!2026y\r')
        wait_exit(p)
    finally:
        if p.poll() is None:
            p.kill()
        os.close(m)
    # ---- run 3: forgot -> GitHub -> recovery secret -> new pw, DATA KEPT ----
    BUF = bytearray()
    p, m = spawn(home)
    try:
        wait_out(m, [r'Home Pi - log in'])
        type_text(m, 'root\r')
        type_text(m, 'Nope!12345\r')
        wait_out(m, [r'Wrong login'])
        type_text(m, 'f')
        wait_out(m, [r'GitHub verified: Greenisus1', r'Recovery OK', r'data is KEPT'])
        type_text(m, 'Duck!2026z\r')
        wait_out(m, [r'repeat it'])
        type_text(m, 'Duck!2026z\r')
        wait_out(m, [r'Password changed\. Old data kept'])
        wait_out(m, [r'username:'])
        # old password must now fail
        type_text(m, 'root\r')
        type_text(m, 'Goose!2026y\r')
        wait_out(m, [r'Wrong login'])
        type_text(m, '\r')
        wait_out(m, [r'username:'])
        type_text(m, 'root\r')
        type_text(m, 'Duck!2026z\r')
        wait_exit(p)
    finally:
        if p.poll() is None:
            p.kill()
        os.close(m)
    # verify the planted secret survived the reset
    master, _ = vaultlib.unlock_with_password(home, 'Duck!2026z')
    assert master, 'vault should unlock with NEW password'
    data = vaultlib.vault_decrypt(master, vaultlib.load_blob(home)['vault'])
    assert data['secrets'].get('game') == 'save1', 'planted secret lost in reset: %r' % data
    print('PTY PASS (data kept through GitHub reset)')


if __name__ == '__main__':
    main()
