# Home Pi

Your own Linux distro for the Raspberry Pi 5. Not a layer on someone else's OS: Home Pi builds its own flashable image with [Buildroot](https://buildroot.org) - the Raspberry Pi kernel source, a minimal busybox userland, and a fullscreen terminal "Home" launcher as the login screen, with his Pi App Store apps on the menu. MIT, Greenisus1 / WinnieGaming.

## Flashing (Raspberry Pi Imager / "pi-flasher")

`./build.sh` produces `images/sdcard.img` via Buildroot's upstream raspberrypi5 post-image step. In Raspberry Pi Imager choose "Use custom" and pick that file (or compress it first: `xz -k images/sdcard.img` - Imager reads .img.xz too). Flash to a SPARE SD card only. The sandbox that wrote this tree is too small to run the build (2 cores, 1.9G RAM), so the exact image filename is confirmed on the build machine, not here.

## Self-update from the repo

`hpupdate` checks `system-version.json` in the Greenisus1/homepi repo against the installed version. When the repo is newer it downloads the manifest, verifies every file's sha256, backs up what it replaces to `/var/backups/homepi-update/`, and installs. It runs daily at 04:17 from busybox crond and from the launcher's "Update Home Pi..." entry (`hpupdate --auto`). It NEVER touches auth.json, vault.enc, fan.conf, watchdog.conf, or anything under /root. `make-release.py <version>` regenerates the repo-side metadata (system-version.json + manifest + payloads) from the overlay before each publish. Honest scope: this updates the Home Pi system scripts only - the kernel and rootfs base are NOT field-updatable; those need a reflash.

## Honest security note

The login gate plus vault is a friendly lock for a single-user appliance, not a real security boundary. A determined attacker who mounts the SD card gets the wrapped key and vault and can brute-force the password offline - the 200k-round PBKDF2 only slows that down; a Pi has no TPM to stop it. Recovery trusts your GitHub account completely: whoever can log in as the linked account can reset the password. The recovery gist is a GitHub SECRET gist, which is unlisted, not truly private - anyone who ever gets its URL can read the secret (useless without the SD card, but still). The GitHub token from the QR flow is used for the immediate calls and never stored. The device-flow QR requests the `gist` scope in addition to `read:user` - that scope is what lets it save and fetch the recovery gist. Full protection would need rootfs encryption, a much bigger build (out of scope).

Watchdog caveat: a watchdog that reboots on freeze is on by default in an image that has never been boot-tested. If something in early userspace wedges the pinger itself, the board reboot-loops every ~15s until you power off and set ENABLED=0 in `/etc/homepi/watchdog.conf` from another machine. First boot on the spare card should be watched for this.

## Honest status

- The distro **definition** (this repo: defconfig, overlay, launcher, build script) is original and ours.
- The kernel is the Raspberry Pi Foundation's fork of Linux (`raspberrypi/linux`), Linux is GPL - see the kernel's own license. Home Pi is a distro built from these parts, like a tiny Debian of our own.
- **Not yet boot-tested.** The image has not been flashed or booted on real hardware. First boot on the real Pi is the first real test, and it will be done carefully with the SD card, never by wiping his working card. A flashable image is only produced by running the build below; none is shipped in this repo.

## What's in the image

- `homepi` fullscreen launcher (curses, zero deps) as the login screen on console/tty1: his App Store apps as menu entries, plus App Store, Shell, Reboot and Power off (both behind a confirm). esc exits to a normal shell.
- Rebrand: hostname `homepi`, `/etc/os-release` NAME="Home Pi" (ID fields untouched), login banner and motd with Greenisus1 / WinnieGaming branding.
- First-boot wizard + login (launcher-level lock for a single-user box): asks a username (Enter = root), then a password that needs 8+ chars, one capital, one number, one special. You confirm you know it (or change it) before it's saved. Then Wi-Fi (writes wpa_supplicant.conf) or ethernet. Then it links your GitHub by QR device flow. Login attempts rate-limit with doubling lockouts.
- Password-derived encryption (the password IS the key): a random 256-bit master key encrypts a data vault (`/etc/homepi/vault.enc`, mode 600). The master key is wrapped under a key derived from your password (PBKDF2-HMAC-SHA256, 200k rounds), so the data is only readable after you log in. The login file stores only a verifier (HMAC of the derived key), never the key or the password. Construction: encrypt-then-MAC, HMAC-SHA256 keystream (counter mode) + HMAC tag, stdlib-only - no third-party crypto package in the image.
- Forgot password = GitHub override that KEEPS your data: at setup a random recovery secret is uploaded to your own GitHub as a secret gist, and the master key gets a second wrap under a key derived from that secret. Reset = scan the QR with the SAME GitHub account -> the app fetches the gist, unwraps the master key, you set a new password - old data survives. The gist alone is useless without the SD card (the wrap and vault live there); the card alone is useless without the password or the gist. The GitHub token is used for the call and never stored. Last resort (no network / gist gone): an explicit type-ERASE wipe-and-reset, with a warning that the old encrypted data dies.
- Fan control (`fanctl.py`, S11fanctl): uses whatever fan the board has. The Pi 5 active cooler is already driven by the kernel/firmware through the device tree - fanctl detects that and leaves it alone. A GPIO/PWM fan that shows up as hwmon `pwm1` in manual mode gets a temperature curve with hysteresis (off below 45C, full speed from 75C). No fan at all: clean no-op. Off switch: `/etc/homepi/fan.conf`. For a GPIO fan, add `dtoverlay=gpio-fan,gpiopin=4,temp=55000` to the boot config.txt (kept out of the image's firmware config on purpose - upstream config stays untouched).
- Reboot-before-freeze watchdog (`watchdogd.py`, S10watchdog, on by default): pings the Pi's built-in kernel watchdog (BCM2835_WDT=y) every 10s; if the system freezes and the pings stop, the hardware reboots the board (~15s). A clean stop writes the magic character so shutting the service down does NOT reboot. Off switch: `/etc/homepi/watchdog.conf`. Note: the watchdog daemon is the image-level safeguard; the Watchgoose app (with its reboot budget and thresholds) remains a separate App Store app.
- Pi App Store built in (`appstore`, from the Home launcher's App Store entry): catalogs the public Greenisus1 GitHub repos carrying the `app-version.json` Pi Store marker, shows installed state from `/root/apps`, installs by fetching the repo tarball and running its `app-store.sh` (the app's own dependency handling). Needs network; works offline only for already-installed apps in the launcher.
- Backup to GitHub (`hpbackup`, launcher entry "Backup to GitHub..."): opt-in backup of folders you pick (default /root/apps + /etc/homepi) to a PRIVATE `homepi-backup` repo on your GitHub. QR device-flow login each run (needs the `repo` scope to create/push the private repo; the token lives in memory only - never in .git/config or any file). Files over 95M are split into numbered parts with a reassemble.sh (GitHub rejects >100M blobs, so nothing is ever rejected for size). Add-only by design: it never deletes remote content and never force-pushes.
- Combined drives (`spanfs.py`): pool drives so a file bigger than any single drive's free space still fits - split into chunks spread across the pool (fill the emptiest drive first, 100M headroom each), with a manifest.json + reassemble.sh stored next to the chunks, and sha256-verified reassembly (`spanfs.py fetch`). Honest tradeoff: this is striping, not redundancy - if ANY drive holding a spanned file dies, that file is gone. Plain mergerfs-style pooling was rejected for the core feature because it keeps files whole, which can never fit a 22G file into 16G free; chunking can.
- Remote desktop (`hpremote`, launcher entry "Remote desktop..."): view and control the Pi's console from your Mac over the SSH the image already has - one-time PIN pairing, an on-screen indicator while anyone is attached, a kill switch, and an attach log. Nothing new listens on the network; no router or firewall changes. See "Remote desktop" below.
- Safe delete (`rmsafe`, alias rm in the interactive shell): the owner's rule after the /root incident - deleting asks for confirmation and MOVES things to /.trash (restorable with --restore, browsable with --list, --empty asks again and is the only erase). A piped/non-interactive rmsafe without --yes refuses instead of deleting. Honest limit: the alias covers the interactive root shell; scripts that call rm directly still hard-delete (they must - package installs depend on it).
- Custom boot screen: the WinnieGaming bear logo with "Made by Greenisus1" and "Home Pi is based on Linux" on the framebuffer while the system boots (`fbv`, `S01splash`, image at `/usr/share/homepi/splash.png`, composed in `make-splash.py`). The same credits show in the launcher.
- python3 + curses, dropbear (SSH from his Mac), DHCP on eth0.
- His published Pi Store apps fetched into `/root/apps` at build time by `fetch-apps.sh` (skips any repo that isn't public yet).

## Remote desktop

Home Pi's screen is a text console, so the remote desktop shares exactly that: the viewer sees what is on the Pi's screen, and the viewer's keystrokes land as if typed on the Pi's own keyboard. It runs over the SSH access the image already has - nothing new listens on the network, no router or firewall changes, and it works anywhere SSH already reaches the Pi (the LAN out of the box, plus any tunnel you already run).

- Turn it on from the launcher ("Remote desktop..." -> turn on) or `hpremote on`. The Pi shows a one-time 6-digit pairing PIN on its own screen, valid 10 minutes.
- Pair the Mac once: `ssh homepi hpremote pair` (or `mac/remote-homepi.sh pair`), type the PIN, and save the pairing token it shows. The PIN burns after one use; 5 wrong tries kill it. Pairing only ever happens against a PIN physically shown on the Pi.
- Watch or control: `hpremote attach TOKEN` (add `--watch` for view-only). Ctrl-Q or Ctrl-] detaches. `mac/remote-homepi.sh view` wraps setup, pairing and attaching in one friendly script.
- The Pi always shows when a viewer is attached: a wall notice on the console, `hpremote status`, and session markers under `/run/hpremote/`. Every attach, detach, refused attach and failed pairing is appended to `/var/log/hpremote.log`.
- Kill switch: `hpremote kill` disconnects every viewer immediately; `hpremote off` (or the launcher entry) turns the feature off entirely.
- Keystrokes are injected through the kernel's uinput virtual keyboard (enabled in the image by `board/homepi/kernel-uinput.fragment`). If a running kernel lacks uinput, hpremote falls back to TIOCSTI; if that is blocked too (it is off by default on Linux 6.2+), the attach runs view-only and says so.
- Honest limits: it mirrors the text console at about 4 redraws a second. No sound, clipboard, or file transfer, and the shared session is 1:1 with the Pi's physical screen - this is a console OS, there is no X11/Wayland desktop to share.

## Build

On a Debian/Linux machine with 8G+ RAM, ~15G free disk and a few hours:

```
./build.sh
```

This clones Buildroot, applies `buildroot-external/configs/homepi_pi5_defconfig` (layered on Buildroot's raspberrypi5 defconfig, external Bootlin toolchain so no from-scratch gcc build), fetches the apps, and builds `buildroot/output/images/sdcard.img`.

The Linux repo itself was requested: `./build.sh` with `HOMEPI_KERNEL_LOCAL=1` clones `raspberrypi/linux` (branch rpi-6.12.y, Pi 5 = bcm2712, aarch64) into `kernel/`, and the defconfig comments show the two-line switch to build from that local tree instead of the pinned tarball.

## Flash (only when the Pi is back and he says go)

```
sudo dd if=buildroot/output/images/sdcard.img of=/dev/sdX bs=4M status=progress conv=fsync
```

Get `/dev/sdX` right; it erases the whole card. Use a SPARE microSD, never his working card.

## Layout

- `homepi.py`, `homepilib.py` - launcher + library (unit + PTY tested on x86-64)
- `buildroot-external/` - the BR2_EXTERNAL tree: defconfig, post-build branding, rootfs overlay (inittab autologin, .profile hook, motd, config, `/usr/bin/homepi`)
- `build.sh`, `fetch-apps.sh`, `make-splash.py` - the build pipeline and splash composer
- `kernel/` - the raspberrypi/linux clone (build input, gitignored)

## License

MIT - Greenisus1 (for the Home Pi definition; each bundled part keeps its own license).

Built with AI assistance from my design.
