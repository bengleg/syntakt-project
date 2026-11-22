# State

Last updated: 2026-11-21

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
- The all-four build is `25773b…` (first six hex; the full SHA was never written down).
- 31 replace sites, 24 changed bytes.
- Behaviour is NOT verified in the emulator or on hardware.

## Mod SDK and picker (2026-11-18, all uncommitted in builder-web)

Decision made: other people make mods with our own small SDK (see OPEN_DECISIONS.md, item 6).

- SDK: `tools/modsdk/modsdk.py` with `init`, `build`, `check`, `fingerprint`, `slots`. Guide: `docs/SDK.md`. Example: `mods/hello-sdk/`. Slots: `tools/modsdk/slots.json` (DelayCtrl reserved 0x4000-0x6E00, dev 0x2000-0x4000).
- Picker: `tools/sypatch/analyze.mjs` finds every conflict (same OS bytes, same patch memory, declared, shared claim), sizes, and a load band. The page shows it under each mod and in a "Your selection" panel; Build is disabled on a conflict. Owner notes: `web/patches/info.json`.
- Page: the field-by-field patch text and the starting-file button were removed. Section 2 now points to docs/SDK.md. `?v=5` stamp in index.html: bump after any change under `web/`, and rebuild with `node web/build.mjs` (needs ELEKLOADER_JS and ESBUILD_JS on the command line only).
- Fixed this session: the SDK and `check_patch.py` refused a `mod.json` saved with a byte-order mark (Notepad, old PowerShell). Both now read it.
- Tests that passed this session: `test_modsdk.py` + `test_sypatch.py` 56, `sypatch_analyze` 13, `sypatch_packages` 19, `engine_bridge` synthetic 12 (3 skipped, need local files).

### Not checked yet

- Done 2026-11-18 (later session): picker looked at in a browser, clash test passed (conflicts shown in plain words, no console errors). Build-off on conflict confirmed in code only (`app.mjs` line ~168), not with a real OS file.
- Done: `docs/SDK.md` compared with `modsdk.py` and fixed; three crash bugs fixed; SDK `mod.json` now carries `info`. Page cache stamp is `?v=7`; several mod files can be added at once; a line under Build says why it is off. Tests: test_modsdk + test_sypatch 81, sypatch_analyze 14. Still uncommitted.
- `cost` in `info` stays `null` or `{instructionsPerBlock, measured}` (not a bare number). Decide if a bare number should be accepted.
- Claim prefixes (`ui:`, `param:`, `audio:`) are enforced by the SDK only, not by `check_patch.py`.
- `web/build.mjs` was run with an esbuild copy from Temp; no permanent setup.
- `fingerprint` was only tested on its refusal path (needs the owner's OS file).
- CPU load is "not measured" for every mod. Thresholds 1000 and 3000 are guesses. `tests/test_delay_control.py::test_cost_per_block` could measure DelayCtrl (needs the OS file; ask first).
- Overlap detection only finds shared bytes. Two mods that clash in what they do, not in bytes, need a declared `conflicts` or a shared claim.

## SDK extensions and fx3 study (2026-11-21, uncommitted in builder-web)

Full record: `SDK_AND_FX3_NOTES.md`. Read that first for anything about third-party mods, clashes or storage.

- New: `docs/START-HERE-MODS.md`, `docs/AI-MOD-BRIEF.md`, `docs/FX3-COVERAGE.md`, `tools/modsdk/taken.json` (31 taken spots).
- SDK: `build` warns on a taken spot, `--strict` makes it an error; hooks take `kind` (`jmp` or `jsr`); `mod.json` takes `defines` and `edits`.
- Tests I ran: `test_modsdk.py` + `test_sypatch.py` 113 passed.
- Not tested: a real clash, a real compile with a define, any fx3-sized build, the emulator, hardware.
- Found: fx3 and DelayCtrl hook the same spots (`0x4008F828`, `0x4008FB04`). Storage layouts differ and may overlap in the file; not yet compared.

## Test status

- Last recorded: `tests\test_delay_control.py` 41 passed, 3 skipped (2026-11-03). Re-run before relying on it.
- `test_splash_mod` needs `pyfiglet`.
- `test_delay_control.py` skips in a worktree with no firmware file.
- `tools/hooks/check_no_firmware.py` blocked only some firmware extensions until commit a63ad93, which added `.smz4` and `.elemod`.

## Not done

- The boot-margin check `tools\build\bootcheck.py` exists in Python only. The browser path has no equivalent, so user-added patch files stay trusted-files-only.
- Nothing is verified for the split-feature builds. Each feature alone and all four together still need an emulator run.
- The SYN page-number probe has not been run, so the two parked SYN graphics items are still open.
- Nothing has been flashed, published, pushed or uploaded. Release path and packaging are undecided (see OPEN_DECISIONS.md items 4 and 5).

## Website polish (2026-11-18)
Builder page redesigned (steps bar, select all/none, drop zones, remove mod, copy SHA, flash note). Cache stamp ?v=8. Uncommitted in builder-web. Evidence and gaps in QUESTS.md.
