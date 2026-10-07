# Development

How Can-Abyss Delay is built, tested and changed. The same process as every New Horizon plugin.

## Toolchain

```sh
apt-get install g++ g++-arm-linux-gnueabihf g++-aarch64-linux-gnu qemu-user lilv-utils
pip install numpy scipy pillow playwright
gcc -O2 -Idpf/distrho/src -Idpf/distrho/src/lv2 tools/lv2host.c -o tools/lv2host -ldl
```

## The loop for every change

1. **Decide the behaviour first** and record it in [spec.md](spec.md). Faithful to the original by default; any deliberate difference goes in the CHANGELOG.
2. **Edit the sources** (`plugins/`, `bundle/`). The LV2 metadata is hand-written: keep port order, ranges and the URI in step with `DistrhoPluginInfo.h` and `initParameter()`.
3. **Build three ways:** native (`make`), Duo (`CXX=arm-linux-gnueabihf-g++ CXXFLAGS="-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard" make`), Duo X / Dwarf (`CXX=aarch64-linux-gnu-g++ make`). Warnings are bugs.
4. **Check the metadata:** build DPF's `lv2_ttl_generator` (from a full DPF checkout at the pinned commit) and compare its output port by port with `bundle/nhe-can-abyss.lv2/nhe-can-abyss.ttl`. Expected difference: audio port symbols only. Then `LV2_PATH=bin lv2info https://github.com/Kiwooky/NHE-Can-Abyss`.
5. **Run the audio suite:** `python3 tools/catest.py` natively, then the Duo build under qemu:
   `CA_SO=<arm .so> CA_HOST="qemu-arm -L /usr/arm-linux-gnueabihf <arm lv2host>" python3 tools/catest.py`.
   It checks echo timing and residual repeats at 44.1/48/96 kHz, darkening per pass and with long times, Disc Size, levels, Time sweeps, torture runs, Hold (freeze, varispeed, clicks), clean output, Tone range, Sag (pitch dip and droop at guitar level), bypass with and without tails, the Safety limiter, warble depth for Wobble, Disc Size and Wear, and silence. **Every reported bug gets a test that fails first.**
6. **CPU:** build with the builder's flags (`make NOOPT=true`) and compare with the other plugins: `python3 tools/bench.py "Ref=<so>:2:<controls>" "Can-Abyss=<so>:2:<controls>"`. Run it on the Duo build under qemu for Duo-like ratios. Only the Duo's own meter gives absolute load.
7. **Face changes:** `python3 tools/preview_face.py bundle/nhe-can-abyss.lv2 preview.html` builds an interactive preview (open it in a browser: drag, click, type values). Take the screenshot from that preview at default settings, because the face script sizes the can; save it as a 256-colour PNG, and the thumbnail at 256×64 or smaller. Never re-save the panel JPEG: it smears the logo's edges.
8. **Bump the version** in `getVersion()` and the TTL together (`d_version(1,0,N)` ↔ `lv2:minorVersion 2 ; lv2:microVersion N`). MOD caches plugin data per version: an unchanged version shows stale faces.
9. **Commit, update `NHE_CAN_ABYSS_VERSION`** in the package file to the new commit, build on builder.mod.audio and check on hardware: face, sound, footswitches, bypass, CPU meter.

## Rules learned the hard way

- **DPF needs `opts:options` and `urid:map`** declared as required features.
- **Parameters arrive with the first `run()`**, not before `activate()`: snap smoothers to their targets on the first run.
- **Buttons and footswitches use `mod-widget="switch"`.** The default film widget ignores a click if the mouse moves a couple of pixels.
- **The face script** (`modgui:javascript`) is one anonymous `function (event, funcs)`. If it throws, mod-ui silently disables it.
- **Once public, ports are frozen.** Never remove, reorder or rename ports, and never change the URI: saved pedalboards depend on them.
- **Test at guitar level.** A guitar into the MOD peaks around -20 dBFS; dynamics tuned for hotter signals (Sag in 1.0.0) barely wake up.
- **Clean beats "authentic" noise.** Hiss and hum were cut after the first hardware test: players kept the movement, not the dirt.
- **Wobble is easy to overdo.** Pitch deviation from a modulated delay grows with the delay; speed changes must be scaled to the current speed or long delays go seasick.
