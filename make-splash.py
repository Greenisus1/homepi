#!/usr/bin/env python3
'''Compose the Home Pi boot splash (WinnieGaming logo + credits).
Usage: python3 make-splash.py logo.png [out.png]  (needs PIL on the build host)'''
import os, sys
from PIL import Image, ImageDraw, ImageFont

def compose(logo_path, out_path, W=1920, H=1080,
            font_bold='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            font_reg='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
    logo = Image.open(logo_path).convert('RGB')
    img = Image.new('RGB', (W, H), (11, 14, 20))
    d = ImageDraw.Draw(img)
    side = 640
    logo = logo.resize((side, side), Image.LANCZOS)
    mask = Image.new('L', (side, side), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, side, side), radius=48, fill=255)
    x, y = (W - side) // 2, 130
    img.paste(logo, (x, y), mask)
    big = ImageFont.truetype(font_bold, 54)
    small = ImageFont.truetype(font_reg, 40)
    t1, t2 = 'Made by Greenisus1', 'Home Pi is based on Linux'
    d.text(((W - d.textlength(t1, font=big)) / 2, y + side + 70), t1, font=big,
           fill=(235, 235, 235))
    d.text(((W - d.textlength(t2, font=small)) / 2, y + side + 150), t2,
           font=small, fill=(150, 160, 175))
    img.save(out_path, optimize=True)
    return out_path

if __name__ == '__main__':
    out = sys.argv[2] if len(sys.argv) > 2 else \
        'buildroot-external/board/homepi/rootfs-overlay/usr/share/homepi/splash.png'
    print(compose(sys.argv[1], out))
