# Open decisions

1. **Split method for the DelayCtrl features.**
   - A: recompile `dc.c` per feature behind flags, one area offset each (cleaner code, needs a new build and a unit test) (Recommended).
   - B: keep one shared blob, no per-feature compilation (no regression test possible for the all-features build).

2. **DJ FREQ snap.**
   - A: magnetic centre and ends inside the mod, no OS reverse engineering (Recommended).
   - B: raw knob-event probe, one more flash and popup.
   - C: drop the snap feature.

3. **FX SYN page graphics.**
   - A: page-number probe on the page dispatcher `0x4004291C`, shown on TRIG 13 (one flash, one popup) (Recommended).
   - B: drop the SYN graphics.

4. **Release path.** ANSWERED 2026-11-22: public repository. Nobody asks Elektron for permission.
   - B: source plus disclaimer, posted publicly.
   - C: no public post.
   - Note: benleg does not want to ask Elektron for permission.

5. **Packaging.**
   - A: Reddit r/Elektron post plus GitHub source (Recommended).
   - B: pursue an Elekloader port, which needs a Syntakt device and core events in their SDK, plus maintainer acceptance.
   - C: both.

6. **How others make mods.** ANSWERED 2026-11-18: our own small SDK (`tools/modsdk`). Rejected: reviewed list only, and Synfact as the SDK (it cannot carry our DJ filter, SYN page or rate boxes). Move to HISTORY.md at the next tidy.

7. **Shared platform direction** (detail in `SDK_AND_FX3_NOTES.md`).
   - A: our plain list is the one door, a converter reads his `patch.json`, review plus badges (Recommended, not yet answered).
   - B: keep ours and add his features one at a time.
   - C: keep both formats, no merge.

8. **Edits: check as code or data.** Asked 2026-11-21, benleg said do nothing yet. Edits are written as data, with no whole-instruction check.

9. **Slot for fx3-sized mods.** About 0xA000 to 0xF000 plus reserved zeroed RAM. Needs addresses confirmed and a boot-margin test first.

10. **One mod area or two.** His loader and ours each unpack their own block. Compare the loaders before choosing.

Decisions are recorded by appending the answer under the item. Resolved items move to HISTORY.md.
