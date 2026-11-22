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

Both hashes match `FIRMWARE_INDEX.csv`. The `.syx` files are git-ignored and are not in the repo.

## Public and distribution

| Item | Status |
|---|---|
| GitHub repo | Public: `bengleg/syntakt-project`, branch `main`. Checked with `gh` on 2026-11-23. |
| Built firmware file | Not distributed. Owner decision (see commit `8ad5c56` and README). |
| GitHub Release | None. Users build from their own stock file. |
| Browser builder `web/` | In the repo. Not hosted: no GitHub Pages, no deploy workflow (there is no `.github/` folder). |
| Browser build core | Reproduces the v2o baseline byte for byte, per STATE.md (2026-11-23). Not re-run for this sheet. |
| To open the page | Needs an engine checkout that is not in the repo, plus a Node build step (`node web/build.mjs`). |

## Unresolved: engine location

- `docs/BUILDING.md` says to clone `elekloader`.
- The generated shim `web/src/engine.generated.mjs` (git-ignored) points at `synfact-dev/`, which is also git-ignored.
- Status: **unresolved**. Pick one engine path, then make the shim and the build doc agree.

## Where to read next

- Open decisions: `OPEN_DECISIONS.md`.
- Unverified items and known gaps: `STATE.md`, section "Not done".
- Working history and round notes: `STATE.md`.
- Agent rules and read order: `AGENTS.md`.
