// The in-memory build the page runs (in the worker, or under node for the test). Nothing is written anywhere.
import { buildSyxWith } from '../../tools/sypatch/bridge.mjs'
import { validatePackage, resolvePackages, mergePackages } from '../../tools/sypatch/merge.mjs'
import { toSites, toArea } from '../../tools/sypatch/convert.mjs'
import * as engine from './engine.generated.mjs'

// Returns the .syx bytes, and the boot room left (margin) and the least it must be (marginMin), in bytes.
export async function buildPatched(doc, stock) {
  const { syx, margin, marginMin } = await buildSyxWith(doc, stock, engine)
  return { syx: syx.slice(), margin, marginMin }
}

// The packages (an object: id -> parsed .sypatch, in manifest order) resolved with their requirements, merged into one
// document and built. Returns the .syx bytes, the package ids used, in order, and the boot room figures.
export async function buildPatchedFromPackages(packagesById, selectedIds, stock) {
  const ids = resolvePackages(packagesById, selectedIds)
  const doc = mergePackages(packagesById, ids)
  const { syx, margin, marginMin } = await buildSyxWith(doc, stock, engine)
  return { syx: syx.slice(), ids, margin, marginMin }
}

// Checks a package from a file the user added, with the same refusals the build makes, before any stock file is read.
export function checkPackage(doc) {
  const { id, title } = validatePackage(doc)
  toSites(doc)
  toArea(doc)
  return { id, title }
}

export const sha = bytes => engine.sha(bytes)
