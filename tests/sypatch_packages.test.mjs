// Run: node --test tests/sypatch_packages.test.mjs
// Synthetic packages only: no firmware, no engine. The shipped package files are read only when they exist.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { sha256 } from '../tools/sypatch/sha256.mjs'
import { validatePackage, resolvePackages, mergePackages, STOCK_SHA256 } from '../tools/sypatch/merge.mjs'

const nodeSha = hex => createHash('sha256').update(Buffer.from(hex, 'hex')).digest('hex')
const fakeSha = s => createHash('sha256').update(s).digest('hex')
const AREA = { img: '0x40348000', ram: '0x46000000', size: '0x10000', compress: 'shlz' }
const AREA_NUMBERS = { img: 0x40348000, ram: 0x46000000, size: 0x10000, compress: 'shlz' }

function hexChange(id, addr, hex, extra = {}) {
  return {
    id, mode: 'replace', section: 3, addr, len: hex.length / 2, kind: 'data',
    stock_sha256: fakeSha(id), new: [['hex', hex]], new_sha256: nodeSha(hex), ...extra,
  }
}

function areaChange(id, offset, hex) {
  return { id, mode: 'area', offset, len: hex.length / 2, kind: 'data', new: [['hex', hex]], new_sha256: nodeSha(hex) }
}

function pkg(id, blocks = [], { requires, area, title } = {}) {
  const doc = {
    format: 'synthack-patchset', schema: 1, id, title: title ?? `Package ${id}`, encoding: 'lowercase-hex',
    target: { device: 'Syntakt', os: '1.41', stock_sha256: STOCK_SHA256 },
    units: [{ id: `${id}-unit`, title: 'Unit', blocks }],
  }
  if (requires) doc.requires = requires
  if (area) doc.area = { ...AREA }
  return doc
}

const byId = docs => Object.fromEntries(docs.map(d => [d.id, d]))

test('sha256 matches node:crypto for lengths around the padding edges', () => {
  for (const n of [0, 1, 55, 56, 63, 64, 65, 119, 120, 1000]) {
    const bytes = Uint8Array.from({ length: n }, (_, i) => (i * 37 + 11) & 0xff)
    assert.equal(sha256(bytes), createHash('sha256').update(bytes).digest('hex'), `length ${n}`)
  }
})

test('a valid package passes and reports its id, title and writes', () => {
  const s = validatePackage(pkg('core', [hexChange('c1', 0x4010a100, '4eb94010b000')]))
  assert.equal(s.id, 'core')
  assert.equal(s.title, 'Package core')
  assert.deepEqual(s.writes, [{ id: 'c1', start: 0x4010a100, end: 0x4010a106 }])
})

test('a package for another target is refused', () => {
  const wrongOs = pkg('a', [hexChange('x', 0x4010a100, '01')])
  wrongOs.target.os = '1.42'
  assert.throws(() => validatePackage(wrongOs), /package "a": the target is not Syntakt OS 1\.41/)
  const wrongHash = pkg('b', [hexChange('x', 0x4010a100, '01')])
  wrongHash.target.stock_sha256 = '00'.repeat(32)
  assert.throws(() => validatePackage(wrongHash), /stock_sha256 is not the OS 1\.41 hash/)
})

test('an id is required, lowercase, and is named in the error', () => {
  assert.throws(() => validatePackage({ ...pkg('x'), id: undefined }), /package id must be/)
  assert.throws(() => validatePackage(pkg('Bad Id')), /package id must be/)
})

test('requires must be a list of ids, and a package cannot require itself', () => {
  assert.throws(() => validatePackage(pkg('a', [], { requires: 'core' })), /requires must be a list/)
  assert.throws(() => validatePackage(pkg('a', [], { requires: ['a'] })), /cannot require itself/)
})

test('length, new_sha256 and stock_sha256 are checked', () => {
  const short = hexChange('x', 0x4010a100, '01020304', { len: 6 })
  assert.throws(() => validatePackage(pkg('a', [short])), /parts add to 4, len is 6/)
  const badSha = hexChange('x', 0x4010a100, '01020304', { new_sha256: 'ab'.repeat(32) })
  assert.throws(() => validatePackage(pkg('a', [badSha])), /new_sha256 does not match/)
})

test('a data change without stock_sha256 is refused', () => {
  const b = hexChange('x', 0x4010a100, '01020304')
  delete b.stock_sha256
  assert.throws(() => validatePackage(pkg('a', [b])), /stock_sha256 is missing or malformed/)
})

test('overlapping writes inside one package are refused', () => {
  const two = [hexChange('p', 0x4010a100, '01020304'), hexChange('q', 0x4010a102, '0506')]
  assert.throws(() => validatePackage(pkg('a', two)), /package "a": change "p" and change "q" change the same bytes/)
})

test('requires are added transitively, in manifest order, and unmet ones are refused', () => {
  const docs = byId([
    pkg('a'),
    pkg('b', [], { requires: ['a'] }),
    pkg('c', [], { requires: ['b'] }),
  ])
  assert.deepEqual(resolvePackages(docs, ['c']), ['a', 'b', 'c'])
  assert.deepEqual(resolvePackages(docs, ['c', 'a']), ['a', 'b', 'c'])
  const shuffled = byId([pkg('c'), pkg('a'), pkg('b', [], { requires: ['a'] })])
  assert.deepEqual(resolvePackages(shuffled, ['b', 'c']), ['c', 'a', 'b'])
  assert.throws(() => resolvePackages(byId([pkg('x', [], { requires: ['missing'] })]), ['x']), /needs "missing", which is not available/)
})

test('an unknown selected id is refused, and a requirement loop is refused', () => {
  const docs = byId([pkg('a')])
  assert.throws(() => resolvePackages(docs, ['nope']), /unknown package "nope"/)
  const loop = byId([pkg('a', [], { requires: ['b'] }), pkg('b', [], { requires: ['a'] })])
  assert.throws(() => resolvePackages(loop, ['a']), /loop/)
})

test('overlapping replace writes across two packages are refused', () => {
  const docs = byId([pkg('a', [hexChange('a1', 0x4010a100, '01020304')]), pkg('b', [hexChange('b1', 0x4010a102, '0506')])])
  assert.throws(() => mergePackages(docs, ['a', 'b']), /change "a1" of package "a" and change "b1" of package "b" change the same bytes/)
})

test('overlapping area writes across two packages are refused', () => {
  const docs = byId([
    pkg('a', [areaChange('a1', 0x4000, '01020304')], { area: true }),
    pkg('b', [areaChange('b1', 0x4002, '0506')], { area: true }),
  ])
  assert.throws(() => mergePackages(docs, ['a', 'b']), /change the same bytes/)
})

test('duplicate change ids across packages are refused', () => {
  const docs = byId([pkg('a', [hexChange('x', 0x4010a100, '01')]), pkg('b', [hexChange('x', 0x4010a200, '02')])])
  assert.throws(() => mergePackages(docs, ['a', 'b']), /change id "x" is in package "a" and in package "b"/)
})

test('mismatched area layouts are refused', () => {
  const b = pkg('b', [areaChange('b1', 0x4000, '01')], { area: true })
  b.area.size = '0x8000'
  const docs = byId([pkg('a', [areaChange('a1', 0x8000, '02')], { area: true }), b])
  assert.throws(() => mergePackages(docs, ['a', 'b']), /mod area layout of package "b" differs from package "a"/)
})

test('a data change without stock_sha256 is refused at merge too', () => {
  const b = hexChange('x', 0x4010a100, '01020304')
  delete b.stock_sha256
  assert.throws(() => mergePackages(byId([pkg('a', [b])]), ['a']), /stock_sha256/)
})

test('a deselected package contributes nothing', () => {
  const docs = byId([pkg('a', [hexChange('a1', 0x4010a100, '01')]), pkg('b', [hexChange('b1', 0x4010a200, '02')])])
  assert.deepEqual(resolvePackages(docs, ['a']), ['a'])
  const merged = mergePackages(docs, ['a'])
  assert.deepEqual(merged.units.map(u => u.id), ['a-unit'])
  assert.equal(merged.id, 'a')
})

test('the merge is deterministic for the same input order, and the area appears only with area changes', () => {
  const docs = byId([
    pkg('a', [hexChange('a1', 0x4010a100, '01020304')], { area: true }),
    pkg('b', [hexChange('b1', 0x4010a200, '0506')]),
  ])
  const first = JSON.stringify(mergePackages(docs, ['a', 'b']))
  assert.equal(first, JSON.stringify(mergePackages(docs, ['a', 'b'])))
  const flipped = mergePackages(docs, ['b', 'a'])
  assert.equal(flipped.id, 'a+b')
  assert.deepEqual(flipped.units.map(u => u.id), ['b-unit', 'a-unit'])
  assert.equal(flipped.area, undefined)
  const withArea = mergePackages(byId([pkg('c', [areaChange('c1', 0x10, '01')], { area: true })]), ['c'])
  assert.deepEqual(withArea.area, AREA_NUMBERS)
})

test('the shipped v2o reference passes the package checks', () => {
  const doc = JSON.parse(readFileSync(new URL('../web/patches/delay-control.sypatch.json', import.meta.url), 'utf8'))
  assert.equal(validatePackage(doc).id, 'delay-control-full')
})

const manifestPath = new URL('../web/patches/manifest.json', import.meta.url)

test('the shipped feature packages resolve and merge', { skip: !existsSync(manifestPath) && 'needs web/patches/manifest.json' }, () => {
  const read = p => JSON.parse(readFileSync(new URL(`../web/patches/${p}`, import.meta.url), 'utf8'))
  const { packages } = read('manifest.json')
  const docs = Object.fromEntries(packages.map(p => [p.id, read(p.file)]))
  const ids = Object.keys(docs).filter(id => id.startsWith('delay-control-'))
  assert.ok(ids.length, 'the manifest lists the feature packages')
  const ordered = resolvePackages(docs, ids)
  assert.equal(new Set(ordered).size, ordered.length)
  const merged = mergePackages(docs, ordered)
  assert.equal(merged.target.os, '1.41')
})
