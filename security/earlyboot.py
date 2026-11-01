#!/usr/bin/python3 -I
"""Local-console provision/unlock for the OPTIONAL encrypted SD-card image."""
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import warnings
sys.path.insert(0, '/usr/lib/homepi')
import accounts
import disk

DEVICE = '/dev/mmcblk0p2'
BOOT = '/dev/mmcblk0p1'
ROOT = '/newroot'


def command(*args):
    subprocess.run(args, check=True)


def main():
    warnings.simplefilter('error', getpass.GetPassWarning)
    if not sys.stdin.isatty():
        raise ValueError('a local console is required for disk unlock')
    for _ in range(30):
        if Path(DEVICE).exists() and Path(BOOT).exists():
            break
        time.sleep(1)
    else:
        raise ValueError('HomePi SD-card partitions are missing')
    Path('/boot').mkdir(exist_ok=True)
    command('/bin/mount', '-t', 'vfat', '-o', 'ro', BOOT, '/boot')
    # Marker only exists in the deliberately blank encrypted image layout.
    marker = Path('/boot/homepi-provision-v1')
    encrypted = disk.run(['isLuks', DEVICE], check=False).returncode == 0
    if not encrypted:
        if not marker.exists():
            raise ValueError('not a provisionable HomePi image; refusing to format')
        print('First boot: encrypt the HomePi system and user files. Boot firmware remains readable.')
        print('This ERASES partition 2 of this SD card: ' + DEVICE)
        if input('Type ENCRYPT to provision this new image: ') != 'ENCRYPT':
            raise ValueError('cancelled; no partition changed')
        password = getpass.getpass('Choose the Homepi administrator / disk password: ')
        if password != getpass.getpass('Repeat password: '):
            raise ValueError('passwords do not match')
        problems = accounts.authlib.check_password_rules(password)
        if problems:
            raise ValueError(', '.join(problems))
        disk.run(['luksFormat', '--type', 'luks2', '--batch-mode', DEVICE], password)
    else:
        password = getpass.getpass('HomePi disk password: ')
    disk.run(['open', DEVICE, 'homepi-root'], password)
    # Never format a partially provisioned or existing LUKS device automatically.
    result = subprocess.run(['/sbin/blkid', '-s', 'TYPE', '-o', 'value', '/dev/mapper/homepi-root'],
                            capture_output=True, text=True)
    if result.stdout.strip() != 'ext4':
        if encrypted:
            print('Interrupted initial provisioning detected. This will erase only the opened encrypted filesystem.')
            if not marker.exists() or input('Type RETRY to copy the factory system again: ') != 'RETRY':
                raise ValueError('recovery cancelled')
        command('/sbin/mkfs.ext4', '-F', '/dev/mapper/homepi-root')
    Path(ROOT).mkdir(exist_ok=True)
    command('/bin/mount', '/dev/mapper/homepi-root', ROOT)
    ready = Path(ROOT + '/etc/homepi/provisioned')
    if not ready.exists():
        with accounts.Accounts(ROOT) as account:
            disk.recover(account, password)
            if (Path(ROOT) / 'etc/homepi/auth.json').exists():
                account.verify('homepi', password)
                accounts.atomic(ready, '1\n', 0o600)
                command('/bin/sync')
                command('/bin/umount', '/boot')
                return 0
        # The factory root is already in RAM. Never copy virtual filesystems.
        for item in Path('/').iterdir():
            if item.name in ('proc', 'sys', 'dev', 'run', 'tmp', 'boot', 'newroot', 'init'):
                continue
            target = Path(ROOT) / item.name
            if item.is_symlink():
                if target.is_symlink():
                    target.unlink()
                target.symlink_to(os.readlink(item))
            elif item.is_dir():
                command('/bin/cp', '-a', str(item), ROOT + '/')
            else:
                shutil.copy2(item, target)
        for name in ('proc', 'sys', 'dev', 'run', 'tmp', 'boot'):
            (Path(ROOT) / name).mkdir(exist_ok=True)
        os.chmod(ROOT + '/tmp', 0o1777)
        with accounts.Accounts(ROOT) as account:
            accounts.atomic(Path(ROOT) / 'etc/homepi/disk.json',
                            json.dumps(dict(device=DEVICE, mapper='homepi-root', version=1)), 0o600)
            account.setup('homepi', password)
        accounts.atomic(ready, '1\n', 0o600)
        command('/bin/sync')
    with accounts.Accounts(ROOT) as account:
        disk.recover(account, password)
    # New root is mounted; the shell PID 1 performs switch_root after Python exits.
    command('/bin/umount', '/boot')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('HomePi remains locked: ' + str(exc), file=sys.stderr)
        sys.exit(1)
