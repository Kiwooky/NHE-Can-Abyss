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
ORDER = ['time', 'repeat', 'reverb', 'tone', 'wobble', 'disc_size', 'mix', 'sag', 'hold',
         'noise_mods', 'disc_noise', 'hiss', 'hum', 'hum_hz', 'tails', 'enabled']
DEF = dict(time=350, repeat=3, reverb=5, tone=5, wobble=5, disc_size=5, mix=50, sag=0, hold=0,
           noise_mods=0, disc_noise=5, hiss=5, hum=5, hum_hz=60, tails=1, enabled=1)
PORT = {k: 3 + i for i, k in enumerate(ORDER)}
QUIET = dict(noise_mods=1, disc_noise=0, hiss=0, hum=0)    # all noise sources off

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


# 1. Impulse: first echo at Time, residual repeats every revolution (Time / 0.9)
for sr in (44100, 48000, 96000):
    x = np.zeros(int(3.0 * sr)); x[int(0.1 * sr)] = 0.5
    _, w = run(x, sr, repeat=0, wobble=0, **QUIET)
    pk = peaks(w, sr, 0.1 + 0.35, 0.35 / 0.9, 4)
    t_first = pk[0][1] - 0.1
    gaps = [pk[k + 1][1] - pk[k][1] for k in range(3)]
    finite = np.isfinite(w).all()
    check('impulse %d Hz: first echo at 350 ms' % sr, abs(t_first - 0.35) < 0.002 and finite,
          '%.1f ms' % (t_first * 1e3))
    check('impulse %d Hz: residual every revolution (388.9 ms)' % sr,
          all(abs(g - 0.35 / 0.9) < 0.003 for g in gaps), ' '.join('%.1f' % (g * 1e3) for g in gaps))
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
               noise_mods=1, disc_noise=10, hiss=10, hum=10)
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

# 8. Noise Mods locked: knob positions make no difference
x = np.zeros(int(1.5 * sr)); x[int(0.1 * sr)] = 0.5
a, _ = run(x, sr, noise_mods=0, disc_noise=5, hiss=5, hum=5)
b, _ = run(x, sr, noise_mods=0, disc_noise=10, hiss=0, hum=2)
check('locked = stock whatever the knobs', np.array_equal(a, b))

# 9. Stock noise floor, and all sources at 0 = silent
z = np.zeros(int(2 * sr))
_, w = run(z, sr)
nf = db(rms(w[sr:]))
check('stock noise floor in range (-80..-60 dBFS)', -80 < nf < -60, '%.1f dBFS' % nf)
_, w = run(z, sr, **QUIET)
check('noise knobs at 0: silent', rms(w[sr:]) < 1e-6, '%.1f dBFS' % db(rms(w[sr:])))
_, w = run(z, sr, noise_mods=1, disc_noise=10, hiss=10, hum=10)
check('noise knobs at 10: louder than stock', db(rms(w[sr:])) > nf + 6, '%.1f dBFS' % db(rms(w[sr:])))

# 10. Predictive gate: quieter in the gaps, open on the echoes
t = np.arange(int(4 * sr)) / sr
burst = ((t % 1.0) < 0.15).astype(float) * 0.3 * np.sin(2 * np.pi * 300 * t)
def gap_and_echo(hiss):
    _, w = run(burst, sr, repeat=0, reverb=0, wobble=0, noise_mods=1, disc_noise=0, hum=0, hiss=hiss)
    gap = rms(w[int(2.70 * sr):int(2.95 * sr)])      # no echo here
    echo = rms(w[int(2.37 * sr):int(2.48 * sr)])     # echo of the burst at 2.0 s
    return gap, echo
g5, e5 = gap_and_echo(5)
g2, e2 = gap_and_echo(1.5)
check('gate: gaps at least 20 dB quieter', db(g2) < db(g5) - 20, '%.1f -> %.1f dBFS' % (db(g5), db(g2)))
check('gate: echoes untouched', abs(db(e2) - db(e5)) < 0.5, '%.2f dB' % (db(e2) - db(e5)))

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

# 12. Silence in, silence out with noise off
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
check('warble stock 3-6 cents RMS', 3 < w350 < 6, '%.1f cents' % w350)
check('warble independent of time', abs(w1500 - w350) < 1.0, '%.1f vs %.1f cents' % (w1500, w350))
check('Wobble 10 about doubles it', 1.6 < w10 / w350 < 2.4, '%.1f cents' % w10)
check('big disc steadier', wbig < 0.75 * w350, '%.1f cents' % wbig)

# 14. Hold engage and Noise Mods unlock are click-free
t = np.arange(int(3 * sr)) / sr
x = 0.3 * np.sin(2 * np.pi * 440 * t)
_, w = run(x, sr, events=[(int(1.0 * sr), 'hold', 1)], repeat=0, reverb=6)
ref = np.abs(np.diff(w[int(0.5 * sr):int(0.9 * sr)])).max()
step = np.abs(np.diff(w[int(0.98 * sr):int(3 * sr)])).max()
check('hold engage and loop seam click-free', step < 1.5 * ref, 'step %.3f vs signal %.3f' % (step, ref))
_, w = run(np.zeros(int(2 * sr)), sr, noise_mods=0, disc_noise=10, hiss=10, hum=10,
           events=[(int(1 * sr), 'noise_mods', 1)])
check('unlock glides (no step)', np.abs(np.diff(w)).max() < 0.01, 'max step %.4f' % np.abs(np.diff(w)).max())

print('\n%d failure(s)' % fails)
sys.exit(1 if fails else 0)
