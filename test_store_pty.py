'''PTY test for the App Store client in demo mode (no network).'''
import fcntl, json, os, pty, re, select, struct, subprocess, tempfile, termios, time

HERE = os.path.dirname(os.path.abspath(__file__))
BUF = bytearray()


def wait_out(fd, patterns, timeout=15):
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
    home = tempfile.mkdtemp()
    src = os.path.join(home, 'src', 'demogame')
    os.makedirs(src)
    with open(os.path.join(src, 'app-version.json'), 'w') as f:
        json.dump({'name': 'demogame', 'version': '1.2.0'}, f)
    with open(os.path.join(src, 'app-store.sh'), 'w') as f:
        f.write('#!/bin/sh\ntouch "$(dirname "$0")/.installed-by-store"\n')
    catalog = os.path.join(home, 'catalog.json')
    with open(catalog, 'w') as f:
        json.dump([{'name': 'demogame', 'version': '1.2.0',
                    'description': 'demo entry', 'src': src},
                   {'name': 'otherapp', 'version': '0.1.0',
                    'description': 'not picked', 'src': src}], f)
    apps_root = os.path.join(home, 'apps')
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
    env = dict(os.environ, TERM='xterm-256color', HOMEPI_STORE_DEMO=catalog,
               HOMEPI_APPS_ROOT=apps_root)
    p = subprocess.Popen(['python3', os.path.join(HERE, 'homepi-store.py')],
                         stdin=slave, stdout=slave, stderr=slave, env=env,
                         close_fds=True)
    os.close(slave)
    fcntl.fcntl(master, fcntl.F_SETFL, os.O_NONBLOCK)
    try:
        wait_out(master, [r'Pi App Store', r'demogame', r'\[not installed\]'])
        os.write(master, b'\r')                       # install first entry
        time.sleep(0.5)
        wait_out(master, [r'demogame 1\.2\.0\.'])
        time.sleep(0.5)
        os.write(master, b'r')                        # refresh: status flips
        wait_out(master, [r'installed 1\.2\.0'])
        os.write(master, b'q')
        deadline = time.time() + 10
        while time.time() < deadline and p.poll() is None:
            time.sleep(0.1)
        if p.poll() is None:
            p.kill()
            raise SystemExit('FAIL: store did not exit')
        if p.returncode != 0:
            raise SystemExit('FAIL: exit %d' % p.returncode)
    finally:
        if p.poll() is None:
            p.kill()
        os.close(master)
    marker = os.path.join(apps_root, 'demogame', '.installed-by-store')
    assert os.path.exists(marker), 'app-store.sh install did not run'
    print('PTY PASS (store: list, install, refresh, quit)')


if __name__ == '__main__':
    main()
