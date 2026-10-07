# Changelog

## 1.0.6 — 2026-10-07

- New panel artwork (logo position).
- Sliders travel further: at zero the caps sit just above the DISC SIZE / MIX AMT labels (204 px of travel, about 1:1 with mod-ui's 200 px drag).
- The can scales from its centre (140 px tall at Disc Size 0, 280 px at 10).

## 1.0.5 — 2026-10-07

The real face (artwork by Niels).

- **Upside-down knobs:** a 128-frame strip sweeping from about 11 o'clock down through 6 to about 1 o'clock. Tone points straight down at centre.
- **Tone centre detent:** 4.6 to 5.4 is exactly flat, so "near the middle" sounds dead centre.
- **Disc Size and Mix sliders** in the right-hand column. The can grows from 140 to 280 px as Disc Size rises, with the Disc Size cap riding on its lid. Each half of the column is its own drag zone; drag up anywhere to raise the value.
- **Live readouts** for Time and Ceiling ("350MS", "-6DB"), filled by mod-ui itself. Click one to type an exact value.
- **Tails** button on the face; the Safety, Tails, Hold and Effect LEDs follow their switches.
- Face is 336 KB. Positions were fitted pixel by pixel to the mockup.
- New tools: `tools/preview_face.py` (try the face in a browser without a MOD) and `tools/ttlcmp.py`. The placeholder face tools are gone.

## 1.0.4 — 2026-10-05

After the 1.0.3 test: it would not oscillate any more. The runaway edge had moved to Repeat 9.3, a sliver of the knob, and Reverb could no longer push it over.

- **Repeat** reaches unity at 8; from about 8.5 it runs away on its own, overdriving harder up to 10 (loop gain 1.4).
- **Reverb can tip it over again, near the edge.** It still backs off as Repeat rises, but keeps a fifth of its strength. Measured edge: Repeat 7 + Reverb 9 to 10, Repeat 7.5 + Reverb 8, Repeat 8 + Reverb 7. Repeat 6 and below never runs away.
- Tests now check that edge on both sides.

## 1.0.3 — 2026-10-05

After the 1.0.2 test (digital ticks; Repeat and Reverb felt like the same knob).

- **Ticks fixed.** Two causes found: the output going past 0 dBFS (up to +3.8 dBFS with Repeat high and Tone bright) and hard-clipping at the converter; and short-time runaways re-sharpening their own edges every lap. Now: 2x oversampled tube and disc stages, loop bandwidth capped at 5.5 kHz plus a gentle 6 kHz roll-off in the Repeat path, and a soft knee just under 0 dBFS on both outputs. A new test plays plucks through seven hard settings and finds no ticks.
- **Repeat and Reverb now do different jobs.** Repeat = echoes. Reverb = wash: two diffusers spread the leftover charge, so each revolution comes back wider (0.6 ms, then 8 ms, then 16 ms) instead of as a second clean echo.
- **One runaway path.** Reverb backs off as Repeat nears unity, so only Repeat tips it over. The last notch of Repeat (9 to 10) is the wild zone: loop gain climbs to 1.4 for hard, overdriven oscillation; once it runs away, Reverb adds some density back.
- **Safety** switch and **Ceiling** knob (−24 to 0 dBFS, default −6): a lookahead limiter (2 ms) with a soft knee on the wet output only. Repeat can still run away inside the can; only what reaches the outputs is capped. Normal echoes pass untouched. The loop is shortened by the lookahead, so echo timing stays exact.
- New ports `ceiling` (after Sag) and `safety` (after Hold): re-add the plugin to test pedalboards.
- CPU: about 1.2x Taj Mahal, level with MultiPlay (was 0.7–0.9x before oversampling).

## 1.0.2 — 2026-10-05

- Hold is latching by default (was momentary): press to freeze, press again to release.

## 1.0.1 — 2026-10-05

After the first hardware test. Ports changed (not yet public, so allowed): re-add the plugin to test pedalboards.

- **Clean by design:** Noise Mods, Hiss, Hum, Hum Hz and the predictive gate are gone. The noise wasn't adding character.
- **Wear** (new, replaces Disc noise): a worn disc's speed and level irregularities, locked to disc position so they repeat every revolution and build in the tails. 0 = new, 3 = stock (light), 10 = beaten up (about 9x stock warble).
- **Disc Size** now goes down to a quarter size: about 3.7x stock warble at 0, darker and twitchier.
- **Wobble** curves steeply above 5: about 3.7x stock at 10 (was 2x). With the smallest disc, about 15x.
- **Sag** reacts to normal guitar levels and droops up to 12 dB; hard hits dip the pitch up to about a semitone.
- **Tone** is a wider tilt EQ around 1.2 kHz: highs -24 dB at 0, +9 dB at 10.
- Face: noise panel removed, Wear knob added. Still a placeholder.
- CPU: about 0.7x Taj Mahal (Duo build under emulation), down from 1.25x.

## 1.0.0 — 2026-10-05

First build.

- Electrostatic oil can model: a leaky disc with no erase head, so leftover charge returns every revolution (Reverb) and darkens each pass; Repeat feeds the read wiper back to the write wiper.
- Time 40 ms – 2 s sets the motor speed: sweeps bend pitch, the read point follows the motor with inertia, and bandwidth follows surface speed (long times are darker).
- Mechanical warble: once-per-revolution runout, belt drift and motor flutter, about 4.5 cents RMS stock at any delay time.
- Tube write and read stages with a touch of even harmonics; Tone shelf out of the loop.
- Modern mods: Disc Size macro, Sag (supply droop + motor slip), Hold (frozen disc that varispeeds), Noise Mods (Disc / Hiss / Hum with a predictive gate, unlock switch, 50/60 Hz hum).
- Mix Out + 100% Wet Out; bypass with Tails on or off, click-free.
- Placeholder pedal face (borrowed MultiPlay knob and switch art).
