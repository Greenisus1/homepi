#!/bin/sh
# Home Pi 1.1.1 flasher - writes the official image to a second SD card or USB drive.
# Never touches the drive the Pi booted from.
# Run as root:  sh homepi-flash.sh
set -e

URL=https://x0.at/8icB.xz
XZSHA=8fac81df5d848b27234e76482c903ec68428f3e4b87f46bcb4fcd1c4251e7e20
IMGSHA=417da524d5e9e12df79f3359d9290c65f72dca1a6b123d81e041711eda6a31cd

if [ "$(id -u)" != "0" ]; then
  echo "Please run as root (log in as root first)."
  exit 1
fi

ROOTSRC=$(findmnt -n -o SOURCE /)
BOOT=$(lsblk -no PKNAME "$ROOTSRC" 2>/dev/null | head -n 1)
if [ -z "$BOOT" ]; then
  BOOT=$(basename "$ROOTSRC" | sed -e 's/p[0-9]*$//' -e 's/[0-9]*$//')
fi
if [ -z "$BOOT" ]; then
  echo "Could not identify the boot drive. Stopping for safety."
  exit 1
fi
echo "Boot drive: /dev/$BOOT (protected, will not be listed)"

lsblk -dn -o NAME,SIZE,TYPE > /tmp/hp-list.txt
NAMES=""
SIZES=""
while read name size type; do
  [ "$type" = "disk" ] || continue
  [ "$name" = "$BOOT" ] && continue
  NAMES="$NAMES $name"
  SIZES="$SIZES $size"
done < /tmp/hp-list.txt
rm -f /tmp/hp-list.txt

if [ -z "$NAMES" ]; then
  echo "No spare drive found. Plug in the second card or USB drive, then run again."
  exit 1
fi

echo ""
echo "Spare drives (all data on the one you pick will be erased):"
n=0
for name in $NAMES; do
  n=$((n+1))
  size=$(echo "$SIZES" | cut -d' ' -f$((n+1)))
  echo "  $n = /dev/$name size $size"
done
printf "Type the number of the drive to use: "
read num
case "$num" in
  ''|*[!0-9]*) echo "Not a number. Stopping."; exit 1;;
esac
[ "$num" -ge 1 ] && [ "$num" -le "$n" ] || { echo "Out of range. Stopping."; exit 1; }
TARGET=$(echo "$NAMES" | cut -d' ' -f$((num+1)))
TSIZE=$(echo "$SIZES" | cut -d' ' -f$((num+1)))

echo ""
echo "Target: /dev/$TARGET size $TSIZE"
echo "EVERYTHING on /dev/$TARGET will be ERASED and replaced with Home Pi 1.1.1."
printf "Type y to go ahead: "
read ans
[ "$ans" = "y" ] || { echo "Stopped. Nothing was written."; exit 1; }

mkdir -p /root/homepi-flash
cd /root/homepi-flash
FREE=$(df -Pm . | awk 'NR==2 {print $4}')
if [ "${FREE:-0}" -lt 400 ]; then
  echo "Only $FREE MB free on this card. Need 400 MB. Stopping."
  exit 1
fi
umount /dev/${TARGET}* 2>/dev/null || true

echo ""
echo "Downloading the image (about 616 MB, takes a while)..."
if ! wget -O homepi.img.xz "$URL"; then
  echo "Download failed. Check the Pi's internet connection and try again."
  exit 1
fi
GOT=$(wc -c < homepi.img.xz | tr -d ' ')
if [ "$GOT" -lt 1000000 ]; then
  echo "Download came back tiny ($GOT bytes) - that is an error page, not the image."
  echo "First line of what the server said:"
  head -c 300 homepi.img.xz
  echo ""
  echo "Check the Pi's internet, wait a minute, and run this again."
  rm -f homepi.img.xz
  exit 1
fi
if [ "$(head -c 6 homepi.img.xz | od -An -tx1 | tr -d ' \n')" != "fd377a585a00" ]; then
  echo "Download is not an xz image (got $GOT bytes of something else)."
  head -c 300 homepi.img.xz
  echo ""
  exit 1
fi
echo "Checking the download hash..."
echo "$XZSHA  homepi.img.xz" | sha256sum -c -
echo "Decompressing..."
xz -d homepi.img.xz
echo "Checking the image hash..."
echo "$IMGSHA  homepi.img" | sha256sum -c -

echo "Writing to /dev/$TARGET (takes a few minutes)..."
dd if=homepi.img of=/dev/$TARGET bs=4M conv=fsync status=progress
sync

rm -f homepi.img
echo ""
echo "DONE. Home Pi 1.1.1 is on /dev/$TARGET."
echo "Power off, swap the card in, and boot."
