// Run: node --test tests/sypatch_analyze.test.mjs
// Synthetic packages only: no firmware, no engine. The shipped package and notes files are read only when they exist.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { validatePackage, mergePackages, STOCK_SHA256 } from '../tools/sypatch/merge.mjs'
import { analyzeSelection, conflictsIfAdded, noteFor } from '../tools/sypatch/analyze.mjs'

const nodeSha = hex => createHash('sha256').update(Buffer.from(hex, 'hex')).digest('hex')
const fakeSha = s => createHash('sha256').update(s).digest('hex')
const AREA = { img: '0x40348000', ram: '0x46000000', size: '0x10000', compress: 'shlz' }

function hexChange(id, addr, hex) {
  return {
    id, mode: 'replace', section: 3, addr, len: hex.length / 2, kind: 'data',
    stock_sha256: fakeSha(id), new: [['hex', hex]], new_sha256: nodeSha(hex), why: 'synthetic',
  }
}

function areaChange(id, offset, hex) {
  return { id, mode: 'area', offset, len: hex.length / 2, kind: 'data', new: [['hex', hex]], new_sha256: nodeSha(hex), why: 'synthetic' }
}

function pkg(id, blocks = [], { title, info, requires, area } = {}) {
  const doc = {
    format: 'synthack-patchset', schema: 1, id, title: title ?? `Package ${id}`, encoding: 'lowercase-hex',
    target: { device: 'Syntakt', os: '1.41', stock_sha256: STOCK_SHA256 },
    units: [{ id: `${id}-unit`, title: 'Unit', blocks }],
  }
  if (requires) doc.requires = requires
  if (area) doc.area = { ...AREA }
  if (info !== undefined) doc.info = info
  return doc
}

const byId = docs => Object.fromEntries(docs.map(d => [d.id, d]))

test('two mods that change the same program bytes give one os-bytes conflict naming both', () => {
  const docs = byId([
    pkg('freeze', [hexChange('f1', 0x4010a100, '01020304')], { title: 'Freeze' }),
    pkg('other', [hexChange('o1', 0x4010a102, '0506')], { title: 'Another mod' }),
  ])
  const r = analyzeSelection(docs, {}, ['freeze', 'other'])
  assert.equal(r.conflicts.length, 1)
  const [c] = r.conflicts
  assert.equal(c.kind, 'os-bytes')
  assert.deepEqual([c.a, c.b], ['freeze', 'other'])
  assert.equal(c.text, "Freeze and Another mod both change the same place in the Syntakt's own program (0x4010a102).")
  assert.doesNotMatch(c.text, /block/i)
  assert.equal(r.blocking, true)
})

test('two mods that want the same patch memory give a patch-memory conflict', () => {
  const docs = byId([
    pkg('a', [areaChange('a1', 0x4000, '01020304')], { area: true, title: 'Alpha' }),
    pkg('b', [areaChange('b1', 0x4002, '0506')], { area: true, title: 'Beta' }),
  ])
  const r = analyzeSelection(docs, {}, ['a', 'b'])
  assert.deepEqual(r.conflicts.map(c => c.kind), ['patch-memory'])
  assert.equal(r.conflicts[0].text, 'Alpha and Beta both use the same part of the shared patch memory (offset 0x4002).')
})

test('a declared conflict is found whichever mod declares it, and the curated notes override the file', () => {
  const declaresB = byId([pkg('a', [], { info: { conflicts: ['b'] } }), pkg('b')])
  const declaredByB = byId([pkg('a'), pkg('b', [], { info: { conflicts: ['a'] } })])
  for (const docs of [declaresB, declaredByB]) {
    const r = analyzeSelection(docs, {}, ['a', 'b'])
    assert.deepEqual(r.conflicts.map(c => c.kind), ['declared'])
  }
  const curatedClears = analyzeSelection(declaresB, { a: { conflicts: [] } }, ['a', 'b'])
  assert.deepEqual(curatedClears.conflicts, [])
})

test('two mods that claim the same thing give a claim conflict', () => {
  const docs = byId([
    pkg('a', [], { title: 'Alpha' }),
    pkg('b', [], { title: 'Beta' }),
  ])
  const info = { a: { claims: ['ui:TRIG 13-16 on the FX track'] }, b: { claims: ['ui:TRIG 13-16 on the FX track'] } }
  const r = analyzeSelection(docs, info, ['a', 'b'])
  assert.deepEqual(r.conflicts.map(c => c.kind), ['claim'])
  assert.equal(r.conflicts[0].text, 'Alpha and Beta both claim the same thing: TRIG 13-16 on the FX track.')
})

test('sizes add up per mod and in total, with the common patch memory size', () => {
  const docs = byId([
    pkg('a', [hexChange('a1', 0x4010a100, '01020304'), hexChange('a2', 0x4010a200, '0506'), areaChange('a3', 0x4000, '010203')], { area: true }),
    pkg('b', [hexChange('b1', 0x4010a300, '07')]),
  ])
  const r = analyzeSelection(docs, {}, ['a', 'b'])
  assert.deepEqual(r.size.perPackage.a, { areaBytes: 3, osBytes: 6, osPlaces: 2 })
  assert.deepEqual(r.size.perPackage.b, { areaBytes: 0, osBytes: 1, osPlaces: 1 })
  assert.equal(r.size.totals.areaBytes, 3)
  assert.equal(r.size.totals.areaSize, 0x10000)
  assert.equal(r.size.totals.osPlaces, 3)
  assert.ok(Math.abs(r.size.totals.areaPercent - (3 / 0x10000) * 100) < 1e-9)
})

test('cost sums the measured mods, and any unmeasured mod makes the band unknown', () => {
  const docs = byId([
    pkg('a', [hexChange('a1', 0x4010a100, '01')]),
    pkg('b', [hexChange('b1', 0x4010a200, '02')]),
    pkg('c', [hexChange('c1', 0x4010a300, '03')]),
  ])
  const cost = (n, measured = 'emulator, test') => ({ instructionsPerBlock: n, measured })
  const two = analyzeSelection(docs, { a: { cost: cost(300) }, b: { cost: cost(200) } }, ['a', 'b'])
  assert.equal(two.cost.known, 500)
  assert.deepEqual(two.cost.unmeasured, [])
  assert.equal(two.cost.band, 'light')
  assert.equal(analyzeSelection(docs, { a: { cost: cost(300) }, b: { cost: cost(200) } }, ['a', 'b'], { noticeable: 100, heavy: 400 }).cost.band, 'heavy')
  const three = analyzeSelection(docs, { a: { cost: cost(300) }, b: { cost: cost(200) } }, ['a', 'b', 'c'])
  assert.equal(three.cost.known, 500)
  assert.deepEqual(three.cost.unmeasured, ['c'])
  assert.equal(three.cost.perPackage.c, null)
  assert.equal(three.cost.band, 'unknown')
})

test('a selection with no hooks and no patch memory has band none', () => {
  const r = analyzeSelection(byId([pkg('n')]), {}, ['n'])
  assert.equal(r.cost.band, 'none')
  assert.equal(r.conflicts.length, 0)
})

test('conflictsIfAdded labels an unticked mod only with what it would add', () => {
  const docs = byId([
    pkg('a', [hexChange('a1', 0x4010a100, '01020304')], { title: 'Alpha' }),
    pkg('b', [hexChange('b1', 0x4010a102, '0506')], { title: 'Beta' }),
    pkg('c', [hexChange('c1', 0x4010a900, '07')]),
  ])
  const added = conflictsIfAdded(docs, {}, ['a'], 'b')
  assert.equal(added.length, 1)
  assert.equal(added[0].kind, 'os-bytes')
  assert.deepEqual(conflictsIfAdded(docs, {}, ['a'], 'c'), [])
  assert.deepEqual(conflictsIfAdded(docs, {}, ['a', 'b'], 'a'), [])
  assert.deepEqual(conflictsIfAdded(docs, {}, [], 'b'), [])
})

test('a package with bad notes is refused by validatePackage, and analysis reports it without throwing', () => {
  const longSummary = pkg('bad', [hexChange('x1', 0x4010a100, '01')], { info: { summary: 'x'.repeat(201) } })
  assert.throws(() => validatePackage(longSummary), /package "bad": info summary must be text of 200 characters or fewer/)
  assert.throws(() => validatePackage(pkg('bad', [], { info: { claims: 'no' } })), /info claims must be a list of text/)
  assert.throws(() => validatePackage(pkg('bad', [], { info: { cost: { instructionsPerBlock: -1, measured: 'x' } } })), /instructionsPerBlock/)
  const r = analyzeSelection(byId([longSummary]), {}, ['bad'])
  assert.equal(r.conflicts.length, 1)
  assert.equal(r.conflicts[0].kind, 'invalid')
  assert.match(r.conflicts[0].text, /^Package bad was refused: package "bad": info summary/)
})

test('curated notes with a wrong shape are reported as an invalid conflict for that mod', () => {
  const docs = byId([pkg('a'), pkg('b')])
  const r = analyzeSelection(docs, { a: { claims: 'no' } }, ['a', 'b'])
  assert.deepEqual(r.conflicts.map(c => [c.a, c.kind]), [['a', 'invalid']])
})

test('info never reaches the merged build document', () => {
  const docs = byId([pkg('a', [hexChange('a1', 0x4010a100, '01')], { info: { summary: 'Freeze note', claims: ['ui:x'] } })])
  const merged = mergePackages(docs, ['a'])
  assert.equal('info' in merged, false)
  assert.equal(JSON.stringify(merged).includes('Freeze note'), false)
})

test('noteFor lets the curated notes win key by key and says where each key came from', () => {
  const { note, from } = noteFor({ summary: 'file', claims: ['x'] }, { summary: 'owner' })
  assert.equal(note.summary, 'owner')
  assert.equal(from.summary, 'curated')
  assert.deepEqual(note.claims, ['x'])
  assert.equal(from.claims, 'file')
})

test('an added file\'s own info (claims and cost) is used when the owner has no notes for it', () => {
  const cost = { instructionsPerBlock: 2000, measured: 'emulator, test' }
  const docs = byId([
    pkg('a', [hexChange('a1', 0x4010a100, '01')], { title: 'Alpha', info: { claims: ['ui:TRIG 13-16'], cost } }),
    pkg('b', [hexChange('b1', 0x4010a200, '02')], { title: 'Beta', info: { claims: ['ui:TRIG 13-16'], cost: { ...cost, instructionsPerBlock: 1500 } } }),
  ])
  const r = analyzeSelection(docs, {}, ['a', 'b'])
  assert.deepEqual(r.conflicts.map(c => c.kind), ['claim'])
  assert.equal(r.cost.known, 3500)
  assert.equal(r.cost.band, 'heavy')
})

const manifestPath = new URL('../web/patches/manifest.json', import.meta.url)
const FEATURES = ['delay-control-core', 'delay-control-dj', 'delay-control-drive', 'delay-control-syn']

test('the four DelayCtrl features selected together: zero conflicts and sensible sizes', { skip: !existsSync(manifestPath) && 'needs web/patches/manifest.json' }, () => {
  const read = p => JSON.parse(readFileSync(new URL(`../web/patches/${p}`, import.meta.url), 'utf8'))
  const { packages } = read('manifest.json')
  const docs = Object.fromEntries(packages.map(p => [p.id, read(p.file)]))
  const curated = read('info.json')
  for (const id of Object.keys(curated.packages)) assert.ok(docs[id], `info.json names "${id}", which the manifest lacks`)

  const r = analyzeSelection(docs, curated.packages, FEATURES, curated.budget)
  assert.deepEqual(r.conflicts, [])
  assert.equal(r.blocking, false)
  assert.ok(r.order.includes('modarea') && r.order.includes('delay-control-runtime'))
  assert.ok(r.size.totals.areaBytes > 0 && r.size.totals.areaBytes < r.size.totals.areaSize)
  assert.equal(r.size.totals.areaSize, 0x10000)
  assert.ok(r.size.totals.osPlaces > 0)
  assert.equal(r.cost.band, 'unknown')
  for (const id of FEATURES) assert.ok(r.cost.unmeasured.includes(id))

  assert.deepEqual(conflictsIfAdded(docs, curated.packages, ['delay-control-core'], 'delay-control-dj', curated.budget), [])
})
