// SHA-256 in plain JS, with no imports, so the pure checks in merge.mjs run in Node and in the browser worker.
// The round constants and the start values are derived from the primes (fractional roots), not typed in.

const primes = []
for (let n = 2; primes.length < 64; n++) if (primes.every(p => n % p)) primes.push(n)

// floor(n ** (1 / k)) for a BigInt n, by Newton's method from an overestimate.
function iroot(n, k) {
  let x = 1n << BigInt(Math.ceil(n.toString(2).length / Number(k)) + 1)
  for (;;) {
    const y = ((k - 1n) * x + n / x ** (k - 1n)) / k
    if (y >= x) return x
    x = y
  }
}

const K = Uint32Array.from(primes, p => Number(iroot(BigInt(p) << 96n, 3n) & 0xffffffffn))
const H0 = Uint32Array.from(primes.slice(0, 8), p => Number(iroot(BigInt(p) << 64n, 2n) & 0xffffffffn))

const rotr = (x, n) => ((x >>> n) | (x << (32 - n))) >>> 0

export function sha256(bytes) {
  const n = bytes.length
  const padded = new Uint8Array(Math.ceil((n + 9) / 64) * 64)
  padded.set(bytes)
  padded[n] = 0x80
  const view = new DataView(padded.buffer)
  const bits = n * 8
  view.setUint32(padded.length - 8, Math.floor(bits / 0x100000000))
  view.setUint32(padded.length - 4, bits % 0x100000000)

  const h = Uint32Array.from(H0)
  const w = new Uint32Array(64)
  for (let off = 0; off < padded.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = view.getUint32(off + 4 * i)
    for (let i = 16; i < 64; i++) {
      const x = w[i - 15], y = w[i - 2]
      const s0 = rotr(x, 7) ^ rotr(x, 18) ^ (x >>> 3)
      const s1 = rotr(y, 17) ^ rotr(y, 19) ^ (y >>> 10)
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0
    }
    let [a, b, c, d, e, f, g, hh] = h
    for (let i = 0; i < 64; i++) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
      const ch = (e & f) ^ (~e & g)
      const t1 = (hh + S1 + ch + K[i] + w[i]) >>> 0
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
      const maj = (a & b) ^ (a & c) ^ (b & c)
      const t2 = (S0 + maj) >>> 0
      hh = g; g = f; f = e; e = (d + t1) >>> 0
      d = c; c = b; b = a; a = (t1 + t2) >>> 0
    }
    const v = [a, b, c, d, e, f, g, hh]
    for (let i = 0; i < 8; i++) h[i] = (h[i] + v[i]) >>> 0
  }
  return Array.from(h, x => x.toString(16).padStart(8, '0')).join('')
}
