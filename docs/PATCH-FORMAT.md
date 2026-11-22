# Patch format `.sypatch` (schema 1), draft

A `.sypatch` file is a **package**: the only file meant to be shared. It holds
our bytes and SHA-256 fingerprints of the original bytes it expects. It never
holds Elektron bytes. The builder reads the user's own OS 1.41 file, checks each
fingerprint, and builds the result in memory.

Developer note: the JSON calls each change an object in `blocks[]`, and this
document uses the same word. User-facing text says "change" or "part".

Status: this document describes the standard. Section "Implementation status"
at the end says what the code does today.

## Package (top level)

| field | meaning |
|---|---|
| `format` | `"synthack-patchset"` |
| `schema` | `1` |
| `id` | unique package id, e.g. `"delay-control-full"`. Lowercase letters, digits and hyphens |
| `title` | short human name |
| `requires` | array of package ids this package needs (`[]` when none). Resolved transitively (see "Combining packages") |
| `encoding` | `"lowercase-hex"` |
| `target` | `{ "device": "Syntakt", "os": "1.41", "stock_sha256": "<hash>" }`. `stock_sha256` is the SHA-256 of the exact stock OS 1.41 file |
| `area` | the mod area layout (only when the package has area changes): `img`, `ram`, `size`, `compress: "shlz"` |
| `units[]` | groups of changes: `id`, `title`, `blocks[]` |

Change ids (`blocks[].id`) are unique within the package, and across all
packages selected together. The builder refuses a duplicate.

## Notes: `info` (optional)

A package may carry a top-level `info` object: plain notes that the page shows
before the visitor ticks the mod. It is optional. It is never written into the
build.

```json
{ "summary": "one plain sentence, 200 characters or fewer",
  "claims": ["ui:TRIG 13-16 on the FX track", "..."],
  "conflicts": ["<other package id>"],
  "cost": { "instructionsPerBlock": 420, "measured": "emulator, <date>, <what was measured>" } }
```

- `summary`: text, 200 characters or fewer.
- `claims`: a list of text. Two mods that claim the same text conflict. Use a
  prefix such as `ui:`, `param:` or `audio:` so the claims read clearly.
- `conflicts`: a list of package ids that this mod cannot be used with. The
  conflict is shown both ways, whichever mod lists it.
- `cost`: `null` (not measured), or an object with a whole number
  `instructionsPerBlock` of 0 or more and text `measured`. The number is the
  measured cost per audio slice (the Syntakt makes sound in small slices). It is
  the author's or owner's measurement, not computed by the page. Leave it `null`
  when nothing was measured; the page then says it is not measured yet.

Wrong types are refused with a plain sentence, both by `validatePackage` in
`tools/sypatch/merge.mjs` and by `check_patch.py`.

There are two sources, and they are read in this order:

1. The package file's own `info`. This is written by the author of the file. The
   page labels it "declared by the file's author, not checked" when the file was
   added by a visitor.
2. The site owner's notes, in `web/patches/info.json`, under `packages` by id.
   Each key they set overrides the file's own value for that key. Their `budget`
   sets the load thresholds (`noticeable`, `heavy`).

The page's conflict and size checks use both. The package's own `info` never goes
into the `.syx` build: `mergePackages` builds a new document without it.

## Addresses: one meaning each

- `addr` (replace changes): a **decoded section-3 address**. The byte offset in
  the file is `addr - 0x40000400`. Container offsets never appear.
- `offset` (area changes): an offset inside our mod area, from its start.
- A change never holds a relative or symbolic address. Its bytes may contain
  absolute jump targets and pointers; the builder does not interpret them, so
  each package must be linked at its own fixed place. Sections 3 and 7 load at the
  same address, so `section` is always required on replace changes.

## Replace change (writes into the user's OS file)

| field | meaning |
|---|---|
| `mode` | `"replace"` |
| `section` | `3` or `7` |
| `addr` | decoded address, hex string |
| `len` | length in bytes |
| `kind` | `"code"` (replaces stock instructions; the engine checks them against the stock bytes), `"data"`, or `"free-code"` (new code written into zeroed free space; the builder decodes its own new bytes, and the engine gets it as data) |
| `stock_sha256` | SHA-256 of the `len` original bytes at `addr` |
| `new` | ordered parts (see below) |
| `new_sha256` | SHA-256 of the assembled `new` bytes |
| `why` | short plain note |

## Parts

- `["hex", "<hex>"]`: our bytes.
- `["stock", "<addr>", "<len>", "<sha256>"]`: copy `len` bytes from the user's
  own pristine file at `addr`, and check their hash. Used when a change must keep
  an original instruction without storing it. Not supported by the builder yet
  (see "Not yet").

The lengths of all parts must add up to `len`.

## Area change (our mod area)

For code and data that do not fit in the free space of the image. The builder
puts these bytes in an area that the OS image decompresses into RAM at boot
(`mods/modarea`).

| field | meaning |
|---|---|
| `mode` | `"area"` |
| `offset` | offset from the start of the mod area (RAM `area.ram`), hex string or number |
| `len` | length in bytes |
| `kind` | `"code"` (decoded by the builder: must be whole instructions) or `"data"` |
| `new` | ordered parts, hex only (no stock parts: an area holds our bytes only) |
| `new_sha256` | SHA-256 of the `new` bytes |
| `why` | short plain note |

Area changes have no `section`, `addr` or `stock_sha256`. The top-level `area`
holds the layout: `img` (where the compressed stream sits, `0x40348000`), `ram`
(`0x46000000`), `size` (`0x10000`, the RAM the loader fills) and `compress`
(`"shlz"`). The builder places the changes at their offsets, zero-fills the gaps,
compresses the result with SHLZ (`tools/sypatch/lz.mjs`, a port of
`tools/build/lz.py` with the same output bytes), and appends it to the stock
image as one blob. Gaps from the end of the stock image to `img` are zero.

All packages selected together must use the same `area` layout.

## Area offsets: the DelayCtrl convention

DelayCtrl uses these offsets in the mod area:

| offset | use |
|---|---|
| `0x4000` | `DC_REG_CORE` (registration word) |
| `0x4004` | `DC_REG_DRIVE` (registration word) |
| `0x4008` | `DC_VIEW` (shared view pointer) |
| `0x4010` and up | runtime code and data |

This is the DelayCtrl convention only. Other authors choose their own area
ranges. When packages are combined, their ranges must not overlap; the builder
refuses overlapping writes.

## Combining packages

When the user selects packages, the builder:

1. resolves `requires` transitively and refuses a missing requirement;
2. merges the `units` of all selected packages;
3. refuses overlapping writes (replace and area changes are checked separately);
4. refuses differing area layouts.

A package that is not selected contributes nothing: none of its changes, units or
area bytes reach the build.

## Checks the builder runs

1. **Stock hash**: the user's file is the exact stock OS 1.41 (`target.stock_sha256`
   matches). Otherwise refuse.
2. **Schema and hex**: `format`, `schema`, `encoding`, field names, lowercase hex.
3. **Lengths**: `len` equals the sum of the parts.
4. **Hashes**: every replace `stock_sha256` matches the user's own bytes at `addr`,
   and every `new_sha256` matches its assembled bytes.
5. **Overlap**: no two changes write the same bytes (replace and area separately).
   Stock-part ranges are read-only and are not counted as changes.
6. **Instruction boundaries**: `kind: "code"` on a replace change is checked by the
   engine against the stock bytes. `"free-code"` and area code changes are decoded
   from their own new bytes: the whole change must be whole instructions.
7. **Area bounds and round-trip**: every area change lies inside `area.size`, and
   the SHLZ stream decompresses to the area bytes (`lz.mjs` round-trip, see
   `tests/engine_bridge.test.mjs`).
8. **Requires resolution**: every id in `requires` is added to the selection,
   transitively, and the merge rules above hold. A requirement that is not
   available is refused.

Data changes must carry `stock_sha256`, `new_sha256` and `why`. They are checked
against the user's own file before anything is written.

## Package content rules

- Only our bytes, our text and hashes. No Elektron bytes. No bytes from the
  original range: keep an original only by hash, or by a stock part that reads the
  user's own file.
- No absolute paths, user names, machine names or other personal data in any
  field, including `why` and `title`.
- The package is one JSON file. No binary attachments.

## Import (browser)

A package chosen in the browser is read as text and parsed as data (`JSON.parse`),
then validated with the checks above. It is **never executed or evaluated**. Nothing
is uploaded. The result is built in memory; a `.syx` is offered for download only
when the user clicks.

## Not yet

Stock parts in the builder, finer progress inside the ~1 min pack (the page
shows a timer and stage text), and splitting mixed code and data changes
automatically (the DelayCtrl code change is split by hand in
`tools/sypatch/delay_control.mjs`, see below).

The browser page is in `web/` (build with `web/build.mjs`, see its header). It
runs the same bridge in a Web Worker and offers the `.syx` for download only
when the user clicks.

## Worked example: DelayCtrl (v2o)

The full DelayCtrl build (mod area loader, 29 fixed changes, and the 3,508-byte
code change as area changes) reproduces the locally built reference file byte for
byte. The code change is two area changes: `0x4000` (+`0xCE6`, decoded as code) and
`0x4CE6` (+`0xCE`, `.rodata` and `.data`, kind `data`). The split point comes
from the decoder, not from the ELF file.

Abridged shape of a replace change from that package (the bytes are ours, shown
shortened):

```json
{
  "id": "modarea-1-400004B2",
  "mode": "replace",
  "section": 3,
  "addr": "0x400004b2",
  "len": 8,
  "kind": "code",
  "stock_sha256": "<sha256 of the 8 original bytes>",
  "new": [["hex", "4ef940338d804e71"]],
  "new_sha256": "<sha256 of the 8 new bytes>",
  "why": "jmp to the mod area loader, then nop"
}
```

## Implementation status

What the code does at this revision:

- `tools/sypatch/check_patch.py` checks: format, schema, target name and hash,
  encoding, `mode`, `kind`, `section`, `addr`, `len`, the parts and their lengths,
  `new_sha256` (when all parts are hex), change ids unique within the file, overlap,
  and area bounds. It does **not** check `requires`, `why`, the stock bytes (it has
  no user file), instruction boundaries, or the SHLZ round-trip.
- `tools/sypatch/bridge.mjs` checks the stock hash against the user's file, the
  instruction boundaries and the engine's overlap rules, and builds in memory.
- `tools/sypatch/convert.mjs` refuses stock parts.
- Cross-package `requires` resolution and the merge of several packages are in
  `tools/sypatch/merge.mjs`. The browser page loads the packages listed in
  `web/patches/manifest.json` as optional checkboxes; the single-file v2o set is a
  separate option.
- An added file is validated in the worker and kept in memory only. Its id may not
  clash with a built-in package.
- The overlap check ignores `section`: writes to sections 3 and 7 at the same
  address are refused. That is conservative.
- The page adds required packages automatically; `requires` is not a user choice.
