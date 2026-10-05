#!/usr/bin/env python3
"""Audio test suite for Can-Abyss Delay (offline, via tools/lv2host).

    python3 tools/catest.py                       native build in bin/
    CA_SO=<arm .so> CA_HOST="qemu-arm -L /usr/arm-linux-gnueabihf <arm lv2host>" python3 tools/catest.py

Prints PASS/FAIL per check and exits non-zero on any failure.
"""
import os, subprocess, sys, tempfile
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SO = os.environ.get('CA_SO', os.path.join(ROOT, 'bin', 'nhe-can-abyss.lv2', 'nhe-can-abyss_dsp.so'))
HOST = os.environ.get('CA_HOST', os.path.join(ROOT, 'tools', 'lv2host')).split()

# control ports in index order (3..18)
ORDER = ['time', 'repeat', 'reverb', 'tone', 'wobble', 'disc_size', 'wear', 'mix', 'sag', 'ceiling',
         'hold', 'safety', 'tails', 'enabled']
DEF = dict(time=350, repeat=3, reverb=5, tone=5, wobble=5, disc_size=5, wear=3, mix=50, sag=0, ceiling=-6,
           hold=0, safety=1, tails=1, enabled=1)
PORT = {k: 3 + i for i, k in enumerate(ORDER)}
QUIET = dict(wear=0)    # a new disc: no wear irregularities

fails = 0


def run(x, sr=48000, events=(), **kw):
    c = dict(DEF); c.update(kw)
    with tempfile.TemporaryDirectory() as d:
        fi, fo = os.path.join(d, 'i.raw'), os.path.join(d, 'o.raw')
        np.asarray(x, np.float32).tofile(fi)
        args = HOST + [SO, fi, fo, str(sr), '1', '2'] + ['%g' % c[k] for k in ORDER]
        args += ['@%d:%d=%g' % (s, PORT[k], v) for s, k, v in events]
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
        y = np.fromfile(fo, np.float32).reshape(-1, 2)
    return y[:, 0], y[:, 1]


def check(name, ok, info=''):
    global fails
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, info))
    if not ok:
        fails += 1


def db(v):
    return 20 * np.log10(max(float(v), 1e-12))


def rms(v):
    return float(np.sqrt(np.mean(np.square(v, dtype=np.float64))))


def centroid(seg, sr):
    s = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    return float((s * f).sum() / max(s.sum(), 1e-12))


def peaks(w, sr, t0, period, n):
    """Peak level in a +/-20 ms window around t0 + k*period."""
    out = []
    for k in range(n):
        c = int((t0 + k * period) * sr)
        a, b = max(c - int(0.02 * sr), 0), c + int(0.02 * sr)
        seg = np.abs(w[a:b])
        out.append((float(seg.max()), (a + int(seg.argmax())) / sr))
    return out


# 1. Impulse: first echo at Time; Reverb returns every revolution (Time / 0.9) as a widening smear
for sr in (44100, 48000, 96000):
    x = np.zeros(int(3.0 * sr)); x[int(0.1 * sr)] = 0.5
    _, w = run(x, sr, repeat=0, wobble=0, **QUIET)
    pk = peaks(w, sr, 0.1 + 0.35, 0.35 / 0.9, 4)
    t_first = pk[0][1] - 0.1
    finite = np.isfinite(w).all()
    check('impulse %d Hz: first echo at 350 ms' % sr, abs(t_first - 0.35) < 0.002 and finite,
          '%.1f ms' % (t_first * 1e3))
    # Reverb is a smear: each pass's energy is centred on one more revolution,
    # and each pass is wider than the last (diffusion), not a clean echo
    P = 0.35 / 0.9
    cen, wid = [], []
    for k in range(3):
        c = 0.1 + 0.35 + k * P
        a0, b0 = int((c - 0.06) * sr), int((c + 0.06) * sr)
        e = w[a0:b0].astype(np.float64) ** 2
        tt = np.arange(a0, b0) / sr
        m0 = float((e * tt).sum() / e.sum())
        cen.append(m0 - (0.1 + 0.35))
        wid.append(float(np.sqrt((e * (tt - m0) ** 2).sum() / e.sum())))
    check('impulse %d Hz: residual centred on each revolution (388.9 ms)' % sr,
          all(abs(cen[k] - k * P) < 0.006 for k in range(3)), ' '.join('%.1f' % (c * 1e3) for c in cen))
    check('impulse %d Hz: each pass smeared wider' % sr, wid[2] > wid[1] > wid[0],
          ' '.join('%.1f ms' % (v * 1e3) for v in wid))
    check('impulse %d Hz: each pass quieter' % sr, all(pk[k + 1][0] < pk[k][0] for k in range(3)),
          ' '.join('%.1f dB' % db(p[0] / 0.5) for p in pk))

# 2. Each residual pass is darker (centroid falls), on noise bursts
sr = 48000
x = np.zeros(int(2.5 * sr)); n0 = int(0.1 * sr)
x[n0:n0 + int(0.03 * sr)] = 0.3 * np.random.default_rng(1).standard_normal(int(0.03 * sr))
_, w = run(x, sr, repeat=0, wobble=0, reverb=8, **QUIET)
cs = []
for k in range(3):
    a = int((0.1 + 0.35 + k * 0.35 / 0.9) * sr)
    cs.append(centroid(w[a - 200:a + int(0.04 * sr)], sr))
check('residual passes darken', cs[0] > cs[1] > cs[2], ' '.join('%.0f Hz' % c for c in cs))

# 3. Long times darken by themselves; a big disc restores brightness
def first_echo_centroid(t_ms, size):
    T = t_ms / 1000
    x = np.zeros(int((T + 0.5) * sr)); n0 = int(0.1 * sr)
    x[n0:n0 + int(0.03 * sr)] = 0.3 * np.random.default_rng(2).standard_normal(int(0.03 * sr))
    _, w = run(x, sr, time=t_ms, repeat=0, reverb=0, wobble=0, disc_size=size, **QUIET)
    a = int((0.1 + T) * sr)
    return centroid(w[a - 200:a + int(0.04 * sr)], sr)

c350, c1500, c1500big = first_echo_centroid(350, 5), first_echo_centroid(1500, 5), first_echo_centroid(1500, 10)
check('long time is darker', c1500 < 0.85 * c350, '%.0f -> %.0f Hz' % (c350, c1500))
check('Disc Size 10 restores brightness', c1500big > 1.15 * c1500, '%.0f -> %.0f Hz' % (c1500, c1500big))

# 4. Level: first echo of a sine near unity (wet out)
t = np.arange(int(1.2 * sr)) / sr
x = 0.25 * np.sin(2 * np.pi * 440 * t) * (t < 0.3)
_, w = run(x, sr, repeat=0, reverb=0, wobble=0, **QUIET)
g = rms(w[int(0.40 * sr):int(0.60 * sr)]) / rms(x[int(0.05 * sr):int(0.25 * sr)])
check('first echo level about unity', -3.5 < db(g) < 1.0, '%.1f dB' % db(g))

# 5. Time sweep 40 ms <-> 2 s with signal: finite, no runaway
x = 0.3 * np.random.default_rng(3).standard_normal(int(8 * sr))
ev = [(int(k * 0.25 * sr), 'time', v) for k, v in enumerate([40, 120, 400, 1000, 2000, 1500, 600, 200, 60, 40, 2000, 40])]
m, w = run(x, sr, events=ev, repeat=6)
check('time sweep finite and bounded', np.isfinite(m).all() and np.abs(w).max() < 4, 'peak %.2f' % np.abs(w).max())

# 6. Torture: everything at max, three rates
for srt in (44100, 48000, 96000):
    x = 0.5 * np.random.default_rng(4).standard_normal(int(6 * srt))
    m, w = run(x, srt, repeat=10, reverb=10, sag=10, wobble=10, disc_size=0, time=40, tone=10,
               wear=10)
    check('torture %d Hz finite and bounded' % srt, np.isfinite(m).all() and np.abs(w).max() < 4,
          'peak %.2f' % np.abs(w).max())

# 7. Hold: the frozen loop keeps 440 Hz and ignores new input; varispeed shifts pitch
t = np.arange(int(4 * sr)) / sr
x = np.where(t < 1.0, 0.3 * np.sin(2 * np.pi * 440 * t), 0.3 * np.sin(2 * np.pi * 1000 * t))
_, w = run(x, sr, events=[(int(0.9 * sr), 'hold', 1)], repeat=0, reverb=6, wobble=0, **QUIET)
seg = w[int(2.0 * sr):int(3.0 * sr)]
s = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))); f = np.fft.rfftfreq(len(seg), 1 / sr)
e440, e1000 = s[(f > 420) & (f < 460)].max(), s[(f > 970) & (f < 1030)].max()
check('hold keeps the loop, ignores new input', e440 > 30 * e1000 and rms(seg) > 0.02,
      '440/1000 = %.0f, rms %.3f' % (e440 / max(e1000, 1e-9), rms(seg)))
_, w = run(x, sr, events=[(int(0.9 * sr), 'hold', 1), (int(1.2 * sr), 'time', 700)],
           repeat=0, reverb=6, wobble=0, **QUIET)
seg = w[int(3.0 * sr):int(4.0 * sr)]
s = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
fpk = f[(f > 100) & (f < 600)][s[(f > 100) & (f < 600)].argmax()]
check('held loop varispeeds (Time x2 -> octave down)', abs(fpk - 220) < 8, '%.1f Hz' % fpk)
_, w = run(x, sr, events=[(int(0.9 * sr), 'hold', 1), (int(2.0 * sr), 'hold', 0)],
           repeat=0, reverb=6, wobble=0, **QUIET)
d = np.abs(np.diff(w[int(1.95 * sr):int(2.1 * sr)]))
check('hold release is click-free', d.max() < 0.1, 'max step %.3f' % d.max())

# 8. Clean: silence in, silence out, even with a worn disc and Sag
_, w = run(np.zeros(int(2 * sr)), sr, wear=10, sag=10, wobble=10, disc_size=0)
check('clean: no hiss, hum or crackle', np.abs(w).max() < 1e-6, '%.1f dBFS peak' % db(np.abs(w).max()))

# 9. Tone: a wide tilt, duller and brighter than stock
x = np.zeros(int(1.0 * sr)); x[4800:4800 + 1440] = 0.3 * np.random.default_rng(5).standard_normal(1440)
tc = {}
for tv in (0, 5, 10):
    _, w = run(x, sr, tone=tv, repeat=0, reverb=0, wobble=0, **QUIET)
    a0 = int(0.45 * sr)
    tc[tv] = centroid(w[a0 - 200:a0 + 1900], sr)
check('Tone 0 much duller', tc[0] < 0.7 * tc[5], '%.0f vs %.0f Hz' % (tc[0], tc[5]))
check('Tone 10 brighter', tc[10] > 1.1 * tc[5], '%.0f vs %.0f Hz' % (tc[10], tc[5]))

# 10. Sag: a hard hit dips the pitch (motor slip) and droops the sustain
from scipy.signal import hilbert as _hb, butter, sosfiltfilt
from scipy.ndimage import uniform_filter1d as _uf
t = np.arange(int(2.5 * sr)) / sr
x = 0.05 * np.sin(2 * np.pi * 440 * t) + np.where((t > 1.0) & (t < 1.25), 0.15 * np.sin(2 * np.pi * 110 * t), 0)
def dip(sag):
    _, w = run(x, sr, sag=sag, repeat=0, reverb=0, wobble=0, **QUIET)
    seg = sosfiltfilt(butter(4, [350, 550], 'bandpass', fs=sr, output='sos'), w[int(0.9 * sr):int(1.33 * sr)])
    f = np.diff(np.unwrap(np.angle(_hb(seg)))) * sr / 2 / np.pi
    return float((1200 * np.log2(np.abs(_uf(f, 480)[1500:-1500]) / 440)).min())
d0, d10 = dip(0), dip(10)
check('Sag 10: hard hits dip the pitch (> 50 cents)', d10 < -50 and d0 > -5, '%.0f cents (Sag 0: %.0f)' % (d10, d0))
g = np.zeros_like(t)
for k in range(2):
    n = int((0.5 + k) * sr); L = int(0.4 * sr)
    g[n:n + L] = 0.1 * np.exp(-np.arange(L) / (0.1 * sr)) * np.sin(2 * np.pi * 196 * np.arange(L) / sr)
sus = []
for sg in (0, 10):
    _, w = run(g, sr, sag=sg, repeat=0, reverb=0, wobble=0, **QUIET)
    sus.append(db(rms(w[int(0.92 * sr):int(1.05 * sr)])))
check('Sag 10: sustain droops at guitar level (> 3 dB)', sus[0] - sus[1] > 3, '%.1f dB' % (sus[0] - sus[1]))

# 11. Bypass: dry at unity, click-free, tails on and off
t = np.arange(int(3 * sr)) / sr
x = 0.3 * np.sin(2 * np.pi * 220 * t)
for tails in (1, 0):
    m, w = run(x, sr, tails=tails, events=[(int(1.0 * sr), 'enabled', 0), (int(2.0 * sr), 'enabled', 1)])
    seg = m[int(1.5 * sr):int(1.9 * sr)]
    dry = x[int(1.5 * sr):int(1.9 * sr)]
    if tails:
        ok = np.abs(m[int(0.95 * sr):int(1.1 * sr)] - x[int(0.95 * sr):int(1.1 * sr)]).max() < 2.0
    else:
        ok = np.abs(seg - dry).max() < 1e-3
    d = np.abs(np.diff(m[int(0.98 * sr):int(1.05 * sr)]))
    check('bypass tails=%d: dry at unity, no click' % tails, ok and d.max() < 0.1,
          'max step %.3f' % d.max())

# 12. Silence in, silence out
_, w = run(np.zeros(int(1 * sr)), sr, **QUIET)
check('silence', np.abs(w).max() < 1e-6)

# 13. Warble: stock about 4-5 cents RMS at any time; Wobble 10 doubles it; big disc halves it
from scipy.signal import hilbert
from scipy.ndimage import uniform_filter1d
def warble(**kw):
    t = np.arange(int(8 * sr)) / sr
    _, w = run(0.3 * np.sin(2 * np.pi * 440 * t), sr, repeat=0, reverb=0, **dict(QUIET, **kw))
    seg = w[int(2.5 * sr):]
    f = np.diff(np.unwrap(np.angle(hilbert(seg)))) * sr / 2 / np.pi
    c = 1200 * np.log2(uniform_filter1d(f, 480)[2000:-2000] / 440)
    return float(c.std())
w350, w1500, w10, wbig = warble(), warble(time=1500), warble(wobble=10), warble(disc_size=10)
wsmall, wworn, wlight = warble(disc_size=0), warble(wear=10), warble(wear=3)
check('warble stock 3-6 cents RMS', 3 < w350 < 6, '%.1f cents' % w350)
check('warble independent of time', abs(w1500 - w350) < 1.0, '%.1f vs %.1f cents' % (w1500, w350))
check('Wobble 10 about 3-4.5x stock', 3.0 < w10 / w350 < 4.5, '%.1f cents' % w10)
check('big disc steadier', wbig < 0.75 * w350, '%.1f cents' % wbig)
check('quarter-size disc about 3-4.5x stock', 3.0 < wsmall / w350 < 4.5, '%.1f cents' % wsmall)
check('Wear 3 (stock) is a light touch', 1.05 < wlight / w350 < 1.6, '%.1f cents' % wlight)
check('Wear 10 is beaten up (> 5x)', wworn > 5 * w350, '%.1f cents' % wworn)

# 14. Hold engage is click-free
t = np.arange(int(3 * sr)) / sr
x = 0.3 * np.sin(2 * np.pi * 440 * t)
_, w = run(x, sr, events=[(int(1.0 * sr), 'hold', 1)], repeat=0, reverb=6)
ref = np.abs(np.diff(w[int(0.5 * sr):int(0.9 * sr)])).max()
step = np.abs(np.diff(w[int(0.98 * sr):int(3 * sr)])).max()
check('hold engage and loop seam click-free', step < 1.5 * ref, 'step %.3f vs signal %.3f' % (step, ref))

# 15. Safety: caps the wet output at the Ceiling while the loop runs away inside
t = np.arange(int(8 * sr)) / sr
x = 0.2 * np.sin(2 * np.pi * 196 * t) * (t < 0.4)
_, w = run(x, sr, repeat=10, reverb=8, tone=8, safety=0)
loud = db(np.abs(w[4 * sr:]).max())
check('runaway without Safety goes past -6 dBFS', loud > -6, '%.1f dBFS' % loud)
for c in (-6, -12, -24):
    m, w = run(x, sr, repeat=10, reverb=8, tone=8, ceiling=c)
    pk, rm = db(np.abs(w[4 * sr:]).max()), db(rms(w[4 * sr:]))
    check('Safety holds the runaway at %d dBFS (and keeps oscillating)' % c, pk <= c + 0.1 and rm > c - 10,
          'peak %.1f, rms %.1f dBFS' % (pk, rm))

# 16. No ticks: musical plucks (smooth envelopes) through hard settings, Safety off.
#     A tick = a burst of >12 kHz energy far above its surroundings.
from scipy.signal import butter as _bt, sosfilt as _sf
_hp = _bt(4, 12000, 'highpass', fs=sr, output='sos')
def tick_count(w):
    h = np.abs(_sf(_hp, w)); e = np.sqrt(np.convolve(h ** 2, np.ones(96) / 96, 'same'))
    bg = np.convolve(e, np.ones(4800) / 4800, 'same') + 1e-7
    idx = np.nonzero((e / bg)[4800:-4800] > 8)[0]
    return len([i for k, i in enumerate(idx) if k == 0 or i - idx[k - 1] > 2400])
t = np.arange(int(10 * sr)) / sr
x = np.zeros_like(t)
for k, f in enumerate([196, 247, 147, 330, 220, 165]):
    n = int((0.2 + 1.5 * k) * sr); L = int(1.2 * sr); a = np.arange(L)
    env = np.exp(-a / (0.3 * sr)) * np.minimum(1, a / (0.002 * sr)) * np.minimum(1, (L - a) / (0.05 * sr))
    x[n:n + L] += 0.15 * env * np.sin(2 * np.pi * f * a / sr)
worst, hot = 0, -99.0
for kw in (dict(repeat=7, reverb=7), dict(repeat=10, reverb=10, sag=10, wear=10), dict(repeat=10, reverb=5, time=60),
           dict(repeat=10, reverb=5, time=40, disc_size=0, wobble=10), dict(repeat=9, reverb=6, tone=10),
           dict(repeat=10, reverb=10, disc_size=0, wobble=10), dict(repeat=7, reverb=7, time=1500)):
    m, w = run(x, sr, safety=0, **kw)
    worst = max(worst, tick_count(w)); hot = max(hot, db(np.abs(m).max()), db(np.abs(w).max()))
check('no ticks across runaway settings (Safety off)', worst == 0, '%d tick(s)' % worst)
check('outputs never reach 0 dBFS (soft knee)', hot < 0.0, 'hottest %.1f dBFS' % hot)

# 17. Where it runs away: Repeat alone from about 8.5; below that a high Reverb
#     tips it over (Repeat 7 + Reverb 9); Repeat 6 and below never runs away
t = np.arange(int(12 * sr)) / sr
a0 = np.arange(int(0.6 * sr))
x = np.zeros_like(t)
x[int(0.2 * sr):int(0.2 * sr) + len(a0)] = 0.1 * np.exp(-a0 / (0.15 * sr)) * np.minimum(1, a0 / (0.002 * sr)) * np.sin(2 * np.pi * 196 * a0 / sr)
def late(**kw):
    _, w = run(x, sr, safety=0, **kw)
    return db(rms(w[10 * sr:]))
for kw, want in ((dict(repeat=6, reverb=10), False), (dict(repeat=7, reverb=5), False), (dict(repeat=8, reverb=0), False),
                 (dict(repeat=7, reverb=10), True), (dict(repeat=8, reverb=7), True), (dict(repeat=8.5, reverb=0), True),
                 (dict(repeat=10, reverb=0), True)):
    l = late(**kw)
    check('Repeat %g + Reverb %g %s' % (kw['repeat'], kw['reverb'], 'runs away' if want else 'dies away'),
          (l > -25) == want, '%.1f dBFS late rms' % l)

print('\n%d failure(s)' % fails)
sys.exit(1 if fails else 0)
