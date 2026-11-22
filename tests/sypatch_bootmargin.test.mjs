// Run: node --test tests/sypatch_bootmargin.test.mjs
// Synthetic payloads need no firmware. The real-file test runs only when these are set (local files, never committed):
//   SYNTAKT_STOCK        path to the stock OS 1.41 .syx
//   ELEKLOADER_JS        path to the engine's js/src folder

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { pack, depack, depackMargin, SECT_HDR } from '../tools/sypatch/aplib.mjs'
import { checkBootMargin, MIN_MARGIN } from '../tools/sypatch/bootmargin.mjs'
import { loadEngine } from '../tools/sypatch/node-engine.mjs'

const { SYNTAKT_STOCK, ELEKLOADER_JS } = process.env
const real = SYNTAKT_STOCK && ELEKLOADER_JS && [SYNTAKT_STOCK, ELEKLOADER_JS].every(p => existsSync(p))

const lcg = n => {
  const a = new Uint8Array(n)
  let x = 1
  for (let i = 0; i < n; i++) {
    x = (x * 1103515245 + 12345) >>> 0
    a[i] = x >>> 16
  }
  return a
}

const periodic = n => Uint8Array.from({ length: n }, (_, i) => 'abcdefgh'.charCodeAt(i % 8))

// Hand-made stream: one literal, then reuse matches of 2047 (2048 bytes out, about 3 bytes in each).
// Output races past input, so the margin goes negative. Same bit layout as the packer in aplib.mjs.
function racingSection(matches) {
  const o = new Uint8Array(SECT_HDR + 16 + matches * 4)
  let n = SECT_HDR, tagpos = -1, tagbits = 0
  const flag = b => {
    if (tagbits === 0) { tagpos = n; o[n++] = 0; tagbits = 8 }
    if (b) o[tagpos] |= 1 << (tagbits - 1)
    tagbits--
  }
  const gamma = v => {
    const nb = v.toString(2).length
    for (let i = nb - 2; i >= 0; i--) { flag((v >>> i) & 1); flag(i === 0 ? 1 : 0) }
  }
  flag(1); o[n++] = 0x41
  for (let k = 0; k < matches; k++) {
    flag(0); gamma(2)
    flag(0); flag(0)
    gamma(2045)
  }
  return o.slice(0, n)
}

test('a highly repetitive payload leaves a large positive margin', () => {
  const r = depackMargin(pack(new Uint8Array(4096)))
  assert.ok(r.margin > 2_000_000, `margin ${r.margin}`)
  assert.doesNotThrow(() => checkBootMargin(pack(new Uint8Array(4096))))
})

test('a poorly compressible payload leaves more room than a repetitive one, and passes', () => {
  const noisy = depackMargin(pack(lcg(4096))).margin
  const flat = depackMargin(pack(new Uint8Array(4096))).margin
  assert.ok(noisy > flat, `noisy ${noisy} flat ${flat}`)
  assert.ok(noisy >= MIN_MARGIN)
})

test('margin shrinks as the same payload is lengthened', () => {
  const margins = [512, 1024, 2048, 4096].map(n => depackMargin(pack(periodic(n))).margin)
  for (let i = 1; i < margins.length; i++) assert.ok(margins[i] < margins[i - 1], `${margins}`)
})

test('reported size equals the original payload length', () => {
  for (const n of [1, 300, 4096]) assert.equal(depackMargin(pack(periodic(n))).size, n)
})

test('a stream that output races past makes checkBootMargin throw', () => {
  const s = racingSection(1100)
  assert.ok(depackMargin(s).margin < 0)
  assert.throws(() => checkBootMargin(s), /Boot room is short/)
})

test('a truncated stream ends without throwing', () => {
  const s = pack(periodic(4096))
  assert.doesNotThrow(() => depackMargin(s.slice(0, s.length >> 1)))
  assert.doesNotThrow(() => depackMargin(s.slice(0, SECT_HDR + 1)))
  assert.doesNotThrow(() => depackMargin(new Uint8Array(SECT_HDR)))
})

test('the real stock OS 1.41 section 3 leaves 99938 bytes of room and passes', { skip: !real && 'needs local files' }, async () => {
  const engine = await loadEngine(ELEKLOADER_JS)
  const stock = readFileSync(SYNTAKT_STOCK)
  const [parsed, dev] = await engine.formats.load(stock)
  const stream = parsed.stored.get(dev.mainSection)
  // The figure tools/build/bootcheck.py and tests/test_bootcheck.py record for stock OS 1.41.
  assert.equal(depackMargin(stream).margin, 99938)
  assert.equal(depackMargin(stream).size, depack(stream).length)
  assert.doesNotThrow(() => checkBootMargin(stream))
})
