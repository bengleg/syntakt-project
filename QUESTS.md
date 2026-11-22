# Quests

Scope: the browser builder page, `builder-web\web\index.html` and `app.mjs` (the only website in this project).
Design reference: Geist (vercel.com/geist), adapted, no Vercel branding or copy, no new dependency.

| # | Quest | Owner | Status |
|---|---|---|---|
| Q1 | Audit page: missing states, weak hierarchy, dead ends | supervisor | done (below) |
| Q2 | Layout, steps header, Geist tokens, focus and contrast, responsive | subagent | done |
| Q3 | Real controls: select all/none, remove added mod, drop zone, copy SHA, OS file details | subagent | done (drag-drop, copy, remove, build run NOT exercised) |
| Q4 | Browser review | supervisor | done, partial |
| Q5 | Evidence, STATE.md | supervisor | done |

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
