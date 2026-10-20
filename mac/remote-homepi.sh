#!/bin/bash
# remote-homepi.sh - view and control your Home Pi's screen from this Mac.
# Part of Home Pi (Greenisus1/homepi, MIT). Uses the SSH access you already
# have to the Pi - nothing new listens on the network, no router changes.
#
#   ./remote-homepi.sh setup    first time: Pi address + SSH check
#   ./remote-homepi.sh pair     pair this Mac (needs the PIN shown by
#                               "hpremote on" / the Pi's Remote desktop menu)
#   ./remote-homepi.sh view     watch + control the Pi's screen (Ctrl-Q detaches)
#   ./remote-homepi.sh watch    view only
#   ./remote-homepi.sh status   is it on? is anyone attached?
#   ./remote-homepi.sh off      turn remote desktop off on the Pi
set -eu
CFG_DIR="$HOME/.homepi-remote"
CFG="$CFG_DIR/config"
mkdir -p "$CFG_DIR"; chmod 700 "$CFG_DIR"
[ -f "$CFG" ] && . "$CFG"
HOST="${HOST:-}"
TOKEN="${TOKEN:-}"

need_host() {
  [ -n "$HOST" ] || { echo "Run: $0 setup"; exit 1; }
}
need_token() {
  [ -n "$TOKEN" ] || { echo "Run: $0 pair"; exit 1; }
}

cmd="${1:-view}"
case "$cmd" in
  setup)
    printf 'Pi address (e.g. homepi.local or its IP): '
    read -r HOST
    echo "Checking SSH to $HOST ..."
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$HOST" true 2>/dev/null; then
      echo "SSH key login works."
    else
      echo "Key login not set up yet. Copy your key to the Pi, e.g.:"
      echo "  ssh-copy-id $HOST      (or: cat ~/.ssh/id_ed25519.pub | ssh $HOST 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys')"
      echo "Then re-run: $0 setup"
      exit 1
    fi
    printf 'HOST="%s"\nTOKEN="%s"\n' "$HOST" "$TOKEN" > "$CFG"; chmod 600 "$CFG"
    echo "Saved to $CFG. Next: turn remote desktop on at the Pi (Home menu -> Remote desktop...), then run: $0 pair"
    ;;
  pair)
    need_host
    echo "The Pi must have remote desktop ON (Home menu -> Remote desktop... or 'hpremote on')."
    ssh -t "$HOST" hpremote pair || exit 1
    printf 'Paste the TOKEN= value it just showed: '
    read -r TOKEN
    TOKEN="${TOKEN#TOKEN=}"
    [ -n "$TOKEN" ] || { echo "empty token"; exit 1; }
    printf 'HOST="%s"\nTOKEN="%s"\n' "$HOST" "$TOKEN" > "$CFG"; chmod 600 "$CFG"
    echo "Paired. Run: $0 view"
    ;;
  view)
    need_host; need_token
    ssh -t "$HOST" hpremote attach "$TOKEN"
    ;;
  watch)
    need_host; need_token
    ssh -t "$HOST" hpremote attach "$TOKEN" --watch
    ;;
  status|off|kill)
    need_host
    ssh "$HOST" hpremote "$cmd"
    ;;
  *)
    sed -n '2,12p' "$0"
    ;;
esac
