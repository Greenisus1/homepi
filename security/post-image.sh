#!/bin/sh
set -eu
HOMEPI_REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# Firmware files are staged separately so the regular image is not overwritten.
HOMEPI_STAGE="$BINARIES_DIR/homepi-encrypted-boot"
rm -rf "$HOMEPI_STAGE"
mkdir -p "$HOMEPI_STAGE"
cp -a "$BINARIES_DIR/rpi-firmware/." "$HOMEPI_STAGE/"
cp "$BINARIES_DIR/Image" "$HOMEPI_STAGE/Image"
cp "$BINARIES_DIR"/*.dtb "$HOMEPI_STAGE/"
cp "$BINARIES_DIR/rootfs.cpio.gz" "$HOMEPI_STAGE/homepi-initramfs.cpio.gz"
# Explicit initramfs; disable firmware's auto-selection and remove plaintext root=.
sed -i '/^auto_initramfs=/d; /^initramfs /d' "$HOMEPI_STAGE/config.txt"
printf '\ninitramfs homepi-initramfs.cpio.gz followkernel\n' >> "$HOMEPI_STAGE/config.txt"
printf 'console=serial0,115200 console=tty1 rdinit=/init\n' > "$HOMEPI_STAGE/cmdline.txt"
printf 'HomePi encrypted image version 1\n' > "$HOMEPI_STAGE/homepi-provision-v1"
# genimage only creates files under the Buildroot output directory.
HOMEPI_TMP="$BUILD_DIR/genimage-homepi-encrypted.tmp"
rm -rf "$HOMEPI_TMP"
python3 - "$HOMEPI_REPO/security/genimage.cfg" "$HOMEPI_STAGE" "$BINARIES_DIR/homepi-genimage.cfg" <<'PYTHON'
import json, pathlib, sys
source, stage, output = map(pathlib.Path, sys.argv[1:])
files = ', '.join(json.dumps('homepi-encrypted-boot/' + p.name) for p in sorted(stage.iterdir()))
output.write_text(source.read_text().replace('#BOOT_FILES#', files))
PYTHON
HOMEPI_EMPTY=$(mktemp -d)
trap 'rmdir "$HOMEPI_EMPTY"' EXIT
"$HOST_DIR/bin/genimage" --rootpath "$HOMEPI_EMPTY" --tmppath "$HOMEPI_TMP" \
    --inputpath "$BINARIES_DIR" --outputpath "$BINARIES_DIR" \
    --config "$BINARIES_DIR/homepi-genimage.cfg"
