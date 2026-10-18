import os, signal, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def run(env_extra, args=('--once',)):
    return subprocess.run(['python3', os.path.join(HERE, 'watchdogd.py')] + list(args),
                          capture_output=True, text=True,
                          env=dict(os.environ, **env_extra))


class TestWatchdogd(unittest.TestCase):
    def test_once_pings_and_disarms(self):
        dev = os.path.join(tempfile.mkdtemp(), 'wd')
        open(dev, 'w').close()
        r = run({'WATCHDOGD_DEV': dev, 'WATCHDOGD_CONF': '/nonexistent'})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(dev).read(), '1V')       # ping then magic close

    def test_missing_device_is_clean_noop(self):
        r = run({'WATCHDOGD_DEV': '/nonexistent/wd', 'WATCHDOGD_CONF': '/nonexistent'})
        self.assertEqual(r.returncode, 0)
        self.assertIn('nothing to do', r.stdout)

    def test_disabled_conf_noop(self):
        dev = os.path.join(tempfile.mkdtemp(), 'wd')
        open(dev, 'w').close()
        conf = os.path.join(tempfile.mkdtemp(), 'watchdog.conf')
        open(conf, 'w').write('ENABLED=0\n')
        r = run({'WATCHDOGD_DEV': dev, 'WATCHDOGD_CONF': conf})
        self.assertIn('disabled', r.stdout)
        self.assertEqual(open(dev).read(), '')         # never touched

    def test_daemon_pings_then_sigterm_disarms(self):
        dev = os.path.join(tempfile.mkdtemp(), 'wd')
        open(dev, 'w').close()
        conf = os.path.join(tempfile.mkdtemp(), 'watchdog.conf')
        open(conf, 'w').write('ENABLED=1\nPING_SECONDS=1\n')
        p = subprocess.Popen(['python3', os.path.join(HERE, 'watchdogd.py')],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=dict(os.environ, WATCHDOGD_DEV=dev, WATCHDOGD_CONF=conf))
        time.sleep(2.5)                                # ~2 pings
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=10)
        self.assertEqual(p.returncode, 0)
        body = open(dev).read()
        self.assertTrue(body.startswith('11') and body.endswith('V'), body)


if __name__ == '__main__':
    unittest.main()
