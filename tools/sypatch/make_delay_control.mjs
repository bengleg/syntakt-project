// Writes web/patches/delay-control.sypatch.json, the page's DelayCtrl patch set, from the local legacy patch.json
// (SYNTAKT_LEGACY_PATCH, or the first argument) and mods/modarea/patch.json in this repo.
//
//   node tools/sypatch/make_delay_control.mjs [path to legacy patch.json]

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { delayControlDoc } from './delay_control.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const legacy = process.argv[2] ?? process.env.SYNTAKT_LEGACY_PATCH
if (!legacy) throw new Error('give the legacy patch.json path, or set SYNTAKT_LEGACY_PATCH')

const doc = delayControlDoc(
  JSON.parse(readFileSync(legacy, 'utf8')).patches,
  JSON.parse(readFileSync(path.join(root, 'mods', 'modarea', 'patch.json'), 'utf8')).patches,
)
const out = path.join(root, 'web', 'patches', 'delay-control.sypatch.json')
mkdirSync(path.dirname(out), { recursive: true })
writeFileSync(out, JSON.stringify(doc, null, 1) + '\n')
console.log(`${path.relative(root, out)}: ${doc.units.reduce((n, u) => n + u.blocks.length, 0)} blocks`)
