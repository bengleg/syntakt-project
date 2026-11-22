# Mod SDK: write C, get a mod file

This guide is for a hobbyist who can write simple C. You do not need to be a
firmware engineer. A **mod** is a small change to the Syntakt's operating
system (OS 1.41). You write it in C, and the SDK turns it into one file that
the page can check and use.

Nothing here contains Elektron's firmware. You use your own OS 1.41 file, on
your own computer.

## What you need

- Python 3.11 or newer.
- Node.js (the page's checks run on it).
- WSL Ubuntu with the m68k toolchain. The m68k toolchain is the compiler that
  makes code for the Syntakt's processor. Install steps are in
  [CONTRIBUTING.md](../CONTRIBUTING.md).
- Your own OS 1.41 file, kept outside the repository.
- The elektron-firmware-tool, only for the `fingerprint` command. Install it,
  or set `EFT_BIN` to its path. Setup is in `tools/unpack/setup_eft.sh`.

## Quick start

Run these from the repository root, in order.

1. `python tools/modsdk/modsdk.py init my-mod`
   Creates `mods/my-mod/mod.json` and `mods/my-mod/main.c`. It refuses an id
   that is not lowercase letters, digits and hyphens, and a folder that already
   exists.
2. Edit `mods/my-mod/mod.json` and `mods/my-mod/main.c` in a text editor.
3. `python tools/modsdk/modsdk.py build mods/my-mod`
   Writes `dist-mods/my-mod.sypatch.json` inside the repository. Add `--out DIR`
   to choose another folder. The build needs WSL with the m68k toolchain. If it
   is missing, the build says so and stops.
4. `python tools/modsdk/modsdk.py check dist-mods/my-mod.sypatch.json`
   Prints `OK`, or `REFUSED:` with the reason and exits with code 1. If Node.js
   is not installed it prints `OK, but the page check was skipped`.
5. Open the page, go to section 2, and add the `.sypatch.json` file. Tick it,
   pick your OS file in section 3, and press Build.

## What goes in mod.json

| Field | What it means |
|---|---|
| `id` | Your mod's short name. Lowercase letters, numbers and dashes. |
| `title` | The name shown on the page. |
| `version` | Your version number, for example `1.0`. |
| `author` | Your name or handle. |
| `target` | Leave as `device` "Syntakt" and `os` "1.41". |
| `requires` | Ids of other mods yours needs. `[]` if none. |
| `sources` | The C files to build. Usually `["main.c"]`. |
| `entry` | The name of the function the mod starts from. |
| `slot` | `"dev"` for trying things, or a slot name given to you (see Slots). |
| `hooks` | The list of changes to the OS. `[]` if you have none. |
| `edits` | Small fixed changes to the OS, such as a few bytes. Optional. See [Edits](#edits). |
| `defines` | Settings passed to the C compiler, such as `"MOD_BASE=0x4000"`. Optional. See [Defines](#defines). |
| `info` | Optional notes the page shows before a visitor ticks the mod. See [The info block](#the-info-block). |

## The code rules

- Write plain C. The standard library is not available: no `printf`, no
  `malloc`, no `string.h`.
- Do not use anything that needs the compiler's helper library (libgcc). The
  build refuses code that needs it.
- Give every global variable a starting value. The build refuses variables
  that have none. The `DATA` macro in `tools/modsdk/include/syntakt.h` helps.
- The processor (ColdFire) has limits. Keep functions small. Save every
  register you change, because the OS keeps values in registers.
- `tools/modsdk/include/syntakt.h` has the common types and a few known
  constants. Use it.

## Hooks

A **hook** is a spot in the OS where your code takes over for a moment. The
SDK puts a jump at that spot. The jump sends the OS into your function.

To write a hook you need three things from your own tools, run on your own
OS file:

- `addr`: the address where the hook starts.
- `len`: how many bytes the hook replaces. It must be even and at least 6.
- `stock_sha256`: a fingerprint of the original bytes at that address.

Get the fingerprint with the SDK. It prints only a hash, never the bytes. It
refuses any file that is not the OS 1.41 file:

`python tools/modsdk/modsdk.py fingerprint --stock <your OS file> --addr 0x<address> --len <N>`

Each hook is one object with these fields: `id` (lowercase letters, digits and
hyphens, unique in the mod and across edits), `addr`, `len`, `stock_sha256`, `call` (the name of
your C function), `why` (one sentence), `section` (3 or 7; leave it out for 3),
and `kind` (`"jmp"` or `"jsr"`; leave it out for `"jmp"`). Any other field is refused.

Your function must do the work of the instructions the jump replaced, before
it returns. The SDK does not do this for you. If you skip it, the OS loses
those steps and may misbehave. In plain words, the pattern is:

```
my_function():
    do my own work
    do the same steps the original instructions did
    return
```

### Hook kind: jmp or jsr

The `kind` field picks how the OS reaches your function:

- `"jmp"` (the default): the OS jumps to your function and does not come back.
  Your function's `return` returns to whoever called the hooked spot.
- `"jsr"`: the OS calls your function, and when it returns the OS carries on
  after the replaced bytes.

Example (fake address and fake fingerprint):

```json
{
  "id": "demo-call",
  "addr": "0x400004a0",
  "len": 8,
  "stock_sha256": "<64 characters from fingerprint>",
  "call": "demo_entry",
  "kind": "jsr",
  "why": "Calls the demo function, then lets the OS carry on."
}
```

With `"jsr"` the SDK still does not replay the replaced instructions. So the
function must do the replaced work itself, unless the replaced bytes were only
padding (the no-op bytes the SDK adds to fill `len`).

## Edits

An **edit** is a small fixed change to the OS: a few bytes, such as one value in
a table. Use an edit when a hook would be too big for the change. Edits go in
the optional `edits` list. Each edit is one object with these fields:

- `id`: lowercase letters, digits and hyphens. Unique across hooks and edits.
- `addr`, `section`: as for a hook (`section` is 3 or 7, and 3 when left out).
- `len`: an even number of bytes, at least 2.
- `stock_sha256`: the fingerprint of the original bytes, from `fingerprint`.
- `hex`: the new bytes, as lowercase hex with exactly `len` bytes (two
  characters for each byte, no spaces).
- `why`: one sentence.

The SDK never reads or prints the original bytes. You give it the address and
the new bytes. Get both from your own analysis of your own OS file, never guess
them.

```json
{
  "id": "demo-table-entry",
  "addr": "0x400004c0",
  "len": 2,
  "stock_sha256": "<64 characters from fingerprint>",
  "hex": "00ff",
  "why": "Changes one table value from the demo."
}
```

Each edit is checked like a hook. It must not overlap another change, and the
build warns if it lands on a spot that a shipped package already makes.

## Defines

`defines` passes settings to the C compiler, so one C file can be built in
different ways. Each entry is `NAME` or `NAME=VALUE`. Your C code can then use
the name. `NAME` starts with a letter or underscore, and uses only letters,
digits and underscores. `VALUE` uses only letters, digits, underscores and
minus signs, with no spaces or quotes. Anything else is refused.

```json
"defines": ["MOD_BASE=0x4000", "DEBUG"]
```

Each entry becomes one `-D` flag for the compiler, for example `-DMOD_BASE=0x4000`.

## The info block

The optional `info` block in `mod.json` gives the notes the page shows before a
visitor ticks your mod. Leave it out and the mod still builds. The page then
shows no notes for it. The build copies the block into the `.sypatch.json` file
as its `info`. It never goes into the OS bytes.

```json
"info": {
  "summary": "Freezes the FX track on a trigger.",
  "claims": ["ui:TRIG 13-16 on the FX track"],
  "conflicts": ["delay-control-core"],
  "cost": null
}
```

- `summary`: one plain sentence, 200 characters or fewer.
- `claims`: a list of text. Each claim must start with `ui:`, `param:` or
  `audio:`, then say what it claims. Two mods that claim the same text are shown
  as conflicting. Use `[]` when there are none.
- `conflicts`: a list of package ids that your mod cannot be used with. The
  page shows the conflict whichever mod lists it. Use `[]` when there are none.
- `cost`: `null` if you have not measured it. Otherwise an object with
  `instructionsPerBlock` (a whole number, 0 or more) and `measured` (text saying
  what was measured and where, such as `"emulator, 2026-11-18, one trigger"`).
  The SDK does not measure the cost for you.

The build refuses an unknown field in the block, and a wrong type, with a plain
sentence. When a visitor adds your file, the page labels these notes as
declared by the file's author, not checked. The site owner's notes for your mod
override them key by key.

## Slots

Every mod sits at a fixed place in one shared memory area of 64 KB. That place
is its **slot**. `tools/modsdk/slots.json` lists:

- reserved ranges, already used by DelayCtrl (0x4000 to 0x6e00);
- the `dev` range: 8 KB, from 0x2000 to 0x4000, for trying things;
- registered ranges, each given to one named mod. Only the owner named in
  `slots.json` can use a registered range. `dev` cannot be registered.

Run `python tools/modsdk/modsdk.py slots` to see them, and the free ranges too.
A mod in the `dev` slot is fine to try on the page. It is never put on the
site's reviewed list.

## What the page checks, and what it cannot

The page checks:

- your OS file's hash;
- every fingerprint in the file;
- that no two changes overlap;
- that every change covers whole instructions;
- that everything fits in the memory area.

Then it builds the file in memory.

The page does check the start-up margin. It replays the unpacking the same way
`tools/build/bootcheck.py` does, and it refuses a file below 4 KB. It does **not**
replay your code, so it cannot say your unit will start. It also does **not**
check what your code does. So every file you add is "trusted only" for what the
code does: you are trusting its author.

## Test before flashing

1. Run the mod in the emulator first (see [emulation.md](emulation.md)).
2. Read [RECOVERY.md](../RECOVERY.md) before you put anything on a real unit.
3. Only then flash, and only your own unit.

## Getting your mod on the reviewed list

The site has a reviewed list in `web/patches/manifest.json`. Mods on it are the
ones people can rely on. To get on it:

1. Send the owner your C source and your `mod.json`. Do not send a built file.
2. The owner reviews the code, assigns a slot, builds it and runs the emulator
   tests.
3. If it passes, the owner adds it to the list.

## Rules

- Never put firmware bytes in a mod: no `.syx`, `.bin`, `.elf` or similar, and
  no OS bytes copied from a dump.
- Never share a `.syx` file. Share only source and `mod.json`.
- Do not post mods or files on Elektronauts.
- Do not write your own OS file's path or your name into a file that you share.

## For people who want the raw format

The `.sypatch.json` format is described in [PATCH-FORMAT.md](PATCH-FORMAT.md).
Writing one by hand is covered in [AUTHORING.md](AUTHORING.md). Most people do
not need either.
