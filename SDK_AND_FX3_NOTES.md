# SDK and fx3 notes (2026-11-21)

Why this file exists: a long talk about how other people make mods, what our SDK can and cannot do, and whether one builder can take his mods (Angelo-politek's Synthack-OS) and ours. This is the record, in plain words, so it can be picked up later. Nothing here is flashed, published or committed.

Status words: **Verified** = read or run in this session. **Reported** = a helper said so, I did not re-check. **Unverified** = a guess or an open question.

## 1. What we built this session (all in `builder-web`, uncommitted)

| What | Where | Status |
|---|---|---|
| Plain-language start guide for non-developers | `docs/START-HERE-MODS.md` | Written. Commands checked against `modsdk.py` by reading. Gap: how to find a hook address. |
| Brief for AI helpers writing a mod | `docs/AI-MOD-BRIEF.md` | Written. Includes the "check what is already taken" rule. |
| List of spots already hooked (DelayCtrl and OS packages), 31 entries, addresses and notes only | `tools/modsdk/taken.json` | Written. Advisory. |
| Build warns when a hook or edit lands on a taken spot; `build --strict` turns it into an error | `tools/modsdk/modsdk.py` | Verified by tests, with synthetic data only. No real clash tested. |
| Hook `kind`: `jmp` (default) or `jsr` (call, then carry on) | `modsdk.py` | Verified by tests. |
| `defines` field in `mod.json` (compiler settings) | `modsdk.py` | Tests check the command text only. No real compile with a define. |
| `edits` list in `mod.json` (small fixed changes, written as data) | `modsdk.py` | Verified by tests. Not checked for whole instructions (see decision 8). |
| Gap report: our SDK against fx3 | `docs/FX3-COVERAGE.md` | Reported. Read-only. |

Tests I ran: `python -m pytest tests/test_modsdk.py tests/test_sypatch.py -q` gave **113 passed** (81 SDK, 32 package format).

## 2. Plain-words answers we reached

**Is our SDK like other mod sites?**
Similar in shape to Elekloader (toolkit, browser page, shop of finished files). Elekloader has no Syntakt. I could not load its site, so this is from the project's own notes (HISTORY.md).

**Can people read what a mod does?**
Only from short notes (`web/patches/info.json`) and the source in the mod repo. The public note for DelayCtrl does not say anything about routing FX delay to a repeater. A plain line per behaviour would fix that.

**Why the builder cannot see two mods fighting over the same sound**
It compares addresses and memory ranges only. If two mods hook different spots in the same routine, the check passes. Catching that needs a list of OS routines (start and end), which needs a disassembly of the owner's own OS file. Parked.

**Is his way or ours better?**
Different jobs. His is stronger for big mods (screens, saved settings, 16 KB code). Ours is stronger for review and sharing (every spot listed as data, fingerprints, clash warnings, notes for users). A shared platform needs the plain list so the builder can check it.

**Can one builder take everything people make?**
Most, not all. Mods that end as a plain list of changes can be checked. Mods that hide changes inside their own build scripts can only be marked "trusted only". No builder can prove behaviour without running it: builder checks, then emulator, then hardware.

**Why only 8 KB for trying things?**
Our own choice (`dev` slot, `tools/modsdk/slots.json`, 0x2000 to 0x4000). The 64 KB mod area is shared. Whether 64 KB is a hard Syntakt limit is unknown.

## 3. His mods (Angelo-politek/Synthack-OS, public, MIT licence)

Licence **verified** (LICENSE file fetched): MIT, copyright Angelo-politek and Syntakt+ contributors; grants nothing over Elektron firmware. Copying needs the copyright and licence text kept. Our own `LEGAL.md` was not compared.

Eleven mod folders under `mods/` (**verified**, from the folder page; I said twelve earlier in the chat, that was a miscount): `master-comp`, `readable-values`, `perf-fx`, `fx3`, `vparams`, `dual-mono`, `splash`, `kitstore`, `projstore`, `modarea`, `mod-zero`.
Plus `README.md`. Each has `make_patch.py` and a test. `patch.json` is a list of `{section, addr, len, expect_sha256, hex}`, with `append: true` for mod-area code.

Dependencies from his README: fx3 needs modarea + vparams; master-comp needs modarea + vparams; readable-values, perf-fx, kitstore, projstore need modarea; vparams needs modarea; dual-mono, splash, mod-zero need nothing.

Only fx3 was read in depth (README, `fx3.c` first part, `patch.json` first 680 of 870 lines, and `make_patch.py` through the helper). The other nine mods were not read.

## 4. Clashes found (fx3 against DelayCtrl)

| Address | fx3 | Ours | Status |
|---|---|---|---|
| `0x4008F828` | delay hook (`jsr fx3_del_hook`, len 6) | delay silence (`dc_del_hook`) in `taken.json` | **Verified**: same address in both |
| `0x4008FB04` | master sums hook (len 10) | listed in `taken.json` | **Verified** same address. DelayCtrl's length at this spot not compared. |

So fx3 and DelayCtrl cannot both run as they are.

## 5. Storage (mod area): the open question

| | Ours | His (fx3) |
|---|---|---|
| Stored in firmware file at | `0x40348000`, 64 KB, compressed (shlz) | fx3 code appended at `0x40352000`, length 15706 (**verified** from his patch.json) |
| Runs from RAM | `0x46000000`, 64 KB | `0x444ed8d0` onward (his modarea unpacks into the OS heap) |
| Loader hooks | start of `0x400004B2` (memory-map.md) | **Unverified** |

- The RAM blocks are in different places.
- **Possible overlap, unverified:** his fx3 code at `0x40352000` falls inside our file range `0x40348000` to `0x40358000`. I did not check whether both numbers are in the same address space.
- **Unverified:** whether his loader hooks the same boot spot as ours. If it does, only one loader can run.
- fx3 size: about 15.7 KB of code (verified from the 15706 above). Its links at `0xA000`, delay line `0xE000` to `0xF000`, feedback cell `0xDFFC` are **reported**, not checked.
- The boot decompression margin must stay above about 4 KB (project rule). A bigger mod area needs a margin test first.

## 6. Why fx3 cannot be built with our SDK yet

From `FX3-COVERAGE.md` (reported), updated for what is now built:

1. Hook kind `jsr`: **done** this session.
2. About 90 small edits, pointer writes, parameter records: `edits` **done** this session; records still need generating.
3. Room: only the 8 KB `dev` slot exists. fx3 needs about 16 KB plus a 4 KB zeroed block. No slot registered, no way to reserve zeroed RAM. **Open.**
4. Settings pages with names and icons, and saved settings per pattern: no SDK support. **Open.**
5. Needs `vparams` and `modarea`: **not confirmed** that a vparams package exists in our tree.
6. Inline machine code with data words may fail our whole-instruction check. **Untested.**
7. Warnings: our build fails on any warning; fx3 under our flags **untested**.

Only `hello-sdk` (16 bytes of code) has ever been built with the SDK. DelayCtrl itself is built by its own Python scripts, not by the SDK.

## 7. Open decisions (also in OPEN_DECISIONS.md)

7. **Shared platform direction.** Leaning (not decided): our plain list as the one door, a converter for his `patch.json`, and review plus badges (checked, emulator-tested, hardware-confirmed, trusted-only).
8. **Edits: data or code check.** Asked, benleg said do nothing yet. Edits are data for now.
9. **Slot for fx3-sized mods.** About 0xA000 to 0xF000 plus reserved zeroed RAM. Needs addresses confirmed and a boot-margin test first.
10. **One mod area or two.** Ours and his each load their own. Needs the two loaders compared.

## 8. Next steps if picked up

1. Compare both loaders (boot hook spot, file range). Read-only. Decides whether combining is possible at all.
2. Read the other nine mods' `patch.json` and list every spot against `taken.json`. Read-only.
3. Build one real fx3-sized test mod once a slot is registered.
4. Add plain-language behaviour lines to the DelayCtrl notes in `web/patches/info.json`.
5. Everything stays private: no flashing, publishing or upload without approval.
