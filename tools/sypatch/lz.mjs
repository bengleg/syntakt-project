// SHLZ, the mod-area format (mods/modarea). A port of tools/build/lz.py: same bytes out, same checks.
// Format: "SHLZ", unpacked length (u32 BE), stream length (u32 BE), then tokens:
//   0xxxxxxx          -> x+1 literal bytes follow
//   1lllllll hi lo    -> copy l+3 bytes from distance hi<<8|lo back

const MAGIC = [0x53, 0x48, 0x4c, 0x5a]
const MIN = 3, MAX_LEN = 130, MAX_LIT = 128, WINDOW = 0xffff, CANDIDATES = 64
const HDR = 12

const key3 = (d, k) => (d[k] << 16) | (d[k + 1] << 8) | d[k + 2]
const u32be = v => [(v >>> 24) & 0xff, (v >>> 16) & 0xff, (v >>> 8) & 0xff, v & 0xff]
const readU32 = (b, k) => ((b[k] << 24) | (b[k + 1] << 16) | (b[k + 2] << 8) | b[k + 3]) >>> 0

export function compress(data) {
  const n = data.length
  const out = []
  let lits = []
  const heads = new Map()

  const flush = () => {
    for (let k = 0; k < lits.length; k += MAX_LIT) {
      const chunk = lits.slice(k, k + MAX_LIT)
      out.push(chunk.length - 1, ...chunk)
    }
    lits = []
  }

  let i = 0
  while (i < n) {
    let bestLen = 0, bestOff = 0
    if (i + MIN <= n) {
      const cands = heads.get(key3(data, i)) ?? []
      for (let c = cands.length - 1; c >= Math.max(0, cands.length - CANDIDATES); c--) {
        const j = cands[c]
        if (i - j > WINDOW) break
        let L = MIN
        while (L < MAX_LEN && i + L < n && data[j + L] === data[i + L]) L++
        if (L > bestLen) {
          bestLen = L
          bestOff = i - j
          if (L === MAX_LEN) break
        }
      }
    }
    const step = bestLen >= MIN ? bestLen : 1
    for (let k = i; k < Math.min(i + step, n - MIN + 1); k++) {
      const key = key3(data, k)
      if (!heads.has(key)) heads.set(key, [])
      heads.get(key).push(k)
    }
    if (bestLen >= MIN) {
      flush()
      out.push(0x80 | (bestLen - MIN), bestOff >> 8, bestOff & 0xff)
    } else {
      lits.push(data[i])
    }
    i += step
  }
  flush()
  return Uint8Array.from([...MAGIC, ...u32be(n), ...u32be(out.length), ...out])
}

export function decompress(blob) {
  if (!MAGIC.every((b, k) => blob[k] === b)) throw new Error('not an SHLZ stream')
  const n = readU32(blob, 4), clen = readU32(blob, 8)
  if (blob.length < HDR + clen) throw new Error('SHLZ stream is truncated')
  const src = blob.subarray(HDR, HDR + clen)
  const out = []
  let i = 0
  const byte = () => {
    if (i >= clen) throw new Error('SHLZ stream is truncated')
    return src[i++]
  }
  while (out.length < n) {
    const c = byte()
    if (c & 0x80) {
      const L = (c & 0x7f) + MIN
      const off = (byte() << 8) | byte()
      if (!(off > 0 && off <= out.length)) throw new Error('SHLZ distance is not valid')
      for (let k = 0; k < L; k++) out.push(out[out.length - off])
    } else {
      for (let k = 0; k <= c; k++) out.push(byte())
    }
  }
  if (out.length !== n || i !== clen) throw new Error('SHLZ lengths do not add up')
  return Uint8Array.from(out)
}
