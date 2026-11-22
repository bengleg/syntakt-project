// Start-up check for section 3: the OS must unpack on the unit without overwriting bytes it has not read yet.
// Port of tools/build/bootcheck.py (MIN_MARGIN, depack_margin).

import { depackMargin } from './aplib.mjs'

export const MIN_MARGIN = 4096

/** section 3 bytes -> { size, margin }. Throws when the room left at start-up is below MIN_MARGIN. */
export function checkBootMargin(sectionBytes) {
  const r = depackMargin(sectionBytes)
  if (r.margin < MIN_MARGIN) {
    throw new Error(`Boot room is short: the OS would not unpack at start-up (${r.margin} bytes of room, ${MIN_MARGIN} needed).`)
  }
  return r
}
