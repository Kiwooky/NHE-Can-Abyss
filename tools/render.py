#!/usr/bin/env python3
"""Render the pedal face's screenshot and thumbnail from the built bundle.

Run `make` first, then:  python3 tools/render.py
Writes bundle/nhe-can-abyss.lv2/modgui/screenshot-can-abyss.png and
thumbnail-can-abyss.png (rebuild afterwards to copy them into bin/).
Needs playwright (Chromium) and pillow.
"""
import re, os, asyncio
from playwright.async_api import async_playwright
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, 'bin', 'nhe-can-abyss.lv2', 'modgui')
OUT = os.path.join(ROOT, 'bundle', 'nhe-can-abyss.lv2', 'modgui')

html = open(R + '/icon-can-abyss.html').read()
css = open(R + '/stylesheet-can-abyss.css').read()
html = re.sub(r'\{\{#effect.*?\{\{/effect[^}]*\}\}', '', html, flags=re.S)
html = html.replace('{{{cns}}}', '').replace('{{{ns}}}', '')
css = css.replace('{{{cns}}}', '').replace('{{{ns}}}', '').replace('/resources/', 'file://' + R + '/')

def knob(v, lo, hi, px=62):
    return '-%dpx 0' % (round((v - lo) / (hi - lo) * 64) * px)

state = {'repeat': 3, 'reverb': 5, 'tone': 5, 'wobble': 5, 'disc_size': 5, 'wear': 3, 'sag': 0}
extra = ''.join('.canabyss .ca-%s{background-position:%s}' % (k, knob(v, 0, 10)) for k, v in state.items())
import math
tpos = math.log(350 / 40) / math.log(2000 / 40)          # Time knob is logarithmic
extra += '.canabyss .ca-time{background-position:-%dpx 0}' % (round(tpos * 64) * 62)
extra += '.canabyss .ca-mix{background-position:%s}' % knob(50, 0, 100)
extra += '.canabyss .ca-tails{background-position:-100px 0}.canabyss .ca-safety{background-position:-100px 0}'
extra += '.canabyss .ca-ceiling{background-position:%s}' % knob(-6, -24, 0)
extra += '.canabyss .ca-effect{background-position:-168px 0}'
page = '<html><head><style>body{margin:0;background:transparent}%s%s</style></head><body>%s</body></html>' % (css, extra, html)
tmp = os.path.join(ROOT, 'build', 'face.html')
os.makedirs(os.path.dirname(tmp), exist_ok=True)
open(tmp, 'w').write(page)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': 650, 'height': 400})
        await pg.goto('file://' + tmp)
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=os.path.join(ROOT, 'build', 'screenshot_full.png'), omit_background=True)
        await b.close()

asyncio.run(main())
im = Image.open(os.path.join(ROOT, 'build', 'screenshot_full.png')).convert('RGBA')
im.quantize(256, method=Image.Quantize.FASTOCTREE).save(OUT + '/screenshot-can-abyss.png', optimize=True)
t = im.copy(); t.thumbnail((256, 64), Image.LANCZOS); t.save(OUT + '/thumbnail-can-abyss.png', optimize=True)
print('screenshot and thumbnail written to', OUT)
