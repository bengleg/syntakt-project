"""Mod SDK: one folder with C code and a mod.json becomes one .sypatch.json package.

    python tools/modsdk/modsdk.py init <id>
    python tools/modsdk/modsdk.py build <mod folder> [--out DIR]
    python tools/modsdk/modsdk.py check <file.sypatch.json>
    python tools/modsdk/modsdk.py fingerprint --stock <your OS 1.41 file> --addr 0x... --len N
    python tools/modsdk/modsdk.py slots

build needs WSL with the m68k toolchain (the same one mods/delay-control uses). It reads no firmware.
fingerprint reads your own OS 1.41 file and prints only a SHA-256. Nothing here writes into a firmware file.

A hook replaces a few stock instructions with a jump to a function of yours. The SDK cannot replay the
replaced instructions for you: the function must do their work itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "unpack"))
sys.path.insert(0, str(REPO / "tools" / "sypatch"))
import eft  # noqa: E402
import check_patch as cp  # noqa: E402

SLOTS = HERE / "slots.json"
TAKEN = HERE / "taken.json"
TEMPLATES = HERE / "templates"
INCLUDE = HERE / "include"
VALIDATE = HERE / "validate.mjs"
DEFAULT_OUT = REPO / "dist-mods"
LOAD = 0x4000_0400
RAM = 0x4600_0000
NOP = bytes.fromhex("4e71")
# The WSL toolchain and compiler flags: copied from mods/delay-control/make_features.py.
TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra"
R_BIN = "$R/usr/bin/m68k-linux-gnu-"
GCC = f"$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B{R_BIN}"

ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
C_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
DEFINE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:=[A-Za-z0-9_-]+)?")
HEX_ADDR = re.compile(r"0x[0-9a-fA-F]+")
HEX_BYTES = re.compile(r"(?:[0-9a-f]{2})*")
SHA = re.compile(r"[0-9a-f]{64}")
TOP_KEYS = ("id", "title", "version", "author", "target", "requires", "sources", "entry", "slot", "hooks", "edits",
            "defines", "info")
REQUIRED = ("id", "title", "version", "author", "target", "sources", "entry", "slot")
HOOK_KEYS = ("id", "addr", "len", "section", "stock_sha256", "call", "why", "kind")
HOOK_REQUIRED = ("id", "addr", "len", "stock_sha256", "call", "why")
HOOK_KINDS = {"jmp": 0x4EF9, "jsr": 0x4EB9}
EDIT_KEYS = ("id", "addr", "len", "section", "stock_sha256", "hex", "why")
EDIT_REQUIRED = ("id", "addr", "len", "stock_sha256", "hex", "why")
INFO_KEYS = ("summary", "claims", "conflicts", "cost")
COST_KEYS = ("instructionsPerBlock", "measured")
CLAIM_PREFIXES = ("ui:", "param:", "audio:")


class ModError(Exception):
    """A plain sentence for the user: what is wrong and what to change."""


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def show(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------- slots

def load_slots() -> dict:
    return json.loads(SLOTS.read_text(encoding="utf-8"))


def _span(d: dict) -> tuple[int, int]:
    return int(d["start"], 0), int(d["end"], 0)


# ---------------------------------------------------------------- taken hooks

def load_taken() -> list[dict]:
    return json.loads(TAKEN.read_text(encoding="utf-8"))["taken"]


def check_taken(hooks: list[dict], taken: list[dict], word: str = "hook") -> list[str]:
    """Warnings for each mod hook (or edit, with word="edit") whose bytes overlap a spot that a shipped package already makes. Never raises."""
    out = []
    for h in hooks:
        ha, hl = int(h["addr"], 0), h["len"]
        for t in taken:
            ta, tl = int(t["addr"], 0), t["len"]
            if ha < ta + tl and ta < ha + hl:
                out.append(f'{word} "{h["id"]}" lands on {t["area"]}, already hooked by {t["package"]}. '
                           "Read builder-web\\docs\\SDK.md before you go on.")
    return out


def check_slot_table(slots: dict) -> None:
    """Every range must sit inside the mod area and none may overlap another."""
    size = int(slots["area"]["size"], 0)
    spans = []
    for name, r in slots["reserved"].items():
        spans.append((f'the reserved range "{name}"', *_span(r)))
    spans.append(("the dev slot", *_span(slots["dev"])))
    for name, r in slots["registered"].items():
        if name == "dev":
            raise ModError('"dev" is the fixed development slot and cannot be registered. Pick another name in tools/modsdk/slots.json.')
        spans.append((f'the registered slot "{name}"', *_span(r)))
    for label, s, e in spans:
        if not 0 <= s < e <= size:
            raise ModError(f"{label} is not inside the mod area. Fix its start and end in tools/modsdk/slots.json.")
    for i, (la, sa, ea) in enumerate(spans):
        for lb, sb, eb in spans[i + 1:]:
            if sa < eb and sb < ea:
                raise ModError(f"{la} overlaps {lb}. Move one of them in tools/modsdk/slots.json.")


def slot_span(info: dict, slots: dict) -> tuple[str, int, int]:
    name = info["slot"]
    if name == "dev":
        start, end = _span(slots["dev"])
    elif name in slots["registered"]:
        entry = slots["registered"][name]
        if entry.get("owner") != info["id"]:
            raise ModError(f'the slot "{name}" belongs to the mod "{entry.get("owner")}". '
                           'Use "dev" while you work, or ask for a slot of your own.')
        start, end = _span(entry)
    else:
        raise ModError(f'the slot "{name}" is not "dev" and is not registered in tools/modsdk/slots.json. '
                       'Use "dev" to try the mod on the page.')
    return name, start, end


def check_fit(size: int, name: str, start: int, end: int) -> None:
    if size > end - start:
        raise ModError(f'the code and data take {size} bytes, but the slot "{name}" holds {end - start} bytes. '
                       "Make the code smaller, or use a bigger slot.")


# ---------------------------------------------------------------- mod.json

def read_info(folder: Path) -> dict:
    path = folder / "mod.json"
    if not path.is_file():
        raise ModError(f'there is no mod.json in "{folder.name}". Check the folder name, or run init to start a new mod.')
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ModError(f"mod.json is not valid JSON, at line {e.lineno}. Check for a missing comma, quote or brace.")
    except UnicodeDecodeError:
        raise ModError("mod.json is not plain text. Save it again as UTF-8 in a text editor.")


def _check_place(h: dict, where: str, min_len: int, min_note: str, seen: set[str]) -> dict:
    """The fields a hook and an edit share: id, addr, section, len and stock_sha256. Returns the normalised ones."""
    hid = h["id"]
    if not isinstance(hid, str) or not ID_RE.fullmatch(hid):
        raise ModError(f'{where}: "id" must use only lowercase letters, digits and hyphens.')
    if hid in seen:
        raise ModError(f'two hooks or edits have the id "{hid}". Give each one its own id.')
    seen.add(hid)
    addr = h["addr"]
    if not isinstance(addr, str) or not HEX_ADDR.fullmatch(addr):
        raise ModError(f'{where}: "addr" must be text such as "0x400004b2".')
    a = int(addr, 0)
    if a < LOAD:
        raise ModError(f'{where}: "addr" must be at or above 0x40000400, the start of section 3.')
    section = h.get("section", 3)
    if section not in (3, 7) or isinstance(section, bool):
        raise ModError(f'{where}: "section" must be 3 or 7. Leave it out for 3.')
    length = h["len"]
    if not isinstance(length, int) or isinstance(length, bool):
        raise ModError(f'{where}: "len" must be a whole number of bytes.')
    if length < min_len:
        raise ModError(f'{where}: "len" must be at least {min_len} bytes{min_note}. Got {length}.')
    if length % 2:
        raise ModError(f'{where}: "len" must be an even number of bytes. Got {length}. Use {min_len}, {min_len + 2}, {min_len + 4} and so on.')
    stock = h["stock_sha256"]
    if not isinstance(stock, str) or not SHA.fullmatch(stock):
        raise ModError(f'{where}: "stock_sha256" must be 64 lowercase hex characters, the SHA-256 of the original bytes. '
                       f'Get it with: python tools/modsdk/modsdk.py fingerprint --stock <your OS file> --addr {addr} --len {length}')
    return {"addr": f"0x{a:08x}", "section": section, "len": length}


def validate_hook(h: object, n: int, seen: set[str]) -> dict:
    where = f"hook {n}"
    if not isinstance(h, dict):
        raise ModError(f"{where} must be an object with fields between braces.")
    if isinstance(h.get("id"), str):
        where = f'hook "{h["id"]}"'
    for key in HOOK_REQUIRED:
        if key not in h:
            raise ModError(f'{where} is missing the field "{key}". Add it, then build again.')
    for key in h:
        if key not in HOOK_KEYS:
            raise ModError(f'{where} has an unknown field "{key}". Check the spelling. The fields are: {", ".join(HOOK_KEYS)}.')
    place = _check_place(h, where, 6, ", the size of a jump", seen)
    if not isinstance(h["call"], str) or not C_NAME.fullmatch(h["call"]):
        raise ModError(f'{where}: "call" must be the name of a C function, such as "my_entry".')
    if not isinstance(h["why"], str) or not h["why"].strip():
        raise ModError(f'{where}: "why" must be one short sentence saying what the hook changes.')
    kind = h.get("kind", "jmp")
    if not isinstance(kind, str) or kind not in HOOK_KINDS:
        raise ModError(f'{where}: "kind" must be "jmp" (jump, the default) or "jsr" (call, then carry on). '
                       'Leave it out for "jmp".')
    return {**h, **place, "kind": kind}


def validate_edit(e: object, n: int, seen: set[str]) -> dict:
    where = f"edit {n}"
    if not isinstance(e, dict):
        raise ModError(f"{where} must be an object with fields between braces.")
    if isinstance(e.get("id"), str):
        where = f'edit "{e["id"]}"'
    for key in EDIT_REQUIRED:
        if key not in e:
            raise ModError(f'{where} is missing the field "{key}". Add it, then build again.')
    for key in e:
        if key not in EDIT_KEYS:
            raise ModError(f'{where} has an unknown field "{key}". Check the spelling. The fields are: {", ".join(EDIT_KEYS)}.')
    place = _check_place(e, where, 2, "", seen)
    new = e["hex"]
    if not isinstance(new, str) or not HEX_BYTES.fullmatch(new):
        raise ModError(f'{where}: "hex" must be the new bytes as lowercase hex, two characters for each byte, '
                       "with no spaces. Use 0 to 9 and a to f.")
    if len(new) // 2 != place["len"]:
        raise ModError(f'{where}: "hex" holds {len(new) // 2} bytes, but "len" is {place["len"]}. '
                       'Make them match: each byte is two hex characters.')
    if not isinstance(e["why"], str) or not e["why"].strip():
        raise ModError(f'{where}: "why" must be one short sentence saying what the edit changes.')
    return {**e, **place, "hex": new}


def validate_notes(notes: object, mod_id: str) -> dict:
    """The optional "info" block: the notes the page shows before a mod is ticked. Same rules as checkInfo."""
    if not isinstance(notes, dict):
        raise ModError('"info" must be one object, with its fields between braces. Leave it out if you have no notes.')
    for key in notes:
        if key not in INFO_KEYS:
            raise ModError(f'"info" has an unknown field "{key}". Check the spelling. The fields are: {", ".join(INFO_KEYS)}.')
    if "summary" in notes and (not isinstance(notes["summary"], str) or len(notes["summary"]) > 200):
        raise ModError('"info" summary must be one sentence of text, 200 characters or fewer.')
    if "claims" in notes:
        claims = notes["claims"]
        if not isinstance(claims, list) or any(not isinstance(c, str) for c in claims):
            raise ModError('"info" claims must be a list of text, such as ["ui:TRIG 13-16 on the FX track"]. Use [] when there are none.')
        for c in claims:
            if not c.startswith(CLAIM_PREFIXES) or not c.split(":", 1)[1].strip():
                raise ModError(f'"info" claim {c!r} must start with ui:, param: or audio:, then what it claims, '
                               'such as "ui:TRIG 13-16 on the FX track".')
    if "conflicts" in notes:
        conflicts = notes["conflicts"]
        if not isinstance(conflicts, list) or any(not isinstance(c, str) or not ID_RE.fullmatch(c) for c in conflicts):
            raise ModError('"info" conflicts must be a list of package ids, such as ["delay-control-core"]. Use [] when there are none.')
        if mod_id in conflicts:
            raise ModError('"info" conflicts cannot list this mod itself.')
    if notes.get("cost") is not None:
        cost = notes["cost"]
        if not isinstance(cost, dict):
            raise ModError('"info" cost must be null (not measured yet) or an object with "instructionsPerBlock" and "measured".')
        for key in cost:
            if key not in COST_KEYS:
                raise ModError(f'"info" cost has an unknown field "{key}". The fields are: {", ".join(COST_KEYS)}.')
        ipb = cost.get("instructionsPerBlock")
        if not isinstance(ipb, int) or isinstance(ipb, bool) or ipb < 0:
            raise ModError('"info" cost "instructionsPerBlock" must be a whole number, 0 or more. Set "cost" to null if you have not measured it.')
        if not isinstance(cost.get("measured"), str):
            raise ModError('"info" cost "measured" must be text saying what was measured and where, such as "emulator, 2026-11-18".')
    return notes


def validate_info(info: object, folder: Path) -> dict:
    if not isinstance(info, dict):
        raise ModError("mod.json must be one object, with its fields between braces.")
    for key in REQUIRED:
        if key not in info:
            raise ModError(f'mod.json is missing the field "{key}". Add it, then build again.')
    for key in info:
        if key not in TOP_KEYS:
            raise ModError(f'mod.json has an unknown field "{key}". Check the spelling. The fields are: {", ".join(TOP_KEYS)}.')
    mod_id = info["id"]
    if not isinstance(mod_id, str) or not ID_RE.fullmatch(mod_id):
        raise ModError('"id" must use only lowercase letters, digits and hyphens, such as "my-mod".')
    for key in ("title", "version", "author"):
        if not isinstance(info[key], str) or not info[key].strip():
            raise ModError(f'"{key}" must be some text, and cannot be empty.')
    if info["target"] != {"device": "Syntakt", "os": "1.41"}:
        raise ModError('"target" must be {"device": "Syntakt", "os": "1.41"}. Other devices and OS versions are not supported.')
    requires = info.get("requires", [])
    if not isinstance(requires, list) or any(not isinstance(r, str) or not ID_RE.fullmatch(r) for r in requires):
        raise ModError('"requires" must be a list of package ids, such as ["delay-control-runtime"]. Use [] when there are none.')
    if len(set(requires)) != len(requires):
        raise ModError('"requires" lists the same package twice. Remove the repeat.')
    if mod_id in requires:
        raise ModError('"requires" cannot list this mod itself.')
    sources = info["sources"]
    if not isinstance(sources, list) or not sources:
        raise ModError('"sources" must be a list of C file names, such as ["main.c"].')
    for s in sources:
        if not isinstance(s, str) or not s.endswith(".c") or "/" in s or "\\" in s:
            raise ModError(f'"sources" entry {s!r} must be a plain C file name in the mod folder, such as "main.c".')
        if not (folder / s).is_file():
            raise ModError(f'"sources" lists "{s}", but the mod folder has no such file. Add the file or fix the name.')
    if not isinstance(info["entry"], str) or not C_NAME.fullmatch(info["entry"]):
        raise ModError('"entry" must be the name of a C function, such as "my_entry".')
    if not isinstance(info["slot"], str) or not info["slot"]:
        raise ModError('"slot" must be "dev" or the name of a registered slot.')
    hooks = info.get("hooks", [])
    if not isinstance(hooks, list):
        raise ModError('"hooks" must be a list. Use [] when there are none.')
    edits = info.get("edits", [])
    if not isinstance(edits, list):
        raise ModError('"edits" must be a list. Use [] when there are none.')
    defines = info.get("defines", [])
    if not isinstance(defines, list):
        raise ModError('"defines" must be a list of text, such as ["MOD_BASE=0x4000"]. Use [] when there are none.')
    for d in defines:
        if not isinstance(d, str) or not DEFINE_RE.fullmatch(d):
            raise ModError(f'"defines" entry {d!r} must be NAME or NAME=VALUE. NAME uses letters, digits and underscores '
                           "and cannot start with a digit. VALUE uses only letters, digits, underscores and minus signs, "
                           "with no spaces or quotes.")
    seen: set[str] = set()
    out = {**info, "requires": requires, "defines": defines,
           "hooks": [validate_hook(h, i, seen) for i, h in enumerate(hooks, 1)],
           "edits": [validate_edit(e, i, seen) for i, e in enumerate(edits, 1)]}
    if "info" in info:
        out["info"] = validate_notes(info["info"], mod_id)
    return out


# ---------------------------------------------------------------- toolchain

def _shell(cmd: str) -> subprocess.CompletedProcess | None:
    argv = ["bash", "-lc", cmd] if sys.platform != "win32" else ["wsl.exe", "-e", "bash", "-lc", cmd]
    try:
        return subprocess.run(argv, capture_output=True, text=True)
    except OSError:
        return None


def toolchain_status() -> tuple[bool, str]:
    r = _shell(f"R={TOOLS}; test -x $R/usr/bin/m68k-linux-gnu-gcc-13 && echo found")
    if r is None:
        return False, "WSL is not available, so the C code cannot be compiled. Install WSL with the m68k toolchain."
    if "found" not in r.stdout:
        return False, f"the m68k compiler was not found in WSL at {TOOLS}. Install the toolchain there, then build again."
    return True, ""


def wsl(cmd: str) -> str:
    r = _shell(cmd)
    if r is None:
        raise ModError("WSL could not be started. Install WSL with the m68k toolchain, then build again.")
    if r.returncode:
        raise ModError(f"the compiler or linker stopped. Details:\n{(r.stderr or r.stdout).strip()}")
    return r.stdout + r.stderr


def check_decode(dis: str, base: int, text: int) -> None:
    """The .text section must be whole instructions covering it exactly (objdump, no (bad) words)."""
    pos, in_text = base, False
    for line in dis.splitlines():
        if line.startswith("Disassembly of section "):
            in_text = line.rstrip(":").endswith(" .text")
            continue
        m = re.match(r"^\s*([0-9a-f]+):\t([0-9a-f ]+?)\s*(?:\t(.*))?$", line)
        if not in_text or not m:
            continue
        if int(m.group(1), 16) != pos or "(bad)" in (m.group(3) or ""):
            raise ModError(f"the code does not split into whole instructions at {pos:#x}. Check the C code near that point.")
        pos += len(m.group(2).replace(" ", "")) // 2
    if pos != base + text:
        raise ModError(f"the code decodes to {pos:#x}, but its code ends at {base + text:#x}.")


def build_code(folder: Path, sources: list[str], entry: str, base: int, defines: list[str] = []) -> dict:
    """Compile the sources with the m68k toolchain and link them at base (the mod area RAM address)."""
    flags = " ".join([CFLAGS, *(f"-D{d}" for d in defines)])
    with tempfile.TemporaryDirectory(prefix="modsdk-") as tmp_name:
        tmp = Path(tmp_name)
        shutil.copy(INCLUDE / "syntakt.h", tmp / "syntakt.h")
        for h in folder.glob("*.h"):
            shutil.copy(h, tmp / h.name)
        for s in sources:
            shutil.copy(folder / s, tmp / s)
        w = eft.to_wsl_path(tmp) if sys.platform == "win32" else str(tmp)
        env = f"R={TOOLS}; cd '{w}'; "
        objs = []
        for s in sources:
            warn = wsl(env + f"{GCC} {flags} -c {s} -o {Path(s).stem}.o")
            if "warning" in warn:
                raise ModError(f"{s} has a compiler warning. Fix it, then build again. Compiler said:\n{warn.strip()}")
            objs.append(Path(s).stem + ".o")
        wsl(env + f"{R_BIN}ld -N -Ttext={base:#x} -e {entry} -o f.elf {' '.join(objs)}")
        undef = wsl(env + f"{R_BIN}nm -u f.elf").strip()
        if undef:
            names = ", ".join(line.split()[-1] for line in undef.splitlines())
            raise ModError(f"the code uses a function from outside the mod ({names}). "
                           "A mod cannot use libc or libgcc. Remove the call; see tools/modsdk/include/syntakt.h.")
        heads = wsl(env + f"{R_BIN}objdump -h f.elf")
        sizes, vma = {}, {}
        for name, size, addr in re.findall(r"^\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)", heads, re.M):
            sizes[name], vma[name] = int(size, 16), int(addr, 16)
        if sizes.get(".bss", 0) or sizes.get(".sbss", 0):
            raise ModError("the code has a .bss section (a variable with no start value). Give each global variable "
                           "DATA and a start value that is not zero, for example DATA u32 count = 1;")
        text = sizes.get(".text", 0)
        if not text or vma.get(".text") != base:
            raise ModError(f"the code has no .text section at {base:#x}. Check that the code is not empty.")
        wsl(env + f"{R_BIN}objcopy -O binary -j .text -j .rodata -j .data f.elf f.bin")
        blob = (tmp / "f.bin").read_bytes()
        syms: dict[str, tuple[int, str]] = {}
        for line in wsl(env + f"{R_BIN}nm f.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = (int(parts[0], 16), parts[1])
        check_decode(wsl(env + f"{R_BIN}objdump -d f.elf"), base, text)
    funcs = {name for name, (_, kind) in syms.items() if kind == "T"}
    if entry not in funcs:
        raise ModError(f'the entry function "{entry}" is not a global C function in the code. '
                       "Check the name in mod.json and in the C file. A static function is not global.")
    return {"blob": blob, "text": text, "syms": syms, "funcs": funcs}


# ---------------------------------------------------------------- package

def hook_bytes(target: int, length: int, kind: str = "jmp") -> bytes:
    if length < 6 or length % 2:
        raise ModError(f"a hook must be an even length of at least 6 bytes. Got {length}.")
    if kind not in HOOK_KINDS:
        raise ModError(f'a hook kind must be "jmp" or "jsr". Got {kind!r}.')
    return struct.pack(">HI", HOOK_KINDS[kind], target) + NOP * ((length - 6) // 2)


def area_block(bid: str, kind: str, offset: int, data: bytes, why: str) -> dict:
    return {"id": bid, "mode": "area", "offset": offset, "len": len(data), "kind": kind,
            "new": [["hex", data.hex()]], "new_sha256": sha(data), "why": why}


def hook_block(h: dict, call_addr: int) -> dict:
    new = hook_bytes(call_addr, h["len"], h.get("kind", "jmp"))
    return {"id": h["id"], "mode": "replace", "section": h["section"], "addr": h["addr"], "len": h["len"],
            "kind": "code", "stock_sha256": h["stock_sha256"], "new": [["hex", new.hex()]],
            "new_sha256": sha(new), "why": h["why"]}


def edit_block(e: dict) -> dict:
    new = bytes.fromhex(e["hex"])
    return {"id": e["id"], "mode": "replace", "section": e["section"], "addr": e["addr"], "len": e["len"],
            "kind": "data", "stock_sha256": e["stock_sha256"], "new": [["hex", new.hex()]],
            "new_sha256": sha(new), "why": e["why"]}


def make_package(info: dict, blob: bytes, text: int, start: int, hook_calls: dict[str, int]) -> dict:
    """The .sypatch.json document for one mod. Pure: no toolchain and no firmware."""
    mod_id = info["id"]
    blocks = [area_block(f"{mod_id}-code", "code", start, blob[:text], "linked code of this mod (.text)")]
    if len(blob) > text:
        blocks.append(area_block(f"{mod_id}-data", "data", start + text, blob[text:],
                                 "constants and variables of this mod"))
    blocks += [hook_block(h, hook_calls[h["call"]]) for h in info["hooks"]]
    blocks += [edit_block(e) for e in info["edits"]]
    requires = ["modarea"] + [r for r in info["requires"] if r != "modarea"]
    doc = {"format": "synthack-patchset", "schema": 1, "id": mod_id, "title": info["title"],
           "encoding": "lowercase-hex", "requires": requires,
           "target": {"device": "Syntakt", "os": "1.41", "stock_sha256": cp.STOCK_SHA256},
           "area": dict(load_slots()["area"])}
    if "info" in info:
        doc["info"] = info["info"]
    doc["units"] = [{"id": mod_id, "title": info["title"], "blocks": blocks}]
    return doc


def build_mod(folder: Path, out_dir: Path, strict: bool = False) -> tuple[Path, dict]:
    info = validate_info(read_info(folder), folder)
    ok, why = toolchain_status()
    if not ok:
        raise ModError(why)
    slots = load_slots()
    check_slot_table(slots)
    name, start, end = slot_span(info, slots)
    code = build_code(folder, info["sources"], info["entry"], RAM + start, info["defines"])
    blob, text = code["blob"], code["text"]
    check_fit(len(blob), name, start, end)
    hook_calls: dict[str, int] = {}
    for h in info["hooks"]:
        if h["call"] not in code["funcs"]:
            raise ModError(f'hook "{h["id"]}" calls "{h["call"]}", which is not a global C function in the code. '
                           "Check the name in mod.json and the C file.")
        hook_calls[h["call"]] = code["syms"][h["call"]][0]
    doc = make_package(info, blob, text, start, hook_calls)
    try:
        cp.check(doc)
    except cp.PatchError as e:
        raise ModError(f"the package does not pass the checks: {e}")
    taken = load_taken()
    warnings = check_taken(info["hooks"], taken) + check_taken(info["edits"], taken, "edit")
    if strict and warnings:
        raise ModError("\n".join(warnings) + "\nMove the hook, or build again without --strict.")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{info['id']}.sypatch.json"
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    summary = {"info": info, "code": text, "data": len(blob) - text, "slot": (name, start, end),
               "hook_calls": hook_calls, "warnings": warnings}
    return path, summary


def check_package(path: Path) -> str:
    """Returns "ok", or "skipped" when Node.js is missing. Raises ModError with the reason when refused."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        raise ModError("the file is not readable JSON.")
    except UnicodeDecodeError:
        raise ModError("the file is not plain text. Save it again as UTF-8.")
    try:
        cp.check(doc)
    except cp.PatchError as e:
        raise ModError(str(e))
    node = shutil.which("node")
    if node is None:
        return "skipped"
    r = subprocess.run([node, str(VALIDATE), str(path.resolve())], capture_output=True, text=True, encoding="utf-8")
    out = r.stdout.strip()
    if r.returncode == 0 and out == "OK":
        return "ok"
    raise ModError(out.removeprefix("REFUSED: ") or r.stderr.strip() or "the page check refused the file without a reason.")


# ---------------------------------------------------------------- commands

def init_mod(mod_id: str, mods_root: Path = REPO / "mods") -> Path:
    if not ID_RE.fullmatch(mod_id):
        raise ModError('the id must use only lowercase letters, digits and hyphens, such as "my-mod".')
    folder = mods_root / mod_id
    if folder.exists():
        raise ModError(f'the folder "{mod_id}" already exists. Choose another id, or remove that folder yourself first.')
    folder.mkdir(parents=True)
    title = mod_id.replace("-", " ").capitalize()
    for template, target in (("mod.json.tmpl", "mod.json"), ("main.c.tmpl", "main.c")):
        text = (TEMPLATES / template).read_text(encoding="utf-8")
        (folder / target).write_text(text.replace("{{id}}", mod_id).replace("{{title}}", title), encoding="utf-8")
    return folder


def fingerprint(stock: Path, addr: int, length: int) -> str:
    if not stock.is_file():
        raise ModError("no file at that path. Check the path to your OS 1.41 file.")
    h = hashlib.sha256()
    with stock.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != cp.STOCK_SHA256:
        raise ModError("this file is not the Syntakt OS 1.41 file. Use your own OS 1.41 file.")
    if addr < LOAD or length <= 0:
        raise ModError("the address must be at or above 0x40000400, and the length must be more than zero.")
    if "EFT_BIN" not in os.environ:
        found = shutil.which("elektron-firmware-tool")
        if found:
            os.environ["EFT_BIN"] = found
    try:
        with tempfile.TemporaryDirectory(prefix="modsdk-fp-") as tmp:
            sec3 = eft.unpack(stock, Path(tmp), ids=[3])[3].read_bytes()
    except eft.EftError:
        raise ModError("could not read section 3 with elektron-firmware-tool. Install it, or set EFT_BIN to its path "
                       "(see tools/unpack/setup_eft.sh).")
    off = addr - LOAD
    if off + length > len(sec3):
        raise ModError("the address and length go past the end of section 3.")
    return sha(sec3[off:off + length])


def slots_report() -> list[str]:
    slots = load_slots()
    check_slot_table(slots)
    size = int(slots["area"]["size"], 0)
    taken = sorted([_span(r) for r in slots["reserved"].values()] + [_span(r) for r in slots["registered"].values()])
    lines = [f"Mod area: 0x0 to {size:#x} (RAM {int(slots['area']['ram'], 0):#010x})", "", "Reserved (DelayCtrl, do not use):"]
    for name, r in slots["reserved"].items():
        s, e = _span(r)
        lines.append(f"  {s:#06x} to {e:#06x}  {name}")
    dev_s, dev_e = _span(slots["dev"])
    lines += ["", f"Development slot (dev): {dev_s:#06x} to {dev_e:#06x}, {dev_e - dev_s} bytes.",
              "  Fine for trying on the page, not for the reviewed list."]
    lines += ["", "Registered slots:"]
    if not slots["registered"]:
        lines.append("  none yet")
    for name, r in slots["registered"].items():
        s, e = _span(r)
        lines.append(f"  {s:#06x} to {e:#06x}  {name} (owner: {r.get('owner', '?')})")
    lines += ["", "Free ranges (not reserved and not registered):"]
    cur = 0
    for s, e in taken + [(size, size)]:
        if s > cur:
            lines.append(f"  {cur:#06x} to {s:#06x}")
        cur = max(cur, e)
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="modsdk.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="make a new mod folder from the templates")
    p.add_argument("id")
    p = sub.add_parser("build", help="build a mod folder into one .sypatch.json file")
    p.add_argument("folder", type=Path)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder (default dist-mods)")
    p.add_argument("--strict", action="store_true", help="treat a hook clash warning as a build error")
    p = sub.add_parser("check", help="check a .sypatch.json file")
    p.add_argument("file", type=Path)
    p = sub.add_parser("fingerprint", help="print the SHA-256 of bytes in your own OS 1.41 file")
    p.add_argument("--stock", type=Path, required=True)
    p.add_argument("--addr", type=lambda s: int(s, 0), required=True)
    p.add_argument("--len", type=int, required=True, dest="length")
    sub.add_parser("slots", help="show the slots and the free ranges of the mod area")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.cmd == "init":
            folder = init_mod(args.id)
            print(f"Made {show(folder)}/mod.json and main.c. Edit them, then run build on the folder.")
        elif args.cmd == "build":
            path, s = build_mod(args.folder, args.out, strict=args.strict)
            name, start, end = s["slot"]
            print(f"Built {s['info']['id']} {s['info']['version']}: {show(path)}")
            print(f"  files: {', '.join(s['info']['sources'])}")
            print(f"  code: {s['code']} bytes, data: {s['data']} bytes")
            print(f"  slot: {name}, {start:#06x} to {end:#06x} ({end - start} bytes, {s['code'] + s['data']} used)")
            if not s["info"]["hooks"]:
                print("  hooks: none")
            for h in s["info"]["hooks"]:
                print(f"  hook {h['id']}: at {h['addr']}, {h['len']} bytes, calls {h['call']} at {s['hook_calls'][h['call']]:#010x}")
            for e in s["info"]["edits"]:
                print(f"  edit {e['id']}: at {e['addr']}, {e['len']} bytes")
            if s["info"]["defines"]:
                print(f"  defines: {', '.join(s['info']['defines'])}")
            if name == "dev":
                print("  development slot: fine for trying on the page, not for the reviewed list")
            for w in s["warnings"]:
                print(f"Warning: {w}")
        elif args.cmd == "check":
            if not args.file.is_file():
                raise ModError("no file at that path.")
            status = check_package(args.file)
            if status == "skipped":
                print("OK, but the page check was skipped: Node.js is not installed, so the page's own rules did not run. "
                      "Install Node.js and check again.")
            else:
                print("OK")
        elif args.cmd == "fingerprint":
            print(fingerprint(args.stock, args.addr, args.length))
        elif args.cmd == "slots":
            print("\n".join(slots_report()))
    except ModError as e:
        if args.cmd == "check":
            print(f"REFUSED: {e}")
        else:
            print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
