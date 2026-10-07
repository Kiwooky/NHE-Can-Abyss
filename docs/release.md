# Release checklist: builder link → beta store → official

As of October 2026, MOD publishes community plugins in three steps.

1. **Builder link.** Upload `mod-plugin-builder/nhe-can-abyss/nhe-can-abyss.mk` to builder.mod.audio. A good build gives a shareable install link for forum testers. No MOD approval needed.
2. **Beta store.** Pull request to [mod-audio/mod-plugin-builder](https://github.com/mod-audio/mod-plugin-builder) adding `plugins/package/nhe-can-abyss/nhe-can-abyss.mk`, pinned to a commit. MOD staff review it.
3. **Official (stable).** MOD's 2026 "Beta no more" criteria: UI, documentation (a PDF behind the "See documentation" button), testing on Dwarf, Duo X and Duo, balanced audio where it applies; presets and demos help ([survey results](https://forum.mod.audio/t/beta-no-more-survey-results/13396), [test procedure](https://forum.mod.audio/t/plugin-test-procedure/13345)).

| Item | Status |
| --- | --- |
| Public repo, MIT code licence | Repo to create: `Kiwooky/NHE-Can-Abyss` |
| Artwork licence | Placeholder; Niels to confirm |
| Own identity (URI, maker, bundle name) | Done in 1.0.0 |
| Ports final | Changed in 1.0.1 after the first test; freeze before going public |
| mod-plugin-builder package | Written; first builder.mod.audio build pending |
| Pedal face | Real artwork in 1.0.5; to check in mod-ui on the Duo |
| Manual PDF + `modgui:documentation` line | To do |
| Factory presets | To do |
| Tested on Duo | 1.0.0 played; 1.0.3 to check (incl. CPU meter) |
| Tested on Duo X and Dwarf | To do (forum volunteers) |
| Assignments: footswitches, knobs, MIDI | To check on hardware |
| Demo audio/video | To do |
| Forum thread with builder link | To do |
