// Run: node --test tests/engine_bridge.test.mjs
// Synthetic tests always run. The real-firmware test runs only when these are set (local files, never committed):
//   SYNTAKT_STOCK        path to the stock OS 1.41 .syx
//   ELEKLOADER_JS        path to the engine's js/src folder
//   SYNTAKT_LEGACY_PATCH path to mods/delay-control/patch.json
//   SYNTAKT_V2O          path to a local build made from that patch (optional, for the comparison)

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import path from 'node:path'
import { toSites, toArea, areaImage } from '../tools/sypatch/convert.mjs'
import { buildSyx } from '../tools/sypatch/node-engine.mjs'
import { pack, depack } from '../tools/sypatch/aplib.mjs'
import { compress as shlz, decompress as unshlz } from '../tools/sypatch/lz.mjs'
import { delayControlDoc, DATA } from '../tools/sypatch/delay_control.mjs'
import { resolvePackages, mergePackages } from '../tools/sypatch/merge.mjs'

test('packer round-trips synthetic data', () => {
  const data = Uint8Array.from({ length: 5000 }, (_, i) => (i * 7 + (i >> 5)) & 0xff)
  assert.equal(Buffer.from(depack(pack(data))).equals(Buffer.from(data)), true)
})

test('packer writes an 8-byte header for an empty section', () => {
  assert.equal(pack(new Uint8Array(0)).length, 8)
})

test('depacker refuses a truncated stream', () => {
  const data = Uint8Array.from({ length: 2000 }, (_, i) => (i * 13) & 0xff)
  assert.throws(() => depack(pack(data).subarray(0, 40)))
})

const sha = b => createHash('sha256').update(b).digest('hex')
const STOCK_SHA = '8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e'
const { SYNTAKT_STOCK, ELEKLOADER_JS, SYNTAKT_LEGACY_PATCH, SYNTAKT_V2O } = process.env
const real = SYNTAKT_STOCK && ELEKLOADER_JS && SYNTAKT_LEGACY_PATCH
  && [SYNTAKT_STOCK, SYNTAKT_LEGACY_PATCH].every(p => existsSync(p))

const block = (over = {}) => ({
  id: 'b', mode: 'replace', section: 3, addr: '0x4010a100', len: 4, kind: 'data',
  stock_sha256: 'ab'.repeat(32), new: [['hex', '4600b400']], new_sha256: null, ...over,
})

test('converts a valid hex block to an engine site', () => {
  const [s] = toSites({ units: [{ blocks: [block()] }] })
  assert.equal(s.addr, '0x4010a100')
  assert.equal(s.new, '4600b400')
})

test('refuses stock parts until they are supported', () => {
  const b = block({ new: [['stock', '0x4010a100', '4', 'cd'.repeat(32)]] })
  assert.throws(() => toSites({ units: [{ blocks: [b] }] }), /stock parts are not supported/)
})

test('refuses a length that does not match the bytes', () => {
  assert.throws(() => toSites({ units: [{ blocks: [block({ len: 8 })] }] }), /4 bytes, len is 8/)
})

test('refuses uppercase hex', () => {
  assert.throws(() => toSites({ units: [{ blocks: [block({ new: [['hex', '4600B400']] })] }] }), /lowercase hex/)
})

// Reference bytes from tools/build/lz.py (same input, same output).
const LZ_INPUT = Uint8Array.from([
  ...Array.from({ length: 120 }, (_, i) => (i * 7 + (i >> 4)) & 0xff), ...new Uint8Array(80), ...Array.from({ length: 40 }, (_, i) => i % 20),
])
const LZ_REF = '53484c5a000000f0000000947800070e151c232a31383f464d545b626971787f868d949ba2a9b0b7bec5ccd3dae2e9f0f7fe050c131a21282f363d444b535a61686f767d848b9299a0a7aeb5bcc4cbd2d9e0e7eef5fc030a11181f262d353c434a51585f666d747b828990979ea6adb4bbc2c9d0d7dee5ecf3fa01080f171e252c333a414800cd0001120102030405060708090a0b0c0d0e0f10111213910014'

test('SHLZ port matches tools/build/lz.py byte for byte and round-trips', () => {
  assert.equal(Buffer.from(shlz(LZ_INPUT)).toString('hex'), LZ_REF)
  assert.equal(Buffer.from(unshlz(shlz(LZ_INPUT))).equals(Buffer.from(LZ_INPUT)), true)
})

test('SHLZ refuses a truncated stream and a bad distance', () => {
  const s = shlz(LZ_INPUT)
  assert.throws(() => unshlz(s.subarray(0, 40)), /truncated/)
  const bad = Uint8Array.from([0x53, 0x48, 0x4c, 0x5a, 0, 0, 0, 3, 0, 0, 0, 3, 0x80, 0, 5])
  assert.throws(() => unshlz(bad), /distance/)
})

const AREA = { img: '0x40348000', ram: '0x46000000', size: '0x10000', compress: 'shlz' }
const abloc = (id, offset, hex) => ({ id, mode: 'area', offset, len: hex.length / 2, kind: 'code', new: [['hex', hex]] })
const adoc = blocks => ({ target: { stock_sha256: 'ab'.repeat(32) }, area: AREA, units: [{ blocks }] })

test('area: blocks land at their offsets, gaps are zero', () => {
  const area = toArea(adoc([abloc('a', 0x4000, '01020304'), abloc('b', 0x4010, 'aabb')]))
  assert.equal(Buffer.from(areaImage(area)).toString('hex'), '00'.repeat(0x4000) + '01020304' + '00'.repeat(12) + 'aabb')
  assert.equal(toSites(adoc([abloc('a', 0x4000, '01020304')])).length, 0)
})

test('area: refuses overlap, out-of-bounds, a missing layout and non-hex', () => {
  assert.throws(() => toArea(adoc([abloc('a', 0x4000, '0102'), abloc('b', 0x4001, '03')])), /overlap/)
  assert.throws(() => toArea(adoc([abloc('a', 0xffff, '0102')])), /outside the 65536 B area/)
  assert.throws(() => toArea({ units: [{ blocks: [abloc('a', 0, '01')] }] }), /compress "shlz"/)
  assert.throws(() => toArea(adoc([{ ...abloc('a', 0, '01'), new: [['hex', '0G']] }])), /lowercase hex/)
})

test('refuses a wrong stock hash before touching the engine', async () => {
  await assert.rejects(
    buildSyx({ id: 'x', target: { stock_sha256: '00'.repeat(32) }, units: [] }, Buffer.from('not firmware'), '.'),
    /not the stock OS 1.41/,
  )
})

function legacyDoc() {
  const legacy = JSON.parse(readFileSync(SYNTAKT_LEGACY_PATCH, 'utf8'))
  const blocks = legacy.patches.filter(p => !p.append).map((p, i) => {
    const a = p.addr.replace(/^0x/i, '').toUpperCase()
    return {
      id: `fixed-${i}-${a}`, mode: 'replace', section: 3, addr: '0x' + a.toLowerCase(), len: p.len,
      kind: DATA.has(a) ? 'data' : 'code', stock_sha256: p.expect_sha256, new: [['hex', p.hex]],
      new_sha256: sha(Buffer.from(p.hex, 'hex')),
    }
  })
  return {
    format: 'synthack-patchset', schema: 1, id: 'delay-control-fixed', encoding: 'lowercase-hex',
    target: { device: 'Syntakt', os: '1.41', stock_sha256: STOCK_SHA },
    units: [{ id: 'delay-control', blocks }],
  }
}

test('DelayCtrl fixed blocks: every site applied and boundary-checked', { skip: !real && 'needs local files' }, async () => {
  const doc = legacyDoc()
  const blocks = doc.units[0].blocks
  const stockRaw = readFileSync(SYNTAKT_STOCK)
  const { image, sites } = await buildSyx(doc, stockRaw, ELEKLOADER_JS, { rebuild: false })
  assert.equal(sites.length, blocks.length)
  for (const s of sites) {
    const off = Number(s.addr) - 0x40000400
    assert.equal(Buffer.from(image.subarray(off, off + s.len)).toString('hex'), Buffer.from(s.new).toString('hex'))
  }
  if (SYNTAKT_V2O && existsSync(SYNTAKT_V2O)) {
    const formats = await import(pathToFileURL(path.join(ELEKLOADER_JS, 'formats.ts')).href)
    const devices = await import(pathToFileURL(path.join(ELEKLOADER_JS, 'devices.ts')).href)
    const [dev] = devices.identify(sha(stockRaw))
    const built = formats.mainImage(formats.parse(readFileSync(SYNTAKT_V2O), dev), dev)
    for (const s of sites) {
      const off = Number(s.addr) - 0x40000400
      assert.equal(Buffer.from(built.subarray(off, off + s.len)).toString('hex'), Buffer.from(s.new).toString('hex'), `v2o at ${s.addr}`)
    }
  }
})

test('DelayCtrl fixed blocks: rebuilt .syx verifies and re-reads to the intended section 3', {
  skip: !real && 'needs local files',
}, async () => {
  const stockRaw = readFileSync(SYNTAKT_STOCK)
  const { syx, image } = await buildSyx(legacyDoc(), stockRaw, ELEKLOADER_JS)
  assert.ok(syx.length > 0)
  const formats = await import(pathToFileURL(path.join(ELEKLOADER_JS, 'formats.ts')).href)
  const devices = await import(pathToFileURL(path.join(ELEKLOADER_JS, 'devices.ts')).href)
  const [dev] = devices.identify(STOCK_SHA)
  const back = formats.mainImage(formats.parse(syx, dev), dev)
  assert.equal(Buffer.from(back).equals(Buffer.from(image)), true)
})

// The full DelayCtrl build as the builder sees it (tools/sypatch/delay_control.mjs): our bytes only.
function fullDoc() {
  return delayControlDoc(
    JSON.parse(readFileSync(SYNTAKT_LEGACY_PATCH, 'utf8')).patches,
    JSON.parse(readFileSync(new URL('../mods/modarea/patch.json', import.meta.url), 'utf8')).patches,
  )
}
test('full DelayCtrl build: the image (stock + mod area) equals the v2o build', {
  skip: !(real && SYNTAKT_V2O && existsSync(SYNTAKT_V2O)) && 'needs local files and the v2o build',
}, async () => {
  const stockRaw = readFileSync(SYNTAKT_STOCK)
  const { image } = await buildSyx(fullDoc(), stockRaw, ELEKLOADER_JS, { rebuild: false })
  const formats = await import(pathToFileURL(path.join(ELEKLOADER_JS, 'formats.ts')).href)
  const devices = await import(pathToFileURL(path.join(ELEKLOADER_JS, 'devices.ts')).href)
  const [dev] = devices.identify(sha(stockRaw))
  const built = formats.mainImage(formats.parse(readFileSync(SYNTAKT_V2O), dev), dev)
  assert.equal(image.length, built.length, 'image length')
  assert.equal(Buffer.from(image).equals(Buffer.from(built)), true, 'image bytes')
})

test('full DelayCtrl build: the rebuilt .syx is the v2o file, byte for byte', {
  skip: !(real && SYNTAKT_V2O && existsSync(SYNTAKT_V2O)) && 'needs local files and the v2o build',
}, async () => {
  const stockRaw = readFileSync(SYNTAKT_STOCK)
  const { syx } = await buildSyx(fullDoc(), stockRaw, ELEKLOADER_JS)
  assert.equal(sha(syx), sha(readFileSync(SYNTAKT_V2O)))
})

// The shipped v2o set split into two packages (the modarea unit, then the DelayCtrl unit) and merged back by the
// package path: the same .syx as the single file, byte for byte.
const v2oSet = JSON.parse(readFileSync(new URL('../web/patches/delay-control.sypatch.json', import.meta.url), 'utf8'))
test('packages: the v2o set split in two and merged builds the v2o file, byte for byte', {
  skip: !(SYNTAKT_STOCK && ELEKLOADER_JS && SYNTAKT_V2O && [SYNTAKT_STOCK, SYNTAKT_V2O].every(p => existsSync(p)))
    && 'needs local files and the v2o build',
}, async () => {
  const [modarea, dc] = v2oSet.units
  const packages = {
    'modarea-part': { ...v2oSet, id: 'modarea-part', units: [modarea] },
    'dc-part': { ...v2oSet, id: 'dc-part', requires: ['modarea-part'], units: [dc] },
  }
  const doc = mergePackages(packages, resolvePackages(packages, ['dc-part']))
  const { syx } = await buildSyx(doc, readFileSync(SYNTAKT_STOCK), ELEKLOADER_JS)
  assert.equal(sha(syx), sha(readFileSync(SYNTAKT_V2O)))
})
