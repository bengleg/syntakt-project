# Building the browser builder

The page is static. Nothing it does leaves the machine: packages are parsed as data and the OS file
is patched in memory, then offered as a download on click.

## What the build does

`web/build.mjs` bundles four entries into `web/dist/` (git-ignored):

- `src/core.mjs` and `src/worker.mjs` — the builder and its worker, both wrapped around the engine
- `tools/sypatch/merge.mjs` and `tools/sypatch/analyze.mjs` — selection preview and conflict analysis,
  pure JS with no engine

It also writes `web/src/engine.generated.mjs`, a five-line re-export shim pointing at the engine
checkout. Both it and `web/dist/` stay out of git.

## The engine

The engine is elekloader's TypeScript `js/src` tree, **GPL-2.0-or-later**. It is never vendored: you
point at a local checkout, so clone one first:

```sh
git clone --depth 1 https://github.com/elekloader/elekloader.git
```

```sh
# PowerShell
$env:ELEKLOADER_JS = "path/to/elekloader/js/src"
$env:ESBUILD_JS   = "file:///path/to/esbuild/lib/main.js"   # only if esbuild is not installed
node web/build.mjs
```

- `ELEKLOADER_JS` is required: the build throws without it.
- `ESBUILD_JS` is optional; leave it unset to use an installed `esbuild`.
- Neither value is written into any file, so no absolute paths are committed.

## Running the page

Workers do not load from `file://`, so serve the folder:

```sh
cd web
python -m http.server 8000
```

Open `http://localhost:8000/`.

## Cache stamp

`index.html` loads `app.mjs?v=<stamp>` and the stamp is carried onto the bundle and the worker.
**Bump it after any change under `web/`**, or a cached copy can run against a fresh page. Current
value: `v=10`.

## Tests

```sh
python -m pytest tests/test_sypatch.py -q
node --test tests/sypatch_analyze.test.mjs tests/sypatch_packages.test.mjs
node --test --test-skip-pattern rebuilt tests/engine_bridge.test.mjs   # synthetic only
node --test tests/sypatch_bootmargin.test.mjs
```

The tests that build a real image need `SYNTAKT_STOCK` and `ELEKLOADER_JS`; they are described in
`docs/AGENT-NOTES.md`.
