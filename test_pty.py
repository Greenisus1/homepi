'''Event-driven PTY smoke test for the Home Pi launcher (demo mode).'''
import fcntl, os, pty, re, select, struct, subprocess, tempfile, termios, time

HERE = os.path.dirname(os.path.abspath(__file__))
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


def main():
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
    env = dict(os.environ, TERM='xterm-256color', HOMEPI_DEMO='1',
               HOME=tempfile.mkdtemp())
    p = subprocess.Popen(['python3', os.path.join(HERE, 'homepi.py')],
                         stdin=slave, stdout=slave, stderr=slave, env=env,
                         close_fds=True)
    os.close(slave)
    fcntl.fcntl(master, fcntl.F_SETFL, os.O_NONBLOCK)
    try:
        wait_out(master, [r'H O M E   P I', r'Cardcoot', r'App Store', r'Backup to GitHub',
                          r'Reboot', r'arrows move', r'Made by Greenisus1',
                          r'based on Linux'])
        # run the first entry (Cardcoot demo), then return to Home
        os.write(master, b'\r')
        wait_out(master, [r'demo-cardcoot', r'back to Home'])
        os.write(master, b'\r')
        wait_out(master, [r'H O M E   P I'])
        # navigate down to Reboot... (index 7), enter, decline the confirm
        for _ in range(7):
            os.write(master, b'j')
            time.sleep(0.15)
        os.write(master, b'\r')
        wait_out(master, [r'Reboot the Pi now\?'])
        os.write(master, b'n')
        wait_out(master, [r'H O M E   P I'])
        os.write(master, b'q')
        deadline = time.time() + 10
        while time.time() < deadline and p.poll() is None:
            time.sleep(0.1)
        if p.poll() is None:
            p.kill()
            raise SystemExit('FAIL: did not exit on q')
        if p.returncode != 0:
            raise SystemExit('FAIL: exit %d' % p.returncode)
        print('PTY PASS')
    finally:
        if p.poll() is None:
            p.kill()
        os.close(master)


if __name__ == '__main__':
    main()
