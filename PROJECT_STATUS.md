# Project status

Last updated: 2026-11-23. Update the row that changed whenever a build, a feature, a hardware result, the repo setup or the web page moves. Put working detail in STATE.md, not here.

## What this is

- Unofficial custom firmware for the Elektron Syntakt on OS 1.41, built on SyntHack-OS by Angelo-politek.
- The repo holds source and patch data only. You build the firmware file yourself from your own stock OS 1.41 file.

## Features

| Feature | Confirmed on hardware? | Known gaps |
|---|---|---|
| DelayCtrl: freeze, chop-lock, fades, delay silencing | Yes | none recorded |
| DelayCtrl: DCTL 9-step rate list (1/4 to 1/64) | **No** | not yet confirmed on a unit |
| DJ filter (shown as "DJ" in FX filter TYPE) | Yes | FREQ snap points parked (OPEN_DECISIONS.md item 2) |
| Drive rectifier (FX Drive 5 to 11, digital tracks only) | Yes | none recorded |
| FX SYN page (reverb, send, filter, Drive shortcuts) | No hardware result recorded | slots 5-6 curve and slots 1-2 reverb box do not work; SYN graphics parked (OPEN_DECISIONS.md item 3) |

## Builds

| Build | SHA-256 | Role |
|---|---|---|
| `delay_control_v2o.syx` | `3df95923db35b0787119b04253e877f62b7c10ee1b7ab3f87340673aa843e3ac` | Tested baseline. DCTL 9-step list not yet confirmed on a unit. |
| `delay_control_v2l.syx` | `4b2a291ee872f827ba4b7644228c4bb9fb89720ed2ecbeb19a63a82c7fdd82e9` | Known-good fallback |
| Four-feature DelayCtrl build (freeze, DJ, drive, SYN; baseline box unticked) | `25773b67048b2232e2a73631f4448be4163ef42d82c8611167c08dbc3adc972f` | Built in the browser page on 2026-11-23 (headless Chrome). Not confirmed on a unit or in an emulator. Not yet listed in `FIRMWARE_INDEX.csv`. |

Both hashes in the first two rows match `FIRMWARE_INDEX.csv`. The `.syx` files are git-ignored and are not in the repo.

## Public and distribution

| Item | Status |
|---|---|
| GitHub repo | Public: `bengleg/syntakt-project`, branch `main`. Checked with `gh` on 2026-11-23. |
| Built firmware file | Not distributed. Owner decision (see commit `8ad5c56` and README). |
| GitHub Release | None. Users build from their own stock file. |
| Browser builder `web/` | Hosted on GitHub Pages at `https://bengleg.github.io/syntakt-project/`, deployed from `main` by `.github/workflows/pages.yml` (added 2026-11-23). Live check 2026-11-23 (headless Chrome, live URL): the v2o box gives `3df959…` and a 2,475,424-byte download. Deploy run 45069258773 succeeded. Verified working end to end on 2026-11-23 in headless Chrome, from a local build (desktop browsers not tested). Known gap: a wrong `.syx` still shows Ready until Build is pressed, then it is refused. |
| Browser build core | Verified end to end on 2026-11-23 (headless Chrome). The baseline box reproduced the v2o build byte for byte (`3df959…`); the four-feature build gave `25773b…`. Evidence in QUESTS.md (Q3/Q6 evidence). |
| To open the page | Public page: nothing to install. Local build: needs a synfact-dev checkout at `fcbc288` and `node web/build.mjs` (see `docs/BUILDING.md`). |

## Resolved: engine location (2026-11-23)

- The engine is `synfact-dev` (`https://github.com/GSM1980/synfact-dev`), pinned at commit `fcbc288`.
- `docs/BUILDING.md` and the Pages workflow both use that pin.
- Licence corrected to GPL-3.0-or-later (`js/LICENSE`). `NOTICE.md` and `docs/BUILDING.md` had said GPL-2.0-or-later.

## Where to read next

- Open decisions: `OPEN_DECISIONS.md`.
- Unverified items and known gaps: `STATE.md`, section "Not done".
- Working history and round notes: `STATE.md`.
- Agent rules and read order: `AGENTS.md`.
