import json, os, tempfile, unittest

import homepilib as H


class TestOsRelease(unittest.TestCase):
    ORIG = ('PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nNAME="Debian GNU/Linux"\n'
            'VERSION_ID="13"\nVERSION="13 (trixie)"\nID=debian\nID_LIKE=\n'
            'HOME_URL="https://www.debian.org/"\n')

    def test_rebrand_keeps_apt_fields(self):
        out = H.render_os_release(self.ORIG)
        self.assertIn('NAME="Home Pi"', out)
        self.assertIn('ID=debian', out)
        self.assertIn('VERSION_ID="13"', out)
        self.assertNotIn('Debian GNU/Linux"\nNAME', out)
        names = [l for l in out.splitlines() if l.startswith('NAME=')]
        prettys = [l for l in out.splitlines() if l.startswith('PRETTY_NAME=')]
        self.assertEqual(len(names), 1)
        self.assertEqual(len(prettys), 1)

    def test_empty_input(self):
        out = H.render_os_release('')
        self.assertIn('Home Pi', out)


class TestDiscovery(unittest.TestCase):
    def test_dirs_and_config(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'coolapp'))
            open(os.path.join(d, 'coolapp/app-store.sh'), 'w').write('#!/bin/bash\n')
            cfg = os.path.join(d, 'apps.json')
            with open(cfg, 'w') as f:
                json.dump({'My Tool': 'mytool --go'}, f)
            apps = H.discover_apps([d], cfg, which=lambda c: None)
            self.assertEqual(dict(apps)['coolapp'], 'bash "%s" run' %
                             os.path.join(d, 'coolapp/app-store.sh'))
            self.assertEqual(dict(apps)['My Tool'], 'mytool --go')

    def test_store_entry_when_present(self):
        apps = H.discover_apps([], None, which=lambda c: '/usr/bin/appstore')
        self.assertIn(('App Store', 'appstore'), apps)

    def test_missing_config_ok(self):
        self.assertEqual(H.discover_apps([], '/nonexistent.json',
                                         which=lambda c: None), [])


if __name__ == '__main__':
    unittest.main()
