case $- in *i*) ;; *) return ;; esac
HISTSIZE=1000
HISTFILESIZE=2000
shopt -s histappend
. /usr/lib/homepi/history.sh
. /usr/bin/homepi-predict-shell
