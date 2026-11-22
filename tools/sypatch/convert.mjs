// Pure conversion: .sypatch blocks -> the engine's format-1 sites (replace) and the mod area (area). No engine import here.
// Stock parts are not supported yet (Round 2); a block that uses one is refused, not guessed at.

import { fromHex } from './hex.mjs'

const HEX = /^(?:[0-9a-f]{2})*$/
const SHA = /^[0-9a-f]{64}$/

const num = (v, what) => {
  const n = typeof v === 'string' ? Number(v) : v
  if (!Number.isInteger(n)) throw new Error(`${what}: not a number: ${v}`)
  return n
}

export function toSites(doc) {
  const sites = []
  for (const unit of doc.units ?? []) {
    for (const b of unit.blocks ?? []) {
      if (b.mode === 'area') continue
      if (b.mode !== 'replace') throw new Error(`${b.id}: only replace and area blocks are supported`)
      const parts = b.new ?? []
      if (parts.some(p => p[0] !== 'hex')) throw new Error(`${b.id}: stock parts are not supported yet`)
      const hex = parts.map(p => p[1]).join('')
      if (!HEX.test(hex)) throw new Error(`${b.id}: replacement is not lowercase hex`)
      if (hex.length / 2 !== b.len) throw new Error(`${b.id}: ${hex.length / 2} bytes, len is ${b.len}`)
      if (!SHA.test(b.stock_sha256 ?? '')) throw new Error(`${b.id}: stock_sha256 malformed`)
      if (!['code', 'data', 'free-code'].includes(b.kind)) throw new Error(`${b.id}: kind must be code, data or free-code`)
      sites.push({ addr: b.addr, len: b.len, new: hex, kind: b.kind, stock_sha256: b.stock_sha256 })
    }
  }
  return sites
}

// Area blocks: our bytes at an offset from the start of the mod area (RAM = area.ram). They claim no stock bytes.
// -> null, or { img, ram, size, blocks: [{ id, kind, offset, bytes }] } with the area's bounds and overlaps checked.
export function toArea(doc) {
  const blocks = (doc.units ?? []).flatMap(u => (u.blocks ?? []).filter(b => b.mode === 'area'))
  if (!blocks.length) return null
  const area = doc.area
  if (area?.compress !== 'shlz') throw new Error('area blocks need doc.area with compress "shlz"')
  const img = num(area.img, 'area.img'), ram = num(area.ram, 'area.ram'), size = num(area.size, 'area.size')
  const out = blocks.map(b => {
    const offset = num(b.offset, `${b.id} offset`)
    const hex = (b.new ?? []).map(p => (p[0] === 'hex' ? p[1] : '!')).join('')
    if (!(b.new ?? []).every(p => p[0] === 'hex') || !HEX.test(hex)) throw new Error(`${b.id}: area bytes must be lowercase hex`)
    if (hex.length / 2 !== b.len) throw new Error(`${b.id}: ${hex.length / 2} bytes, len is ${b.len}`)
    if (offset < 0 || offset + b.len > size) throw new Error(`${b.id}: offset ${offset} +${b.len} is outside the ${size} B area`)
    if (b.kind !== 'code' && b.kind !== 'data') throw new Error(`${b.id}: area kind must be code or data`)
    if (b.new_sha256 !== undefined && !SHA.test(b.new_sha256)) throw new Error(`${b.id}: new_sha256 malformed`)
    return { id: b.id, kind: b.kind, offset, bytes: fromHex(hex) }
  })
  const sorted = [...out].sort((a, b) => a.offset - b.offset)
  for (let k = 1; k < sorted.length; k++) {
    const p = sorted[k - 1], q = sorted[k]
    if (q.offset < p.offset + p.bytes.length) throw new Error(`${p.id} and ${q.id} overlap in the mod area`)
  }
  return { img, ram, size, blocks: out }
}

// The mod area as the RAM will see it, from its start to the last byte written; the gaps are zero.
export function areaImage(area) {
  const end = Math.max(0, ...area.blocks.map(b => b.offset + b.bytes.length))
  const out = new Uint8Array(end)
  for (const b of area.blocks) out.set(b.bytes, b.offset)
  return out
}
