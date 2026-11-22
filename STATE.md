# State

Last updated: 2026-11-23

## Builds

| Build | SHA-256 | Status |
|---|---|---|
| `delay_control_v2o.syx` | `3df95923db35b0787119b04253e877f62b7c10ee1b7ab3f87340673aa843e3ac` | tested baseline, DCTL 9-step list not yet confirmed on the unit |
| `delay_control_v2l.syx` | `4b2a291ee872f827ba4b7644228c4bb9fb89720ed2ecbeb19a63a82c7fdd82e9` | known-good fallback |

## Branches

| Worktree | Branch | Head | State |
|---|---|---|---|
| builder-web | `private/webbuilder-r6` | a63ad93 | clean |
| builder-r1 | `private/patch-format-r1` | a75a38c | clean |
| Synthack-OS | `synfact-split` | 86cc1c8 | clean |
| synfact-dev | `main` | fcbc288 | clean and level with origin |

## Round 6

- Round 6 split DelayCtrl into `web\patches\dc-{runtime,core,dj,drive,syn}.sypatch.json`, plus `modarea` and `manifest.json`.
- Fixed header at mod area offsets 0x4000 (core entry), 0x4004 (drive entry) and 0x4008 (KeyboardView).
- Feature slots: runtime 0x4010, core 0x4800, DJ 0x6000, drive 0x6800, SYN 0x6C00.
- A fresh v2o build reproduces `3df959…`.
- The all-four build is `25773b67048b2232e2a73631f4448be4163ef42d82c8611167c08dbc3adc972f`. The full SHA was first written down on 2026-11-23: the browser page built it from the four features with the baseline box unticked (see QUESTS.md, Q3/Q6 evidence 2026-11-23). Not verified in an emulator or on hardware.
- 31 replace sites, 24 changed bytes.
- Behaviour is NOT verified in the emulator or on hardware.

## Mod SDK and picker (2026-11-18, uncommitted in builder-web when written; since committed in the repository import, 929f05f)

Decision made: other people make mods with our own small SDK (see OPEN_DECISIONS.md, item 6).

- SDK: `tools/modsdk/modsdk.py` with `init`, `build`, `check`, `fingerprint`, `slots`. Guide: `docs/SDK.md`. Example: `mods/hello-sdk/`. Slots: `tools/modsdk/slots.json` (DelayCtrl reserved 0x4000-0x6E00, dev 0x2000-0x4000).
- Picker: `tools/sypatch/analyze.mjs` finds every conflict (same OS bytes, same patch memory, declared, shared claim), sizes, and a load band. The page shows it under each mod and in a "Your selection" panel; Build is disabled on a conflict. Owner notes: `web/patches/info.json`.
- Page: the field-by-field patch text and the starting-file button were removed. Section 2 now points to docs/SDK.md. `?v=5` stamp in index.html: bump after any change under `web/`, and rebuild with `node web/build.mjs` (needs ELEKLOADER_JS and ESBUILD_JS on the command line only).
- Fixed this session: the SDK and `check_patch.py` refused a `mod.json` saved with a byte-order mark (Notepad, old PowerShell). Both now read it.
- Tests that passed this session: `test_modsdk.py` + `test_sypatch.py` 56, `sypatch_analyze` 13, `sypatch_packages` 19, `engine_bridge` synthetic 12 (3 skipped, need local files).

### Not checked yet

- Done 2026-11-18 (later session): picker looked at in a browser, clash test passed (conflicts shown in plain words, no console errors). Build-off on conflict confirmed in code only (`app.mjs` line ~168), not with a real OS file.
- Done: `docs/SDK.md` compared with `modsdk.py` and fixed; three crash bugs fixed; SDK `mod.json` now carries `info`. Page cache stamp is `?v=7`; several mod files can be added at once; a line under Build says why it is off. Tests: test_modsdk + test_sypatch 81, sypatch_analyze 14. Was uncommitted when written; since committed in the repository import (929f05f).
- `cost` in `info` stays `null` or `{instructionsPerBlock, measured}` (not a bare number). Decide if a bare number should be accepted.
- Claim prefixes (`ui:`, `param:`, `audio:`) are enforced by the SDK only, not by `check_patch.py`.
- `web/build.mjs` was run with an esbuild copy from Temp; no permanent setup.
- `fingerprint` was only tested on its refusal path (needs the owner's OS file).
- CPU load is "not measured" for every mod. Thresholds 1000 and 3000 are guesses. `tests/test_delay_control.py::test_cost_per_block` could measure DelayCtrl (needs the OS file; ask first).
- Overlap detection only finds shared bytes. Two mods that clash in what they do, not in bytes, need a declared `conflicts` or a shared claim.

## SDK extensions and fx3 study (2026-11-21, uncommitted in builder-web when written; since committed in the repository import, 929f05f)

Full record: `SDK_AND_FX3_NOTES.md`. Read that first for anything about third-party mods, clashes or storage.

- New: `docs/START-HERE-MODS.md`, `docs/AI-MOD-BRIEF.md`, `docs/FX3-COVERAGE.md`, `tools/modsdk/taken.json` (31 taken spots).
- SDK: `build` warns on a taken spot, `--strict` makes it an error; hooks take `kind` (`jmp` or `jsr`); `mod.json` takes `defines` and `edits`.
- Tests I ran: `test_modsdk.py` + `test_sypatch.py` 113 passed.
- Not tested: a real clash, a real compile with a define, any fx3-sized build, the emulator, hardware.
- Found: fx3 and DelayCtrl hook the same spots (`0x4008F828`, `0x4008FB04`). Storage layouts differ and may overlap in the file; not yet compared.

## Boot-margin check in the browser (2026-11-23)

- New: `tools/sypatch/bootmargin.mjs` (the check), with `depackMargin` in `tools/sypatch/aplib.mjs`.
- Wired through `tools/sypatch/bridge.mjs`, `web/src/core.mjs`, `web/src/worker.mjs`, `web/app.mjs` and `web/index.html`. The result line reads "Boot room: N bytes", and a file below 4096 is refused.
- New test: `tests/sypatch_bootmargin.test.mjs` (synthetic; the real-file part skips without `SYNTAKT_STOCK` + `ELEKLOADER_JS`). `tests/web_core.test.mjs` now also asserts that the build reports a margin.
- Page cache stamp is `v=10`.
- Evidence: the JS port and `tools/build/bootcheck.py` both give 99 938 B on stock 1.41 (decoded section 3 = 3 438 480 B). The page core's DelayCtrl build still reproduces the tested v2o `.syx` byte for byte, with a boot room of 19 743 B.
- Was uncommitted in the working tree when written; since committed in the repository import (929f05f).

## Test status

- Last recorded: `tests\test_delay_control.py` 41 passed, 3 skipped (2026-11-03). Re-run before relying on it.
- `test_splash_mod` needs `pyfiglet`.
- `test_delay_control.py` skips in a worktree with no firmware file.
- `tools/hooks/check_no_firmware.py` blocked only some firmware extensions until commit a63ad93, which added `.smz4` and `.elemod`.

## Not done

- A build that adds code past the stock image end (a section-3 append) is still not built by the page. Only the page's own build path is covered by the margin check.
- Nothing is verified for the split-feature builds. Each feature alone and all four together still need an emulator run.
- The SYN page-number probe has not been run, so the two parked SYN graphics items are still open.
- Nothing has been flashed. The repository is public and pushed (`bengleg/syntakt-project`, branch `main`). The built `.syx` is deliberately not distributed (owner decision). OPEN_DECISIONS.md item 4 is answered (public repo, 2026-11-22). Packaging is still open (OPEN_DECISIONS.md item 5). This includes the boot-margin change of 2026-11-23.

## Website polish (2026-11-18)
Builder page redesigned (steps bar, select all/none, drop zones, remove mod, copy SHA, flash note). Cache stamp ?v=8. Was uncommitted in builder-web when written; since committed in the repository import (929f05f). Evidence and gaps in QUESTS.md.
