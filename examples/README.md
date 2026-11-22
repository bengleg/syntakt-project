# Synthetic examples

Two small `.sypatch` packages that show the shape of a schema 1 package. They
are **synthetic**: they do not change any real firmware, and they contain no
Elektron bytes.

| file | what it shows |
|---|---|
| `synthetic-data-change.sypatch.json` | a package with no `requires` and one replace change (kind `data`) |
| `synthetic-area-feature.sypatch.json` | a package that requires the first one and has one area change (kind `code`) with the area layout |

Read [docs/PATCH-FORMAT.md](../docs/PATCH-FORMAT.md) for the fields and
[docs/AUTHORING.md](../docs/AUTHORING.md) for the steps to write a real one.

## What is made up

- **Stock bytes** of the data change: 16 bytes that alternate in 4-byte groups,
  first `0xa5`, then `0x5a`, and so on. Their SHA-256 is `stock_sha256` in the
  file. These bytes are not from any firmware.
- **New bytes** of the data change: the 16 bytes `0x00` to `0xff` in steps of
  `0x11`. Their SHA-256 is `new_sha256`.
- **Address** of the data change: `0x7e000100`. It lies outside every range in
  [docs/memory-map.md](../docs/memory-map.md) and outside section 3, so it means
  nothing on a real OS 1.41 file.
- **Area code** of the area change: `nop`, `nop`, `rts` (`4e71 4e71 4e75`), at area
  offset `0x8000`. Its SHA-256 is `new_sha256`.
- **Area layout** (`img`, `ram`, `size`, `compress`): the same values as the real
  DelayCtrl layout, because the loader's addresses are fixed in our code.

The `target.stock_sha256` is the real OS 1.41 hash, so each package passes the
file-level check that the builder runs first.

## What would happen on a real file

- `synthetic-data-change`: refused. The address is outside section 3, and the 16
  bytes there do not match the stated stock bytes.
- `synthetic-area-feature`: its area code would be written only after its
  requirement resolves. On its own (without `synthetic-data-change`), the builder
  refuses it at the requires check.

These are structure examples. Do not build them, flash them or copy their
addresses.

## Checker output

Run from the repository root:

```powershell
python tools/sypatch/check_patch.py examples/synthetic-data-change.sypatch.json
python tools/sypatch/check_patch.py examples/synthetic-area-feature.sypatch.json
```

Both print `OK`. The checker is structural: it does not check `requires`, the
stock bytes (it has no user file) or instruction boundaries. Passing it does not
mean a package would build.
