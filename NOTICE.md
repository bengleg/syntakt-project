# Provenance and attribution

Read with [LEGAL.md](LEGAL.md). This file records where the material came from; it does not extend
any licence.

## This repository

The tree was imported on 2026-11-22 from the working branch `private/webbuilder-r6` in
`..\Default Project\Synthack-OS` (commit `a63ad93`, plus uncommitted SDK work that existed nowhere
else). The pre-import history is still in that repository; the branches are `private/webbuilder-r6`
and `private/patch-format-r1`, and `GIT_LOG.txt` records the tips at import time. Git history here
starts at the import commit.

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
| [elekloader](https://github.com/elekloader/elekloader) `js/src` | GPL-2.0-or-later | local path via `ELEKLOADER_JS`; bundled into git-ignored `web/dist/` |
| [Unicorn](https://github.com/unicorn-engine/unicorn) | GPL-2.0 | Python package, installed separately |
| esbuild | MIT | npm package or local file via `ESBUILD_JS` |
| m68k GNU toolchain | GPL-3.0 | system packages, under WSL/Linux |

The GPL engine is never committed, so no GPL source obligation arises here; the bundle in `web/dist/`
is derived from it and is likewise not committed.

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
