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

# main knobs: two rows of four (62 px), centres
cols = [61, 146, 231, 316]
for cx, t in zip(cols, ['TIME', 'REPEAT', 'REVERB', 'TONE']):
    label(cx, 134, t)
for cx, t in zip(cols, ['WOBBLE', 'DISC SIZE', 'MIX', 'SAG']):
    label(cx, 230, t)
label(61, 147, '40 ms · 747 · 2 s', tiny)

# noise panel
d.rounded_rectangle((388, 58, 636, 236), radius=8, outline=quiet, width=1)
label(450, 132, 'NOISE MODS')
label(575, 132, 'HUM HZ  50 | 60', tiny)
for cx, t in zip([432, 512, 592], ['DISC', 'HISS', 'HUM']):
    label(cx, 214, t)

# footswitch row
d.text((64, 271), 'HOLD', font=small, fill=cream)
d.text((264, 271), 'EFFECT', font=small, fill=cream)
label(512, 338, 'TAILS')

im.save(os.path.join(ROOT, 'bundle', 'nhe-can-abyss.lv2', 'modgui', 'background.jpg'), quality=88)
print('background written')
