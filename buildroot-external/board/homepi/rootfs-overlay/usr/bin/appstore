#!/usr/bin/env python3
"""Home Pi App Store: browse and install Pi Store apps from the Home launcher.
Catalog: the public Greenisus1 GitHub repos carrying an app-version.json
marker (the Pi Store format). Install = fetch the repo tarball into
/root/apps/<name> and run its app-store.sh. Needs network for live use.
Demo/tests: HOMEPI_STORE_DEMO=<catalog.json> with local src dirs, no network,
apps root overridden by HOMEPI_APPS_ROOT."""
import curses, json, os, subprocess, sys, urllib.request

VERSION = '1.0.0'
ORG = 'Greenisus1'
REPOS_URL = 'https://api.github.com/users/%s/repos?per_page=100' % ORG
MARKER_URL = 'https://raw.githubusercontent.com/%s/%%s/main/app-version.json' % ORG
TARBALL_URL = 'https://github.com/%s/%%s/archive/refs/heads/main.tar.gz' % ORG
DEMO_CATALOG = os.environ.get('HOMEPI_STORE_DEMO')
APPS_ROOT = os.environ.get('HOMEPI_APPS_ROOT', '/root/apps')


def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'homepi-store'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def live_catalog():
    apps = []
    for repo in fetch_json(REPOS_URL):
        name = repo.get('name')
        try:
            marker = fetch_json(MARKER_URL % name)
        except Exception:
            continue                     # no app-version.json = not a store app
        apps.append({'name': name,
                     'version': str(marker.get('version', '?')),
                     'description': repo.get('description') or ''})
    return sorted(apps, key=lambda a: a['name'])


def demo_catalog():
    with open(DEMO_CATALOG) as f:
        return json.load(f)


def get_catalog():
    return demo_catalog() if DEMO_CATALOG else live_catalog()


def installed_version(name):
    try:
        with open(os.path.join(APPS_ROOT, name, 'app-version.json')) as f:
            return str(json.load(f).get('version', '?'))
    except Exception:
        return None


def install(app):
    name = app['name']
    dest = os.path.join(APPS_ROOT, name)
    os.makedirs(APPS_ROOT, exist_ok=True)
    if DEMO_CATALOG:
        src = app.get('src')
        subprocess.run(['rm', '-rf', dest], check=False)
        subprocess.run(['cp', '-r', src, dest], check=True)
    else:
        tgz = '/tmp/homepi-store-%s.tar.gz' % name
        urllib.request.urlretrieve(TARBALL_URL % name, tgz)
        subprocess.run(['rm', '-rf', dest], check=False)
        os.makedirs(dest, exist_ok=True)
        subprocess.run(['tar', '-xzf', tgz, '-C', dest, '--strip-components=1'],
                       check=True)
    script = os.path.join(dest, 'app-store.sh')
    if os.path.exists(script):
        subprocess.run(['sh', script, 'install'], cwd=dest, check=False)
    return True


def draw(scr, apps, pos, status):
    scr.erase()
    h, w = scr.getmaxyx()
    scr.addstr(1, 2, 'Pi App Store', curses.A_BOLD)
    scr.addstr(2, 2, 'Greenisus1 / WinnieGaming - enter=install  r=refresh  q=quit')
    for i, app in enumerate(apps[:h - 6]):
        inst = installed_version(app['name'])
        tag = '[installed %s]' % inst if inst else '[not installed]'
        line = '%-16s %-8s %-18s %s' % (app['name'], app.get('version', '?'),
                                        tag, (app.get('description') or '')[:40])
        scr.addstr(4 + i, 2, line[:w - 4],
                   curses.A_REVERSE if i == pos else curses.A_NORMAL)
    if status:
        scr.addstr(h - 2, 2, status[:w - 4], curses.A_BOLD)
    scr.refresh()


def store(scr):
    curses.curs_set(0)
    status = 'Loading catalog...'
    apps = []
    try:
        apps = get_catalog()
        status = '' if apps else 'No apps found.'
    except Exception as e:
        status = 'Catalog failed: %s (need network?)' % e
    pos = 0
    while True:
        draw(scr, apps, pos, status)
        k = scr.getch()
        if k in (ord('q'), ord('Q'), 27):
            return 0
        if k in (curses.KEY_UP, ord('k')) and pos > 0:
            pos -= 1
        elif k in (curses.KEY_DOWN, ord('j')) and pos < len(apps) - 1:
            pos += 1
        elif k == ord('r'):
            status = 'Refreshing...'
            draw(scr, apps, pos, status)
            try:
                apps = get_catalog()
                status = ''
            except Exception as e:
                status = 'Catalog failed: %s' % e
        elif k in (10, 13, curses.KEY_ENTER) and apps:
            app = apps[pos]
            status = 'Installing %s...' % app['name']
            draw(scr, apps, pos, status)
            try:
                install(app)
                status = 'Installed %s %s.' % (app['name'], app.get('version', '?'))
            except Exception as e:
                status = 'Install failed: %s' % e


def main():
    if '--version' in sys.argv:
        print(VERSION)
        return 0
    if '--list' in sys.argv:
        for a in get_catalog():
            inst = installed_version(a['name'])
            print('%-16s %-8s %s' % (a['name'], a.get('version', '?'),
                                     'installed %s' % inst if inst else 'not installed'))
        return 0
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.stderr.write('appstore: needs a real terminal.\n')
        return 2
    try:
        return curses.wrapper(store)
    except curses.error as e:
        sys.stderr.write('appstore: terminal error: %s\n' % e)
        return 2


if __name__ == '__main__':
    sys.exit(main())
