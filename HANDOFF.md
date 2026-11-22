# Handoff pointer

This file is a pointer only. It holds no project facts.

- The project briefing lives in `AGENTS.md`.
- The current state (builds, rounds, tests) lives in `STATE.md`.
- Open decisions live in `OPEN_DECISIONS.md`.
- `archive/` holds the older handoffs: `archive/HANDOFF-v2o-full.md` (the full v2o handoff) and `archive/SESSION_HANDOFF_2026-11-16.md`.
- The content was reorganized, not rewritten. Nothing was removed.

## What happened to the old folders

`builder-web/` and `builder-r1/` were linked worktrees of the `Synthack-OS` repository. Their content
was imported here and the folders were removed; their history stays in
`..\Default Project\Synthack-OS` (branches `private/webbuilder-r6`, `private/patch-format-r1`).

`synfact-dev/` is a separate clone used for evaluation, with its own `.git`. It stays on disk and is
git-ignored; it may hold local firmware copies.
