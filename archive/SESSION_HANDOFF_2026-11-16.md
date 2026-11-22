# Syntakt DelayCtrl: session handoff (2026-11-16)

Read this first, then `HANDOFF.md`, `DISCOVERY_LOG.md` and `FIRMWARE_INDEX.csv` in this folder.

## Current state

- **Build:** `Synthack-OS/out/delay_control_v2o.syx`, SHA-256 `3DF95923DB35B0787119B04253E877F62B7C10EE1B7AB3F87340673AA843E3AC`. Tested on the unit by the user. This is the **DelayCtrl 1.0 Full Package** candidate. It contains DelayCtrl, DJ filter, FX Drive rectifier and SYN page.
- **Known issues to state in release notes:** SYN slots 5-6 curve and SYN slots 1-2 reverb box do not work.
- **Repo:** `Default Project\Synthack-OS`, branch `synfact-split`, based on `86cc1c8`. No changes made on the branch.
- **Synfact work:** source cloned to `Syntakt_Project\synfact-dev` (separate copy, not the original). Tools in `Syntakt_Project\tools`: SGDK 2.11, llvm-mingw, elektron-firmware-tool (built from source). Synfact's setup check passes (`VERIFIED`, core builds). Nothing ported yet.
- **Nothing has been published, uploaded, sent or flashed.**

## Findings

1. **Synfact memory:** ordinary mods share 64 KB at `46000000..46010000`. The core already uses 65,516 of 65,536 bytes (20 free). DelayCtrl's rolling buffer (`RING_LOG 17`, 1 MB) cannot fit there.
2. **Synfact bank route (SMZ4):** a bank may have up to 2 MiB of MAIN allocation (not confirmed that a 1 MB runtime buffer fits). Banks cannot change stock code, so DJ filter, SYN page and the DCTL page patches cannot go in a bank. Possible in a bank via events: DelayCtrl freeze/chop/beat repeat (key, delay, mix events) and the rectifier (mix event, after DelayCtrl).
3. **Shared hooks:** Synfact's core already owns three addresses our mod patches: `0x4000B420` (key), `0x4008F828` (delay input), `0x4008FB04` (mix). Our mod would need to subscribe to events there instead.
4. **Stock hash:** Synfact's 1.41 file is the same as ours (`8e2488…`).
5. **Elektron terms:** Elektron's download page allows personal use only, and forbids modifying or redistributing its material.
6. **OS 1.42:** Elektron's page lists Syntakt OS 1.42 (Oct 1, 2026) as the current update. Our mod targets 1.41 only.

## User decisions

- **Release path:** private only, source with disclaimer, or no public post. Not yet decided.
- **Builder:** private only, public tool with own mods only, or public everything. Not yet decided.
- **Format guideline:** whether to write it (private first). Not yet decided.
- **Elektron:** the user does not want to ask Elektron for permission.
- **Packaging:** the user asked for a "Full Package" release. Synfact cannot take it, so the full package is a SyntHack-style release.

## Rules to keep (from `HANDOFF.md` and `AGENTS.md`)

- Never distribute `.syx`, `.smz4`, `.bin` or built `.elemod` files. No Elektron material in any release.
- Don't change originals in `Default Project`. Work in copies or git commits.
- No flashing, publishing or uploading without explicit approval.
- Verify each build: rebuild, check the SHA changed, run tests, then commit.
- Keep work rounds near $1.5 of model spend.
- Stay on OS 1.41 only.

## Next step (for the new chat)

Decide the release path and builder option. If the user chooses a format guideline, draft it privately from the fields in `mods/delay-control/patch.json`, with hashes instead of Elektron bytes.
