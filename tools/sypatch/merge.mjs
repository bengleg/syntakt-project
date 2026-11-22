// Patch packages: one .sypatch file each, selected by id, resolved with their requirements, and merged into ONE
// .sypatch document that the bridge builds. Pure: no file system, no engine. The checks mirror check_patch.py.
// A package is data. Nothing here runs code from it.

import { sha256 } from './sha256.mjs'
import { fromHex } from './hex.mjs'

export const STOCK_SHA256 = '8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e'
const LOAD = 0x40000400
const HEX = /^(?:[0-9a-f]{2})*$/
const SHA = /^[0-9a-f]{64}$/
const ID = /^[a-z0-9][a-z0-9-]*$/
const NUM = /^(?:0x[0-9a-f]+|[0-9]+)$/i

const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key)

// The first two writes that share a byte, or null. Sorted by start, each write is checked against the one that reaches
// furthest, so a long write that contains a later one is caught.
function firstOverlap(writes) {
  const sorted = [...writes].sort((a, b) => a.start - b.start || a.end - b.end)
  let top = null
  for (const w of sorted) {
    if (top && w.start < top.end) return [top, w]
    if (!top || w.end > top.end) top = w
  }
  return null
}

const describe = w => `change "${w.id}"${w.pkg ? ` of package "${w.pkg}"` : ''}`
const overlapText = ([p, q]) => `${describe(p)} and ${describe(q)} change the same bytes`

// The optional notes about a package (`info`): author-declared in the file, or curated by the site owner. Data only.
// Throws an Error with a plain sentence; ownId is the package the notes belong to (it may not conflict with itself).
// Mirrored by _check_info in tools/sypatch/check_patch.py: keep the two in step.
export function checkInfo(info, ownId) {
  const fail = text => { throw new Error(text) }
  if (!info || typeof info !== 'object' || Array.isArray(info)) fail('info must be an object')
  if (info.summary !== undefined && (typeof info.summary !== 'string' || [...info.summary].length > 200)) {
    fail('info summary must be text of 200 characters or fewer')
  }
  if (info.claims !== undefined && (!Array.isArray(info.claims) || info.claims.some(c => typeof c !== 'string'))) {
    fail('info claims must be a list of text')
  }
  if (info.conflicts !== undefined) {
    if (!Array.isArray(info.conflicts) || info.conflicts.some(c => typeof c !== 'string' || !ID.test(c))) {
      fail('info conflicts must be a list of package ids')
    }
    if (ownId !== undefined && info.conflicts.includes(ownId)) fail('info conflicts cannot name the package itself')
  }
  if (info.cost !== undefined && info.cost !== null) {
    const c = info.cost
    if (typeof c !== 'object' || Array.isArray(c)) fail('info cost must be null or an object')
    if (!Number.isInteger(c.instructionsPerBlock) || c.instructionsPerBlock < 0) {
      fail('info cost instructionsPerBlock must be a whole number, 0 or more')
    }
    if (typeof c.measured !== 'string') fail('info cost measured must be text')
  }
  return info
}

// Checks one package and returns its summary: id, title, requires, the normalised area layout (or null), the change
// ids, and the bytes it writes (replace: absolute addresses; area: offsets). Throws an Error naming the package.
export function validatePackage(doc) {
  const who = typeof doc?.id === 'string' ? doc.id : '(no id)'
  const fail = text => { throw new Error(`package "${who}": ${text}`) }
  if (!doc || typeof doc !== 'object') throw new Error('the file is not a patch package')
  if (doc.format !== 'synthack-patchset' || doc.schema !== 1) fail('not a synthack-patchset schema 1 file')
  if (doc.encoding !== 'lowercase-hex') fail('encoding must be lowercase-hex')
  if (typeof doc.id !== 'string' || !ID.test(doc.id)) {
    throw new Error('the package id must be lowercase letters, digits and hyphens, such as "delay-control-core"')
  }
  if (doc.title !== undefined && typeof doc.title !== 'string') fail('title must be text')
  if (doc.info !== undefined) {
    try { checkInfo(doc.info, doc.id) } catch (e) { fail(e.message) }
  }
  const requires = doc.requires ?? []
  if (!Array.isArray(requires) || requires.some(r => typeof r !== 'string' || !ID.test(r))) {
    fail('requires must be a list of package ids')
  }
  if (requires.includes(doc.id)) fail('a package cannot require itself')

  const t = doc.target ?? {}
  if (t.device !== 'Syntakt' || t.os !== '1.41') fail('the target is not Syntakt OS 1.41')
  if (t.stock_sha256 !== STOCK_SHA256) fail('target.stock_sha256 is not the OS 1.41 hash')

  const num = (v, what) => {
    const n = typeof v === 'number' ? v : (typeof v === 'string' && NUM.test(v) ? Number(v) : NaN)
    if (!Number.isInteger(n)) fail(`${what} is not a number: ${v}`)
    return n
  }

  let layout = null
  if (doc.area !== undefined) {
    const a = doc.area ?? {}
    if (a.compress !== 'shlz') fail('area.compress must be shlz')
    layout = { img: num(a.img, 'area.img'), ram: num(a.ram, 'area.ram'), size: num(a.size, 'area.size'), compress: 'shlz' }
  }

  if (doc.units !== undefined && !Array.isArray(doc.units)) fail('units must be a list')
  const ids = new Set()
  const changeIds = []
  const writes = []
  const areaWrites = []
  for (const unit of doc.units ?? []) {
    const blocks = unit?.blocks ?? []
    if (!Array.isArray(blocks)) fail('the unit changes must be a list')
    for (const b of blocks) {
      const bid = typeof b?.id === 'string' && b.id ? b.id : fail('a change has no id')
      if (ids.has(bid)) fail(`change id "${bid}" is repeated`)
      ids.add(bid)
      changeIds.push(bid)
      if (b.mode !== 'replace' && b.mode !== 'area') fail(`change "${bid}": mode must be replace or area`)
      if (!['code', 'data', 'free-code'].includes(b.kind)) fail(`change "${bid}": kind must be code, data or free-code`)
      if (!Array.isArray(b.new)) fail(`change "${bid}": new must be a list of parts`)
      const len = num(b.len, `change "${bid}" len`)
      if (len <= 0) fail(`change "${bid}": len must be more than zero`)

      let total = 0, hexText = '', allHex = true
      for (const p of b.new) {
        if (Array.isArray(p) && p[0] === 'hex' && p.length === 2 && typeof p[1] === 'string') {
          if (!HEX.test(p[1])) fail(`change "${bid}": hex part is not lowercase hex`)
          total += p[1].length / 2
          hexText += p[1]
        } else if (Array.isArray(p) && p[0] === 'stock' && p.length === 4 && b.mode === 'replace') {
          const k = num(p[2], `change "${bid}" stock len`)
          if (k <= 0) fail(`change "${bid}": empty stock part`)
          if (!SHA.test(p[3])) fail(`change "${bid}": stock part sha256 is malformed`)
          total += k
          allHex = false
        } else {
          fail(`change "${bid}": unknown part`)
        }
      }
      if (total !== len) fail(`change "${bid}": parts add to ${total}, len is ${len}`)
      if (b.new_sha256 != null && !SHA.test(b.new_sha256)) fail(`change "${bid}": new_sha256 is malformed`)
      const shaRequired = b.mode === 'replace' || b.new_sha256 != null
      if (allHex && shaRequired && sha256(fromHex(hexText)) !== b.new_sha256) fail(`change "${bid}": new_sha256 does not match its bytes`)

      if (b.mode === 'area') {
        if (!layout) fail(`change "${bid}": area changes need a top-level area`)
        if (b.kind === 'free-code' || 'addr' in b || 'section' in b || 'stock_sha256' in b) {
          fail(`change "${bid}": an area change has an offset, not an addr, section or stock_sha256`)
        }
        const off = num(b.offset, `change "${bid}" offset`)
        if (off < 0 || off + len > layout.size) fail(`change "${bid}": offset outside the mod area`)
        areaWrites.push({ id: bid, start: off, end: off + len })
      } else {
        if (b.section !== 3 && b.section !== 7) fail(`change "${bid}": section must be 3 or 7`)
        const addr = num(b.addr, `change "${bid}" addr`)
        if (addr < LOAD) fail(`change "${bid}": bad address`)
        if (!SHA.test(b.stock_sha256 ?? '')) fail(`change "${bid}": stock_sha256 is missing or malformed`)
        writes.push({ id: bid, start: addr, end: addr + len })
      }
    }
  }
  for (const clash of [firstOverlap(writes), firstOverlap(areaWrites)]) {
    if (clash) fail(overlapText(clash))
  }
  return {
    id: doc.id, title: doc.title ?? doc.id, requires, layout, changeIds, writes, areaWrites,
  }
}

// The ids to build, in dependency order: the selected ids plus their requirements. Refuses an unknown id, a
// requirement that is not in packagesById, and a loop. Ties keep the order of packagesById (the manifest order).
export function resolvePackages(packagesById, selectedIds) {
  if (!Array.isArray(selectedIds)) throw new Error('the selection must be a list of package ids')
  const reqs = id => (Array.isArray(packagesById[id]?.requires) ? packagesById[id].requires : [])
  const want = new Set()
  const queue = []
  for (const id of selectedIds) {
    if (!has(packagesById, id)) throw new Error(`unknown package "${id}"`)
    queue.push(id)
  }
  while (queue.length) {
    const id = queue.shift()
    if (want.has(id)) continue
    want.add(id)
    for (const r of reqs(id)) {
      if (!has(packagesById, r)) throw new Error(`package "${id}" needs "${r}", which is not available`)
      queue.push(r)
    }
  }
  const order = Object.keys(packagesById)
  const placed = []
  while (placed.length < want.size) {
    const next = order.find(id => want.has(id) && !placed.includes(id) && reqs(id).every(r => placed.includes(r)))
    if (!next) throw new Error('some packages require each other in a loop')
    placed.push(next)
  }
  return placed
}

// ONE .sypatch document from the packages in orderedIds (validated, with the same target and mod area layout, unique
// change ids, and no byte written twice). Units are concatenated in the given order.
export function mergePackages(packagesById, orderedIds) {
  if (!Array.isArray(orderedIds) || !orderedIds.length) throw new Error('no package is selected')
  const summaries = new Map()
  for (const id of orderedIds) {
    if (summaries.has(id)) throw new Error(`package "${id}" is listed twice`)
    if (!has(packagesById, id)) throw new Error(`unknown package "${id}"`)
    if (packagesById[id]?.id !== id) throw new Error(`package "${id}" does not carry that id`)
    summaries.set(id, validatePackage(packagesById[id]))
  }
  const list = [...summaries.values()]
  for (const s of list) {
    for (const r of s.requires) {
      if (!summaries.has(r)) throw new Error(`package "${s.id}" needs "${r}", which is not in the set`)
    }
  }
  const layouts = list.filter(s => s.layout)
  for (const s of layouts) {
    if (JSON.stringify(s.layout) !== JSON.stringify(layouts[0].layout)) {
      throw new Error(`the mod area layout of package "${s.id}" differs from package "${layouts[0].id}"`)
    }
  }
  const owner = new Map()
  for (const s of list) {
    for (const cid of s.changeIds) {
      if (owner.has(cid)) throw new Error(`change id "${cid}" is in package "${owner.get(cid)}" and in package "${s.id}"`)
      owner.set(cid, s.id)
    }
  }
  const replace = list.flatMap(s => s.writes.map(w => ({ ...w, pkg: s.id })))
  const area = list.flatMap(s => s.areaWrites.map(w => ({ ...w, pkg: s.id })))
  for (const writes of [replace, area]) {
    const clash = firstOverlap(writes)
    if (clash) throw new Error(overlapText(clash))
  }
  const doc = {
    format: 'synthack-patchset', schema: 1,
    id: [...orderedIds].sort().join('+'),
    title: list.map(s => s.title).join(' + '),
    encoding: 'lowercase-hex',
    target: { device: 'Syntakt', os: '1.41', stock_sha256: STOCK_SHA256 },
  }
  if (area.length) doc.area = { ...layouts[0].layout }
  doc.units = orderedIds.flatMap(id => packagesById[id].units ?? [])
  return doc
}
