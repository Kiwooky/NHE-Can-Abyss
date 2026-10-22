#!/usr/bin/env python3
"""Compare a hand-written plugin TTL with the one DPF's lv2_ttl_generator writes.

    python3 tools/ttlcmp.py <dpf_generated.ttl> <hand_written.ttl>

Compares every port (index, symbol, name, ranges, units, properties,
designation) and the plugin version. Audio port names and symbols differ by
design (DPF writes lv2_audio_in_1 ...) and are ignored. Also ignored:
mod:preferMomentaryOnByDefault and mod:tempoRelatedDynamicScalePoints,
which DPF can't express. A custom unit (written to set a display format, e.g.
units:render "%.0fms") matches the stock unit DPF writes if the symbols agree.
Port groups compare by name and symbol; a group's lv2:index is hand-only (DPF
can't write it, and MOD needs it to order groups), so it is ignored.
Exit code 1 on any other difference. Needs: pip install rdflib
"""
import sys
import rdflib

L = rdflib.Namespace('http://lv2plug.in/ns/lv2core#')
IGNORE_PROPS = {'http://moddevices.com/ns/mod#preferMomentaryOnByDefault',
                'http://moddevices.com/ns/mod#tempoRelatedDynamicScalePoints'}  # DPF can't write either
U = 'http://lv2plug.in/ns/extensions/units#'
# stock unit -> its symbol, so a custom unit with the same symbol matches it
STOCK = {'ms': 'ms', 's': 's', 'min': 'min', 'hz': 'Hz', 'khz': 'kHz', 'mhz': 'MHz', 'db': 'dB', 'pc': '%',
         'bpm': 'BPM', 'cent': 'ct', 'semitone12TET': 'semi', 'oct': 'oct', 'midiNote': 'note', 'coef': ''}


def node(g, o):
    """A blank node (e.g. a custom unit) compares by its contents, not its random ID."""
    if isinstance(o, rdflib.BNode):
        return '[' + '; '.join(sorted('%s %s' % (str(k).split('#')[-1], node(g, v)) for k, v in g.predicate_objects(o))) + ']'
    return str(o)


def unit_symbol(v):
    """'ms' for units:ms or for a custom unit whose units:symbol is 'ms'."""
    if v.startswith(U):
        return STOCK.get(v[len(U):])
    if v.startswith('['):
        for part in v.strip('[]').split('; '):
            if part.startswith('symbol '):
                return part[len('symbol '):]
    return None


def load(f):
    g = rdflib.Graph(); g.parse(f, format='turtle')
    ports, audio = {}, set()
    for p in g.objects(None, L['port']):
        v = g.value(p, L['index'])
        if v is None:
            continue
        d = {}
        for k in set(g.predicates(p)):
            key = str(k).split('#')[-1].split('/')[-1]
            vals = sorted(node(g, o) for o in g.objects(p, k) if str(o) not in IGNORE_PROPS)
            if key != 'scalePoint':
                d[key] = vals
        if str(L['AudioPort']) in d.get('type', []):
            audio.add(int(v))
        ports[int(v)] = d
    ver = {}
    for k in ('minorVersion', 'microVersion'):
        for s, _, o in g.triples((None, L[k], None)):
            ver[k] = str(o)
    groups = {}
    PG = rdflib.Namespace('http://lv2plug.in/ns/ext/port-groups#')
    for gr in set(g.objects(None, PG['group'])):
        groups[str(gr)] = (str(g.value(gr, L['name'])), str(g.value(gr, L['symbol'])))
    return ports, audio, ver, groups


a, audio, va, ga = load(sys.argv[1])
b, _, vb, gb = load(sys.argv[2])
bad = 0
if len(a) != len(b):
    print('port count differs: DPF %d, hand %d' % (len(a), len(b))); bad += 1
for i in sorted(set(a) | set(b)):
    da, dh = a.get(i, {}), b.get(i, {})
    for k in sorted(set(da) | set(dh)):
        if i in audio and k in ('name', 'symbol'):
            continue
        x, y = da.get(k), dh.get(k)
        if x == y:
            continue
        if k == 'unit' and x and y and len(x) == len(y) == 1 and unit_symbol(x[0]) is not None \
                and unit_symbol(x[0]) == unit_symbol(y[0]):
            continue   # stock unit vs custom unit with the same symbol
        try:
            # float32 in DPF vs decimal by hand: 80.71 is written 80.7099990845
            if x and y and len(x) == len(y) and all(abs(float(p) - float(q)) <= 1e-5 * max(1.0, abs(float(q))) for p, q in zip(x, y)):
                continue
        except ValueError:
            pass
        print('port %d %s: DPF %s, hand %s' % (i, k, x, y)); bad += 1
for k in sorted(set(ga) | set(gb)):
    if ga.get(k) != gb.get(k):
        print('group %s: DPF %s, hand %s' % (k.split('#')[-1], ga.get(k), gb.get(k))); bad += 1
for k in ('minorVersion', 'microVersion'):
    if va.get(k) != vb.get(k):
        print('%s: DPF %s, hand %s' % (k, va.get(k), vb.get(k))); bad += 1
print('TTL matches DPF (%d ports, %d groups, version %s.%s)' % (len(a), len(gb), vb.get('minorVersion'), vb.get('microVersion')) if not bad
      else '%d difference(s)' % bad)
sys.exit(1 if bad else 0)
