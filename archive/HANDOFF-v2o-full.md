# Archive: full handoff as written for v2o (superseded by ..\AGENTS.md)
# Syntakt custom firmware: handoff for a new chat

Paste this file (or point the new chat at it) to continue. Current version: **v2o**, OS 1.41 only.

## 1. Goal

Custom firmware mod for the Elektron Syntakt on OS 1.41, built on the community SyntHack-OS repo. Features:

1. **DelayCtrl**: Octatrack-style freeze / beat repeat on MOD B. TRIG 13-16 freeze, chop-lock, dry mute, tempo-synced loop. Selectable rates on the DCTL setup page (9 steps: 1/4, 1/6, 1/8, 1/12, 1/16, 1/24, 1/32, 1/48, 1/64).
2. **DJ filter**: replaces LP-Notch in the FX filter TYPE list. FREQ 0-63 lowpass, 64-127 highpass, shown as "DJ".
3. **Drive rectifier**: FX Drive 5→11 blends in a full-wave rectifier. Digital tracks only.
4. **FX SYN page**: reverb / send / filter / Drive shortcuts. Slots 5-6 curve and slots 1-2 reverb box **not working** (see parked items).

## 2. Current state

- **Good build for the user:** `out/delay_control_v2o.syx`, SHA-256 `3df95923db35b0787119b04253e877f62b7c10ee1b7ab3f87340673aa843e3ac`. Last commit `86cc1c8`. The user has tested v2l and v2n (DCTL boxes OK). v2o (9-step list) is built but **not yet confirmed on the unit**.
- **Known-good older build:** `out/delay_control_v2l.syx` (SHA `4b2a291e…dc82e9`).
- **Tests:** `tests/test_delay_control.py`: 41 passed, 3 skipped.
- **Git:** clean at `86cc1c8`.
- **Unpublished:** nothing. No firmware has been posted or uploaded.

## 3. Parked (tried twice each, failed)

- **DJ FREQ snap points (FUNC + turn):** the Syntakt's FREQ has no snap list; FUNC + turn jumps to the end. The TUNE knob does have 0/25/50/75/100% snaps, but the descriptors don't carry them over. Two probes (hooks at `0x4003B4D2` and the setter `0x4000DA32`) logged nothing for knob E. Options: (a) a magnetic centre/ends inside the mod, or (b) a raw knob-event probe. User hasn't picked yet.
- **SYN slots 5-6 curve:** routing "page 32" to the filter draw routine did nothing; the FX SYN page number was a wrong deduction. Next step would be a page-number probe (log which numbers pass through the page dispatcher `0x4004291C`), shown on TRIG 13.
- **SYN slots 1-2 reverb box:** needs a custom routine combining the REV box code and the FLTR curve. Bigger job.

## 4. Key facts and gotchas

- Build command (WSL, Ubuntu): see `Synthack-OS` build section; always check the `.syx` SHA-256 changed after a rebuild (a failed patch once produced a byte-identical file).
- Patch builder: `mods/delay-control/make_patch.py`. Hooks are listed as `fixed(addr, bytes, what, old_bytes)`. A `SNAP_PROBE` / `DC_DEBUG` env flag enables probe builds (`DC_CFLAGS=-DSNAP_PROBE`).
- OS returns pointers in `d0`, not `a0`. Declare such functions as `u32`.
- Only mod-area code: DC code lives at `0x46004000`.
- The DCTL page reads MOD B values (ids 54-57) on every key event through store `0x400186E8(project)`, vtbl[40].
- Freeze bus: `0x8000DAD0` (the FX-block-routed digital bus; SyntHack docs have the two buses swapped).
- Routing polarity: 0 = through the FX block.
- External-input capture scale 128/256 (user-calibrated by ear).
- Old project values for DCTL are on the old 0..0x1000 scale. Boxes can read odd values until reset.
- Legal: Elektron's EULA forbids modifying and sharing. **Never distribute `.syx` files.** Share source, the manual and build instructions only.

## 5. Where things are

| What | Where |
|---|---|
| Project repo | ``..\Default Project\Synthack-OS` (git) |
| Mod source | `…\Synthack-OS\mods\delay-control\dc.c`, `make_patch.py` |
| Tests | `…\Synthack-OS\tests\test_delay_control.py` |
| Stock OS | `…\Synthack-OS\firmware\Syntakt_OS1.41.syx` (Elektron code, keep local) |
| Spec + backlog | ``..\Default Project\syntakt_mod_spec.md` |
| User manual (v2o) | ``..\Default Project\Syntakt_DelayCtrl_Firmware_Manual.md` |
| RE notes | `…\Synthack-OS\work\NOTES_trigmod.md` (all found addresses) |
| Discovery log | ``.\DISCOVERY_LOG.md` |
| Firmware index (hashes) | ``.\FIRMWARE_INDEX.csv` |
| Commit log | ``.\GIT_LOG.txt` |
| Mac transfer kit | ``..\Syntakt_Mac_Transfer` (+ `MAC_SETUP.md`) |
| Recovery | `…\Synthack-OS\RECOVERY.md` |
| Conversation export | `…\Syntakt_Mac_Transfer\session_ses_e687f9ee9ffexMqrT8gc2oKAeh.json` |

**Do not copy:** `MACBOOK_ACCESS.md` (holds a plaintext password; rotate it), `work/os141/`, `unpacked/`, `third_party/`.

## 6. Packaging and distribution: decision needed

The user wants to package the mod for **Elekloader** (`https://elekloader.github.io/shop/#library`). Findings from reading the site and `docs/SHOP.md`:

- Elekloader is a shop of `.elemod` files built with **its own SDK and core**. It does not host firmware and builds run in the user's browser.
- **Syntakt is not a supported device** on Elekloader. Its devices are Digitakt, Digitone, Octatrack, Analog Rytm MKII, Analog Four MKII and Models (plus Digitakt II / Digitone II as early cores).
- Our mod uses SyntHack's `patch.json` format, not `.elemod`. A listing needs a **port**: a Syntakt device entry and core events in Elekloader's SDK, which is outside this project and only accepted via their repo.
- Submission requires the author to declare that they wrote the mod and that the files hold no Elektron firmware. The mod code itself meets that; the device support does not exist.

**Recommended next step:** keep distributing as source plus the manual (the Reddit route), and ask Elekloader maintainers whether a Syntakt device would be accepted before any port. Don't submit a `.syx` anywhere.

## 7. Open questions for the user

1. DJ snap: magnetic centre/ends (a), or a raw knob-event probe (b)?
2. Go ahead with the SYN page-number probe (one flash, one popup), or drop the SYN graphics?
3. Packaging: Reddit only, or pursue Elekloader (requires a port and maintainer acceptance)?
4. Reddit post: still waiting on how to release without upsetting Elektron.

## 8. Rules for the next chat

- Keep each work round to roughly $1.5 of model spend.
- Don't change the originals in `Default Project`; work in copies or git commits.
- Don't flash hardware, publish, or upload anything without explicit approval.
- Verify every build: rebuild, check SHA changed, run tests, then commit.
- Use the emulator tests before asking the user to flash.
- Start requested work automatically and keep going until it is reviewable (global rule in `~/.config/opencode/AGENTS.md`, "Work rule"). Routine "shall I start?" checkpoints are removed. Explicit gates stay: format approval, flashing, publishing, uploading, and anything that spends beyond the round budget.
- Subagents use only Claude Haiku 5.5 (`venice/claude-haiku-5-5`). Keep configured models and providers unchanged.
- Current track is private only. Nothing is shared until the release path is decided.

## 9. Next chat: builder web, split DelayCtrl into 4 features

State: branch `private/webbuilder-r5` in `Syntakt_Project\builder-web` (last commit `3d57061`). The browser page (`web/`) builds the DelayCtrl v2o `.syx` in memory and matches the tested hash. Page is Geist dark. Do not show block counts to end users.

Block map of the legacy DelayCtrl patch (`Default Project\Synthack-OS\mods\delay-control\patch.json`, 30 entries, 1 append):
- Freeze / DelayCtrl core: hooks 2-5, 11-13 (keys, event, delay silence, CV mute, mix); RETRIG rate boxes 14-25; DCTL page names 26-30.
- DJ filter: hooks 6-9 (`dc_flt_hook`, `dc_s_dj`, `dc_fdraw_hook`, `dc_tgfx`).
- FX SYN page: hook 10 only (`dc_syn_stub`).
- Drive rectifier: in v2o, inside the code blob, not a separate hook. `rectify()` in `mods/delay-control/dc.c` (around line 231), called at line 353; reads the FX Drive value at 0x800028F0. Reach it by the mix hook (block 13) or by its own feature flag.
- Code blob (3,508 B, area, offset 0x4000): one compiled blob shared by all features. Shared hooks: `dc_mix_hook`, `dc_mute_hook`.

Open decisions (not yet answered by benleg):
1. Split method: recompile `dc.c` per feature with flags (each feature its own area offset), or keep one blob. Recompiling gives a new build; the all-features build is no longer byte-identical to v2o and needs a unit test.
2. Rectifier: confirmed in v2o (see block map above). Decide whether it is its own feature flag in the split.
3. User uploads: trusted files only until the boot-margin check (`tools/build/bootcheck.py`) exists in the browser path.

Plan once decided: feature patch files under `web/patches/`, one per feature; verify each alone and all four together against a fresh build; keep v2o as the baseline. Use the WSL m68k toolchain for `dc.c` (see `mods/delay-control/make_patch.py`).

Rules still apply: no `.syx`/`.elemod` files in the repo, no firmware bytes in repo files or prompts, nothing flashed, published or uploaded without approval, Default Project originals untouched.

### Round 6 status (branch `private/webbuilder-r6`, worktree `builder-web`, not pushed)

- Split done: `web/patches/dc-{runtime,core,dj,drive,syn}.sypatch.json` + `modarea` + `manifest.json`, generated by `mods/delay-control/make_features.py`. Fixed header at mod area offsets 0x4000 (core entry), 0x4004 (drive entry), 0x4008 (KeyboardView). Slots: runtime 0x4010, core 0x4800, DJ 0x6000, drive 0x6800, SYN 0x6C00.
- Verified: fresh v2o build equals the supplied v2o (`3df959…`). All-four build (`25773b…`) does not match v2o, as expected from the relinked code. Replace sites: same 31 addresses; 24 change bytes (jump targets and pointers). Behaviour in emulator/hardware NOT verified.
- Merge/validation: `tools/sypatch/merge.mjs`; page loads the manifest, imports files as data, validates in the worker.
- Patch standard: `docs/PATCH-FORMAT.md`, `docs/AUTHORING.md`, `AGENTS.md`, `examples/` (synthetic).
- Open: `tools/hooks/check_no_firmware.py` does not block `.smz4`/`.elemod`; `README.md` line 56 says "blocks firmware files" (pre-existing, user-facing); `test_splash_mod` needs `pyfiglet` (environment); `test_delay_control.py` skips here (no firmware file in the worktree).
