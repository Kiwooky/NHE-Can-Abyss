#!/usr/bin/env python3
"""Relative CPU benchmark: render the same 60 s of noise through each plugin.

    python3 tools/bench.py name=<so>:<n_out>:<ctl,ctl,...> ...

Times each with tools/lv2host (best of 3) and prints cost relative to the
first entry. Host overhead (file I/O) is measured with silence through a
trivial pass and subtracted. Only the ratios mean anything; the Duo's own
CPU meter is the real number.
"""
import os, subprocess, sys, tempfile, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = os.environ.get('CA_HOST', os.path.join(ROOT, 'tools', 'lv2host')).split()
SR, SECS = 48000, 60

def best(args, n=3):
    t = []
    for _ in range(n):
        a = time.perf_counter(); subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
        t.append(time.perf_counter() - a)
    return min(t)

with tempfile.TemporaryDirectory() as d:
    fi, fo = os.path.join(d, 'i.raw'), os.path.join(d, 'o.raw')
    (0.2 * np.random.default_rng(0).standard_normal(SR * SECS)).astype(np.float32).tofile(fi)
    res = []
    for spec in sys.argv[1:]:
        name, rest = spec.split('=', 1)
        so, nout, ctl = rest.split(':')
        t = best(HOST + [so, fi, fo, str(SR), '1', nout] + ctl.split(','))
        res.append((name, t))
    base = res[0][1]
    for name, t in res:
        print('%-14s %6.2f s for %d s audio  (%.2f%% of one core here, %.2fx %s)'
              % (name, t, SECS, 100 * t / SECS, t / base, res[0][0]))
