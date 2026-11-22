# Start here: making your first mod

This guide is for you if you make music and want to change how the Syntakt
works, without being a programmer. A **mod** is a small change to the
Syntakt's operating system (its built-in software, OS 1.41). You write the
change in a few lines of C (a common programming language). The SDK (the
software kit in `tools\modsdk`) turns your lines into one file. The builder
page checks that file and makes it ready to use.

Nothing in this guide contains Elektron's software. You always use your own
OS 1.41 file, kept on your own computer.

The full technical guide is [SDK.md](SDK.md). This page is the easy route in.
Run all commands from the `builder-web` folder, the one that holds `tools`
and `mods`.

## 1. What you need before you start

| Item | What it is for | Hard? |
|---|---|---|
| Python 3.11 or newer | Runs the SDK. | Easy. Free from python.org. |
| Node.js | Runs the page's own checks. Without it the SDK still works, but it skips one check. | Easy. |
| WSL Ubuntu with the m68k toolchain | Turns your C lines into machine code for the Syntakt's chip. WSL is a Linux system inside Windows. The toolchain is the set of tools that does the turning. | **Hard.** Setup steps are in [CONTRIBUTING.md](../CONTRIBUTING.md). A helper may be needed. |
| Your own OS 1.41 file | Needed to find addresses and fingerprints for hooks. Keep it outside the project folder. | Easy to have. Never move it or edit it. |
| elektron-firmware-tool | Reads your OS file. Only needed for the `fingerprint` command. Setup is in `tools\unpack\setup_eft.sh`. | **Hard.** A helper may be needed. |
| An emulator | A computer program that runs the Syntakt's code on your PC, so you can test a mod before it touches a real unit. See [emulation.md](emulation.md). | Medium. |

You can make a simple mod with only Python, WSL and the toolchain. You need
the file and the fingerprint tool only when you want a **hook**, which is
explained in section 4.

## 2. The flow in one screen

```
1. write      edit main.c and mod.json          (text editor)
2. build      python tools/modsdk/modsdk.py build mods/my-mod
3. check      python tools/modsdk/modsdk.py check dist-mods/my-mod.sypatch.json
4. open page  open the builder page
5. add file   section 2: add dist-mods\my-mod.sypatch.json and tick it
6. pick OS    section 3: pick YOUR OS 1.41 file
7. build      press Build on the page
8. emulator   test it on your PC first
9. unit       only after step 8 passes, and only on your own unit
```

Steps 1 to 3 happen in the SDK. Steps 4 to 7 happen on the page. Step 8 is
your own test on your PC. Step 9 is the last step, and only you decide it.

## 3. Your first mod

**Step A. Make the folder.** Run this:

```
python tools/modsdk/modsdk.py init my-mod
```

It makes the folder `mods\my-mod` with two files. The id must use only
lowercase letters, numbers and dashes. The command refuses a name that is
already taken.

**Step B. Know the two files.**

- `mod.json` is the label. It tells the SDK your mod's name, version and
  author, and which C file to build. Its id, title, version and author are
  the things to change first.
- `main.c` is the code. It holds one function (the part that does the work)
  and one counter (a number that remembers things while the mod runs).

**Step C. Change the label and the code.** Look at the example
`mods\hello-sdk`. It is a working mod that counts its own calls. Copy its
style. Change `id`, `title`, `author` and `version` in `mod.json`. Keep
`"hooks": []` for now, so the mod changes nothing in the OS yet. Keep
`"slot": "dev"`, which is the development space for trying things.

**Step D. Build.** Run:

```
python tools/modsdk/modsdk.py build mods/my-mod
```

It writes `dist-mods\my-mod.sypatch.json`. The build stops with a plain
message if something is wrong, such as a missing toolchain or a compiler
warning. Fix the named problem and build again.

**Step E. Check.** Run:

```
python tools/modsdk/modsdk.py check dist-mods/my-mod.sypatch.json
```

It prints `OK`. If it prints `REFUSED:` with a reason, fix that reason. If
it says the page check was skipped, install Node.js and check again.

Your first mod is now ready to add to the page (steps 4 to 7 in section 2).

## 4. Hooks: the hard part

A **hook** is a spot in the OS where your code takes over for a moment. Think
of a detour sign placed over one stretch of road. Traffic (the OS) turns off
at the sign, drives through your function, and must then come back onto the
road. The sign replaces a few stock instructions (the OS's own steps) with a
jump to your code.

Your function must do the work of the steps the sign covered. The SDK does
not do this for you. If it is skipped, the OS may misbehave.

A hook needs three facts, from your own OS file:

- `addr`: where the sign goes.
- `len`: how many bytes the sign covers. Even, and at least 6.
- `stock_sha256`: a fingerprint (a short code that identifies exact bytes)
  of the original bytes at that spot. The SDK never prints the bytes, only
  this code. Get it with:

```
python tools/modsdk/modsdk.py fingerprint --stock <your OS 1.41 file> --addr 0x<address> --len <N>
```

The command refuses any file that is not the OS 1.41 file.

**Open gap: finding the address.** This guide does not yet show how to find
the right `addr` for a sound or a button. The SDK does not have a command
for it, and the guide does not describe one. Do not guess an address. Until
that method is written down, hooks are for people who already have an
address from a trusted source. Ask a helper (section 6).

## 5. Safety

- **Test in the emulator first.** Run the mod on your PC before it touches a
  unit. See [emulation.md](emulation.md).
- **Read [RECOVERY.md](../RECOVERY.md) before any real unit.** It explains how
  to restore a Syntakt that will not start. Do one dry run with the stock OS
  first.
- **Only flash your own unit.** Never flash a unit that is not yours.
- **Never share a `.syx` file.** That is the file the Syntakt loads. It is
  made from your OS, so it must stay on your computer.
- **Never put your OS file's path or name into a shared file.** Keep your
  own folder names out of anything you send.
- **Do not post mods or files on Elektronauts.**
- **The page trusts the file's author.** The page checks the file's shape,
  not what the code does. Only add files from people you trust.

## 6. Where to ask for help, and what to send

Ask on the project's issue page, or ask the person who gave you this
project. Say what you are trying to do and paste the exact message the SDK
printed.

When you send a mod to a helper, send only:

- the C file (`main.c`, or any other `.c` in the folder);
- `mod.json`.

Never send the built file (`dist-mods\...sypatch.json` or any `.syx`). Never
send your OS file. Check the folder before you send it.

To get a mod onto the site's reviewed list, the owner reviews your code,
assigns a slot, and runs the emulator tests. Only then does it go on the
list. See the last part of [SDK.md](SDK.md).
