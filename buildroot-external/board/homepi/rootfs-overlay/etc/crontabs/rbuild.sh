#!/bin/bash
# Home Pi image builder. Run on a Debian/Linux machine with 8G+ RAM, ~15G free
# disk, and a few hours. Produces a flashable Raspberry Pi 5 image.
# Usage: ./build.sh            (uses the pinned kernel tarball - reproducible)
#        HOMEPI_KERNEL_LOCAL=1 ./build.sh   (use the local raspberrypi/linux clone)
set -eu
cd -- "$(dirname -- "$0")"
BUILDROOT_REF="${BUILDROOT_REF:-master}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing build dependency: $1"; exit 1; }; }
for tool in git make gcc g++ unzip rsync bc bison flex python3; do need "$tool"; done

if [ ! -d buildroot ]; then
  git clone --depth 1 --branch "$BUILDROOT_REF" https://github.com/buildroot/buildroot buildroot
fi

# Optional: use the local kernel clone instead of the pinned tarball.
if [ "${HOMEPI_KERNEL_LOCAL:-0}" = "1" ]; then
  [ -d kernel ] || git clone --depth 1 --branch rpi-6.12.y --single-branch \
    https://github.com/raspberrypi/linux kernel
  echo "Using local kernel tree at $(pwd)/kernel (edit configs/homepi_pi5_defconfig to switch)."
fi

./fetch-apps.sh

make -C buildroot BR2_EXTERNAL="$(pwd)/buildroot-external" homepi_pi5_defconfig
make -C buildroot BR2_EXTERNAL="$(pwd)/buildroot-external" -j"$(nproc)"

echo
echo "Done. Flashable image: buildroot/output/images/sdcard.img"
echo "Flash with:  sudo dd if=buildroot/output/images/sdcard.img of=/dev/sdX bs=4M status=progress conv=fsync"
echo "Get /dev/sdX right - it erases that whole card."
