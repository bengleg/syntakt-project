// Bundles the page's worker and the test core from this repo and the local engine. Output: web/dist (git-ignored).
// The engine is GPL and stays local: it is bundled here, never committed.
//
//   ELEKLOADER_JS=<engine js/src>  [ESBUILD_JS=<esbuild module: a name, or a file:// URL>]  node web/build.mjs
//
// Then serve the web folder over HTTP (workers do not load from file://):
//   cd web && python -m http.server 8000      and open http://localhost:8000/
//
// The page is loaded as app.mjs?v=<stamp> (index.html) and that stamp is carried onto the bundle and the worker:
// bump it after any change under web/, or a cached copy can run against a fresh page.

import { writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const engine = process.env.ELEKLOADER_JS
if (!engine) throw new Error('set ELEKLOADER_JS to the engine js/src folder')
const { build } = await import(process.env.ESBUILD_JS ?? 'esbuild')

const at = f => path.join(engine, f).split(path.sep).join('/')
const dist = path.join(here, 'dist')
mkdirSync(dist, { recursive: true })
writeFileSync(path.join(here, 'src', 'engine.generated.mjs'), [
  `export { sha } from '${at('bytes.ts')}'`,
  `export * as formats from '${at('formats.ts')}'`,
  `export * as elemod from '${at('elemod.ts')}'`,
  `export * as devices from '${at('devices.ts')}'`,
  `export * as coldfire from '${at('isa/coldfire.ts')}'`,
  '',
].join('\n'))

const common = { bundle: true, format: 'esm', target: 'es2022', logLevel: 'warning' }
await build({ ...common, entryPoints: [path.join(here, 'src', 'core.mjs')], outfile: path.join(dist, 'core.mjs') })
await build({ ...common, platform: 'browser', entryPoints: [path.join(here, 'src', 'worker.mjs')], outfile: path.join(dist, 'worker.mjs') })
// The page's own selection preview: the pure package checks only (no engine).
await build({ ...common, platform: 'browser', entryPoints: [path.join(here, '..', 'tools', 'sypatch', 'merge.mjs')], outfile: path.join(dist, 'merge.mjs') })
// The page's selection analysis (conflicts, size, load): also pure, no engine.
await build({ ...common, platform: 'browser', entryPoints: [path.join(here, '..', 'tools', 'sypatch', 'analyze.mjs')], outfile: path.join(dist, 'analyze.mjs') })
console.log('web/dist: core.mjs, worker.mjs, merge.mjs, analyze.mjs')
