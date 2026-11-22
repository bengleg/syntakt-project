# Syntakt custom firmware project

Unofficial mods for the **Elektron Syntakt**, OS 1.41 only. Everything is source plus patch data:
a build starts from the stock OS file you downloaded from elektron.se, so no firmware is stored here.

> Not affiliated with Elektron. Modified firmware can make the unit unusable and may void the
> warranty. Read [RECOVERY.md](RECOVERY.md) before flashing.

**Public.** Anyone can clone it and build their own OS file. Nothing Elektron ships is stored here.

## Install it on your Syntakt

You can download a ready-built file from [Releases](https://github.com/bengleg/syntakt-project/releases), or build it yourself on a computer with the steps below. Both come from your own OS 1.41 file.

What the buttons do is in [MANUAL.md](MANUAL.md).

What you need:
- Your own OS 1.41 file, `Syntakt_OS1.41.syx`, from elektron.se. Only OS 1.41 works.
- A MIDI DIN interface, so you can recover the unit if something goes wrong.
- Your projects backed up. Read [RECOVERY.md](RECOVERY.md) before you flash anything.

On the computer: Windows with WSL (Ubuntu), or Linux. You need Python 3.9 or newer, plus Git,
`make` and `gcc`, which the one-time setup uses to build a helper tool.

Steps, run in WSL or Linux from the project folder:
1. Put `Syntakt_OS1.41.syx` in the `firmware/` folder. Git ignores it, so it is never shared.
2. Once: `bash tools/unpack/setup_eft.sh`
3. Build the file:
   `python3 tools/build/build.py --stock firmware/Syntakt_OS1.41.syx mods/modarea mods/delay-control -o out/out.syx`
4. The result is `out/out.syx`. Read [RECOVERY.md](RECOVERY.md) before you send it to the unit.

The build stops with an error if the stock file is not exactly OS 1.41.

## What is in here

| Component | Path | What it is |
|---|---|---|
| Mod sources | `mods/` | DelayCtrl (`delay-control`), its diagnostic (`dc-diag`), the SDK example (`hello-sdk`), and upstream SyntHack mods |
| Mod SDK | `tools/modsdk/` | `init`, `build`, `check`, `fingerprint`, `slots`; header, templates, slot map, taken-spot list |
| Patch format | `tools/sypatch/` | `.sypatch.json` format (schema 1), structural checker, merger, conflict analyser |
| Web builder | `web/` | Page, worker, package merge and conflict analysis; builds an OS file in memory, no uploads |
| Firmware tools | `tools/unpack/`, `tools/build/` | Unpack/repack a `.syx`; assemble a verified build (wrong OS, overlaps and protected sections refused) |
| Emulator harness | `tools/emu/`, `tools/measure/` | ColdFire model (Unicorn) used to test a mod against the original code |
| Guard | `tools/hooks/` | Pre-commit check that refuses firmware in the staging area |
| Docs | `docs/` | SDK guide, authoring, patch format, memory map, UI and audio notes |

Agent briefing: [AGENTS.md](AGENTS.md). Current state: [STATE.md](STATE.md). Open decisions:
[OPEN_DECISIONS.md](OPEN_DECISIONS.md). History: [HISTORY.md](HISTORY.md).

## Prerequisites

- Python 3.9+ (`pytest` for the tests)
- Node 20+ for the browser builder and the JS tests
- WSL or Linux with `m68k-linux-gnu-gcc` for compiling mods; `bash` for `tools/unpack/setup_eft.sh`
- The engine: a local checkout of elekloader's `js/src` (GPL-2.0, never vendored) — needed by the
  browser build and by the full-image tests
- Your own `Syntakt_OS1.41.syx`, kept in a local `firmware/` folder (git-ignored)

The m68k/LLVM toolchain, SGDK and the firmware container tool live in `tools/` on disk but are
git-ignored; see [NOTICE.md](NOTICE.md) for what they are and where the licences sit.

## Commands

These are the paths as they exist; the three marked *verified* were run on the import commit.
```sh
git config core.hooksPath tools/hooks            # once: guard against committing firmware
python -m pytest tests/test_modsdk.py -q          # verified: SDK tests
python -m pytest tests/test_sypatch.py -q         # verified: format and structural checks
python -m pytest tests/test_check_no_firmware.py -q   # verified: the guard itself
```

Builder setup and the browser build (needs `ELEKLOADER_JS`, optional `ESBUILD_JS`):
[docs/BUILDING.md](docs/BUILDING.md).

A full build needs your stock file:

```sh
python tools/build/build.py --stock firmware/Syntakt_OS1.41.syx mods/modarea mods/delay-control -o out/out.syx
```

## Writing a mod

[docs/START-HERE-MODS.md](docs/START-HERE-MODS.md) then [docs/SDK.md](docs/SDK.md). Packages without
the SDK: [docs/AUTHORING.md](docs/AUTHORING.md) and [docs/PATCH-FORMAT.md](docs/PATCH-FORMAT.md).
Examples: `examples/` and `mods/hello-sdk/`.

## Rules that bite

- No firmware bytes in the repo. Hashes only. `firmware/` holds just a README.
- Area code lives in the mod area at `0x46000000` and above; take a slot from `tools/modsdk/slots.json`.
- Keep the boot margin above ~4 KB; the build refuses below it.
- Never touch sections 2 and 6; never lengthen the intro.
- A failed patch can produce a byte-identical file — always compare the SHA.

## Licence and provenance

MIT for this repository's own code and docs ([LICENSE](LICENSE)); the upstream SyntHack-OS work is
MIT by Angelo-politek. Third-party tools and the GPL engine are used as external programs and kept
out of the tree. Attribution and the exact boundaries: [NOTICE.md](NOTICE.md) and [LEGAL.md](LEGAL.md).
