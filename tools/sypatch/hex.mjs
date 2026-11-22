// Hex strings <-> bytes, without Buffer, so the same code runs in Node and in the browser worker.

export const toHex = b => Array.from(b, x => x.toString(16).padStart(2, '0')).join('')

export const fromHex = s => Uint8Array.from(s.match(/../g) ?? [], h => parseInt(h, 16))
