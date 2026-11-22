# Quests

Scope: the browser builder page, `builder-web\web\index.html` and `app.mjs` (the only website in this project).
Design reference: Geist (vercel.com/geist), adapted, no Vercel branding or copy, no new dependency.

| # | Quest | Owner | Status |
|---|---|---|---|
| Q1 | Audit page: missing states, weak hierarchy, dead ends | supervisor | done (below) |
| Q2 | Layout, steps header, Geist tokens, focus and contrast, responsive | subagent | done |
| Q3 | Real controls: select all/none, remove added mod, drop zone, copy SHA, OS file details | subagent | done (drag-drop, copy, remove as of 2026-11-18 not exercised; build run now verified end to end 2026-11-23, see Q3/Q6 evidence) |
| Q4 | Browser review | supervisor | done, partial |
| Q5 | Evidence, STATE.md | supervisor | done |
| Q6 | Boot-margin check in the browser (port of bootcheck.py) | subagent | done (below) |

## Q1 audit
- One long column of four cards; no sense of progress; step status is only visible in a small text line.
- OS file input is a bare file picker: no file name, size, or clear/replace action.
- Added mods cannot be removed. No "select all / none". No copy button for the SHA.
- Result card has no next-step guidance (flash is a separate, gated step).
- Single-file v2o option sits inside the Features card and is easy to miss.
- Not available (stay honest): no backend, nothing is uploaded; CPU load is unmeasured; stock-file hash check is not possible.

## Evidence (2026-11-18)
- Served over HTTP, loaded in browser: 0 console warnings or errors, no horizontal scroll at 1409px and 357px (iframe test).
- Lighthouse: accessibility 1.0, best practices 1.0, SEO 0.75 (meta description added after).
- Select none / all, fake .syx pick (build enabled), bad mod file rejected with clear message: all worked.
- Fixed: step chips showed 'Problem' when only input was missing; now 'To do'.
- Not tested: real build, drag-and-drop, clipboard, Remove on an added mod, keyboard tab order by hand, a real mod file. No production build exists for this page (static; web/dist untouched).

## Q6 evidence (2026-11-23)
- Ported the start-up margin check to JS: tools/sypatch/bootmargin.mjs (with depackMargin in tools/sypatch/aplib.mjs). Wired into the page build; the page shows 'Boot room: N bytes' and refuses a file below 4096.
- JS and Python agree on stock 1.41: 99 938 B (decoded section 3 = 3 438 480 B).
- The page core's DelayCtrl build still reproduces the tested v2o .syx byte for byte, and its boot room is 19 743 B (limit 4 096 B).
- Tests: tests/sypatch_bootmargin.test.mjs (synthetic; real-file part skips without SYNTAKT_STOCK + ELEKLOADER_JS). tests/web_core.test.mjs asserts the build reports a margin. Page cache stamp v=10.
- Not verified (as of this entry): a real page build driven end to end in a browser. Now verified: see "Q3/Q6 evidence (2026-11-23, browser end to end)" below. The refusal path was covered only by the synthetic test and the Python build.py refusal at the time; the browser refusal is now also checked in that block.

## Q3/Q6 evidence (2026-11-23, browser end to end)

Headless Chrome, page served from a local HTTP server. A user picked the stock OS 1.41 file, ticked the baseline box, pressed Build and got the correct file.

- Page loads with no page errors. The only console entry was a 404, inferred (not logged) as `/favicon.ico`.
- With no OS file chosen, Build is disabled. The reason line says: "Build is off: no OS 1.41 file chosen yet. Choose it in step 3."
- Choosing the file flips the card to "Ready", showing `Syntakt_OS1.41.syx`, 2.5 MB. Build becomes enabled.
- Baseline box ticked ("DelayCtrl v2o (single file, tested baseline)"): build took 44.6 s. SHA-256 `3df95923db35b0787119b04253e877f62b7c10ee1b7ab3f87340673aa843e3ac`, which is the expected v2o hash. Downloaded file: 2 475 424 bytes, suggested name `delay-control-3df95923.syx`.
- Wrong file (a 1 000-byte junk `.syx`): Build refuses with "Not built: the file is not the stock OS 1.41 (hash differs)". No file is produced.
- Baseline box unticked, four features ticked: build succeeded in 43.6 s. SHA-256 `25773b67048b2232e2a73631f4448be4163ef42d82c8611167c08dbc3adc972f`. This is the all-four build. Not verified in an emulator or on hardware.
- Node core test `tests/web_core.test.mjs` passed 3/3 with `SYNTAKT_STOCK` and `SYNTAKT_V2O` set.
- Rules check on `web/index.html`, `web/app.mjs`, `web/build.mjs`: no `eval(`, no `new Function`, no `innerHTML`. Dynamic `import()` only loads the app's own `dist/` modules, never package content. No user-facing text says "block".
- Known UX gap: a wrong `.syx` still shows "Ready" in the card. The mismatch only shows when Build is pressed.
- Caveat: only headless Chrome was driven. Desktop browsers were not tested in this run.
