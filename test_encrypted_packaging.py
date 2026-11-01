"""Validate genimage layout with harmless dummy firmware, not a physical disk."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('genimage') and shutil.which('mkdosfs') and shutil.which('mdir'),
                     'Linux image-packaging tools required')
class PackagingTests(unittest.TestCase):
    def test_boot_files_and_blank_encrypted_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / 'images'
            firmware = images / 'rpi-firmware'
            firmware.mkdir(parents=True)
            (firmware / 'config.txt').write_text('kernel=Image\nauto_initramfs=1\n')
            (firmware / 'cmdline.txt').write_text('root=/dev/mmcblk0p2\n')
            (firmware / 'overlays').mkdir()
            (firmware / 'overlays/test.dtbo').write_bytes(b'overlay')
            (images / 'Image').write_bytes(b'kernel')
            (images / 'test.dtb').write_bytes(b'dtb')
            (images / 'rootfs.cpio.gz').write_bytes(b'factory')
            host = root / 'host/bin'
            host.mkdir(parents=True)
            (host / 'genimage').symlink_to(shutil.which('genimage'))
            build = root / 'build'
            build.mkdir()
            env = dict(os.environ, BINARIES_DIR=str(images), BUILD_DIR=str(build), HOST_DIR=str(root / 'host'))
            subprocess.run(['sh', 'security/post-image.sh'], env=env, check=True, capture_output=True)
            self.assertGreater((images / 'homepi-encrypted.img').stat().st_size, 2 * 1024**3)
            listing = subprocess.check_output(['mdir', '-i', str(images / 'homepi-encrypted-boot.vfat'), '::'], text=True)
            self.assertIn('Image', listing)
            self.assertIn('overlays', listing)
            config = (images / 'homepi-encrypted-boot/config.txt').read_text()
            self.assertIn('initramfs homepi-initramfs.cpio.gz followkernel', config)
            self.assertNotIn('auto_initramfs=', config)
            self.assertNotIn('root=', (images / 'homepi-encrypted-boot/cmdline.txt').read_text())


if __name__ == '__main__':
    unittest.main()
