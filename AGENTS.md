# Syntakt firmware project — agent briefing

This is an unofficial custom firmware mod for the Elektron Syntakt on OS 1.41, built on the
community SyntHack-OS framework by Angelo-politek. Elektron forbids redistributing firmware, so
everything ships as source plus patch data that is applied to the user's own stock OS file.
Public repository (decided 2026-11-22). Build from the stock OS file you downloaded yourself.

## Read order

1. This file.
2. STATE.md.
3. OPEN_DECISIONS.md.
4. DISCOVERY_LOG.md.
5. `docs/AGENT-NOTES.md` — code-level rules: verification commands, package rules, browser rules.

HISTORY.md, SDK_AND_FX3_NOTES.md and `archive/` only on demand.

## Hard rules

- No firmware bytes (`.syx`, `.smz4`, `.bin`, `.elemod`, `.elf`, `.img`, `.raw`) tracked by git, in repo files, prompts, logs or fixtures. Use hashes only. `.gitignore` and `tools/hooks/check_no_firmware.py` enforce it; check `git status` before every commit anyway. `synfact-dev/` may hold local copies — it is ignored.
- Originals in `..\Default Project` are read-only.
- Nothing is flashed, published, uploaded, pushed or sent without explicit approval.
- No personal data or absolute paths in committed docs.
- Never claim a check passed that was not run.
- Stay on OS 1.41 only.
- Do not change configured models or providers.

## The work

- **DelayCtrl**: Octatrack-style freeze and beat repeat on MOD B. TRIG 13-16 freeze, chop-lock, dry mute, tempo-synced loop. DCTL setup page with a 9-step rate list (1/4 to 1/64). Freeze, chop, fades and delay silencing confirmed on hardware. The 9-step list (v2o) is not yet confirmed.
- **DJ filter**: replaces LP-Notch in the FX filter TYPE list, shown as "DJ". FREQ 0-63 is lowpass, 64-127 highpass. Confirmed on hardware. The FREQ snap points are parked.
- **Drive rectifier**: FX Drive 5 to 11 blends in a full-wave rectifier, digital tracks only. Confirmed on hardware.
- **FX SYN page**: reverb, send, filter and Drive shortcuts. Slots 5-6 curve and slots 1-2 reverb box do not work. Both SYN graphics items are parked.

## Where things are

| What | Where | Notes |
|---|---|---|
| Mod source | `mods/delay-control\`, `mods/dc-diag\` | `dc.c`, `make_patch.py`, `make_features.py` |
| Mod SDK | `tools/modsdk\` | `init`, `build`, `check`, `fingerprint`, `slots`; guide `docs/SDK.md` |
| Patch format and checks | `tools/sypatch\` | `docs/PATCH-FORMAT.md` |
| Browser builder | `web\` | build with `docs/BUILDING.md` |
| Build and emulator tools | `tools/build\`, `tools/emu\` | |
| m68k toolchain | WSL, `~/tools/m68k/root` | not in the repo |
| Tests | `tests\` | |
| Upstream's own mods | `mods\` (other folders) | Angelo-politek, MIT |
| Verified addresses | `DISCOVERY_LOG.md` | |
| Build hashes | `FIRMWARE_INDEX.csv` | |
| Old worktree history | `..\Default Project\Synthack-OS` | branches `private/*` |
| User manual | `..\Default Project\Syntakt_DelayCtrl_Firmware_Manual.md` | |
| Recovery doc | `RECOVERY.md` | |

## How work is done here

- Keep each work round to roughly $1.5 of model spend.
- Verify every build: rebuild, confirm the `.syx` SHA changed, run the tests, then commit.
- Run emulator tests before asking Isaac to flash.
- Explicit gates stay: flashing, publishing and uploading need approval.
- Keep builder changes and package changes in separate commits.
- User-supplied patch files are trusted-files-only until the boot-margin check exists in the browser path.

## Known traps

- The OS returns pointers in `d0`, not `a0`. Declare such functions as `u32`.
- Mod-area code lives only in the mod area at `0x46000000` and above. The SDK slot map is `tools/modsdk/slots.json`; DelayCtrl owns offsets `0x4000-0x6E00`, i.e. `0x46004000-0x46006E00`.
- The DCTL page reads MOD B ids 54-57 via store `0x400186E8(project)`, `vtbl[40]`.
- The freeze bus is `0x8000DAD0`. The SyntHack docs have the two buses swapped.
- Routing polarity: 0 = through the FX block.
- External-input capture scale is 128/256 (set by ear).
- A failed patch can produce a byte-identical file, so always check the SHA.
- The boot decompression margin must stay above about 4 KB.
- fx3 and DelayCtrl hook the same two spots (`0x4008F828`, `0x4008FB04`); combining them needs a chain, not a rebase.

## Status right now

- Tested baseline: `delay_control_v2o.syx`, SHA-256 `3df95923db35b0787119b04253e877f62b7c10ee1b7ab3f87340673aa843e3ac`. The DCTL 9-step list is not yet confirmed on the unit.
- Known-good fallback: `delay_control_v2l.syx`, SHA-256 `4b2a291ee872f827ba4b7644228c4bb9fb89720ed2ecbeb19a63a82c7fdd82e9`.
- All-features build from round 6 is `25773b…` (first six hex, full value not recorded). Not verified in the emulator or on hardware.
- Details: STATE.md. Open decisions: OPEN_DECISIONS.md.
