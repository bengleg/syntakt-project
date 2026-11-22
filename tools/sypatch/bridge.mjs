// Runs a .sypatch through the elekloader engine (GPL, used privately for now): checks every site against
// the user's own stock file, checks instruction boundaries, applies, rebuilds the .syx in memory and verifies it.
// Pure: the engine modules are passed in (node-engine.mjs loads them from a path; the browser worker bundles them).
// Nothing here touches the file system, and the caller's stock bytes are copied before use.

import { toSites, toArea, areaImage } from './convert.mjs'
import { compress as shlz } from './lz.mjs'
import { pack } from './aplib.mjs'
import { toHex, fromHex } from './hex.mjs'

const padTo4 = b => (b.length % 4 ? Uint8Array.from([...b, ...new Uint8Array(4 - (b.length % 4))]) : b)

// The mod area, SHLZ-compressed and appended to the stock image: the engine's one blob, loaded at the image end.
// The zero gap runs from the image end to area.img, so the stream sits where modarea.S reads it.
function areaBlob(area, mainEnd, sha) {
  const gap = area.img - mainEnd
  if (gap < 0) throw new Error('the mod area starts inside the stock image')
  const raw = areaImage(area)
  if (raw.length > area.size) throw new Error(`mod area: ${raw.length} B, more than the ${area.size} B in RAM`)
  const pad = new Uint8Array(gap)
  const stream = shlz(raw)
  const bytes = Uint8Array.from([...pad, ...stream])
  return { load: mainEnd, len: bytes.length, sha256: sha(bytes), parts: [['hex', toHex(pad)], ['hex', toHex(stream)]] }
}

// engine: { sha, formats, elemod, devices, coldfire } from the engine's src (formats.ts, elemod.ts, devices.ts, isa/coldfire.ts).
export async function buildSyxWith(doc, callerStock, engine, { rebuild = true } = {}) {
  const { sha, formats, elemod, devices, coldfire } = engine
  const stockRaw = Uint8Array.from(callerStock)
  if (doc.target?.stock_sha256 !== sha(stockRaw)) throw new Error('the file is not the stock OS 1.41 (hash differs)')

  const [stock, dev, rel] = await formats.load(stockRaw)
  if (rel.version !== '1.41') throw new Error('only OS 1.41 is supported')

  const newCode = (bytes, addr, what) => {
    const r = coldfire.wholeInstructionsAt(bytes, addr, addr, bytes.length, 0)
    if (!r.ok) throw new Error(`${what}: ${r.note}`)
  }

  // Free-space code (zeros in stock) has no stock instructions to check, so its own bytes are checked here, and the
  // engine gets it as data. Stock-code sites keep the engine's check against the stock bytes.
  const sites = toSites(doc).map(s => {
    if (s.kind !== 'free-code') return s
    newCode(fromHex(s.new), Number(s.addr), `${s.addr} (new code in free space)`)
    return { ...s, kind: 'data' }
  })
  const area = toArea(doc)
  for (const b of area?.blocks ?? []) {
    if (b.kind === 'code') newCode(b.bytes, area.ram + b.offset, `${b.id} (mod area code)`)
  }
  const modDoc = {
    elemod: 1, id: doc.id, version: '1', target: devices.targetOf(dev, rel), sites,
  }
  if (area) modDoc.blob = areaBlob(area, devices.imageEnd(dev, rel), sha)
  const mod = new elemod.Mod(modDoc, doc.id)
  const image = formats.mainImage(stock, dev)
  const out = elemod.apply([mod], image)
  if (!rebuild) return { syx: null, image: out, sites: mod.sites }
  const outputs = formats.write(stock, padTo4(pack(out, 3)), dev, null)
  formats.verify(outputs, stock, out, dev, null)
  return { syx: outputs.syx, image: out, sites: mod.sites }
}
