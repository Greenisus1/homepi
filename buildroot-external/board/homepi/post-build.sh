#!/bin/bash
# Home Pi post-build: brand os-release without touching apt/dpkg fields.
set -eu
TARGET_DIR="$1"
OSR="$TARGET_DIR/etc/os-release"
if [ -f "$OSR" ]; then
  sed -i 's/^NAME=.*/NAME="Home Pi"/; s/^PRETTY_NAME=.*/PRETTY_NAME="Home Pi (Buildroot Linux)"/' "$OSR"
  grep -q '^NAME=' "$OSR" || sed -i '1i NAME="Home Pi"' "$OSR"
fi
echo 'Home Pi post-build branding done.'
# Repository overlay files may arrive without executable bits.
chmod 0755 "$TARGET_DIR/usr/bin/predict"
