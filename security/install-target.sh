#!/bin/sh
set -eu
TARGET_DIR=$1
HOMEPI_REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
install -d -m 0755 "$TARGET_DIR/usr/lib/homepi"
for file in accounts.py disk.py earlyboot.py history.sh; do
    install -m 0644 "$HOMEPI_REPO/security/$file" "$TARGET_DIR/usr/lib/homepi/$file"
done
for file in authlib.py vaultlib.py; do
    install -m 0644 "$HOMEPI_REPO/$file" "$TARGET_DIR/usr/lib/homepi/$file"
done
for command in password user; do
    printf '#!/bin/sh\nexec /usr/bin/python3 -I /usr/lib/homepi/accounts.py %s "$@"\n' "$command" > "$TARGET_DIR/usr/bin/$command"
    chmod 0755 "$TARGET_DIR/usr/bin/$command"
done
install -m 0755 "$HOMEPI_REPO/security/init" "$TARGET_DIR/init"
# Administrators use normal sudo authentication, never a second UID 0 account.
install -d -m 0750 "$TARGET_DIR/etc/sudoers.d"
printf '%%sudo ALL=(ALL:ALL) ALL\n' > "$TARGET_DIR/etc/sudoers.d/90-homepi-admin"
chmod 0440 "$TARGET_DIR/etc/sudoers.d/90-homepi-admin"
# Include syntax is accepted by sudo even though it begins with '#'.
if ! grep -q 'includedir /etc/sudoers.d' "$TARGET_DIR/etc/sudoers"; then
    printf '\n@includedir /etc/sudoers.d\n' >> "$TARGET_DIR/etc/sudoers"
fi
chmod 0755 "$TARGET_DIR/usr/bin/homepi-login" "$TARGET_DIR/usr/bin/homepiauth.py" "$TARGET_DIR/usr/bin/homepi"

# Existing overlay scripts are text files in git; make appliance entry points executable.
for source in "$HOMEPI_REPO"/buildroot-external/board/homepi/rootfs-overlay/usr/bin/*; do
    [ -f "$source" ] || continue
    chmod 0755 "$TARGET_DIR/usr/bin/$(basename "$source")"
done
for source in "$HOMEPI_REPO"/buildroot-external/board/homepi/rootfs-overlay/etc/init.d/S*; do
    [ -f "$source" ] || continue
    chmod 0755 "$TARGET_DIR/etc/init.d/$(basename "$source")"
done
