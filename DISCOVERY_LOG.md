# Discovery log (Syntakt OS 1.41)

Full address notes: `Synthack-OS\work\NOTES_trigmod.md`. This file is the record of what is known to work. Failed and parked attempts are in HISTORY.md.

## Working

| Finding | Detail |
|---|---|
| Stock OS 1.41 hash | SHA-256 `8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e` |
| Key handling TRIG 13-16 | consumeKeyEvent `0x4002E850`, keys hook `0x4002EA92`, dispatcher `0x4000B420` |
| Modifier selection (MOD B active) | `0x40015AF6(STORE(PAT_ENTRY(project)))`, project = `*(KeyboardView+148)` |
| FX-block digital bus (freeze source) | `0x8000DAD0` (SyntHack docs have the two buses swapped) |
| Delay call | `0x4008F828` (in `0x8000DBD0`, out `0x8000DCD0`), silenced by hook |
| Analog mute mask | `0x80003150`, read at `0x400903F8` |
| External-in CVs | `0x400908FC` (`hw+8`, `hw+18`) |
| FX filter CVs | `0x40095FA6` (DJ type hook) |
| Filter type name table | `0x401D4710` (entry 6 = LP-Notch → "DJ") |
| TYPE icon invoker | `0x4018C794` → `dc_tgfx` (draws "DJ" text) |
| FLTR curve routine | `0x40042646` (DJ flips LP2/HP2 in drawing) |
| SYN page slot init | `0x40195156` (slots 1-7 replaced) |
| DCTL setup page | MOD B descriptors ids 54-57 at `0x4022D59C + 52*id`; RETRIG formatter proto `0x41B9DF00`, box graphic proto `0x41B9D930` |
| Parameter store | `0x400186E8(project)`, `vtbl[40](store, id)` returns the value (value >> 8 = step) |
| Tempo | `0x402D7010` (BPM×120) |
| Engine copy | tracks base `0x800021B0` (+142 per track, ROUT +126); DRIVE `0x800028F0`; TYPE `0x800028CC`; FREQ `0x800028CE`; RESO `0x800028D0`; FPAN `0x800028E0` |
| Parameter descriptors | 52-byte records, id 133 = FREQ, id 158 = TUNE (has snaps), id 34 = Portamento |
| OS return convention | pointers returned in `d0` |
| Boot decompression margin | must stay above ~4 KB; zero padding can break boot |

## Third-party mods (Angelo-politek/Synthack-OS, MIT) — added 2026-11-21

Detail and open questions: `SDK_AND_FX3_NOTES.md`.

| Finding | Detail | Status |
|---|---|---|
| fx3 hook on the delay call | `0x4008F828`, same spot as DelayCtrl's delay hook | verified (fx3 patch list and `taken.json`) |
| fx3 hook on the master sums | `0x4008FB04`, also in `taken.json` | verified address; DelayCtrl length not compared |
| fx3 appended code | 15706 bytes at `0x40352000`, RAM `0x444ed8d0` | verified from his patch list |
| Our mod area | file `0x40348000`, RAM `0x46000000`, 64 KB, loader at `0x400004B2` | from `docs/memory-map.md` |
| Possible file overlap | fx3 code at `0x40352000` is inside `0x40348000`–`0x40358000` | unverified: same address space not confirmed |
| His loader boot hook | not read | unverified |

## Credits to record

- SyntHack-OS: karigardarsson, Angelo-politek (mod framework, toolchain).
- elektron-firmware-tool: mischa85 / Marcel Bierling (MIT).
- Syntakt Firmware Workbench: Bezronczek (referenced by the MAX post; check before crediting specific work).
- Unicorn (emulator, GPL-2.0, installed separately).

Failed or parked attempts, testing results and distribution research: see HISTORY.md.
