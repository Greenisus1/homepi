# Home Pi: land on the auth gate + Home launcher at login (esc exits to shell).
if [ -n "$PS1" ] && [ -z "$HOMEPI_LAUNCHER_OFF" ] && command -v homepi-login >/dev/null 2>&1; then
  homepi-login
fi
# Safety rule: interactive rm moves to trash after a confirm (scripts unaffected).
alias rm='rmsafe'
if [ -n "$PS1" ]; then
  . /usr/bin/homepi-predict-shell
fi
