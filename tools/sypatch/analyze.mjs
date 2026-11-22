// What the picked packages do together: conflicts, patch memory and program places used, and an audio load estimate.
// Pure: no engine, no file system. Packages and notes are data; nothing here runs them. The page calls this on every
// change of the ticks; the build itself still uses merge.mjs.

import { validatePackage, resolvePackages, checkInfo } from './merge.mjs'

export const DEFAULT_BUDGET = { noticeable: 1000, heavy: 3000 }
const NOTE_KEYS = ['summary', 'claims', 'conflicts', 'cost']
const has = (obj, key) => obj != null && Object.prototype.hasOwnProperty.call(obj, key)
const hex8 = n => `0x${n.toString(16).padStart(8, '0')}`
const hexShort = n => `0x${n.toString(16)}`
const sumBytes = writes => writes.reduce((n, w) => n + (w.end - w.start), 0)
// "dc: TRIG 13-16 on the FX track" -> "TRIG 13-16 on the FX track"
const claimWords = c => (c.includes(':') ? c.slice(c.indexOf(':') + 1) : c)

// The notes for one package: the file's own info, with the curated notes winning key by key. `from` says where each
// key came from ('curated' or 'file'), so the page can say which notes the file's author wrote.
export function noteFor(fileInfo, curatedInfo) {
  const note = {}
  const from = {}
  for (const key of NOTE_KEYS) {
    if (has(curatedInfo, key)) { note[key] = curatedInfo[key]; from[key] = 'curated' }
    else if (has(fileInfo, key)) { note[key] = fileInfo[key]; from[key] = 'file' }
  }
  return { note, from }
}

const titleOf = (packagesById, id) => {
  const t = has(packagesById, id) ? packagesById[id]?.title : undefined
  return typeof t === 'string' && t ? t : id
}

function summarize(packagesById, id) {
  if (!has(packagesById, id) || packagesById[id]?.id !== id) throw new Error(`package "${id}" does not carry that id`)
  return validatePackage(packagesById[id])
}

// Analyses the selection. Returns:
//   order: the ids to build, dependencies first (resolvePackages)
//   conflicts: every problem found, each { a, b, kind, text }; kind is os-bytes, patch-memory, declared, claim or invalid
//   blocking: true when there is any conflict
//   size: { perPackage: id -> { areaBytes, osBytes, osPlaces }, totals: { areaBytes, areaSize, areaPercent, osPlaces } }
//   cost: { perPackage: id -> instructionsPerBlock or null, known, unmeasured: [ids], band }
//     band is none, unknown, light, noticeable or heavy. Unmeasured packages never count as zero: any unmeasured
//     package makes the band unknown.
export function analyzeSelection(packagesById, infoById, selectedIds, budget) {
  const b = { ...DEFAULT_BUDGET, ...budget }
  const conflicts = []
  const names = id => titleOf(packagesById, id)
  let order = []
  try {
    order = resolvePackages(packagesById, selectedIds)
  } catch (e) {
    conflicts.push({ a: null, b: null, kind: 'invalid', text: `The selection cannot be built: ${e.message}.` })
  }

  const parts = new Map()
  for (const id of order) {
    let s
    try {
      s = summarize(packagesById, id)
    } catch (e) {
      conflicts.push({ a: id, b: null, kind: 'invalid', text: `${names(id)} was refused: ${e.message}.` })
      continue
    }
    let curated = null
    if (has(infoById, id)) {
      try {
        checkInfo(infoById[id], id)
        curated = infoById[id]
      } catch (e) {
        conflicts.push({ a: id, b: null, kind: 'invalid', text: `The notes for ${names(id)} were refused: ${e.message}.` })
      }
    }
    const { note } = noteFor(packagesById[id].info, curated)
    parts.set(id, { s, note })
  }

  const valid = order.filter(id => parts.has(id))
  for (let i = 0; i < valid.length; i++) {
    for (let j = i + 1; j < valid.length; j++) {
      const A = valid[i]
      const B = valid[j]
      const pa = parts.get(A)
      const pb = parts.get(B)
      const ta = names(A)
      const tb = names(B)
      if (pa.s.layout && pb.s.layout && JSON.stringify(pa.s.layout) !== JSON.stringify(pb.s.layout)) {
        conflicts.push({ a: A, b: B, kind: 'invalid', text: `${ta} and ${tb} use different patch memory layouts, so they cannot be built together.` })
      }
      for (const w of pa.s.writes) {
        for (const v of pb.s.writes) {
          if (w.start < v.end && v.start < w.end) {
            conflicts.push({ a: A, b: B, kind: 'os-bytes', text: `${ta} and ${tb} both change the same place in the Syntakt's own program (${hex8(Math.max(w.start, v.start))}).` })
          }
        }
      }
      for (const w of pa.s.areaWrites) {
        for (const v of pb.s.areaWrites) {
          if (w.start < v.end && v.start < w.end) {
            conflicts.push({ a: A, b: B, kind: 'patch-memory', text: `${ta} and ${tb} both use the same part of the shared patch memory (offset ${hexShort(Math.max(w.start, v.start))}).` })
          }
        }
      }
      if ((pa.note.conflicts ?? []).includes(B) || (pb.note.conflicts ?? []).includes(A)) {
        conflicts.push({ a: A, b: B, kind: 'declared', text: `${ta} and ${tb} are marked as conflicting in their notes.` })
      }
      const claimsB = new Set(pb.note.claims ?? [])
      for (const c of new Set(pa.note.claims ?? [])) {
        if (claimsB.has(c)) {
          conflicts.push({ a: A, b: B, kind: 'claim', text: `${ta} and ${tb} both claim the same thing: ${claimWords(c)}.` })
        }
      }
    }
  }

  const seen = new Set()
  const unique = conflicts.filter(c => {
    const key = JSON.stringify([c.a, c.b, c.kind, c.text])
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })

  const perPackage = {}
  for (const id of valid) {
    const s = parts.get(id).s
    perPackage[id] = { areaBytes: sumBytes(s.areaWrites), osBytes: sumBytes(s.writes), osPlaces: s.writes.length }
  }
  const layout = valid.map(id => parts.get(id).s.layout).find(Boolean) ?? null
  const areaSize = layout ? layout.size : 0
  const areaBytes = valid.reduce((n, id) => n + perPackage[id].areaBytes, 0)
  const osPlaces = valid.reduce((n, id) => n + perPackage[id].osPlaces, 0)
  const totals = { areaBytes, areaSize, areaPercent: areaSize ? (areaBytes / areaSize) * 100 : 0, osPlaces }

  const costPer = {}
  const unmeasured = []
  let known = 0
  for (const id of valid) {
    const ipb = parts.get(id).note.cost?.instructionsPerBlock
    costPer[id] = Number.isInteger(ipb) ? ipb : null
    if (costPer[id] === null) unmeasured.push(id)
    else known += costPer[id]
  }
  const hasHooks = valid.some(id => perPackage[id].osPlaces > 0 || perPackage[id].areaBytes > 0)
  const band = !hasHooks ? 'none'
    : unmeasured.length ? 'unknown'
      : known < b.noticeable ? 'light'
        : known < b.heavy ? 'noticeable' : 'heavy'

  return {
    order,
    conflicts: unique,
    blocking: unique.length > 0,
    size: { perPackage, totals },
    cost: { perPackage: costPer, known, unmeasured, band },
  }
}

// The conflicts that appear when candidateId joins the selection: those not already there without it. Empty when the
// candidate is already selected. The page labels unticked mods with these before the visitor ticks them.
export function conflictsIfAdded(packagesById, infoById, selectedIds, candidateId, budget) {
  const ids = Array.isArray(selectedIds) ? selectedIds : []
  if (ids.includes(candidateId)) return []
  const before = new Set(analyzeSelection(packagesById, infoById, ids, budget).conflicts.map(c => c.text))
  return analyzeSelection(packagesById, infoById, [...ids, candidateId], budget).conflicts.filter(c => !before.has(c.text))
}
