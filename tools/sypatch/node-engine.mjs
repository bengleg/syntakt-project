// Node only: loads the engine from its js/src folder (ELEKLOADER_JS, never copied into this repo) and runs the bridge.
// The browser worker does not use this file; it bundles the engine itself (web/build.mjs).

import { createHash } from 'node:crypto'
import { pathToFileURL } from 'node:url'
import path from 'node:path'
import { buildSyxWith } from './bridge.mjs'

export async function loadEngine(engineSrc) {
  const load = f => import(pathToFileURL(path.join(engineSrc, f)).href)
  const [formats, elemod, devices, coldfire, bytes] = await Promise.all([
    load('formats.ts'), load('elemod.ts'), load('devices.ts'), load('isa/coldfire.ts'), load('bytes.ts'),
  ])
  return { sha: bytes.sha, formats, elemod, devices, coldfire }
}

export async function buildSyx(doc, callerStock, engineSrc, opts = {}) {
  const early = createHash('sha256').update(Uint8Array.from(callerStock)).digest('hex')
  if (doc.target?.stock_sha256 !== early) throw new Error('the file is not the stock OS 1.41 (hash differs)')
  return buildSyxWith(doc, callerStock, await loadEngine(engineSrc), opts)
}
