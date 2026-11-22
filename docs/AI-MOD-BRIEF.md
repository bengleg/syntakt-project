# AI brief: write or change a Syntakt mod

Audience: an AI coding helper asked to write or change a mod for the Syntakt
SDK. Read this file, then the repo files it names. You need nothing else.

Paths below are relative to the `builder-web` folder. Run every command from
the `builder-web` folder too.

Background for humans: [SDK.md](SDK.md) is the plain guide. This file is the
working brief for an AI.

## 1. Hard rules (read first, never break)

| # | Rule |
|---|---|
| 1 | **Never write, paste, quote, invent, summarise or guess stock OS 1.41 bytes, dumps, byte listings or disassembly.** Hashes of stock bytes are allowed. Use only the `fingerprint` command for them. |
| 2 | **Never commit or stage firmware-like files:** `.syx`, `.smz4`, `.bin`, `.elemod`, `.elf`, `.img`, `.raw`. The `dist-mods/` folder is git-ignored, but still do not copy built files into any other place. Share source and `mod.json` only. |
| 3 | **Never write an absolute path, a user name, a machine name or an account detail** into any file, comment, log, commit or report. Use relative paths such as `mods/my-mod/main.c`. The user's OS file path is never written into a repo file. |
| 4 | **Never flash, upload, publish, push, post or send** anything. Never contact a device. The SDK does none of these. You do none of these either. Ask the user first, using the `question` tool with options. |
| 5 | **Originals are read-only.** Never change, move, rename or delete the user's OS 1.41 file, or any file in a `firmware/` folder. Work on copies outside the repo. |
| 6 | **Never commit to git.** Leave changes in the working tree. |
| 7 | **Never edit a file outside the mod folder** unless the user names it. In particular do not edit `tools/modsdk/slots.json` or `tools/modsdk/modsdk.py` to get a build to pass. |
| 8 | **Never claim a check passed** unless you ran it in this session. Report the exact output. |
| 9 | **Stay on OS 1.41.** The SDK refuses any other OS. Do not try to make it accept one. |
| 10 | **A passing check is not proof that the unit works.** The page checks the file format, not what your code does. Say so in every report. |

## Check what is already taken before you write

- Before you write any hook, read `tools/modsdk/taken.json`. It lists the spots
  already hooked by shipped packages, including DelayCtrl.
- If `taken.json` is missing, do not guess. Say so in the report and ask the
  user before you write a hook.
- DelayCtrl already owns the FX delay engine: its "delay" hook and the FX
  silence. Do not write a new delay, repeater or FX delay routing mod unless the
  user says so explicitly and names the conflict.
- `build` prints a `Warning:` line when a hook lands on a taken spot. Add
  `--strict` to turn that warning into a failed build. Use `--strict` when you
  are unsure. A warning is still a reason to stop and ask, as below.
- If you find a clash, stop and ask the user which way to go. Do not hook the
  same spot to "fix" it. Offer these options with the `question` tool:
  pick a different spot, add the mod to the other package's `conflicts` list, or
  drop the change.
- The SDK compares addresses only. It does not know what a hook does. So a
  passing build does not prove there is no clash in behaviour. Say so in the
  report.
- In the report, say whether `taken.json` was checked and what it showed.

## 2. The task recipe

Follow the steps in order. Stop where the stop rule says.

### Step 0: ask the user for what you cannot know

Before you write any hook, ask the user (with the `question` tool) for:

- the hook address (`addr`), the length of the change (`len`) and the stock
  fingerprint (`stock_sha256`), or permission to get the fingerprint with the
  `fingerprint` command;
- the path to their own OS 1.41 file, given to the command only. Do not write
  it down.

Never guess an address. Never guess a length. Never fill in a fingerprint from
memory or from another mod. If the user cannot give them, make a mod with no
hooks (`"hooks": []`) and say that hooks are pending.

### Step 1: start a new mod (or work in an existing folder)

```
python tools/modsdk/modsdk.py init <id>
```

- `<id>` must use only lowercase letters, digits and hyphens. Example: `my-mod`.
- `init` creates `mods/<id>/mod.json` and `mods/<id>/main.c`.
- `init` refuses an id with other characters, and refuses a folder that already
  exists. It has no other options.

To change an existing mod, skip `init` and edit the files in its folder.
A worked example is in `mods/hello-sdk/`. It has no hooks and builds OK. Copy its
shape, not its name.

### Step 2: edit `mod.json` and `main.c`

Edit only the files in `mods/<id>/`. Follow sections 3 to 6 below.

### Step 3: build

```
python tools/modsdk/modsdk.py build mods/<id>
```

- Writes `dist-mods/<id>.sypatch.json`.
- Optional: `--out DIR` to write to another folder. Use it only if the user asks.
- Needs WSL with the m68k toolchain. If it is missing, the build prints an error
  and stops. Do not try to install it. Report it and stop.
- A compiler warning refuses the build. Fix the C code, then build again.
- The build prints the code size, the data size, the slot used and each hook.

### Step 4: check

```
python tools/modsdk/modsdk.py check dist-mods/<id>.sypatch.json
```

- Prints `OK`, exit code 0.
- Prints `REFUSED: <reason>`, exit code 1. Fix the reason, then go back to Step 2.
- Prints `OK, but the page check was skipped` when Node.js is missing. This is
  **not** a full pass. Report it as "format checked, page check skipped".

### Step 5: stop

Stop when the build prints `Built ...` and the check prints `OK`. Then:

1. Run the checklist in section 8.
2. Write the report in section 9.
3. Hand the files back. Say that the next steps (emulator, then flashing) are
   the user's decision.

Stop earlier, and ask the user, when:

- the build needs something you cannot install (WSL, the toolchain);
- a hook needs an address, length or fingerprint you were not given;
- the user asks for a registered slot (see section 7);
- the mod needs more room than its slot holds (the build says so).

Do not flash, upload or publish, whatever the user's earlier message says,
unless the user names that exact action in this session.

### Commands: the complete list

Only these commands and flags exist in `tools/modsdk/modsdk.py`. Do not invent others.

| Command | Flags | What it does |
|---|---|---|
| `python tools/modsdk/modsdk.py init <id>` | none | Makes `mods/<id>/` from the templates. |
| `python tools/modsdk/modsdk.py build <folder>` | `--out DIR` (optional), `--strict` (optional) | Builds one `.sypatch.json`. Default output: `dist-mods/`. `--strict` fails the build on a hook clash warning. |
| `python tools/modsdk/modsdk.py check <file>` | none | Prints `OK` or `REFUSED: ...`. |
| `python tools/modsdk/modsdk.py fingerprint --stock <OS file> --addr 0x<hex> --len <N>` | all three required | Prints one SHA-256 of the bytes at that place in the user's OS file. Never prints bytes. |
| `python tools/modsdk/modsdk.py slots` | none | Shows the mod area, reserved ranges, the dev slot, registered slots and free ranges. |

`fingerprint` needs `elektron-firmware-tool`, found on the PATH or through the
`EFT_BIN` environment variable. If it is missing, the command says so. Do not
install it yourself.

## 3. The code rules

| Rule | Why | What to do |
|---|---|---|
| Plain C only. | The mod has no standard library. | No `printf`, `malloc`, `memcpy`, `string.h`, `stdio.h`. Write your own loop. |
| No compiler helper library (libgcc). | The build refuses it. | Avoid 64-bit maths and anything else the compiler turns into a helper call. The build names the missing helper if one slips in. |
| Every global variable is `DATA` with a non-zero start value. | Zero-start variables go to `.bss`, which the build refuses. | `DATA u32 count = 1;` Use the `DATA` macro from `syntakt.h`. |
| Global functions only for `entry` and `call`. | The build looks up global names. | Do not write `static` on those. |
| Keep functions small. | ColdFire has short-branch limits (a `bra.s` or `bne.s` reaches 127 bytes). | The compiler picks the branch form. Keep functions short. |
| Save every register you change. | The OS keeps values in registers. | The C compiler does this for C functions. If you write assembly, save and restore. |
| Do not write `exg`. Use `movem` only with `(An)` or `d16(An)`. | Rules from `syntakt.h`. | Prefer plain C. |
| Use `syntakt.h`. | It has the common types and known constants. | `#include "syntakt.h"` at the top of each C file. |
| No compiler warnings. | Any warning refuses the build. | Build, read the warning, fix the code. |

The compiler flags are fixed by the SDK: `-mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra`. Do not change them.

### What `syntakt.h` gives you

| Name | What it is |
|---|---|
| `u8`, `u16`, `u32` | Unsigned integers, 8, 16 and 32 bits. |
| `s32` | Signed 32-bit integer. |
| `DATA` | Puts a global variable in the mod's own `.data` section. Use as `DATA u32 name = 1;`. |
| `FX_BUS` | Pointer to the digital tracks sent to the FX block, `(s32 *)0x8000DAD0u`. |
| `FRAMES` | 32. The frame count of `FX_BUS`. |

Do not add your own addresses to the header. Put them in your C file, with a comment saying where they came from (in plain words, not as stock bytes).

### Sources and headers

- `sources` in `mod.json` lists C file names only, such as `["main.c"]`. Each one must be a plain file name in the mod folder. No folders, no slashes.
- Extra `.h` files in the mod folder are copied to the build for you.

## 4. Hooks

### What a hook is

A hook is a spot in the OS where your code takes over. The SDK writes a jump
(6 bytes) at that spot, then fills the rest of the replaced length with no-op
instructions. The jump sends the OS into your function.

### The rule your function must obey

**The SDK does not replay the replaced instructions.** Your function must do their
work itself, then return. Without this the OS loses those steps.

```
my_function():
    do my own work
    do the same steps the original instructions did
    return
```

You can only write these steps if the user gave you the original instructions in
their own tools. Do not look them up in any file in the repo. Do not reconstruct
them from memory.

### The three inputs you must ask the user for

| Input | Rule | Where it comes from |
|---|---|---|
| `addr` | Text such as `"0x400004b2"`. Must be at or above `0x40000400`. | The user's own analysis of their own OS 1.41 file. |
| `len` | A whole number of bytes. Even. At least 6. Covers whole instructions. | The same analysis. |
| `stock_sha256` | 64 lowercase hex characters. | Run the `fingerprint` command (below). |

### The fingerprint command

```
python tools/modsdk/modsdk.py fingerprint --stock <path to the user's OS 1.41 file> --addr 0x<hex> --len <N>
```

- It prints one SHA-256 line. Copy only that line into `stock_sha256`.
- It refuses any file that is not the OS 1.41 file.
- It needs `elektron-firmware-tool`. See section 2.
- Use the path the user gives you. Do not write that path into any file.

**The AI must not guess addresses.** An address written by guess passes the build
but breaks the OS. If you do not have a confirmed `addr`, `len` and fingerprint
from the user, do not write a hook.

### Hook fields

Each hook is one object in the `hooks` list of `mod.json`.

| Field | Required | Allowed value |
|---|---|---|
| `id` | yes | Lowercase letters, digits and hyphens. Unique in this mod. |
| `addr` | yes | Text, `"0x"` then hex. At or above `0x40000400`. |
| `len` | yes | Whole number, even, at least 6. |
| `stock_sha256` | yes | 64 lowercase hex characters. |
| `call` | yes | Name of a global C function in your sources. |
| `why` | yes | One plain sentence saying what the change does. Not empty. |
| `section` | no | `3` or `7`. Leave it out for `3`. |
| `kind` | no | `"jmp"` (default, jump and do not come back) or `"jsr"` (call, then the OS carries on after the replaced bytes). With `"jsr"` the SDK still does not replay the replaced instructions. |

Any other field is refused. Check the spelling.

### Hook example (shape only)

```json
"hooks": [
  {
    "id": "freeze-trig",
    "addr": "<addr from the user>",
    "len": 6,
    "stock_sha256": "<the 64-character line from fingerprint>",
    "call": "freeze_entry",
    "why": "Runs the freeze check before the FX step."
  }
]
```

The values in angle brackets are placeholders. Replace them only with values the
user gave you. Do not keep a placeholder in a file.

## 5. `mod.json`

### Top-level fields

| Field | Required | Allowed value |
|---|---|---|
| `id` | yes | Lowercase letters, digits, hyphens. Not the same as another package's id. |
| `title` | yes | Text, not empty. Shown on the page. |
| `version` | yes | Text, not empty. Example: `"0.1"`. |
| `author` | yes | Text, not empty. Use a neutral name, never a real person's name the user did not give. |
| `target` | yes | Exactly `{"device": "Syntakt", "os": "1.41"}`. |
| `requires` | no | List of package ids. `[]` if none. No duplicates. Cannot list this mod. |
| `sources` | yes | List of C file names, such as `["main.c"]`. Not empty. |
| `entry` | yes | Name of a global C function. |
| `slot` | yes | `"dev"`, or a registered slot name you were given (section 7). |
| `hooks` | no | List of hook objects. `[]` if none. |
| `edits` | no | List of edit objects (small fixed byte changes, same rules as hooks, with `hex` for the new bytes). `[]` if none. |
| `defines` | no | List of `NAME` or `NAME=VALUE` text, passed to the compiler as `-D` flags. `[]` if none. |
| `info` | no | Notes block (section 6). Leave it out if you have none. |

Any other top-level field is refused. Required fields missing are refused.

Never guess an edit's address or bytes. Get both from the user, with the
fingerprint from `fingerprint`, the same as for a hook.

The build adds `modarea` to `requires` on its own. Do not add it yourself.

## 6. The info block

The `info` block gives the notes the page shows before a visitor ticks the mod.

### Fields

| Field | Required | Allowed value |
|---|---|---|
| `summary` | no, but add it | One plain sentence. Text, **200 characters or fewer**. |
| `claims` | no | List of text. Each item must start with `ui:`, `param:` or `audio:`, followed by some text. `[]` when none. |
| `conflicts` | no | List of package ids that this mod cannot be used with. `[]` when none. Cannot list this mod itself. |
| `cost` | no | `null` unless measured. Otherwise an object (below). |

### The `cost` object

| Field | Allowed value |
|---|---|
| `instructionsPerBlock` | Whole number, 0 or more. |
| `measured` | Text saying what was measured and where. Example: `"emulator, 2026-11-18, one trigger"`. |

Set `cost` to `null` unless someone actually measured it. Do not estimate it. The
SDK does not measure cost for you.

### Example

```json
"info": {
  "summary": "Freezes the FX track on a trigger.",
  "claims": ["ui:TRIG 13-16 on the FX track"],
  "conflicts": [],
  "cost": null
}
```

Any unknown field, or a wrong type, is refused by the build with a plain sentence.
A visitor sees these notes labelled as "declared by the file's author, not
checked".

## 7. Slots

Every mod sits at one fixed place in a 64 KB mod area. That place is its **slot**.
The mod area starts at RAM `0x46000000`. Slot numbers are offsets from there.

### The current layout (from `tools/modsdk/slots.json`)

| Name | Range | Who may use it |
|---|---|---|
| `delay-control` (reserved) | `0x4000` to `0x6e00` | DelayCtrl only. Do not use. |
| `dev` | `0x2000` to `0x4000` (8192 bytes) | Anyone, for trying things on the page. Never the reviewed list. |
| Registered slots | none at the time of writing | Only the named owner. `dev` cannot be registered. |

Free ranges are shown by the `slots` command. Run it to see the current state:

```
python tools/modsdk/modsdk.py slots
```

### Rules

- **Use only `"dev"`** in `mod.json`, unless the user names a registered slot.
- Do not edit `tools/modsdk/slots.json` to make a slot for yourself. Ask the user
  first (section 2, Step 0 style: `question` tool, with options).
- Code and data together must fit the slot. The build says how many bytes are
  used and how many the slot holds. The `dev` slot holds 8192 bytes.
- A registered slot name that is not yours is refused by the build.

## 8. Checklist before you report "done"

Run through every line. A line you did not do is a gap. Write it in the report.

- [ ] `init` ran (or the existing folder was edited in place).
- [ ] `build mods/<id>` ran and printed `Built <id> ...`. Record the exact line.
- [ ] `check dist-mods/<id>.sypatch.json` ran and printed `OK`. If it printed
      `OK, but the page check was skipped`, record that as "page check skipped".
- [ ] Every hook has `addr`, `len`, `stock_sha256` from the user or from
      `fingerprint`. No value was guessed.
- [ ] Each hook's function does the work of the replaced instructions.
- [ ] `info` (if present) follows section 6. `summary` is 200 characters or fewer.
- [ ] `cost` is `null`, unless it was measured and the measurement is named.
- [ ] No file in the mod folder or the repo contains a firmware-like file
      (`.syx`, `.smz4`, `.bin`, `.elemod`, `.elf`, `.img`, `.raw`). Look at
      `mods/<id>/` and `dist-mods/`. Built files stay in `dist-mods/`, which is
      git-ignored, and are never shared.
- [ ] No file you wrote contains an absolute path, a user name, a machine name
      or any stock bytes. Search your own changes for `C:\`, `/Users/`, `/home/`
      and any name the user did not put in `author`.
- [ ] Nothing was committed, flashed, uploaded, published or pushed.
- [ ] `slot` is `"dev"`, unless the user named a registered slot.
- [ ] `taken.json` read, and any warnings reported.

## 9. Report template

Use this shape. Plain sentences. Put the real output in the code block.

```
What changed:
- <file>: <one line on what changed>
- ...

What was run, and the exact result:
- python tools/modsdk/modsdk.py build mods/<id>
  <paste the output lines>
- python tools/modsdk/modsdk.py check dist-mods/<id>.sypatch.json
  <paste the output line: OK, or REFUSED: ..., or OK but the page check was skipped>
- (any other command, with its result)

Not verified:
- The unit has not been tested. Nothing has been run in the emulator.
- The page check does not check what the code does, or whether the unit starts.
- <hook addresses and fingerprints: "given by the user, not checked against the OS file", if so>
- <anything from the checklist you did not do, and why>

Where to review:
- mods/<id>/mod.json
- mods/<id>/main.c
- dist-mods/<id>.sypatch.json (git-ignored, not for sharing)

Questions for the user (if any), with options:
- <question>
```

Do not write the report with "it works", "safe" or "tested" unless you ran the
test in this session and can paste its output.

## 10. What the SDK does not do

- It does not measure cost.
- It does not replay the replaced instructions in a hook.
- It does not test your code on the unit or in the emulator.
- It does not check that the unit will still start. The start-up margin check
  (`tools/build/bootcheck.py`) runs on a built file, outside the SDK.
- It does not put your mod on the reviewed list. That needs the owner's review
  (see [SDK.md](SDK.md), "Getting your mod on the reviewed list").
