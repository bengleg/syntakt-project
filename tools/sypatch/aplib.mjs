// aPLib-variant codec, ported to JavaScript from elektron-firmware-tool's aplib.c
// (MIT License, Copyright (c) 2026 Marcel Bierling). Same stream format, same cost-optimal parse, level 3 by default.
// A section is an 8-byte header [u32 stream length BE][u32 byte-sum BE] followed by the stream.

const OFFSET_BIAS = 767
const REUSE_GAMMA = 2
const FAR_THRESHOLD = 3328
const MIN_MATCH = 2
export const SECT_HDR = 8
const LIT_BITS = 9
const MAX_OFFSET = 1 << 20
const MAX_MATCH = 2048
const HBITS = 17
const HSIZE = 1 << HBITS
const LEVELS = [16, 64, 256, 2048]
const COST_INF = 0xffffffff

class Packer {
  constructor(cap) {
    this.o = new Uint8Array(cap)
    this.n = SECT_HDR
    this.tagpos = -1
    this.tagbits = 0
  }
  bit(b) {
    if (this.tagbits === 0) {
      this.tagpos = this.n
      this.o[this.n++] = 0
      this.tagbits = 8
    }
    if (b) this.o[this.tagpos] |= 1 << (this.tagbits - 1)
    this.tagbits--
  }
  byte(v) { this.o[this.n++] = v }
  gamma(v) {
    const nb = v.toString(2).length
    for (let i = nb - 2; i >= 0; i--) {
      this.bit((v >>> i) & 1)
      this.bit(i === 0 ? 1 : 0)
    }
  }
  literal(b) {
    this.bit(1)
    this.byte(b)
  }
  match(off, matchlen, st) {
    this.bit(0)
    if (off === st.last) {
      this.gamma(REUSE_GAMMA)
    } else {
      const raw = off + OFFSET_BIAS
      this.gamma(raw >>> 8)
      this.byte(raw & 0xff)
      st.last = off
    }
    const bonus = off > FAR_THRESHOLD ? 1 : 0
    const lbase = matchlen - 1 - bonus
    if (lbase <= 3) {
      this.bit(lbase >> 1)
      this.bit(lbase & 1)
    } else {
      this.bit(0)
      this.bit(0)
      this.gamma(lbase - 2)
    }
  }
}

const gammaCost = v => {
  const nb = v === 0 ? 0 : v.toString(2).length
  return 2 * (nb - 1)
}

const matchCost = (off, L, last) => {
  let b = 1 + (off === last ? 2 : gammaCost((off + OFFSET_BIAS) >>> 8) + 8)
  const lb = L - 1 - (off > FAR_THRESHOLD ? 1 : 0)
  b += lb <= 3 ? 2 : 2 + gammaCost(lb - 2)
  return b
}

const matchRun = (d, a, b, cap) => {
  let l = 0
  while (l < cap && d[a + l] === d[b + l]) l++
  return l
}

const hash2 = (d, i) => ((d[i] << 8) ^ d[i + 1]) & (HSIZE - 1)

/** data: Uint8Array -> the section bytes (8-byte header + stream). */
export function pack(data, level = 3) {
  const len = data.length
  if (len === 0) return new Uint8Array(SECT_HDR)
  const maxChain = LEVELS[Math.min(Math.max(level, 0), 3)]
  const head = new Int32Array(HSIZE).fill(-1)
  const prev = new Int32Array(len)
  const cost = new Uint32Array(len + 1).fill(COST_INF)
  const lo = new Uint32Array(len + 1)
  const from = new Int32Array(len + 1)
  const toff = new Uint32Array(len + 1)
  const tlen = new Uint32Array(len + 1)
  cost[0] = 0
  lo[0] = 1
  from[0] = -1

  const relax = (pos, nc, nl, frm, to, tl) => {
    if (nc < cost[pos]) {
      cost[pos] = nc
      lo[pos] = nl
      from[pos] = frm
      toff[pos] = to
      tlen[pos] = tl
    }
  }

  for (let i = 0; i < len; i++) {
    if (cost[i] === COST_INF) continue
    const bi = cost[i], loi = lo[i]
    const cap = Math.min(len - i, MAX_MATCH)
    relax(i + 1, bi + LIT_BITS, loi, i, 0, 0)
    if (i + 1 < len) {
      if (i >= loi) {
        const rl = matchRun(data, i - loi, i, cap)
        const mn = loi > FAR_THRESHOLD ? MIN_MATCH + 1 : MIN_MATCH
        for (let cl = mn; cl <= rl; cl++) relax(i + cl, bi + matchCost(loi, cl, loi), loi, i, loi, cl)
      }
      let j = head[hash2(data, i)]
      let chain = maxChain
      let pm = 1
      while (j >= 0 && chain-- > 0) {
        const off = i - j
        if (off > MAX_OFFSET) break
        if (pm >= cap) break
        if (data[j + pm] !== data[i + pm]) {
          j = prev[j]
          continue
        }
        const l = matchRun(data, j, i, cap)
        if (l > pm) {
          const mn = off > FAR_THRESHOLD ? MIN_MATCH + 1 : MIN_MATCH
          const start = Math.max(pm + 1, mn)
          for (let cl = start; cl <= l; cl++) relax(i + cl, bi + matchCost(off, cl, loi), off, i, off, cl)
          pm = l
          if (l >= cap) break
        }
        j = prev[j]
      }
    }
    if (i + 1 < len) {
      const h = hash2(data, i)
      prev[i] = head[h]
      head[h] = i
    }
  }

  const path = []
  for (let j = len; j > 0; j = from[j]) path.push(j)
  path.reverse()

  const p = new Packer(len * 2 + 64)
  const st = { last: 1 }
  for (const pos of path) {
    const src = from[pos]
    if (tlen[pos] === 0) p.literal(data[src])
    else p.match(toff[pos], tlen[pos], st)
  }
  p.bit(0)
  p.gamma(0x1000002)
  p.byte(0xff)

  const stream = p.n - SECT_HDR
  let ssum = 0
  for (let k = SECT_HDR; k < p.n; k++) ssum = (ssum + p.o[k]) % 0x100000000
  const out = p.o.slice(0, p.n)
  const dv = new DataView(out.buffer)
  dv.setUint32(0, stream)
  dv.setUint32(4, ssum)
  return out
}

/** section bytes -> the decoded data. Throws on a malformed stream. */
export function depack(src) {
  if (src.length < SECT_HDR) throw new Error('aPLib: section shorter than its header')
  let ip = SECT_HDR, tag = 0
  const end = src.length
  const getbit = () => {
    tag = (tag << 1) >>> 0
    if ((tag & 0xff) === 0) {
      if (ip >= end) throw new Error('aPLib: stream ends early')
      const by = src[ip++]
      tag = ((by << 1) | 1) >>> 0
      return (by >> 7) & 1
    }
    return (tag >> 8) & 1
  }
  const getgamma = () => {
    let v = 1
    for (;;) {
      v = v * 2 + getbit()
      if (getbit()) break
      if (v > 0x02000000) throw new Error('aPLib: bad gamma')
    }
    return v
  }
  const out = []
  let lastOff = 1
  for (;;) {
    if (getbit()) {
      if (ip >= end) throw new Error('aPLib: literal past end')
      out.push(src[ip++])
      continue
    }
    const g = getgamma()
    let off
    if (g === REUSE_GAMMA) {
      off = lastOff
    } else {
      if (ip >= end) throw new Error('aPLib: offset past end')
      off = (g * 256 + src[ip++]) >>> 0
      if (off === OFFSET_BIAS) break
      off -= OFFSET_BIAS
      lastOff = off
    }
    const sl = 2 * getbit() + getbit()
    let L = sl ? sl : getgamma() + 2
    if (off > FAR_THRESHOLD) L += 1
    if (off === 0 || off > out.length) throw new Error('aPLib: bad offset')
    const n = L + 1
    for (let k = 0; k < n; k++) out.push(out[out.length - off])
  }
  return Uint8Array.from(out)
}

const BOOT_BASE = 0x40200000 - 0x40000400
const BOOT_END = {}

/** section bytes -> { size, margin }: decoded size and the smallest gap (bytes) between the unread stream and the last written byte during start-up unpacking. A stream that runs out ends quietly. */
export function depackMargin(src) {
  let ip = SECT_HDR, op = 0, tag = 0, lastOff = 1
  let worst = 2 ** 40
  const bit = () => {
    tag = (tag << 1) & 0xffff
    if ((tag & 0xff) === 0) {
      if (ip >= src.length) throw BOOT_END
      const by = src[ip++]
      tag = (by << 1) | 1
      return by >> 7
    }
    return (tag >> 8) & 1
  }
  const gamma = () => {
    let v = 1
    for (;;) {
      v = (v << 1) + bit()
      if (bit()) return v
    }
  }
  try {
    while (ip < src.length) {
      if (bit()) {
        ip++
        op++
      } else {
        const g = gamma()
        let off
        if (g === REUSE_GAMMA) {
          off = lastOff
        } else {
          if (ip >= src.length) throw BOOT_END
          off = (g << 8) + src[ip++]
          if (off === OFFSET_BIAS) break
          off -= OFFSET_BIAS
          lastOff = off
        }
        let L = 2 * bit()
        L += bit()
        if (!L) L = gamma() + 2
        if (off > FAR_THRESHOLD) L += 1
        op += L + 1
      }
      const m = BOOT_BASE + ip - op
      if (m < worst) worst = m
    }
  } catch (e) {
    if (e !== BOOT_END) throw e
  }
  return { size: op, margin: worst }
}
