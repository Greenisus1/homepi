'''Home Pi transform library: rebrand + launcher install on a DietPi base.
All file operations take a root prefix so tests run against a fakeroot.'''
import glob, json, os, shutil

APP = 'homepi'
OS_NAME = 'Home Pi'
BRAND = 'Greenisus1 / WinnieGaming'
MARK_BEGIN = '# >>> homepi launcher >>>'
MARK_END = '# <<< homepi launcher <<<'
LAUNCH_HOOK = '''%s
# Home Pi: land on the fullscreen Home launcher at login (esc exits to shell).
if [ -n "$PS1" ] && [ -z "$HOMEPI_LAUNCHER_OFF" ] && command -v homepi >/dev/null 2>&1; then
  homepi
fi
%s
''' % (MARK_BEGIN, MARK_END)


def _p(root, path):
    return os.path.join(root, path.lstrip('/'))


def render_os_release(orig):
    '''Rebrand NAME/PRETTY_NAME only. Never touch ID, ID_LIKE, VERSION, apt fields.'''
    keep, seen = [], set()
    for line in orig.splitlines():
        key = line.split('=', 1)[0].strip() if '=' in line else ''
        if key in ('NAME', 'PRETTY_NAME'):
            continue
        keep.append(line)
        if key:
            seen.add(key)
    out = ['NAME="%s"' % OS_NAME, 'PRETTY_NAME="%s (DietPi base)"' % OS_NAME]
    out.extend(keep)
    return '\n'.join(out) + '\n'


def render_issue():
    return ('%s \\n \\l\n\n' % OS_NAME)


def render_motd():
    return ('\n  Welcome to %s\n  %s\n  A friendly layer on DietPi (Debian).\n'
            '  Type `homepi` any time for the Home screen; esc exits to the shell.\n\n'
            % (OS_NAME, BRAND))


def discover_apps(roots, config_path=None, which=None):
    '''Find runnable apps: dirs containing app-store.sh, plus config entries.
    Returns [(label, command), ...] sorted by label.'''
    import glob, subprocess
    found = {}
    for base in roots:
        for script in sorted(glob.glob(os.path.join(base, '*', 'app-store.sh'))):
            name = os.path.basename(os.path.dirname(script))
            found.setdefault(name, 'bash "%s" run' % script)
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path) as f:
                for label, cmd in json.load(f).items():
                    found[label] = cmd
        except Exception:
            pass
    if which is None:
        which = lambda c: shutil.which(c)
    if which('appstore'):
        found.setdefault('App Store', 'appstore')
    return sorted(found.items())
