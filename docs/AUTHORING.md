# Authoring a package

> Most people should use the SDK instead: see [SDK.md](SDK.md). It turns your C
> code into the package file for you. This guide is for writing a package by hand.

This guide is for someone who wants to write a `.sypatch` package that the
builder can apply to **their own** Syntakt OS 1.41 file, or for an AI agent
helping them. Read the format first: [PATCH-FORMAT.md](PATCH-FORMAT.md). Read
[LEGAL.md](../LEGAL.md) and [RECOVERY.md](../RECOVERY.md) before you flash
anything.

Nothing in this repository contains Elektron bytes. You need your own OS 1.41
file, obtained legally as Elektron provides it. Do not share that file, do not
commit it, and do not paste its bytes into a package, an issue or a prompt.

You need Python 3.11+. The m68k GCC toolchain is optional: you need it only for
code changes (step c). Data-only packages need no compiler.

## (a) Get your OS file and check its hash

Keep your file outside the repository. Compute its SHA-256 and compare it with
`STOCK_SHA256` in `tools/sypatch/check_patch.py`:

```powershell
Get-FileHash -Algorithm SHA256 "C:\path\to\your\OS-file"
```

If the hash differs, stop. The builder refuses any other file, and so will your
packages.

## (b) Find addresses and fingerprints with your own tools

- Use your own emulator or disassembler, run on your own file. The repo's notes
  help you know where to look: [memory-map.md](memory-map.md),
  [modding-guide.md](modding-guide.md), [emulation.md](emulation.md). They hold
  addresses and our findings, not stock bytes.
- Do not copy disassembly, memory dumps or byte listings of the stock OS into the
  repo or your package. They carry Elektron bytes.
- For each hook or data change, note the decoded section-3 address (never a
  container offset), the length, and the original bytes. Compute the SHA-256 of
  the original bytes with your own tool. The package stores only that hash.
- Stay out of sections 2 and 6 (boot). Do not make the boot intro longer
  ([CONTRIBUTING.md](../CONTRIBUTING.md), rules 3 and 4).

## (c) Write mod-area code (code changes only)

Code that does not fit in the free space goes to the mod area (RAM from
`0x46000000`, 64 KB, unpacked at boot).

1. Write freestanding code: no libc, no libgcc. Use ColdFire-safe constructs (see
   the gotchas below).
2. Compile and link at a fixed base in the area, for example
   `ld -N -Ttext=0x46000000+offset`. Use your own offset range, and keep it clear
   of other authors' ranges (see the DelayCtrl convention in PATCH-FORMAT.md).
3. Check the object: `nm -u` must list **no undefined symbols**, which means no
   libgcc calls.
4. Check that there is **no `.bss`**. Put variables in `.data`
   (`__attribute__((section(".data")))`). The area is zeroed anyway, but the build
   checks.
5. Split the output. Take the text and data with
   `objcopy -O binary -j .text -j .rodata -j .data`. Split at the end of `.text`
   (its size from `objdump -h`). The code part is an area change with `kind:
   "code"`; the rest is `kind: "data"`.
6. Check the split. The code part must decode as **whole instructions** to its
   end. If decoding stops early, move the split to where it stops and check again.
   The DelayCtrl split came from the decoder, not from the ELF file.

Toolchain used by `mods/delay-control/make_patch.py` (run through WSL on
Windows):

```
m68k-linux-gnu-gcc-13 -mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -c code.c
m68k-linux-gnu-ld -N -Ttext=<base> -e <entry> -o code.elf code.o
m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data code.elf code.bin
```

Install it as in [CONTRIBUTING.md](../CONTRIBUTING.md). Use the `.bin` only in
your own build folder, never in the repo.

ColdFire gotchas (from [CONTRIBUTING.md](../CONTRIBUTING.md) and
[modding-guide.md](modding-guide.md)):

- no `exg`;
- `movem` only with `(An)` or `d16(An)`;
- `muls.l` takes no absolute address (use `d16(An)`);
- short branches reach only ±127 bytes;
- save every register you use: the OS keeps values in registers across a hook.

## (d) Write the hook and data changes

- **Hook**: replace at least 6 original bytes with `jsr` or `jmp` to your code,
  padded with `nop` (`4e71`) to the length of the replaced instructions. Your
  trampoline replays the replaced instructions before it returns (see
  [modding-guide.md](modding-guide.md), section 2).
- **Hook change** (`mode: "replace"`, `kind: "code"`): `section: 3`, `addr` of the
  first replaced byte, `len` = replaced bytes, `stock_sha256` of the original
  bytes, `new` = your `jsr`/`jmp` and `nop`s, `new_sha256`, `why`.
- **Data change** (`kind: "data"`): the same fields, with `new` holding your
  constants or pointers.
- **Code in the area**: an area change with `offset` (from the area start), `len`,
  `kind`, `new`, `new_sha256` and `why`. No `stock_sha256`.
- Change only the bytes you need. Each `why` is one short plain sentence with no
  personal data.

## (e) Export the package JSON

Write one `.sypatch.json` file with the top-level fields from PATCH-FORMAT.md:
`format`, `schema`, `id`, `title`, `requires`, `encoding`, `target`, `area` (only
with area changes), `units`.

- Every hex string is **lowercase**. The checker refuses uppercase.
- `target.stock_sha256` is the hash from step (a).
- `requires` lists every package whose bytes or addresses you rely on, and `[]`
  when there are none.
- Generate the file with a small script that reads your own file only to compute
  hashes. Do not embed original bytes.

[examples/](../examples/README.md) has two small packages that show the shape.

## (f) Validate

```powershell
python tools/sypatch/check_patch.py my-mod.sypatch.json
```

The checker prints `OK`, or `REJECTED` with the reason. It does not check
`requires`, instruction boundaries or the stock bytes; the page does (step g).

Then open the page:

```powershell
cd web
python -m http.server 8000
```

Open `http://localhost:8000/`. Workers do not load from `file://`. The page needs
a local build (`node web/build.mjs`, with the engine path in `ELEKLOADER_JS`, see
the header of `web/build.mjs`). The engine is not in the repo.

In the page, import your `.sypatch.json` (a file picker: the file is read as data,
never executed), then choose your OS file.

## (g) Build in memory and compare the hash

- The page checks the stock hash, every fingerprint, overlaps, instruction
  boundaries and the area round-trip, then builds the `.syx` **in memory**.
- Compare the SHA-256 the page shows with the one from your own reference build,
  made with your own tools from your own file. If the two differ, do not trust
  the package; find out why first.
- Nothing is written to disk and nothing is flashed in this step. The download
  appears only when you click it.
- Test in the emulator before flashing (see [emulation.md](emulation.md) and
  [modding-guide.md](modding-guide.md), section 7). Flash only after reading
  [RECOVERY.md](../RECOVERY.md).

## (h) Share only the package JSON

Share:

- the `.sypatch.json` file;
- a short description;
- its `target` (Syntakt OS 1.41) and its `requires` list.

Never share your OS file, a built `.syx`, a memory dump, disassembly, or emulator
logs that contain bytes. Do not post on Elektronauts (see
[README.md](../README.md#contributing)).

## Checklist

- [ ] Your OS file's SHA-256 equals `STOCK_SHA256` in the checker.
- [ ] The package holds only our bytes and hashes. No original bytes, no paths,
      no personal data.
- [ ] `id` is unique and lowercase. `requires` lists every package you need.
- [ ] Each replace change has `section`, `addr`, `len`, `kind`, `stock_sha256`,
      `new`, `new_sha256`, `why`.
- [ ] Each area change has `offset` within `area.size`, does not overlap other
      ranges, and uses the same `area` layout as its partners.
- [ ] Every hex string is lowercase.
- [ ] Code: no undefined symbols, no `.bss`, the code part decodes as whole
      instructions.
- [ ] `check_patch.py` prints `OK`.
- [ ] The page builds in memory, and its SHA-256 matches your reference.
- [ ] The emulator test passed. Flashing follows RECOVERY.md.
- [ ] Only the package JSON is shared.
