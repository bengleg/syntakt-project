# FX3 coverage: what our mod SDK can and cannot build yet

Checked: 2026-11-21. Read-only review. Nothing was built, flashed or committed.

## Short answer

The package format can already hold most of what fx3 needs. The SDK (the
tool that turns a mod folder into a package) cannot yet produce it. The gap is
mainly in the SDK, not in the format. Three blockers matter most:

1. **Only one kind of hook.** The SDK writes only the "jump and do not come
   back" form. fx3 uses the "call, then carry on" form on eight of its hooks.
2. **About 90 small fixed edits.** fx3 changes many small spots in the OS:
   menu names, icons, parameter tables, a few pointers. The SDK can only write
   whole-function hooks of 6 bytes or more. Small edits need a separate
   generator, or new SDK support.
3. **No room for fx3 yet.** The only slot the SDK has for development is 8 KB.
   fx3's code is about 16 KB and it needs a 4 KB zeroed delay line beside it.
   No registered slot exists for it, and the SDK has no way to reserve zeroed
   RAM.

## What I read

- Ours: `tools/modsdk/modsdk.py`, `tools/modsdk/include/syntakt.h`,
  `tools/modsdk/slots.json`, `docs/SDK.md`, `docs/PATCH-FORMAT.md`,
  `tools/sypatch/check_patch.py`.
- Theirs (public repo, read through the web, nothing downloaded to our
  files): `mods/fx3/README.md`, `mods/fx3/make_patch.py`, and the first
  1,264 of about 1,412 lines of `mods/fx3/fx3.c`. The rest of `fx3.c` (the end
  of the assembly for the routing screen and the file-format code) was cut off
  in the fetch and is not covered here.
- Their `patch.json` was not read or copied, as asked.

## Needs versus our SDK

Status key: **Supported** = works today. **Partly** = possible with a
workaround or only some of it works. **Missing** = the SDK cannot do it.

| # | What fx3 needs | What our SDK does today | Status | What closes it |
|---|---|---|---|---|
| 1 | Several C source files | `sources` in `mod.json` lists any number of `.c` files. Each is compiled and linked together. | Supported | None. |
| 2 | Own header files | The build copies every `.h` in the mod folder next to the sources. | Supported | None. |
| 3 | Generated headers (`fx3_tables.h`, `fx3_names.h`) | Their Python script writes them into a temporary folder before compiling. We have no generate step. | Partly | Commit the generated headers into the mod folder (no SDK change), or add a "run this script first" step. |
| 4 | Inline assembly inside C | The compiler accepts it. The build then checks that `.text` decodes as whole instructions. fx3 puts data words (`.word`) inside its assembly, which may not decode cleanly. | Partly | Build one trampoline as a test. If the check fails, move the data into `.data`. |
| 5 | Separate assembly files (`.s`) | Only `.c` files are accepted. | Not needed | fx3 keeps its assembly inside `.c` files. |
| 6 | Compiler flags per mod (`-D...` defines) | None. Flags are fixed in the SDK. fx3 needs defines for the mod-area address and two layout headers. | Missing | Add a `defines` field in `mod.json` and pass it to the compiler. |
| 7 | Compiler warnings | Any warning fails the build (`-Wall -Wextra`). | Partly | fx3 uses the same flags in its own repo. Whether it is warning-free under ours is not checked. |
| 8 | About 20 whole-function hooks | Hooks have no fixed cap. Each one needs its own fingerprint, and the `fingerprint` command reads and unpacks the whole OS file on every call. | Partly | Works, but slow. Add a batch fingerprint mode. |
| 9 | "Call, then carry on" hooks (`jsr`, 8 of fx3's hooks) | `hook_bytes` writes only the jump form (`jmp`). The 8 hooks would lose their return. | Missing | Add a `kind` of `jsr` or `jmp` to each hook, and write the matching bytes. |
| 10 | "Jump and do not come back" hooks (`jmp`, about 4) | Supported, with the rule that the function must do the replaced work itself. | Supported | None. |
| 11 | Small fixed edits of 2 to 6 bytes (a few immediate values, a one-byte table entry) | The format accepts any even-length replacement with a fingerprint. The SDK refuses hooks shorter than 6 bytes and has no other edit type. | Missing in the SDK; Supported in the format | Add an `edits` list in `mod.json`: address, expected fingerprint, new bytes. Each becomes a replacement block. |
| 12 | Data pointer replacements (menu name pointers, the graphic pointer, the reverb page list) | The format accepts a data replacement with a fingerprint. The SDK cannot make one, and it does not export the addresses of data symbols. | Missing | Export data symbol addresses from the build, and use the same `edits` list as row 11. |
| 13 | Parameter table records (about 52 bytes each, eight new parameters) | Same as rows 11 and 12. Their script writes these records by hand. | Missing in the SDK | Generate them from a script that writes the package directly (see Order of work). |
| 14 | Fingerprint of the original bytes (their `expect_sha256`) | Our `stock_sha256`: the SHA-256 of the original bytes at that address and length. Same idea, different name. The page checks it against the user's own file. | Supported | None. Only the name differs. |
| 15 | Code appended to the image at a RAM address (their `append` and `ram`) | Area blocks: an offset inside the 64 KB mod area, at RAM `0x46000000` plus the offset. The area is compressed into the image. | Supported | Check that our image address and their image address are the same. I did not verify theirs. |
| 16 | Room for about 16 KB of code | The dev slot is 8 KB (`0x2000` to `0x4000`). No registered slot exists. The free range from `0x6E00` to `0x10000` is about 37 KB. | Missing as shipped; Supported once a slot is registered | Register a slot for fx3 in `slots.json`, starting at `0xA000` and ending at `0xF000` or later. Owner: fx3. |
| 17 | Zeroed RAM beside the code (4 KB delay line and a one-word feedback cell, at fixed offsets) | Area gaps are zero-filled, but nothing declares them. The SDK refuses `.bss`, so a zeroed variable cannot be declared. Another mod could write over the gap. | Partly | Add a "reserved zero RAM" entry to `slots.json`, so the gap is owned and cannot be used by someone else. |
| 18 | Hard-coded addresses of OS functions and data | C can cast a fixed address to a function pointer, and the SDK does not stop it. The only shared header is `syntakt.h`, which defines the bus address and frame count. | Partly | Add a shared header of verified OS addresses, each one checked against our own OS file. |
| 19 | Calls into another mod (vparams functions and descriptors) | The build refuses any undefined symbol, so a call into another mod must go by address. `requires` names the mod, but nothing checks that it exists. | Partly | Add a verified address table for each shared mod, and a check that every `requires` entry is a real package. |
| 20 | Dependency on modarea | The SDK always adds `modarea` to `requires`. vparams is not checked: I did not confirm that a vparams package exists in our tree. | Partly | Confirm that a vparams package exists and matches their layout, or port it. |
| 21 | Mod-area layout and owner | Our owner list is `slots.json`. It has DelayCtrl reserved and no other entries. Their owner list is `modarea_layout.py`, which I could not read. | Partly | Choose one layout. Put fx3's range and reserved RAM in `slots.json`, and confirm the image and RAM addresses match theirs. |
| 22 | Settings saved per pattern (kit words, and hooks on the kit writer and reader) | The SDK has no notion of saved settings. The hooks are ordinary jump hooks. The kit words fx3 uses are not reserved in any list we keep. | Partly | Add a list of kit words in `slots.json`, the same way as slots, so two mods cannot use the same word. |
| 23 | Symbols given to hooks and to tables (their `symbols` map) | The build exports function symbols for hook targets only. Data symbols and a symbol file are not written out. | Missing | Write the symbol table out next to the package, and let the generator read it. |
| 24 | Hook clash check | `check_taken` warns when a hook overlaps one in `taken.json`. `--strict` turns the warning into an error. I did not read `taken.json`, so I do not know whether fx3's hooks clash with DelayCtrl. | Supported | Run the build and read the warnings. |
| 25 | Section 7 hooks | Supported. | Supported | None. |
| 26 | Notes shown before ticking, claims, conflicts | Supported. fx3 does not use them, so none are needed. | Supported | None. |
| 27 | Stock parts (copy original bytes from the user's file) | Not supported by the builder. fx3 uses hashes, not copies, so it does not need them. | Not needed | None. |
| 28 | fx3's own tests (`tests/test_fx3.py`, model checks) | Ours are separate. Their tests need their own model code. | Missing | Not needed to build. Needed before any review. |

Rows 8, 11 and 12 are the places where most of the work sits.

## Hooks and small edits: the counts

I counted from reading `make_patch.py`, not by running it.

- About 14 real hooks: 8 "call, then carry on" hooks in the main list, 1 more
  "call" on the routing draw, 4 "jump" hooks (2 for the kit file, 2 for
  routing), and 1 "jump" on the tab draw.
- About 14 small fixed edits of 2 bytes: 3 outside the parameter table, and
  about 11 inside it and the external-input send.
- About 3 pointer writes to data (names, and the reverb page list).
- About 57 entries for the eight parameter records, plus about 9 for the
  external-input send. Together with the rest, about 90 entries in all.

## Mod-area layout

- fx3 links its code at `0xA000` inside the mod area and uses a fixed
  delay line at `0xE000`, which ends at `0xF000`. The feedback cell is at
  `0xDFFC`. These come from its own script.
- Our mod area is `0x10000` bytes, so `0xF000` fits.
- DelayCtrl reserves `0x4000` to `0x6E00`. fx3's range does not overlap it.
- Our dev slot is 8 KB, so fx3 cannot build in it.

## Licence

The repository has a LICENSE file. It is the **MIT licence**. The copyright
line names the repository's author and its contributors. The licence says it
covers only the code and documentation in that repository, and gives no
rights over Elektron firmware.

What this means for us: we may use or copy their code if we keep their
copyright notice and the licence text with it. Their repo does not contain
firmware. I did not check our own licence or `LEGAL.md` for compatibility, so
that check is still open.

## Order of work

The smallest set of SDK changes that would let fx3 build, in order:

1. **Register a slot for fx3** in `tools/modsdk/slots.json`: owner fx3, start
   `0xA000`, end `0xF000`. Add a reserved zero-RAM note for the delay line.
   No code change. Confirm the image and RAM addresses match theirs first.
2. **Add the "call, then carry on" hook kind** in `modsdk.py`: a `kind` field
   on each hook, and `hook_bytes` writes the matching opcode. About 10 lines,
   plus tests in `tests/test_modsdk.py`.
3. **Add a `defines` field** to `mod.json`, passed to the compiler. About 5 lines.
4. **Commit the generated headers** into the fx3 folder, so the build does not
   need their Python script.
5. **Add an `edits` list** for small fixed changes and pointer writes: address,
   expected fingerprint, new bytes. Each entry becomes a replacement block.
   Export the addresses of data symbols so pointers can refer to them.
6. **Build fx3 once** and run `check` on the output. Then compare the warnings
   and the hook clash list.

Option to consider instead of steps 5 and 6: write a small generator that
writes the `.sypatch.json` directly, using the same format and `check_patch.py`.
That needs no SDK change for the edits, but it is one more script to keep.

Recommended first step: steps 1 and 2. They are small, they can be tested on
their own, and they answer whether the rest of fx3 is worth porting.

## What I could not verify

- I did not run `modsdk.py`, `check_patch.py` or any test. Every status above
  comes from reading the code.
- I did not read the rest of `fx3.c` (about 150 lines after the cut-off), nor
  their `modarea_layout.py`, `dualmono_layout.py` or `vparams` code. Their
  defines depend on those files.
- I did not read `tools/modsdk/taken.json`, so the hook clash result is unknown.
- I did not confirm that a vparams package exists in our tree.
- I did not check that fx3's code compiles warning-free under our flags.
- I did not check the fixed OS addresses fx3 uses. They come from their own
  analysis of the OS, and must be checked against our own OS file before any
  build.
- I did not check the 15.7 KB code size. It comes from the brief, not from a
  build.
- Our own licence and `LEGAL.md` were not compared with the MIT licence.
