#!/bin/bash
# Opt-in new SD-card image. Does not write any physical disk or update a running Pi.
set -euo pipefail
cd -- "$(dirname -- "$0")"
HOMEPI_REPO=$PWD
HOMEPI_BR=${HOMEPI_BUILDROOT:-$HOMEPI_REPO/buildroot}
[ -f "$HOMEPI_BR/Makefile" ] || { echo 'First download Buildroot 2025.08.1 to buildroot/ (see docs/encryption.md).'; exit 1; }
[ "${1:-}" = --configure-only ] || ./fetch-apps.sh
make -C "$HOMEPI_BR" BR2_EXTERNAL="$HOMEPI_REPO/buildroot-external" homepi_pi5_defconfig
python3 - "$HOMEPI_BR/.config" "$HOMEPI_REPO" <<'PY'
import sys
from pathlib import Path
p, root = Path(sys.argv[1]), sys.argv[2]
settings = {
 'BR2_ROOTFS_OVERLAY': '"'+root+'/buildroot-external/board/homepi/rootfs-overlay '+root+'/security/rootfs-overlay"',
 'BR2_ROOTFS_USERS_TABLES': '"'+root+'/security/users.txt"',
 'BR2_ROOTFS_POST_BUILD_SCRIPT': '"board/raspberrypi5/post-build.sh '+root+'/buildroot-external/board/homepi/post-build.sh '+root+'/security/install-target.sh"',
 'BR2_ROOTFS_POST_IMAGE_SCRIPT': '"'+root+'/security/post-image.sh"',
 'BR2_LINUX_KERNEL_CONFIG_FRAGMENT_FILES': '"board/raspberrypi/linux-4k-page-size.fragment '+root+'/buildroot-external/board/homepi/kernel-uinput.fragment '+root+'/security/kernel.fragment"',
 'BR2_PACKAGE_CRYPTSETUP': 'y', 'BR2_PACKAGE_LIBXCRYPT': 'y',
 'BR2_PACKAGE_BASH': 'y',
 'BR2_PACKAGE_E2FSPROGS': 'y', 'BR2_PACKAGE_PYTHON3_CURSES': 'y',
 'BR2_PACKAGE_UTIL_LINUX_BINARIES': 'y',
 'BR2_TARGET_ROOTFS_CPIO': 'y', 'BR2_TARGET_ROOTFS_CPIO_GZIP': 'y',
 'BR2_TARGET_ENABLE_ROOT_LOGIN': 'n',
}
lines = [l for l in p.read_text().splitlines() if not any(l.startswith(k+'=') or l == '# '+k+' is not set' for k in settings)]
lines += [k+'='+v if v != 'n' else '# '+k+' is not set' for k,v in settings.items()]
p.write_text('\n'.join(lines)+'\n')
PY
make -C "$HOMEPI_BR" olddefconfig
[ "${1:-}" != --configure-only ] || exit 0
make -C "$HOMEPI_BR" -j"${HOMEPI_JOBS:-2}"
echo "Encrypted first-boot image: $HOMEPI_BR/output/images/homepi-encrypted.img"
echo 'Use a SPARE SD card. It contains no password until first boot.'
