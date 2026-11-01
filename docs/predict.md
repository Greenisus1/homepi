# HomePi Predict

New images enable command suggestions in the root login shell (BusyBox ash).
Additional users can source `/usr/bin/homepi-predict-shell` from their interactive
profile. Bash also supports this hook. Scripts and successful commands are unaffected.

```
ehco hello
# did you mean echo hello
predict use
# hello
sudo predict use
predict wrong echo
predict reload
predict reset
```

`use` runs the last suggestion once. First generate a new suggestion before each
`use`. Nothing is ever executed automatically. `wrong COMMAND [ARG ...]` learns a
replacement for the last missing executable name, persists it across logins, and
sets that exact command as the current suggestion. On subsequent failures,
original arguments are appended to the learned replacement prefix. Quote arguments
normally, e.g. `predict wrong echo 'hello world'`. A quoted whole command such as
`predict wrong 'echo hello'` is rejected. Learning corrects executable names only;
it does not infer invalid options, subcommands, pipelines, aliases, or builtins.

`reload` starts a fresh process, verifies persisted state and clears pending work
while retaining learned corrections. There is no background daemon to crash or
restart: every request starts Python anew. If state is corrupt, `reset` recovers it.
`reset` atomically replaces only `~/.homepi-predict/state.json` with defaults;
other HomePi settings, files, authentication and backups are untouched.

The interactive `sudo` function recognizes exactly `sudo predict use`. Predict
reads and consumes state as the original user and invokes the real sudo with an
absolute executable and separate arguments. Normal sudoers policy/password checks
apply. No sudoers grants are installed; admin access requires an administrator's
existing policy. Root is already admin. Direct `command sudo predict use`, sudo
options before predict, and noninteractive sudo invocation are deliberately refused.
Other sudo commands pass through normally.

Execution never uses a shell, eval, or a command string. Metacharacters in arguments
are literal; redirection, variable expansion and globbing are not replayed. The
shell has already expanded arguments before the missing-command hook runs. Only
executables in `/usr/sbin:/usr/bin:/sbin:/bin` are suggested and resolved. Custom
PATH entries, slash-containing commands and shell builtins are unsupported. Python
runs in isolated mode. Per-user state uses a private 0700 directory, no-follow
opens, locking and atomic replacement; HOME and sudo environment values cannot
redirect state to another user's files. Suggestions may contain sensitive command
arguments and persist until consumed, reloaded, reset or replaced.

Buildroot enables `CONFIG_ASH_BASH_NOT_FOUND_HOOK` through a BusyBox fragment and
includes sudo. The post-build step ensures predict is executable. Existing update
manifests are intentionally unchanged: installing the executable alone does not
install shell integration or change an already built BusyBox. Rebuild the image,
or have an administrator install the files and enable the corresponding ash option.

Run `python3 -m unittest test_predict -v`. CI also verifies real BusyBox ash hook
argument preservation. Before release, boot a Pi image, try `ehco hello`, `predict
use`, learning across logins, reload/reset, and admin acceptance/denial with a
non-root account. A full image build and hardware boot are separate from unit tests.
