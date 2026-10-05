#!/usr/bin/env python3
"""Placeholder pedal-face background (650 x 400) until the real artwork lands.
Writes bundle/nhe-can-abyss.lv2/modgui/background.jpg."""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 650, 400
y, x = np.mgrid[0:H, 0:W]
# deep oxblood can, darker towards the edges, a faint oil-swirl sheen
r = np.hypot((x - 330) / 420, (y - 170) / 300)
swirl = 0.06 * np.sin(9 * np.arctan2(y - 170, x - 330) + 14 * r)
v = np.clip(1.0 - 0.75 * r + swirl, 0, 1)[..., None]
col = np.array([92, 28, 24]) * v + np.array([14, 8, 10]) * (1 - v)
im = Image.fromarray(col.astype(np.uint8), 'RGB')
d = ImageDraw.Draw(im)
F = '/usr/share/fonts/truetype/dejavu/'
big = ImageFont.truetype(F + 'DejaVuSerif-Bold.ttf', 30)
small = ImageFont.truetype(F + 'DejaVuSans-Bold.ttf', 11)
tiny = ImageFont.truetype(F + 'DejaVuSans.ttf', 9)
cream = (236, 222, 196)
quiet = (190, 160, 140)

d.text((24, 14), 'CAN-ABYSS DELAY', font=big, fill=cream)
d.text((26, 48), 'NEW HORIZON ELECTRONICS', font=small, fill=quiet)
d.text((640, 20), 'placeholder face', font=tiny, fill=quiet, anchor='ra')

def label(cx, ty, text, f=small):
    d.text((cx, ty), text, font=f, fill=cream, anchor='ma')

# main knobs (62 px): row 1 Time Repeat Reverb Tone Mix, row 2 Wobble Disc Size Wear Sag
cols = [61, 146, 231, 316, 401]
for cx, t in zip(cols, ['TIME', 'REPEAT', 'REVERB', 'TONE', 'MIX']):
    label(cx, 134, t)
for cx, t in zip(cols, ['WOBBLE', 'DISC SIZE', 'WEAR', 'SAG']):
    label(cx, 230, t)
label(61, 147, '40 ms · 747 · 2 s', tiny)
label(316, 147, 'dull · bright', tiny)

# the mods corner
d.rounded_rectangle((470, 58, 636, 246), radius=8, outline=quiet, width=1)
d.text((482, 64), 'NEW HORIZON MODS', font=tiny, fill=quiet)
d.text((482, 80), 'Disc Size · Wear · Sag', font=tiny, fill=quiet)
d.text((482, 94), 'Hold freezes the disc;', font=tiny, fill=quiet)
d.text((482, 106), 'Time still varispeeds it.', font=tiny, fill=quiet)
label(553, 222, 'TAILS')

# footswitch row
d.text((64, 271), 'HOLD', font=small, fill=cream)
d.text((264, 271), 'EFFECT', font=small, fill=cream)

im.save(os.path.join(ROOT, 'bundle', 'nhe-can-abyss.lv2', 'modgui', 'background.jpg'), quality=88)
print('background written')
