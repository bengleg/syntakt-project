> Project picture (when working in the Syntakt_Project checkout): ..\PROJECT_STATUS.md, ..\AGENTS.md, ..\STATE.md, ..\OPEN_DECISIONS.md.

# Agent notes: code-level rules (this is docs/AGENT-NOTES.md; the root briefing is ..\AGENTS.md)

Guidance for AI agents working in this repository. Read it before you change
anything. Humans: [CONTRIBUTING.md](../CONTRIBUTING.md) and [LEGAL.md](../LEGAL.md).

## Privacy and licence rules (hard limits)

- **Never commit firmware or firmware-like files**: no `.syx`, `.smz4`, `.bin`,
  `.elemod`, `.elf`, `.img`, `.raw`. `.gitignore` and `tools/hooks` cover some of
  these; the rule covers all of them. Check `git status` before every commit.
- **No stock bytes** (original OS 1.41 bytes) in prompts, logs, test fixtures,
  examples, generated output, commit messages or issue text. Hashes of original
  bytes are allowed. Dumps, disassembly and byte listings of the stock OS are not.
- **Originals are read-only.** Never modify, move, rename or delete the user's OS
  file or any file in `firmware/`. Work on copies outside the repository.
- **Nothing leaves the machine without explicit approval.** Do not publish, upload,
  send, post, flash or push anything, and do not contact devices, without the
  user's explicit approval for that specific action.
- **No personal data** in any file: no absolute paths, user names, machine names,
  serial numbers or account data. Use relative paths in docs and examples.
- **Never claim a check passed** unless you ran it in this session, and report the
  exact result.

## Verification commands

Run from the repository root. Check the env column before you run a command.

| command | needs | notes |
|---|---|---|
| `python -m pytest tests/test_sypatch.py -q` | nothing | structural tests on synthetic data |
| `node --test --test-skip-pattern rebuilt tests/engine_bridge.test.mjs` | nothing | runs synthetic tests; skips the tests named "rebuilt", which build a full `.syx` in memory |
| `node --test tests/sypatch_bootmargin.test.mjs` | nothing (the real-file part skips without `SYNTAKT_STOCK` + `ELEKLOADER_JS`) | start-up margin check in `tools/sypatch/bootmargin.mjs` |
| `node --test tests/engine_bridge.test.mjs` | `SYNTAKT_STOCK`, `ELEKLOADER_JS`, `SYNTAKT_LEGACY_PATCH` (+ optional `SYNTAKT_V2O`) | builds a full image; run only when the user asks |
| `node web/build.mjs` | `ELEKLOADER_JS` (+ optional `ESBUILD_JS`) | writes `web/dist/`, which is git-ignored |
| `node --test tests/web_core.test.mjs` | `SYNTAKT_STOCK`, `SYNTAKT_V2O`, and a previous `node web/build.mjs` | skipped without the bundle and local files |
| `python -m pytest tests/test_modsdk.py -q` | nothing | tests that need the WSL m68k toolchain skip without it; the SDK in `tools/modsdk` |

Trap: `python -m pytest tests/test_bootcheck.py -q` does not skip without its files. It fails. It needs the stock file copied into the repo's `firmware/` folder and a working `elektron-firmware-tool` (set `EFT_BIN`, or run `bash tools/unpack/setup_eft.sh`).

Variables, as read by the tests:

- `SYNTAKT_STOCK`: the user's stock OS 1.41 file (local, never committed).
- `ELEKLOADER_JS`: the engine's `js/src` folder (GPL, local only).
- `SYNTAKT_LEGACY_PATCH`: `mods/delay-control/patch.json`.
- `SYNTAKT_V2O`: a locally built reference file, for comparison only.
- `ESBUILD_JS`: an esbuild module (a name, or a `file://` URL) used by `web/build.mjs`.

Do not set these to paths inside the repository. Do not write their values into
any file or output.

Rule for agents: the tests that build a full image (the "rebuilt" tests and the
full DelayCtrl builds) produce bytes derived from the stock file. Run them only
when the user asks, keep their output in memory, and never save it.

## Patch packages

A package is one `.sypatch.json` file, specified in
[docs/PATCH-FORMAT.md](PATCH-FORMAT.md). Packages are normally produced by
the SDK (see [docs/SDK.md](SDK.md)). Hand-written packages follow the steps
below. To add or change a package:

1. Use `format: "synthack-patchset"`, `schema: 1`, `encoding: "lowercase-hex"`,
   and `target` with `device "Syntakt"`, `os "1.41"` and the OS 1.41 hash from
   `tools/sypatch/check_patch.py`. Never change that hash.
2. Give the package an `id` that no other package uses (lowercase, hyphens).
3. List every package it depends on in `requires` (`[]` when none). Check that each
   id exists. Do not add a dependency that the package does not use.
4. If the package has area changes, add the top-level `area` layout. It must be
   identical to the layout of every other package that is combined with it. Keep
   area offsets clear of other packages' ranges. The DelayCtrl ranges are that
   package's own convention, not a global one.
5. Give each change a unique `id`, a `why`, a `new_sha256` and, for replace
   changes, a `stock_sha256`. Use lowercase hex only.
6. Validate: `python tools/sypatch/check_patch.py <file>`. A `REJECTED` result
   means the package is not done. The checker does not check `requires` or stock
   bytes; say so in your report if you rely on it.
7. Keep the package free of personal data and original bytes.

Synthetic examples live in [examples/](../examples/README.md). Do not put real
packages there.

## Browser and user-facing text

- **The browser never executes patch content.** A package is read as text and
  parsed as data. Do not add `eval`, `new Function`, dynamic `import()` or
  `innerHTML` for anything that comes from a package, and do not load code from a
  package URL. Package fields are data, always.
- **User-facing text never says "block".** Say "change" or "part" in the page, in
  error messages, in the README and in release notes. "Block" is developer
  vocabulary for the JSON `blocks[]` and stays in developer docs and code only.
- The page offers the `.syx` for download only when the user clicks. Do not add
  auto-download, auto-upload or any network call that sends the built file.

## Separation of code and packages

- **Builder code**: `tools/` (including `tools/sypatch/`) and `web/src/`, `web/app.mjs`,
  `web/index.html`, `web/build.mjs`. Changes here are builder changes.
- **Patch packages**: `web/patches/` and `examples/`. Changes here are package
  changes.
- Keep a builder change and a package change in separate commits. Do not edit a
  package to get around a builder check; fix the package or raise the issue.
- `mods/<name>/` holds our mod sources and their `make_*.py` scripts. Do not edit
  them when you only change a package, and do not hand-edit a generated `patch.json`.
- Other agents may be editing the same tree at the same time. Run `git status`
  first, do not revert changes you did not make, and leave them as they are.

## Working style for this repo

- Prefer small, reviewable changes that match the surrounding code.
- Do not change the stock OS hash, the section 2 and 6 rules or the boot timing
  rules (see CONTRIBUTING.md). Do not change configured models or providers.
- Record meaningful assumptions in your final report, and name what you did not
  verify.
