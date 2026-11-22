# Provenance and attribution

Read with [LEGAL.md](LEGAL.md). This file records where the material came from; it does not extend
any licence.

## This repository

The tree was imported on 2026-11-22 from the working branch `private/webbuilder-r6` in
`..\Default Project\Synthack-OS` (commit `a63ad93`, plus uncommitted SDK work that existed nowhere
else). The pre-import history is still in that repository; the branches are `private/webbuilder-r6`
and `private/patch-format-r1`, and `GIT_LOG.txt` records the tips at import time. Git history here
starts at the import commit. When the repository was published on 2026-11-23, its three commits were
re-authored as `bengleg`; their messages and contents are unchanged, and the LICENSE line for this
repository's own code names `bengleg` alongside the upstream line.

## Upstream: SyntHack-OS

- **Author:** Angelo-politek, with contributors.
- **Source:** https://github.com/Angelo-politek/Synthack-OS
- **Licence:** MIT (`LICENSE`, "Angelo-politek and Syntakt+ contributors").
- **Carried over substantially:** `mods/` (except `delay-control`, `dc-diag`, `hello-sdk`), `tools/build/`,
  `tools/emu/`, `tools/unpack/`, `tools/splash/`, `docs/memory-map.md`, `docs/audio-path.md`,
  `docs/ui-parameters.md`, `docs/emulation.md`, `docs/firmware-format.md`, `docs/modding-guide.md`,
  `RECOVERY.md`, `CONTRIBUTING.md`, `tools/hooks/`, and the `.gitignore` base.

Modifications by this project: the mod SDK, the `.sypatch` format and its tools, the web builder, the
DelayCtrl and dc-diag mods, the docs listed as new below, and the `.gitignore` additions.

## New to this repository

`README.md`, `AGENTS.md`, `NOTICE.md`, `STATE.md`, `OPEN_DECISIONS.md`, `DISCOVERY_LOG.md`,
`HISTORY.md`, `QUESTS.md`, `SDK_AND_FX3_NOTES.md`, `FIRMWARE_INDEX.csv`, `docs/SDK.md`,
`docs/START-HERE-MODS.md`, `docs/AI-MOD-BRIEF.md`, `docs/AUTHORING.md`, `docs/PATCH-FORMAT.md`,
`docs/FX3-COVERAGE.md`, `docs/BUILDING.md`, `docs/AGENT-NOTES.md`, `tools/modsdk/`, `tools/sypatch/`,
`web/`, `examples/`, `mods/delay-control/`, `mods/dc-diag/`, `mods/hello-sdk/`, and the tests for them.

## Not included, used as external programs

| Tool | Licence | How |
|---|---|---|
| [elektron-firmware-tool](https://github.com/mischa85/elektron-firmware-tool) | MIT | `tools/eft-src/` and `tools/eft-build/`, or `tools/elektron-firmware-tool.exe`; or cloned to `third_party/` by `setup_eft.sh`. All git-ignored |
| [synfact-dev](https://github.com/GSM1980/synfact-dev) `js/src`, pinned at commit `fcbc288` | GPL-3.0-or-later | local path via `ELEKLOADER_JS`; built into `web/dist/` (git-ignored here) and published on the site `https://bengleg.github.io/syntakt-project/` |
| [Unicorn](https://github.com/unicorn-engine/unicorn) | GPL-2.0 | Python package, installed separately |
| esbuild | MIT | npm package or local file via `ESBUILD_JS` |
| m68k GNU toolchain | GPL-3.0 | system packages, under WSL/Linux |

The GPL engine source is not committed to this repository, and neither is the bundle built from it
(`web/dist/` is git-ignored). The bundle is published on the site `https://bengleg.github.io/syntakt-project/`
by the Pages workflow, so the site carries GPL-3.0-or-later engine code. The source is linked in the table
above at the pinned commit `fcbc288`. An earlier version of this note named elekloader, gave the licence as
GPL-2.0-or-later, and said no GPL obligation arose; that was wrong about the licence and about publishing.

## Local toolchains kept out of git

These sit in `tools/` on disk but are git-ignored (they are hundreds of megabytes, and one archive
is over GitHub's 100 MB file limit). They are third-party and are **not** covered by this
repository's MIT licence.

| Path | Contents | Licence found |
|---|---|---|
| `tools/llvm-mingw-*/`, `tools/llvm-mingw.zip` | clang, lld, mingw-w64 runtime, bundled Python | "Apache License v2.0 with LLVM Exceptions"; busybox under GPL-2.0; `share/make` and `share/gendef` under GPL-3.0; Python licence; MinGW-w64 `COPYING*` |
| `tools/sgdk/`, `tools/*.7z` | SGDK (Sega Genesis kit, used by the bundled samples) | "MIT License, Copyright (c) 2025 Stephane Dallongeville"; `COPYING.RUNTIME` GCC Runtime Library Exception 3.1; `tools/sjasm` by Konamiman; `tools/convsym` MIT, 2018 vladikcomper |
| `tools/eft-src/`, `tools/eft-build/` | elektron-firmware-tool source (each with its own `.git`) | MIT, Copyright (c) 2026 Marcel Bierling |


## Firmware

Elektron's OS is not included in any form. Patch data carries only this project's bytes plus SHA-256
hashes of the stock bytes each change expects.
