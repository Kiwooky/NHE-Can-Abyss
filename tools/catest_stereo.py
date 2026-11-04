#!/usr/bin/env python3
"""Tests for Can-Abyss Delay Stereo (two discs on one motor).

    python3 tools/catest_stereo.py
    CA_SO=<arm stereo .so> CA_MONO_SO=<arm mono .so> CA_HOST="qemu-arm -L /usr/arm-linux-gnueabihf <arm lv2host>" python3 tools/catest_stereo.py

Needs both plugins built (make; make NAME=nhe-can-abyss-stereo) and tools/lv2host.
The mono plugin's own suite is tools/catest.py.
"""
import os, subprocess, sys, tempfile
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SO = os.environ.get('CA_SO', os.path.join(ROOT, 'bin', 'nhe-can-abyss-stereo.lv2', 'nhe-can-abyss-stereo_dsp.so'))
MONO = os.environ.get('CA_MONO_SO', os.path.join(ROOT, 'bin', 'nhe-can-abyss.lv2', 'nhe-can-abyss_dsp.so'))
HOST = os.environ.get('CA_HOST', os.path.join(ROOT, 'tools', 'lv2host')).split()

ST = ['time', 'repeat', 'hold', 'spread', 'reverb', 'tone', 'disc_size', 'wobble', 'wear', 'sag',
      'ceiling', 'safety', 'tails', 'mix', 'enabled']           # control ports 4..18
MO = ['time', 'repeat', 'hold', 'reverb', 'tone', 'disc_size', 'wobble', 'wear', 'sag',
      'ceiling', 'safety', 'tails', 'mix', 'enabled']           # mono, ports 3..16
DEF = dict(time=350, repeat=3, hold=0, spread=0, reverb=5, tone=5, disc_size=5, wobble=5, wear=3, sag=0,
           ceiling=-6, safety=1, tails=1, mix=50, enabled=1)
fails = 0


def _run(so, order, base, nin, nout, x, sr, c, events):
    with tempfile.TemporaryDirectory() as d:
        fi, fo = os.path.join(d, 'i.raw'), os.path.join(d, 'o.raw')
        np.asarray(x, np.float32).tofile(fi)
        args = HOST + [so, fi, fo, str(sr), str(nin), str(nout)] + ['%g' % c[k] for k in order]
        args += ['@%d:%d=%g' % (s, base + order.index(k), v) for s, k, v in events]
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
        return np.fromfile(fo, np.float32).reshape(-1, nout)


def stereo(l, r, sr=48000, events=(), **kw):
    c = dict(DEF); c.update(kw)
    y = _run(SO, ST, 4, 2, 2, np.stack([l, r], 1), sr, c, events)
    return y[:, 0], y[:, 1]


def mono(x, sr=48000, events=(), **kw):
    c = dict(DEF); c.update(kw); c.pop('spread')
    return _run(MONO, MO, 3, 1, 2, x, sr, c, events)[:, 0]


def check(name, ok, info=''):
    global fails
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, info))
    if not ok:
        fails += 1


def db(v):
    return 20 * np.log10(max(float(v), 1e-12))


def plucks(sr, secs, gap=1.2, level=0.1, freqs=(196, 247, 147, 330, 220, 165)):
    x = np.zeros(int(secs * sr))
    for k, f in enumerate(freqs):
        n = int((0.1 + gap * k) * sr); L = int(1.0 * sr)
        if n + L > len(x):
            break
        a = np.arange(L)
        env = np.exp(-a / (0.3 * sr)) * np.minimum(1, a / (0.005 * sr)) * np.minimum(1, (L - a) / (0.05 * sr))
        x[n:n + L] += level * env * sum(np.sin(2 * np.pi * f * h * a / sr) / h for h in (1, 2, 3))
    return x


def tick_count(w, sr=48000):
    from scipy.signal import butter, sosfilt
    h = np.abs(sosfilt(butter(4, 8000, 'hp', fs=sr, output='sos'), w))
    e = np.sqrt(np.convolve(h ** 2, np.ones(96) / 96, 'same'))
    bg = np.convolve(e, np.ones(4800) / 4800, 'same') + 1e-7
    idx = np.nonzero((e / bg)[4800:-4800] > 8)[0]
    return len([i for k, i in enumerate(idx) if k == 0 or i - idx[k - 1] > 2400])


sr = 48000
x = plucks(sr, 8)

# 1. Same signal on both inputs, Spread 0 = the mono plugin's Mix Out. Not bit for
#    bit: DPF builds with fast-math, so the two-disc code rounds slightly differently
#    (measured 1e-6 at the defaults, 2e-5 in runaways); the limit is -80 dBFS.
worst = 0.0
cases = [{}, dict(mix=0), dict(mix=100), dict(repeat=9, reverb=8, safety=0), dict(wobble=10, wear=10, sag=10, disc_size=0),
         dict(time=40, repeat=10, reverb=10), dict(time=2000, tone=0), dict(tails=0, ceiling=-24)]
evs = [(), (), (), (), (), (), (), ()]
cases += [{}, {}]
evs += [((sr * 2, 'hold', 1), (sr * 4, 'hold', 0)), ((sr * 2, 'enabled', 0), (sr * 3, 'enabled', 1), (sr * 5, 'time', 900))]
for c, ev in zip(cases, evs):
    m = mono(x, sr, ev, **c)
    l, r = stereo(x, x, sr, ev, **c)
    worst = max(worst, np.abs(l - m).max(), np.abs(r - m).max())
check('same signal both sides, Spread 0 = mono within -80 dBFS (10 cases)', db(worst) < -80, 'max diff %.0f dBFS' % db(worst))

# 2. The sides stay apart: left only in -> right out silent
l, r = stereo(x, np.zeros_like(x), sr, sag=10, repeat=9)
check('left only: right output silent', db(np.abs(r).max()) < -120, 'right peak %.0f dBFS' % db(np.abs(r).max()))
check('left only: left output has echoes', db(np.abs(l[int(0.5 * sr):]).max()) > -40)

# 3. Spread: right echo at 2/3 of Time at 100 %, both sides together at 0
def first_echo(y, x0, lo, hi):
    seg = y[lo:hi]
    c = np.correlate(seg, x0, 'valid')
    return lo + int(np.argmax(np.abs(c)))
burst = np.random.default_rng(3).standard_normal(int(0.03 * sr)) * np.hanning(int(0.03 * sr)) * 0.1
xb = np.zeros(int(2 * sr)); xb[int(0.1 * sr):int(0.1 * sr) + len(burst)] = burst
for sp, want_r in ((0, 600.0), (50, 500.0), (100, 400.0)):
    l, r = stereo(xb, xb, sr, time=600, spread=sp, mix=100, repeat=0, reverb=0, wobble=0, wear=0, tone=5)
    tl = (first_echo(l, burst, int(0.3 * sr), int(1.0 * sr)) - int(0.1 * sr)) / sr * 1000
    tr = (first_echo(r, burst, int(0.3 * sr), int(1.0 * sr)) - int(0.1 * sr)) / sr * 1000
    check('Spread %d%%: left %.0f ms, right %.0f ms' % (sp, 600, want_r),
          abs(tl - 600) < 3 and abs(tr - want_r) < 3, 'measured %.1f / %.1f ms' % (tl, tr))

# 4. Moving Spread glides (the wiper arm moves): no ticks
ev = [(int(sr * (1 + 0.5 * k)), 'spread', v) for k, v in enumerate((100, 0, 60, 10, 100))]
l, r = stereo(x, x, sr, ev, repeat=6)
l0, r0 = stereo(x, x, sr, repeat=6)          # the detector also flags note onsets: count only extra ones
n = tick_count(l) + tick_count(r) - tick_count(l0) - tick_count(r0)
check('Spread swept while playing: no ticks', n <= 0, '%d extra tick(s)' % max(n, 0))

# 5. Runaways stay under 0 dBFS, Safety off, stereo input
xr = plucks(sr, 8, freqs=(220, 165, 262, 196, 147, 330))
hot = -99
for c in (dict(repeat=10, reverb=10, sag=10, wear=10), dict(repeat=10, time=40, disc_size=0, wobble=10, spread=100)):
    l, r = stereo(x, xr, sr, safety=0, **c)
    hot = max(hot, db(np.abs(l).max()), db(np.abs(r).max()))
check('runaway, Safety off: outputs never reach 0 dBFS', hot < 0.0, 'hottest %.1f dBFS' % hot)

# 6. Safety is linked: a runaway on the left also pulls the right wet down by the same gain
l, r = stereo(x, x * 0.1, sr, repeat=10, reverb=8, mix=100, ceiling=-12, spread=0)
lu, ru = stereo(x, x * 0.1, sr, repeat=10, reverb=8, mix=100, ceiling=0, safety=0, spread=0)
tail = slice(int(6 * sr), int(8 * sr))
gl = np.sqrt(np.mean(l[tail] ** 2)) / np.sqrt(np.mean(lu[tail] ** 2))
gr = np.sqrt(np.mean(r[tail] ** 2)) / np.sqrt(np.mean(ru[tail] ** 2))
check('Safety limits both sides together (image holds)', abs(db(gl) - db(gr)) < 1.0, 'left %.1f dB, right %.1f dB' % (db(gl), db(gr)))

# 7. Bypass: dry at unity on both sides, no click
ev = [(sr * 2, 'enabled', 0), (int(sr * 4.3), 'enabled', 1)]
l, r = stereo(x, xr, sr, ev, mix=100, tails=0)
seg = slice(int(3.0 * sr), int(4.2 * sr))
check('bypass, Mix 100: dry at unity both sides', np.abs(l[seg] - x[seg]).max() < 1e-4 and np.abs(r[seg] - xr[seg]).max() < 1e-4)
step = max(np.abs(np.diff(l)).max(), np.abs(np.diff(r)).max())
check('bypass in/out: no click', step < 0.05, 'max step %.3f' % step)

# 8. Torture: finite at every rate, everything at once, Hold toggling
for rate in (44100, 48000, 96000):
    xt = np.random.default_rng(1).standard_normal(int(3 * rate)) * 0.5
    ev = [(int(rate * 0.8), 'hold', 1), (int(rate * 1.6), 'spread', 100), (int(rate * 2.2), 'hold', 0)]
    l, r = stereo(xt, xt[::-1].copy(), rate, ev, repeat=10, reverb=10, sag=10, wear=10, wobble=10, disc_size=0, time=40, safety=0)
    check('torture %d Hz' % rate, np.isfinite(l).all() and np.isfinite(r).all(), 'peak %.2f' % max(np.abs(l).max(), np.abs(r).max()))

# 9. Hold freezes both discs
ev = [(int(sr * 2.0), 'hold', 1)]
l, r = stereo(x, xr, sr, ev, repeat=4, mix=100, spread=40)
late = slice(int(5 * sr), int(8 * sr))
check('Hold: both sides keep playing the frozen discs', db(np.sqrt(np.mean(l[late] ** 2))) > -50 and db(np.sqrt(np.mean(r[late] ** 2))) > -50)

# 10. Silence in, silence out
l, r = stereo(np.zeros(sr * 2), np.zeros(sr * 2), sr)
check('silence', np.abs(l).max() < 1e-9 and np.abs(r).max() < 1e-9)

print('\n%d failure(s)' % fails)
sys.exit(1 if fails else 0)
