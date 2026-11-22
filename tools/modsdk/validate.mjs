// Runs the page's own package check (tools/sypatch/merge.mjs) on one .sypatch.json file.
//
//     node tools/modsdk/validate.mjs <file>
//
// Prints OK, or REFUSED: <reason> and exits 1. Called by modsdk.py check. Reads the file as data only.

import { readFileSync } from 'node:fs'
import { validatePackage } from '../sypatch/merge.mjs'

const file = process.argv[2]
let doc
try {
  doc = JSON.parse(readFileSync(file, 'utf8'))
} catch {
  console.log('REFUSED: the file is not valid JSON.')
  process.exit(1)
}
try {
  validatePackage(doc)
  console.log('OK')
} catch (e) {
  console.log(`REFUSED: ${e.message}`)
  process.exit(1)
}
