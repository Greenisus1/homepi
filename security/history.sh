# Source from interactive Bash. Use the real clear program after trimming history.
case $- in *i*) ;; *) return ;; esac
if [ -n "${BASH_VERSION:-}" ]; then
    # Timestamps delimit complete entries when reloading multiline command history.
    HISTTIMEFORMAT=${HISTTIMEFORMAT:-'%F %T '}
    clear() {
        local homepi_saved_histsize=${HISTSIZE:-500}
        # Assigning HISTSIZE prunes complete Bash history entries, including multiline ones.
        HISTSIZE=4
        if [ -n "${HISTFILE:-}" ]; then
            builtin history -w "$HISTFILE" || {
                HISTSIZE=$homepi_saved_histsize
                printf '%s\n' 'clear: could not save trimmed history' >&2
                return 1
            }
        fi
        HISTSIZE=$homepi_saved_histsize
        command clear "$@"
    }
fi
