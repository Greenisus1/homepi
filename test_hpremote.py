#!/usr/bin/env python3
"""Tests for hpremote (Home Pi remote desktop). Unit tests run anywhere;
the PTY test exercises the viewer UI against a fake console buffer."""
import contextlib, hashlib, io, json, os, pty, select, signal, subprocess, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hpremote


def make_vcsa(rows, cols, text):
    """Build a fake /dev/vcsaN buffer with `text` at the top-left."""
    cells = bytearray()
    grid = [list(text[i * cols:(i + 1) * cols].ljust(cols)) for i in range(rows)]
    for r in range(rows):
        for c in range(cols):
            cells += grid[r][c].encode('latin-1')[:1] + b'\x07'
    return bytes([rows, cols, 0, 0]) + bytes(cells)


class StateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        hpremote.STATE_DIR = self.tmp
        hpremote.STATE = os.path.join(self.tmp, 'remote.json')
        hpremote.LOG = os.path.join(self.tmp, 'hpremote.log')
        hpremote.RUN_DIR = os.path.join(self.tmp, 'run')

    def _on(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(hpremote.cmd_on(), 0)
        pin = out.getvalue().split('Pairing PIN:')[1].split()[0]
        self.assertEqual(len(pin), 6)
        return pin

    def test_parse_vcsa(self):
        rows, cols, cur, lines = hpremote.parse_vcsa(make_vcsa(2, 4, 'Hi'))
        self.assertEqual((rows, cols), (2, 4))
        self.assertEqual(lines[0], 'Hi')
        self.assertEqual(lines[1], '')
        self.assertEqual(hpremote.parse_vcsa(b''), (0, 0, (0, 0), []))

    def test_keymaps(self):
        self.assertEqual(hpremote.char_to_key('a'), (30, False, False))
        self.assertEqual(hpremote.char_to_key('Z'), (44, True, False))
        self.assertEqual(hpremote.char_to_key('\x03'), (46, False, True))
        self.assertEqual(hpremote.map_key(hpremote.KEY_UP)[0][1], 103)
        self.assertEqual(hpremote.events_to_bytes(hpremote.map_key(hpremote.KEY_UP)), b'\x1b[A')
        self.assertEqual(hpremote.events_to_bytes(hpremote.map_key(13)), b'\r')
        self.assertEqual(hpremote.map_key(17), [])  # Ctrl-Q never injected

    def test_pair_one_time_and_token(self):
        self.assertEqual(hpremote.cmd_pair(), 1)  # off: cannot pair
        pin = self._on()
        # wrong PIN
        hpremote.getpass.getpass = lambda prompt='': '000000' if pin != '000000' else '111111'
        self.assertEqual(hpremote.cmd_pair(), 1)
        self.assertEqual(hpremote.load_state()['pin_attempts'], 1)
        # right PIN
        hpremote.getpass.getpass = lambda prompt='': pin
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(hpremote.cmd_pair(), 0)
        token = out.getvalue().split('TOKEN=')[1].split()[0]
        st = hpremote.load_state()
        self.assertIsNone(st['pin_hash'])  # one-time: PIN burned
        self.assertTrue(hpremote.token_ok(st, token))
        self.assertFalse(hpremote.token_ok(st, 'wrong' + token))
        # PIN cannot be reused
        self.assertEqual(hpremote.cmd_pair(), 1)

    def test_pin_expiry_and_lockout(self):
        pin = self._on()
        st = hpremote.load_state()
        st['pin_expires'] = time.time() - 1
        hpremote.save_state(st)
        hpremote.getpass.getpass = lambda prompt='': pin
        self.assertEqual(hpremote.cmd_pair(), 1)  # expired
        pin = self._on()
        st = hpremote.load_state()
        st['pin_attempts'] = hpremote.MAX_PIN_ATTEMPTS
        hpremote.save_state(st)
        self.assertEqual(hpremote.cmd_pair(), 1)  # locked out

    def test_off_kills_sessions(self):
        self._on()
        sleeper = subprocess.Popen(['sleep', '60'])
        os.makedirs(hpremote.RUN_DIR, exist_ok=True)
        with open(hpremote.session_file(sleeper.pid), 'w') as f:
            json.dump({'pid': sleeper.pid, 'since': 'x', 'peer': 'y', 'watch': False}, f)
        self.assertEqual(len(hpremote.sessions()), 1)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hpremote.cmd_off()
        time.sleep(0.2)
        self.assertEqual(sleeper.poll(), -signal.SIGTERM)
        self.assertEqual(hpremote.sessions(), [])
        self.assertFalse(hpremote.load_state()['enabled'])

    def test_status_and_menu_smoke(self):
        self._on()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hpremote.cmd_status()
        self.assertIn('ON', out.getvalue())


class PtyViewerTest(unittest.TestCase):
    def test_attach_watch_renders_console_and_detaches(self):
        tmp = tempfile.mkdtemp()
        vcsa = os.path.join(tmp, 'vcsa')
        with open(vcsa, 'wb') as f:
            f.write(make_vcsa(3, 20, 'Hi Home Pi'))
        token = 'testtoken123'
        salt = 'salty'
        st = {'enabled': True, 'pin_salt': salt,
              'tokens': [hashlib.sha256((salt + ':' + token).encode()).hexdigest()]}
        with open(os.path.join(tmp, 'remote.json'), 'w') as f:
            json.dump(st, f)
        env = dict(os.environ, TERM='xterm',
                   HPREMOTE_STATE_DIR=tmp, HPREMOTE_LOG=os.path.join(tmp, 'log'),
                   HPREMOTE_RUN_DIR=os.path.join(tmp, 'run'),
                   HPREMOTE_VCSA=vcsa, HPREMOTE_BACKEND='none')
        pid, fd = pty.fork()
        if pid == 0:
            os.execvpe(sys.executable, [sys.executable, os.path.join(os.path.dirname(__file__), 'hpremote.py'), 'attach', token, '--watch'], env)
        got, deadline = b'', time.time() + 15
        while time.time() < deadline and b'Hi Home Pi' not in got:
            r, _, _ = select.select([fd], [], [], 0.5)
            if r:
                try:
                    got += os.read(fd, 65536)
                except OSError:
                    break
        self.assertIn(b'Hi Home Pi', got)
        self.assertIn(b'watch only', got)
        os.write(fd, b'\x11')  # Ctrl-Q detaches
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        with open(os.path.join(tmp, 'log')) as f:
            logtext = f.read()
        self.assertIn('attach start', logtext)
        self.assertIn('attach end', logtext)

    def test_attach_refused_without_pairing(self):
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, 'remote.json'), 'w') as f:
            json.dump({'enabled': True, 'pin_salt': 's', 'tokens': []}, f)
        env = dict(os.environ, HPREMOTE_STATE_DIR=tmp)
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'hpremote.py'), 'attach', 'nope'],
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn('Not paired', r.stdout)


if __name__ == '__main__':
    unittest.main()
