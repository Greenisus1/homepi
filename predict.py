#!/usr/bin/python3 -I
"""Opt-in argv-only command correction for HomePi; no shell evaluation."""
import difflib
import fcntl
import json
import os
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import sys

SAFE_PATH = '/usr/sbin:/usr/bin:/sbin:/bin'
NAME = re.compile(r'^[a-zA-Z0-9_][a-zA-Z0-9_.+-]{0,63}$')


def valid(argv):
    return (isinstance(argv, list) and 0 < len(argv) <= 128
            and all(isinstance(a, str) and len(a) <= 4096
                    and not any(ord(c) < 32 or ord(c) == 127 for c in a) for a in argv)
            and bool(NAME.fullmatch(argv[0])) and argv[0] != 'predict')


def candidates():
    # Fixed system directories avoid suggesting executables from writable PATH entries.
    return sorted({n for d in SAFE_PATH.split(':') if os.path.isdir(d)
                   for n in os.listdir(d) if NAME.fullmatch(n)
                   and os.access(os.path.join(d, n), os.X_OK)
                   and os.path.isfile(os.path.join(d, n)) and n != 'predict'})


class State:
    def __enter__(self):
        home = pwd.getpwuid(os.getuid()).pw_dir
        path = os.path.join(home, '.homepi-predict')
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            pass
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        st = os.fstat(self.fd)
        if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
            os.close(self.fd)
            raise ValueError('prediction directory must be owned by you with mode 0700')
        self.lock = os.open('lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        return self

    def load(self):
        try:
            fd = os.open('state.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        except FileNotFoundError:
            return {}
        with os.fdopen(fd) as f:
            data = json.loads(f.read(1024 * 1024))
        if not isinstance(data, dict):
            raise ValueError('invalid prediction state; run predict reset')
        return data

    def save(self, data):
        # Exclusive temporary file, followed by atomic replacement under the lock.
        name = 'tmp-' + os.urandom(16).hex()
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            os.rename(name, 'state.json', src_dir_fd=self.fd, dst_dir_fd=self.fd)
        finally:
            try:
                os.unlink(name, dir_fd=self.fd)
            except FileNotFoundError:
                pass

    def __exit__(self, *exc):
        os.close(self.lock)
        os.close(self.fd)


def main(args=None):
    args = sys.argv[1:] if args is None else args
    # Never let a privileged interpreter consume another user's state or imports.
    if os.getuid() != os.geteuid() or 'SUDO_UID' in os.environ:
        raise ValueError('use sudo predict use from the HomePi interactive shell; direct sudo invocation refused')
    if not args:
        print('predict use | wrong COMMAND [ARG ...] | reload | reset')
        return 0
    action, rest = args[0], args[1:]
    execute = None
    with State() as store:
        if action == 'reset' and not rest:
            store.save({})
            print('Prediction settings reset.')
            return 0
        data = store.load()
        if action == 'suggest' and not valid(rest):
            data.pop('suggestion', None)
            data.pop('failed', None)
            store.save(data)
            return 127
        if action == 'suggest' and valid(rest):
            data.pop('suggestion', None)
            data['failed'] = rest
            learned = data.get('corrections', {}).get(rest[0])
            if learned and valid(learned):
                suggestion = learned + rest[1:]
            else:
                matches = difflib.get_close_matches(rest[0], candidates(), n=1, cutoff=0.75)
                suggestion = [matches[0]] + rest[1:] if matches else None
            if suggestion and valid(suggestion):
                data['suggestion'] = suggestion
                print('did you mean ' + shlex.join(suggestion))
            store.save(data)
            return 127
        if action == 'wrong' and valid(rest):
            failed = data.get('failed')
            if not valid(failed):
                raise ValueError('no failed command to correct')
            # Store replacement command prefix, preserving arguments on future failures.
            corrections = data.setdefault('corrections', {})
            if len(corrections) >= 1000 and failed[0] not in corrections:
                raise ValueError('correction limit reached; reset to clear')
            corrections[failed[0]] = rest
            data['suggestion'] = rest
            store.save(data)
            print('Correction saved.')
            return 0
        if action == 'reload' and not rest:
            data.pop('suggestion', None)
            data.pop('failed', None)
            store.save(data)
            print('Predict reloaded (fresh process on every command).')
            return 0
        if action in ('use', '--sudo-use') and not rest:
            execute = data.pop('suggestion', None)
            if not valid(execute):
                raise ValueError('no valid suggestion; mistype a command first')
            store.save(data)  # Consume once, before executing and after releasing lock.
        else:
            raise ValueError('invalid command; run predict for usage')
    program = shutil.which(execute[0], path=SAFE_PATH)
    if not program:
        raise ValueError('suggested executable no longer exists')
    argv = [program] + execute[1:]
    if action == '--sudo-use' and os.getuid() != 0:
        sudo = shutil.which('sudo', path=SAFE_PATH)
        if not sudo:
            raise ValueError('sudo is not installed; ask your administrator')
        argv = [sudo, '--'] + argv
    return subprocess.run(argv, shell=False).returncode


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, AttributeError) as e:
        print('predict: ' + str(e), file=sys.stderr)
        sys.exit(1)
