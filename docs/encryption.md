# Experimental encrypted HomePi image

This optional image adds LUKS2 encryption of the persistent Linux system and user
files, a first-boot Homepi administrator password, password/account commands, and
Bash history trimming. It is separate from the normal image and existing updates.
**Do not migrate a working SD card until a spare-card boot and recovery test passes.**
No installed device is reformatted by building the repository or running hpupdate.

## What is encrypted

The SD card's second partition contains a LUKS2 encrypted ext4 root filesystem:
Linux configuration, account databases, programs, application/user files, logs,
and the HomePi vault. The first partition contains public Pi firmware, kernel,
and a factory initramfs; it must remain readable so the Pi can load the unlocker.
The initramfs includes the factory system, not personal files or an unlock secret.
The plaintext factory filesystem is therefore also available in the boot archive.
Changes and personal files on the running root filesystem are encrypted at rest.
No network service or rescue shell runs in the pre-unlock environment. This
version uses a local keyboard/display unlock, not remote SSH unlock.

This does not encrypt RAM, removable disks, network backups, or data written
explicitly to the boot partition. No swap is configured. Encryption protects a
powered-off card; it does not protect files from an administrator on an unlocked
machine or prevent an attacker replacing unsigned boot firmware to capture a
future password. Secure/measured boot and full-disk backup recovery are separate
work. Keep an offline backup; forgotten disk passwords cannot be reset through
the existing GitHub vault recovery. The legacy recovery path is blocked for
accounts coupled to Linux/disk authentication.

## Build and first boot

On a Linux build machine with the dependencies used in the image workflow:

```
git clone --depth 1 --branch 2025.08.1 https://github.com/buildroot/buildroot.git buildroot
./build-encrypted.sh
```

Output: `buildroot/output/images/homepi-encrypted.img`. This is a new SD-card
image, not an in-place encryption update. Flash only to a spare card with
Raspberry Pi Imager's custom-image option. The dedicated image has a 512 MiB boot
partition and a 2 GiB encrypted-root partition; it is intended for the Pi's SD
slot (`/dev/mmcblk0p2`), not USB boot or an arbitrary existing partition layout.

At the first local boot, confirm `ENCRYPT`, choose/repeat a password, and wait
while the factory filesystem is installed into the encrypted partition. That
password unlocks the disk, the actual Linux `homepi` account (SSH and sudo), and
the HomePi vault. Each subsequent boot asks for the disk password before Linux
starts. The normal Linux login follows. `homepi` has UID 1000 and administrator
rights through authenticated sudo, rather than sharing root's UID. Root login
and console autologin are disabled in this optional image.

Setup never replaces existing auth/vault files. A failed/interrupted provisioning
stays locked; if LUKS exists without an ext4 filesystem, `RETRY` is required to
format the opened encrypted filesystem. Existing recognized account data is
verified rather than overwritten. Hardware power-loss testing is still required.
Do not treat an old plaintext SD card or a backup as encrypted after migration.

## Account commands

Recommended (passwords are hidden):

```
sudo password
sudo user
```

Requested compatibility syntax is also accepted:

```
sudo password 'CURRENT_PASSWORD' 'NEW_PASSWORD'
sudo user 'CURRENT_PASSWORD' 'new_username'
```

Real passwords in arguments can appear in process listings, shell history and
sudo/audit logs. Hidden prompts avoid putting secrets in argv. Normal sudo policy
still applies, and the supplied current password must authenticate both Linux
and the existing vault. Password rules: at least eight characters including a
capital, number and special character. Do not run these commands as root directly;
the target is the real non-root sudo caller. They are not arbitrary user managers.

A password change keeps the existing data-encryption/master keys and ciphertext.
It creates and verifies a new LUKS slot, retires slots accepting the old password,
and updates Linux shadow and the vault's wrapped key/verifier. A root-only,
fsynced recovery journal contains hashes and encrypted wraps, never passwords or
unwrapped keys. An interrupted encrypted-root change requires the **new** password
to finish at next boot; if the new disk slot was never created the pending
transaction is discarded. A failed commit remains recoverable with that new key.
The regular unencrypted installation path can update Linux/vault credentials but
explicitly reports that it does not add root encryption. There is no migration
command for mismatched pre-existing Linux/vault passwords in this draft.

Renaming verifies the current password, changes the Linux and HomePi names and
supplementary group membership strings, and preserves numeric UID/GID, home path,
file ownership and encryption keys. It deliberately leaves the home directory
and primary group names unchanged. Reconnect using the new login name. Existing
sessions may still display the old name until logout. Username-specific sudo
policies and existing user crontabs block rename for manual migration. Other
services referencing usernames (including external SSH policies) need review.

## `clear` and history

The optional image uses Bash for Homepi. Running `clear` keeps the four most
recent history entries in that Bash session and writes the trimmed history file,
then clears the screen. Entries are counted as commands, so multiline commands
stay intact. `clear` itself counts if Bash recorded it. Ordinary later commands
accumulate normally until the next `clear`. Other options to clear are passed to
the screen-clearing program.

For an existing Bash installation, source `security/history.sh` in `.bashrc`.
It does not modify noninteractive scripts or BusyBox ash history. This is history
trimming, not secure erasure: other open shells can later save their older copies,
and filesystem remnants, backups, sudo/audit logs and terminal scrollback remain.
Close other sessions if you want this file to remain trimmed.

## Validation and release gate

Run `python3 -m unittest test_accounts test_authlib test_vaultlib -v`.
CI also tests real LUKS key rotation on a disposable regular file, native Linux
password hashing, and resolution of the pinned Buildroot configuration. The image
build is a separate manually dispatched workflow. Before publishing an update,
build and boot the image on a spare Pi SD card; test wrong passwords, SSH/sudo,
rename/reconnect, ciphertext preservation, cold boots, and power loss throughout
initial provisioning and password rotation. A unit-test pass does not establish
that the Pi firmware/initramfs/kernel path boots successfully.
