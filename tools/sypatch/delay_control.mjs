// The DelayCtrl build as a .sypatch document: the mod area loader and hook (mods/modarea), the 29 fixed DelayCtrl
// blocks and the 3,508-byte code block as two area blocks. Our bytes and fingerprints only; no Elektron bytes.
// Takes the parsed patch.json files; make_delay_control.mjs reads them from disk. Node only (fingerprints via
// node:crypto). The browser page only loads the JSON this writes.

import { createHash } from 'node:crypto'

export const IMG = 0x40348000
export const STOCK_SHA = '8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e'

// Stock data (pointers and tables) rather than code: checked as data.
export const DATA = new Set([
  '4018AD86', '4018AD94', '4018ADC4', '4018ADD6', '4018AE06', '4018AE14', '4018AE48', '4018AE56',
  '4022E0A0', '4022E0D4', '4022E108', '4022E13C', '401D4710', '4018C794', '40040B74', '401952A8',
  '4019524A', '4004E9BC',
])

// The loader's code goes into zeroed free space: its own bytes are checked, not the stock ones.
const FREE_CODE = new Set(['0X40338D80'])
// The code block is .text, then .rodata and .data (strings, tables). The decoder finds the code end at 0xCE6.
export const DC_CODE_END = 0xce6

const sha = hex => createHash('sha256').update(Buffer.from(hex, 'hex')).digest('hex')

const fixed = (p, i, tag) => {
  const a = p.addr.replace(/^0x/i, '').toUpperCase()
  const kind = FREE_CODE.has(p.addr.toUpperCase()) ? 'free-code' : (DATA.has(a) ? 'data' : 'code')
  return {
    id: `${tag}-${i}-${a}`, mode: 'replace', section: 3, addr: '0x' + a.toLowerCase(), len: p.len,
    kind, stock_sha256: p.expect_sha256, new: [['hex', p.hex]], new_sha256: sha(p.hex),
  }
}

export function delayControlDoc(legacyPatches, modareaPatches) {
  const dc = legacyPatches
  const dcBlock = dc.find(p => p.append)
  const at = Number(dcBlock.addr) - IMG
  const area = [
    { id: 'delay-control-code', mode: 'area', offset: at, len: DC_CODE_END, kind: 'code', new: [['hex', dcBlock.hex.slice(0, 2 * DC_CODE_END)]] },
    { id: 'delay-control-data', mode: 'area', offset: at + DC_CODE_END, len: dcBlock.len - DC_CODE_END, kind: 'data', new: [['hex', dcBlock.hex.slice(2 * DC_CODE_END)]] },
  ]
  return {
    format: 'synthack-patchset', schema: 1, id: 'delay-control-full', title: 'DelayCtrl (v2o)', encoding: 'lowercase-hex',
    target: { device: 'Syntakt', os: '1.41', stock_sha256: STOCK_SHA },
    area: { img: '0x40348000', ram: '0x46000000', size: '0x10000', compress: 'shlz' },
    units: [
      { id: 'modarea', title: 'Mod area loader', blocks: modareaPatches.map((p, i) => fixed(p, i, 'modarea')) },
      { id: 'delay-control', title: 'DelayCtrl', blocks: [...dc.filter(p => !p.append).map((p, i) => fixed(p, i, 'dc')), ...area] },
    ],
  }
}
