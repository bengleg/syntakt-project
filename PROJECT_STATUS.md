# Project status

Last updated: 2026-11-23. Update the row that changed whenever a build, a feature, a hardware result, the repo setup or the web page moves. Put working detail in STATE.md, not here.

## What this is

- Unofficial custom firmware for the Elektron Syntakt on OS 1.41, built on SyntHack-OS by Angelo-politek.
- The repo holds source and patch data only. The browser page is the easy route to a file; building it yourself from your own stock OS 1.41 file is the other.

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
| Repo and live page | Repo `bengleg/syntakt-project` is public, branch `main` (checked with `gh` on 2026-11-23). Page live at `https://bengleg.github.io/syntakt-project/`, deployed from `main` by `.github/workflows/pages.yml` (deploy run 45069258773, succeeded). Live check, headless Chrome, two runs: the v2o box gives `3df959…` and a 2,475,424-byte download, in about 42 s. |
| Page re-deploys itself | The Pages workflow runs on pushes to `main` that touch `web/**` or `tools/sypatch/**`, so a page change publishes with no separate step. It can also be run by hand. |
| Built firmware file | Not distributed, on purpose. No GitHub Release; users build from their own stock file. Owner decision (commit `8ad5c56` and README). |
| Page verification and use | Only headless Chrome, only the owner's stock file; desktop browsers not tested. Known gaps: `favicon.ico` returns 404; a wrong `.syx` still shows Ready until Build is pressed, then it is refused. Nothing to install to use the public page. A local build needs a synfact-dev checkout at `fcbc288` and `node web/build.mjs` (see `docs/BUILDING.md`). |

## Resolved: engine location (2026-11-23)

- The engine is `synfact-dev` (`https://github.com/GSM1980/synfact-dev`), pinned at commit `fcbc288`. `docs/BUILDING.md` and the Pages workflow use the same pin.
- Licence is GPL-3.0-or-later (`js/LICENSE`). `NOTICE.md` and `docs/BUILDING.md` had said GPL-2.0-or-later; corrected.

## Open for the owner

- Confirm the DCTL 9-step rate list on a real unit.
- Packaging (`OPEN_DECISIONS.md` item 5): a live page is a new distribution channel, and the owner has not yet said which option it belongs to. Not decided.

## Where to read next

- Open decisions: `OPEN_DECISIONS.md`.
- Unverified items and known gaps: `STATE.md`, section "Not done".
- Agent rules and read order: `AGENTS.md`.
