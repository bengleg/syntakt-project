// Run: node --test tests/web_core.test.mjs   (after node web/build.mjs with ELEKLOADER_JS set)
// The page's bundled core (web/dist/core.mjs, the engine bundled in) builds the DelayCtrl patch set from the user's
// stock file and must give the tested v2o .syx byte for byte. Skipped unless the bundle and the local files exist.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const { SYNTAKT_STOCK, SYNTAKT_V2O } = process.env
const bundleUrl = new URL('../web/dist/core.mjs', import.meta.url)
const bundle = fileURLToPath(bundleUrl)
const ready = [bundle, SYNTAKT_STOCK, SYNTAKT_V2O].every(p => p && existsSync(p))

test('the page core builds DelayCtrl byte for byte as the tested v2o .syx', { skip: !ready && 'needs web/dist and local files' }, async () => {
  const { buildPatched } = await import(bundleUrl.href)
  const doc = JSON.parse(readFileSync(new URL('../web/patches/delay-control.sypatch.json', import.meta.url), 'utf8'))
  const syx = await buildPatched(doc, readFileSync(SYNTAKT_STOCK))
  const sha = b => createHash('sha256').update(b).digest('hex')
  assert.equal(sha(syx), sha(readFileSync(SYNTAKT_V2O)))
})

test('the page core refuses a file that is not the stock OS 1.41', { skip: !ready && 'needs web/dist and local files' }, async () => {
  const { buildPatched } = await import(bundleUrl.href)
  const doc = JSON.parse(readFileSync(new URL('../web/patches/delay-control.sypatch.json', import.meta.url), 'utf8'))
  await assert.rejects(buildPatched(doc, Buffer.from('not firmware')), /hash differs/)
})

test('the package path builds the v2o set byte for byte when it is the only package', { skip: !ready && 'needs web/dist and local files' }, async () => {
  const { buildPatchedFromPackages } = await import(bundleUrl.href)
  const doc = JSON.parse(readFileSync(new URL('../web/patches/delay-control.sypatch.json', import.meta.url), 'utf8'))
  const { syx, ids } = await buildPatchedFromPackages({ [doc.id]: doc }, [doc.id], readFileSync(SYNTAKT_STOCK))
  const sha = b => createHash('sha256').update(b).digest('hex')
  assert.deepEqual(ids, [doc.id])
  assert.equal(sha(syx), sha(readFileSync(SYNTAKT_V2O)))
})
