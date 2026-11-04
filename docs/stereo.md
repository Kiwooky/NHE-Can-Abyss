# Can-Abyss Delay Stereo — spec v1.0.0

Two discs on one motor shaft. Stereo in, stereo out. Same face, ports and presets as the mono plugin, plus Spread (settings only).

## Model

- **One motor:** Time, motor inertia, the warble (runout, belt drift, flutter) and Sag's motor slip are shared, so both sides stay in time and wobble together.
- **One tube supply:** Sag's droop follows the louder side and applies to both.
- **Two discs:** each side has its own disc, charge, residual wash, read stage, Tone and Repeat loop. Nothing crosses between them (left-only input leaves the right output silent: −240 dBFS).
- **Spread** (0–100 %, default 0, settings only): turns the right disc's read wiper back from 324° to 216°. The right echo comes earlier, at (1 − Spread/3) × Time: 600 / 500 / 400 ms at 0 / 50 / 100 % with Time 600 (measured). The right wiper then also reads a different patch of a worn disc. The wiper arm glides (0.2 s), so moving Spread bends the right side's pitch briefly instead of clicking. Left out of the factory presets, so it stays where you set it when you change preset.
- **Safety** is one limiter for both sides (linked), so a runaway on one side doesn't shift the image: −8.0 dB on both in the test.
- **Hold** freezes both discs.
- Bypass: dry at unity on both sides, Tails as in mono.

**Mono-compatible:** the same signal on both inputs with Spread at 0 gives the mono plugin's Mix Out on both sides, to within −84 dBFS (float rounding: DPF builds with fast-math, so the two-disc code rounds slightly differently from the mono code; not bit for bit).

## Ports

0 `in_l`, 1 `in_r`, 2 `out_l`, 3 `out_r` (a `pg:StereoGroup`), then the controls in groups: **Delay** time, repeat, hold, spread · **Colour** reverb, tone, disc_size · **Vibe** wobble, wear, sag · **Mix** ceiling, safety, tails, mix · then `lv2_enabled`. No Wet Out: for wet only, set Mix to 100.

URI `https://github.com/Kiwooky/NHE-Can-Abyss-Stereo`, unique ID `CABS`, `d_version(1,0,0)` = minorVersion 2, microVersion 0.

## CPU

1.7× the mono plugin (x86 1.70×, Duo build under qemu 1.73×; 20 s of noise, Repeat 6, Spread 50). The mono measured about 1.2× the hall reverb, so the stereo is about 2× the hall reverb. Check the Duo's CPU meter on a real pedalboard.

## Build and test

```sh
make NAME=nhe-can-abyss-stereo          # plus `make` for the mono, which the tests compare against
python3 tools/catest_stereo.py           # 16 checks; the mono suite is tools/catest.py
```

## Files (everything stereo; mono files are untouched)

`plugins/can-abyss-stereo/`, `bundle/nhe-can-abyss-stereo.lv2/`, `mod-plugin-builder/nhe-can-abyss-stereo/`, `tools/catest_stereo.py`, this file. The top-level `Makefile` takes `NAME=` for either plugin.

## To do

- [ ] Face: STEREO badge art (`bundle/nhe-can-abyss-stereo.lv2/modgui/background.jpg`), then re-render the screenshot and thumbnail. It borrows the mono face for now (two jacks each side).
- [ ] Hardware test on the Duo, including the CPU meter.
- [ ] Repo and package: private `NHE-Can-Abyss-Stereo` (paid) or public; then the commit hash in the package `.mk`.
