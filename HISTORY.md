# History

Moved out of DISCOVERY_LOG.md and the v2o handoff on 2026-11-18. Nothing removed.

## Parked and failed attempts

| Attempt | Result | Lesson |
|---|---|---|
| Hook knob-turn function `0x4003B4D2` for FREQ snap probe | No log; all zeros | It's the encoder press/touch handler, not the value path |
| Hook setter `0x4000DA32` for FREQ snap probe (probe 4) | No log for knob E | FREQ isn't written through this setter for encoder turns |
| DJ FREQ snap via FUNC + turn | FREQ has no snap list; FUNC + turn jumps to the end | Matching TUNE's snap points needs a different mechanism; parked |
| SYN slots 5-6 curve by routing "page 32" to filter draw | No change on SYN | FX SYN page number was a wrong deduction; needs a page-number probe |
| SYN dispatcher hook `0x40042938` | No effect | Removed in v2n |
| DCTL boxes with old 0..0x1000 range | Old saved values read as odd (1/80) | Expected; set the four boxes once after flashing |
| Plain turn in DJ with v2g CV-based level scaling | Far too quiet | Reverted; flags `CV_LEVELS`, `DJ_BYPASS` kept at 0 |

The DJ FREQ snap and the SYN slots 5-6 curve were recorded in the v2o handoff as tried twice each. The other rows are single attempts.

## SYN graphics blockers

- **DJ FREQ snap points (FUNC + turn):** the Syntakt's FREQ has no snap list; FUNC + turn jumps to the end. The TUNE knob does have 0/25/50/75/100% snaps, but the descriptors don't carry them over. Two probes (hooks at `0x4003B4D2` and the setter `0x4000DA32`) logged nothing for knob E. Options: (a) a magnetic centre/ends inside the mod, or (b) a raw knob-event probe.
- **SYN slots 5-6 curve:** routing "page 32" to the filter draw routine did nothing; the FX SYN page number was a wrong deduction. Next step would be a page-number probe (log which numbers pass through the page dispatcher `0x4004291C`), shown on TRIG 13.
- **SYN slots 1-2 reverb box:** needs a custom routine combining the REV box code and the FLTR curve. Bigger job.

## Testing results from the user

- DelayCtrl freeze, chop, fades, delay silenced: working on hardware.
- FX Drive rectifier: "works perfectly".
- DJ filter and "DJ" TYPE text: working.
- External-in level scale 128/256: matches live level by ear.
- DCTL boxes (v2n): work; defaults show odd values until set.
- DCTL 9-step list (v2o): not yet confirmed by the user at time of handoff.
- SYN curve (v2m): no change on SYN page.
- Snap probes 3-4: all zeros.

## Distribution research

| Source | Finding |
|---|---|
| Elekloader (`elekloader.github.io/shop`) | Shop of `.elemod` built with its own SDK/core. Devices: Digitakt, Digitone, Octatrack, Rytm MKII, Analog Four MKII, Models. **No Syntakt.** Submission needs the author's declaration of no Elektron firmware and a permissive licence. |
| Reddit r/Elektron "Syntakt MAX 1.0" post | Another community build on SyntHack-OS; its author credits Angelo-politek (SyntHack) and Bezronczek (Syntakt Firmware Workbench). Release is a Windows builder that generates the `.syx` from the user's own OS file. Read through the in-app browser (plain fetch was blocked with 403). |

## Session log

### 2026-11-03

v2o built.

### 2026-11-16

Synfact evaluation. Decisions still open: release path, builder option, format guideline, packaging.

### 2026-11-18

Docs reorganised: HANDOFF.md turned into a pointer, AGENTS.md, STATE.md, OPEN_DECISIONS.md, README.md and HISTORY.md created, archive\ created. Nothing else changed.
