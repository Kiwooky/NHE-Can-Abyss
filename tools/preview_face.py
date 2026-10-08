#!/usr/bin/env python3
"""Build a self-contained, interactive preview of a modgui face: try it in a
browser without a MOD.

    python3 tools/preview_face.py <bundle>.lv2 out.html [--set symbol=value ...]

Emulates the parts of mod-ui a face depends on, copied from mod-ui's
html/js/modgui.js (Oct 2026):
  - film widget: frames = strip width / element width; vertical drag
    (100 / (steps/2) px per step, rounded up) and horizontal drag at half that;
    logarithmic ports on a log2 scale; mouse wheel
  - mod-widget="switch": click toggles, classes on/off
  - mod-role="bypass": click toggles, class on = bypassed
  - mod-role="input-control-value": the unit's units:render format (a bare %f
    becomes %.2f, as in mod-ui), updated live; click to type a value
  - the face script (modgui:javascript) gets 'start' and 'change' events,
    with jQuery like in mod-ui, and funcs.set_port_value (which, as in
    mod-ui, updates the widgets but does not echo a 'change' to the script)
Below the face: every port's value, for checking. Not emulated: addressing,
presets, MIDI learn, tablet gestures. Images are inlined; jQuery loads from
cdnjs.
"""
import base64, json, mimetypes, os, re, sys
import rdflib

L = rdflib.Namespace('http://lv2plug.in/ns/lv2core#')
MG = rdflib.Namespace('http://moddevices.com/ns/modgui#')
U = rdflib.Namespace('http://lv2plug.in/ns/extensions/units#')
STOCK_RENDER = {'ms': '%f ms', 's': '%f s', 'hz': '%f Hz', 'khz': '%f kHz', 'db': '%f dB', 'pc': '%f%%',
                'bpm': '%f BPM', 'cent': '%f ct', 'semitone12TET': '%f semi', 'oct': '%f oct'}


def main():
    bundle, out = sys.argv[1].rstrip('/'), sys.argv[2]
    sets = dict(a.split('=', 1) for a in sys.argv[3:] if '=' in a and not a.startswith('--'))
    g = rdflib.Graph()
    for fn in os.listdir(bundle):
        if fn.endswith('.ttl'):
            g.parse(os.path.join(bundle, fn), format='turtle')
    gui = next(g.objects(None, MG['gui']))
    def rel(k):
        v = g.value(gui, MG[k])
        if v is None:
            return None
        p = str(v).replace('file://', '')
        return p if os.path.isabs(p) else os.path.join(bundle, p)
    res = rel('resourcesDirectory')
    html = open(rel('iconTemplate')).read()
    css = open(rel('stylesheet')).read()
    js = open(rel('javascript')).read() if rel('javascript') else ''

    ports = {}
    for p in g.objects(None, L['port']):
        sym = g.value(p, L['symbol'])
        if sym is None or g.value(p, L['default']) is None:
            continue
        props = [str(o).split('#')[-1] for o in g.objects(p, L['portProperty'])]
        if g.value(p, L['designation']) == L['enabled']:
            props.append('enabled')
        unit = g.value(p, U['unit'])
        render = '%f'
        if isinstance(unit, rdflib.BNode):
            render = str(g.value(unit, U['render']) or '%f')
        elif unit is not None:
            render = STOCK_RENDER.get(str(unit).split('#')[-1], '%f')
        ports[str(sym)] = dict(value=float(sets.get(str(sym), g.value(p, L['default']))),
                               min=float(g.value(p, L['minimum'])), max=float(g.value(p, L['maximum'])),
                               props=props, render=render, name=str(g.value(p, L['name'])))

    def inline(m):
        f = os.path.join(res, m.group(1))
        mime = mimetypes.guess_type(f)[0] or 'application/octet-stream'
        return 'url(data:%s;base64,%s)' % (mime, base64.b64encode(open(f, 'rb').read()).decode())
    css = css.replace('{{{cns}}}', '').replace('{{{ns}}}', '')
    css = re.sub(r'url\(/resources/([^)]+)\)', inline, css)
    html = re.sub(r'\{\{#.*?\}\}.*?\{\{/.*?\}\}', '', html, flags=re.S).replace('{{{cns}}}', '').replace('{{{ns}}}', '')

    page = '''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Face preview: %(name)s</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.1/jquery.min.js"></script>
<style>
:root { --bg:#2b2f36; --fg:#e8e6e1; --dim:#9aa0a8; }
@media (prefers-color-scheme: light) { :root:not([data-theme="dark"]) { --bg:#e9e7e2; --fg:#1f2329; --dim:#5d636b; } }
:root[data-theme="light"] { --bg:#e9e7e2; --fg:#1f2329; --dim:#5d636b; }
:root { box-sizing: border-box; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }
html, body { margin: 0; background: var(--bg); color: var(--fg); font: 13px/1.4 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
.wrap { padding: 18px; max-width: 100%%; }
.stage { position: relative; overflow-x: auto; padding-bottom: 6px; }
.stage .mod-pedal { position: relative !important; }
h1 { font-size: 15px; margin: 0 0 4px; } p.note { color: var(--dim); margin: 0 0 14px; max-width: 650px; }
table { border-collapse: collapse; margin-top: 14px; font-variant-numeric: tabular-nums; }
td { padding: 2px 14px 2px 0; } td.v { text-align: right; min-width: 70px; }
.mod-drag-handle { display: none; }
%(css)s
</style></head><body><div class="wrap">
<h1>%(name)s: face preview</h1>
<p class="note">Drag knobs and sliders up or down (or use the wheel); click switches and the footswitches.
Click a readout to type a value. This mimics mod-ui's widgets; check the real thing on your MOD.</p>
<div class="stage">%(html)s</div>
<table id="vals"></table>
</div>
<script>
const PORTS = %(ports)s;
const faceScript = %(js)s;
const root = $('.mod-pedal');
function render(fmt, v) {
  fmt = fmt.replace('%%f', '%%.2f');
  return fmt.replace(/%%%%/g, '\\u0001').replace(/%%\\.(\\d+)f/, (m, d) => v.toFixed(+d)).replace(/%%d/, Math.round(v)).replace(/\\u0001/g, '%%');
}
// as mod-ui: values set from the face script (funcs.set_port_value) update the
// widgets but are NOT sent back to the script as 'change' events
const FUNCS = { set_port_value: (sym, v) => { if (PORTS[sym]) setValue(sym, v, null, true); } };
function emit(sym, value, fromJs) {
  if (faceScript && !fromJs) { try { faceScript({ type: 'change', symbol: sym, value: value, icon: root, api_version: 3 }, FUNCS); } catch (e) { console.error('face script error', e); } }
  $('[mod-role=input-control-value][mod-port-symbol="' + sym + '"]').text(render(PORTS[sym].render, value));
  const row = document.getElementById('row-' + sym); if (row) row.textContent = (+value).toFixed(2);
}
function setValue(sym, v, el, fromJs) {
  const p = PORTS[sym]; v = Math.min(p.max, Math.max(p.min, v));
  if (p.props.includes('integer') || p.props.includes('toggled')) v = Math.round(v);
  p.value = v; (el ? $(el) : $('[mod-port-symbol="' + sym + '"][mod-role=input-control-port]')).each(function () { draw(this, sym); });
  emit(sym, v, fromJs);
}
const isLog = p => p.props.includes('logarithmic') && p.min > 0 && p.max > 0;
const scale = (p, v) => isLog(p) ? Math.log2(v) : v;
const unscale = (p, s) => isLog(p) ? Math.pow(2, s) : s;
function draw(el, sym) {
  const p = PORTS[sym], d = el._film;
  if ($(el).attr('mod-widget') === 'switch') { $(el).toggleClass('on', p.value > p.min).toggleClass('off', !(p.value > p.min)); return; }
  if (!d) return;
  const lo = scale(p, p.min), hi = scale(p, p.max);
  const steps = Math.round((scale(p, p.value) - lo) * d.portSteps / (hi - lo));
  d.pos = steps;
  const rot = Math.min(d.filmSteps, Math.max(0, Math.round(steps / d.portSteps * d.filmSteps)));
  el.style.backgroundPosition = (-rot * d.size) + 'px 0px';
}
async function setupFilm(el, sym) {
  const cs = getComputedStyle(el); const m = cs.backgroundImage.match(/url\\(["']?(.*?)["']?\\)/);
  if (!m) return;
  const img = new Image(); img.src = m[1]; await img.decode();
  const height = parseInt((cs.backgroundSize.split(' ')[1]) || 0) || img.naturalHeight;
  const sw = Math.round(parseFloat(cs.width));
  const filmSteps = Math.max(1, Math.round(height * img.naturalWidth / (sw * img.naturalHeight)) - 1);
  const p = PORTS[sym];
  let portSteps = filmSteps, prec = filmSteps / 2;
  if (p.props.includes('toggled')) { portSteps = prec = 1; }
  else if (p.props.includes('integer') && !p.props.includes('logarithmic')) { portSteps = p.max - p.min; while (portSteps > 300) portSteps = Math.round(portSteps / 2); prec = portSteps + 50 * Math.log10(1 + Math.pow(2, 1 / portSteps)); }
  el._film = { filmSteps, portSteps, size: sw, pv: Math.ceil(100 / prec), ph: Math.ceil(200 / prec), div: portSteps / Math.max(portSteps, 30) };
  draw(el, sym);
  const d = el._film;
  const fromSteps = s => { s = Math.min(d.portSteps, Math.max(0, s)); const lo = scale(p, p.min), hi = scale(p, p.max); return unscale(p, lo + s * (hi - lo) / d.portSteps); };
  el.addEventListener('pointerdown', e => {
    e.preventDefault(); el.setPointerCapture(e.pointerId);
    let lx = e.pageX, ly = e.pageY;
    const move = ev => {
      const hd = (lx - ev.pageX) / d.ph, vd = (ly - ev.pageY) / d.pv;   // as mod-ui: up or right increases
      if (Math.abs(hd) > 0) lx = ev.pageX; if (Math.abs(vd) > 0) ly = ev.pageY;
      d.pos = Math.min(d.portSteps, Math.max(0, d.pos + (vd - hd) * d.div));
      p.value = fromSteps(d.pos);
      const rot = Math.min(d.filmSteps, Math.max(0, Math.round(d.pos / d.portSteps * d.filmSteps)));
      el.style.backgroundPosition = (-rot * d.size) + 'px 0px';
      emit(sym, p.value);
    };
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); };
    el.addEventListener('pointermove', move); el.addEventListener('pointerup', up);
  });
  el.addEventListener('wheel', e => { e.preventDefault(); d.pos = Math.min(d.portSteps, Math.max(0, d.pos + (e.deltaY < 0 ? 1 : -1) * Math.max(1, d.portSteps / 30))); setValue(sym, fromSteps(d.pos), el); }, { passive: false });
}
(async () => {
  const vals = document.getElementById('vals');
  for (const [sym, p] of Object.entries(PORTS)) {
    const tr = document.createElement('tr'); tr.innerHTML = '<td>' + p.name + ' <span style="color:var(--dim)">(' + sym + ')</span></td><td class="v" id="row-' + sym + '"></td>'; vals.appendChild(tr);
  }
  for (const el of document.querySelectorAll('[mod-role=input-control-port][mod-port-symbol]')) {
    const sym = el.getAttribute('mod-port-symbol'); if (!PORTS[sym]) continue;
    if (el.getAttribute('mod-widget') === 'switch') { draw(el, sym); el.addEventListener('click', () => setValue(sym, PORTS[sym].value > PORTS[sym].min ? PORTS[sym].min : PORTS[sym].max, el)); }
    else await setupFilm(el, sym);
  }
  const en = Object.keys(PORTS).find(s => PORTS[s].props.includes('enabled'));
  $('[mod-role=bypass]').each(function () {
    const b = this, show = () => { const byp = en ? PORTS[en].value < 0.5 : false; $(b).toggleClass('on', byp).toggleClass('off', !byp); };
    show(); b.addEventListener('click', () => { if (en) { PORTS[en].value = PORTS[en].value > 0.5 ? 0 : 1; emit(en, PORTS[en].value); } show(); });
  });
  $('[mod-role=input-control-value]').each(function () {
    const f = this, sym = f.getAttribute('mod-port-symbol');
    f.addEventListener('click', () => { const v = prompt(PORTS[sym].name + ' (' + PORTS[sym].min + ' to ' + PORTS[sym].max + ')', PORTS[sym].value); if (v !== null && !isNaN(parseFloat(v))) setValue(sym, parseFloat(v)); });
  });
  for (const [sym, p] of Object.entries(PORTS)) emit(sym, p.value);
  if (faceScript) { try { faceScript({ type: 'start', ports: Object.entries(PORTS).map(([symbol, p]) => ({ symbol, value: p.value })), icon: root, api_version: 3 }, FUNCS); } catch (e) { console.error('face script error', e); } }
  document.title = 'ready';
})();
</script></body></html>''' % dict(name=os.path.basename(bundle), css=css, html=html, ports=json.dumps(ports),
                                   js=('(' + js.strip() + ')') if js.strip() else 'null')
    open(out, 'w').write(page)
    print('wrote %s (%.0f KB)' % (out, os.path.getsize(out) / 1024))


if __name__ == '__main__':
    main()
