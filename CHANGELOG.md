# Changelog

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
