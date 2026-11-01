if [ -n "${PS1:-}" ]; then
    . /usr/lib/homepi/history.sh
    . /usr/bin/homepi-predict-shell
    sudo /usr/bin/homepi-login
fi
