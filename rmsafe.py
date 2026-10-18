#!/usr/bin/env python3
"""Home Pi safe delete (the owner's safety rule): deleting asks for confirmation
and MOVES things to a trash folder instead of erasing them.
- Interactive shell alias rm -> rmsafe (set in /root/.profile). Scripts that
  call rm directly still hard-delete; that is correct, only people get the
  safety net.
- Nothing is ever erased automatically: --empty asks again.
- Non-interactive use without --yes refuses (so a misfired command in a
  pipeline cannot silently delete).
Trash root: /.trash (override in tests with RMSAFE_TRASH)."""
import os, shutil, sys, time

VERSION = '1.0.0'
TRASH = os.environ.get('RMSAFE_TRASH', '/.trash')


def trash_path(name):
    dest = os.path.join(TRASH, name)
    n = 1
    while os.path.lexists(dest):
        n += 1
        dest = os.path.join(TRASH, '%s.%d' % (name, n))
    return dest


def confirm(question):
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    sys.stdout.write(question + '  [y/N] ')
    sys.stdout.flush()
    try:
        return sys.stdin.readline().strip().lower() in ('y', 'yes')
    except Exception:
        return False


def move_to_trash(paths, yes=False):
    existing = [p for p in paths if os.path.lexists(p)]
    missing = [p for p in paths if not os.path.lexists(p)]
    for m in missing:
        print('rmsafe: no such file: %s' % m, file=sys.stderr)
    if not existing:
        return 1
    if not yes and not confirm('Move %d item(s) to trash?' % len(existing)):
        print('rmsafe: nothing deleted.')
        return 2
    os.makedirs(TRASH, exist_ok=True)
    for p in existing:
        dest = trash_path(os.path.basename(os.path.abspath(p)))
        shutil.move(p, dest)
        print('trashed: %s -> %s' % (p, dest))
    return 0


def restore(name):
    src = os.path.join(TRASH, name)
    if not os.path.lexists(src):
        print('rmsafe: not in trash: %s' % name, file=sys.stderr)
        return 1
    dest = os.path.join(os.getcwd(), name)
    if os.path.lexists(dest):
        print('rmsafe: %s already exists here' % name, file=sys.stderr)
        return 1
    shutil.move(src, dest)
    print('restored: %s' % dest)
    return 0


def main():
    args = sys.argv[1:]
    if '--version' in args:
        print(VERSION)
        return 0
    if '--list' in args:
        try:
            for n in sorted(os.listdir(TRASH)):
                print(n)
        except FileNotFoundError:
            print('(trash is empty)')
        return 0
    if '--empty' in args:
        if not confirm('PERMANENTLY erase everything in trash?'):
            print('rmsafe: trash kept.')
            return 2
        shutil.rmtree(TRASH, ignore_errors=True)
        print('trash emptied.')
        return 0
    if '--restore' in args:
        i = args.index('--restore')
        return restore(args[i + 1])
    yes = '--yes' in args or '-y' in args
    paths = [a for a in args if not a.startswith('-')]
    if not paths:
        print('usage: rmsafe [--yes] <path>... | --list | --restore <name> | --empty')
        return 2
    return move_to_trash(paths, yes=yes)


if __name__ == '__main__':
    sys.exit(main())
