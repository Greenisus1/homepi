#!/bin/bash
# Fetch published Pi Store apps into the image's /root/apps overlay.
# Missing/private repos are skipped with a note - the image still builds.
set -u
cd -- "$(dirname -- "$0")"
DEST=buildroot-external/board/homepi/rootfs-overlay/root/apps
mkdir -p "$DEST"
APPS="cardcoot furrowfinch stormpetrel wrenville swiftrail blockcraft fetchwing watchgoose bowerbird"
for app in $APPS; do
  if [ -d "$DEST/$app" ]; then echo "have $app"; continue; fi
  url="https://github.com/Greenisus1/$app/archive/refs/heads/main.tar.gz"
  if curl -fsL "$url" -o "/tmp/homepi-$app.tgz" 2>/dev/null; then
    mkdir -p "$DEST/$app"
    tar -xzf "/tmp/homepi-$app.tgz" -C "$DEST/$app" --strip-components=1
    echo "fetched $app"
  else
    echo "skip $app (not public at $url)"
  fi
done
