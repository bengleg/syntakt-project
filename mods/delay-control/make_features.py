"""DelayCtrl feature packages: the v2o build split into five packages the page can select one by one.

    python mods/delay-control/make_features.py [--out DIR]

Builds each package from mods/delay-control/features/ with the WSL m68k toolchain (the flags of make_patch.py),
links it at its own address in the mod area, and writes modarea.sypatch.json, dc-*.sypatch.json and manifest.json
(default DIR: web/patches). Nothing is written under out/, and no .syx, .bin or .elemod file is made.
SYNTAKT_STOCK, if set, is the user's own OS 1.41 file: it is read only to check the SHA-256 fingerprints
(the section 3 unpack needs EFT_BIN, or elektron-firmware-tool on PATH via tools/unpack).
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
import eft  # noqa: E402

FEAT = HERE / "features"
PATCHES = REPO / "web" / "patches"
LOAD = 0x4000_0400
RAM = 0x4600_0000
STOCK_SHA256 = "8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e"
TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra"
R_BIN = "$R/usr/bin/m68k-linux-gnu-"
GCC = f"$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B{R_BIN}"
AREA = {"img": "0x40348000", "ram": "0x46000000", "size": "0x10000", "compress": "shlz"}
NOP = bytes.fromhex("4e71")

# package id: file, title, requires, sources, entry symbol, area slot [start, end) (offsets in the mod area)
PACKAGES = {
    "modarea": ("modarea.sypatch.json", "Mod area loader", [], None, None, None),
    "delay-control-runtime": ("dc-runtime.sypatch.json", "DelayCtrl runtime", ["modarea"],
                              ["common.c"], "dc_run", (0x4010, 0x4800)),
    "delay-control-core": ("dc-core.sypatch.json", "Freeze / DelayCtrl",
                           ["modarea", "delay-control-runtime"], ["core.c"], "dc_core_run", (0x4800, 0x6000)),
    "delay-control-dj": ("dc-dj.sypatch.json", "DJ filter", ["modarea", "delay-control-runtime"],
                         ["dj.c"], "dc_flt", (0x6000, 0x6800)),
    "delay-control-drive": ("dc-drive.sypatch.json", "Drive rectifier", ["modarea", "delay-control-runtime"],
                            ["drive.c"], "dc_drive_run", (0x6800, 0x6C00)),
    "delay-control-syn": ("dc-syn.sypatch.json", "FX SYN page", ["modarea"], ["syn.c"], "dc_syn_stub",
                          (0x6C00, 0x6E00)),
}
ORDER = list(PACKAGES)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["bash", "-lc", cmd] if sys.platform != "win32" else ["wsl.exe", "-e", "bash", "-lc", cmd],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"command failed:\n{cmd}\n{r.stderr}")
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
            raise SystemExit(f"code does not decode as whole instructions at {pos:#x}: {line.strip()}")
        pos += len(m.group(2).replace(" ", "")) // 2
    if pos != base + text:
        raise SystemExit(f"code decodes to {pos:#x}, .text ends at {base + text:#x}")


def build(src: list[str], entry: str, base: int) -> dict:
    """Compile and link one package at `base` (RAM address). Returns its bytes, sizes and symbols."""
    with tempfile.TemporaryDirectory(prefix="dcf-") as tmp:
        tmp = Path(tmp)
        for f in src + ["dc.h"]:
            shutil.copy(FEAT / f, tmp / f)
        w = eft.to_wsl_path(tmp) if sys.platform == "win32" else str(tmp)
        env = f"R={TOOLS}; cd '{w}'; "
        objs = []
        for s in src:
            warn = wsl(env + f"{GCC} {CFLAGS} -c {s} -o {Path(s).stem}.o")
            if "warning" in warn:
                raise SystemExit(f"{s}: {warn}")
            objs.append(Path(s).stem + ".o")
        wsl(env + f"{R_BIN}ld -N -Ttext={base:#x} -e {entry} -o f.elf {' '.join(objs)}")
        undef = wsl(env + f"{R_BIN}nm -u f.elf").strip()
        if undef:
            raise SystemExit(f"external symbols not allowed: {undef}")
        heads = wsl(env + f"{R_BIN}objdump -h f.elf")
        sizes, vma = {}, {}
        for name, size, addr in re.findall(r"^\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)", heads, re.M):
            sizes[name], vma[name] = int(size, 16), int(addr, 16)
        if sizes.get(".bss", 0) or sizes.get(".sbss", 0):
            raise SystemExit("no .bss allowed")
        text = sizes.get(".text", 0)
        if not text or vma[".text"] != base:
            raise SystemExit(f".text missing or not at {base:#x}")
        wsl(env + f"{R_BIN}objcopy -O binary -j .text -j .rodata -j .data f.elf f.bin")
        blob = (tmp / "f.bin").read_bytes()
        syms = {}
        for line in wsl(env + f"{R_BIN}nm f.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        check_decode(wsl(env + f"{R_BIN}objdump -d f.elf"), base, text)
    return {"blob": blob, "text": text, "rodata": sizes.get(".rodata", 0), "data": sizes.get(".data", 0),
            "syms": syms, "base": base}


def expect_of(spec: dict) -> dict[int, tuple[int, str]]:
    """Stock fingerprints of the replaced ranges, from a v2o-style patch.json: addr -> (len, sha256)."""
    return {int(p["addr"], 16): (p["len"], p["expect_sha256"]) for p in spec["patches"] if not p.get("append")}


def verify_stock(stock: Path, expects: dict[int, tuple[int, str]]) -> None:
    if sha(stock.read_bytes()) != STOCK_SHA256:
        raise SystemExit("SYNTAKT_STOCK is not the OS 1.41 file")
    with tempfile.TemporaryDirectory(prefix="dcs-") as tmp:
        sec3 = eft.unpack(stock, Path(tmp), ids=[3])[3].read_bytes()
    for addr, (n, want) in expects.items():
        if sha(sec3[addr - LOAD:addr - LOAD + n]) != want:
            raise SystemExit(f"{addr:#x}: stock bytes do not match expect_sha256")


def jsr(target: int) -> bytes:
    return struct.pack(">HI", 0x4EB9, target)


def jmp(target: int) -> bytes:
    return struct.pack(">HI", 0x4EF9, target)


def ptr(target: int) -> bytes:
    return struct.pack(">I", target)


def rep(pid: str, expect: dict, addr: int, new: bytes, kind: str, why: str) -> dict:
    n, stock = expect[addr]
    if n != len(new):
        raise SystemExit(f"{addr:#x}: {len(new)} new bytes, patch.json has {n}")
    return {"id": f"{pid}-{addr:08X}", "mode": "replace", "section": 3, "addr": f"0x{addr:08x}", "len": n,
            "kind": kind, "stock_sha256": stock, "new": [["hex", new.hex()]], "new_sha256": sha(new), "why": why}


def area(pid: str, tag: str, kind: str, offset: int, data: bytes, why: str) -> dict:
    return {"id": f"{pid}-{tag}", "mode": "area", "offset": offset, "len": len(data), "kind": kind,
            "new": [["hex", data.hex()]], "new_sha256": sha(data), "why": why}


def area_blocks(pid: str, b: dict) -> list[dict]:
    """Code (the .text bytes) and data (.rodata and .data, if any), split at the .text size."""
    off, text = b["base"] - RAM, b["text"]
    blocks = [area(pid, "code", "code", off, b["blob"][:text], "linked code of this package (.text)")]
    if len(b["blob"]) > text:
        blocks.append(area(pid, "data", "data", off + text, b["blob"][text:], "constants and data of this package"))
    return blocks


MODAREA_WHY = {
    0x4033_8D80: "mod area loader: decompress the area stream to RAM, zero the rest, jump back",
    0x4000_04B2: "start of the BSS clear: jmp modarea_reloc ; nop",
}


def modarea_blocks(spec: dict) -> list[dict]:
    blocks = []
    for p in spec["patches"]:
        addr = int(p["addr"], 16)
        new = bytes.fromhex(p["hex"])
        kind = "free-code" if addr == 0x4033_8D80 else "code"
        blocks.append({"id": f"modarea-{addr:08X}", "mode": "replace", "section": 3, "addr": f"0x{addr:08x}",
                       "len": p["len"], "kind": kind, "stock_sha256": p["expect_sha256"],
                       "new": [["hex", new.hex()]], "new_sha256": sha(new), "why": MODAREA_WHY[addr]})
    return blocks


def dc_blocks(pkg: str, b: dict, expect: dict) -> list[dict]:
    s = b["syms"]
    r = lambda addr, new, kind, why: rep(pkg, expect, addr, new, kind, why)
    if pkg == "delay-control-runtime":
        return [
            r(0x4002E850, jsr(s["dc_entry_hook"]) + NOP, "code", "consumeKeyEvent entry: jsr dc_entry_hook ; nop"),
            r(0x4008FB04, jsr(s["dc_mix_hook"]) + NOP + NOP, "code", "after FX bus sums: jsr dc_mix_hook ; nop ; nop"),
        ]
    if pkg == "delay-control-core":
        blocks = [
            r(0x4002EA92, jmp(s["dc_kbd_hook"]) + NOP, "code", "keys 13-16: jmp dc_kbd_hook ; nop"),
            r(0x4000B420, jsr(s["dc_ev_hook"]), "code", "event dispatcher: jsr dc_ev_hook"),
            r(0x4008F828, jsr(s["dc_del_hook"]), "code", "delay: jsr dc_del_hook (silence while active)"),
            r(0x400908FC, jsr(s["dc_ext_hook"]), "code", "external in level CVs: jsr dc_ext_hook (mute while frozen)"),
            r(0x400903F8, jsr(s["dc_mute_hook"]), "code", "analog voice CV loop: jsr dc_mute_hook (mute mask)"),
            r(0x401952C4, bytes.fromhex("42b941b9fa0c"), "code", "DCTL page slot 4: DEST hidden (clr.l)"),
        ]
        d_max = lambda pid: 0x4022_D59C + 52 * pid + 12    # MOD B M1-M4 (ids 54-57) max / default
        for pid, f_op, g_op, default in ((54, 0x4018_AD86, 0x4018_AD94, 0x000), (55, 0x4018_ADC4, 0x4018_ADD6, 0x200),
                                         (56, 0x4018_AE06, 0x4018_AE14, 0x400), (57, 0x4018_AE48, 0x4018_AE56, 0x600)):
            blocks += [
                r(f_op, ptr(s["dc_mfmt_proto"]), "data", f"id {pid} +20: RETRIG formatter (clamped)"),
                r(g_op, ptr(s["dc_mgfx_proto"]), "data", f"id {pid} +36: RETRIG box graphic (clamped)"),
                r(d_max(pid), struct.pack(">II", 0x800, default), "data", f"id {pid}: max 0x800 (9 steps), default {default:#x}"),
            ]
        blocks += [
            r(0x4004_0B74, ptr(s["dc_s_on"]), "data", "popup Mod B ON -> DelayCtrl ON"),
            r(0x4019_52A8, ptr(s["dc_s_long"]), "data", "name Mod B -> DelayCtrl"),
            r(0x4019_524A, ptr(s["dc_s_short"]), "data", "page name MODB -> DCTL"),
            r(0x4004_E9BC, ptr(s["dc_s_short"]), "data", "TrigModListView title MODB -> DCTL"),
        ]
        return blocks
    if pkg == "delay-control-dj":
        return [
            r(0x4009_5FA6, jsr(s["dc_flt_hook"]), "code", "FX filter CVs: jsr dc_flt_hook (DJ type)"),
            r(0x401D_4710, ptr(s["dc_s_dj"]), "data", "filter type 6 name LPN -> DJ"),
            r(0x4018_C794, ptr(s["dc_tgfx"]), "data", "FX filter TYPE icon: invoker -> dc_tgfx (DJ text)"),
            r(0x4004_2646, jsr(s["dc_fdraw_hook"]), "code", "filter tab curve: jsr dc_fdraw_hook (DJ as LP2/HP2)"),
        ]
    if pkg == "delay-control-syn":
        return [r(0x4019_5156, jsr(s["dc_syn_stub"]), "code", "FX SYN page init: jsr dc_syn_stub (slots 1-7)")]
    return []


def registration(pkg: str, offset: int, target: int, why: str) -> dict:
    return area(pkg, "reg", "data", offset, ptr(target), why)


def package(pid: str, blocks: list[dict]) -> dict:
    file, title, requires, *_ = PACKAGES[pid]
    doc = {"format": "synthack-patchset", "schema": 1, "id": pid, "title": title, "encoding": "lowercase-hex",
           "requires": requires,
           "target": {"device": "Syntakt", "os": "1.41", "stock_sha256": STOCK_SHA256}}
    if any(bl["mode"] == "area" for bl in blocks):
        doc["area"] = AREA
    doc["units"] = [{"id": pid, "title": title, "blocks": blocks}]
    return doc


def make(stock: Path | None) -> tuple[dict[str, dict], dict[str, dict]]:
    spec = json.loads((HERE / "patch.json").read_text(encoding="utf-8"))
    mod = json.loads((REPO / "mods" / "modarea" / "patch.json").read_text(encoding="utf-8"))
    expect = expect_of(spec)
    mod_expect = expect_of(mod)
    if stock is not None:
        verify_stock(stock, {**expect, **mod_expect})
    docs, info = {}, {}
    docs["modarea"] = package("modarea", modarea_blocks(mod))
    built = {}
    for pid in ORDER[1:]:
        _, _, _, src, entry, (lo, hi) = PACKAGES[pid]
        b = build(src, entry, RAM + lo)
        if RAM + lo + len(b["blob"]) > RAM + hi:
            raise SystemExit(f"{pid}: {len(b['blob'])} B does not fit [{lo:#x}, {hi:#x})")
        built[pid] = b
    for pid in ORDER[1:]:
        b = built[pid]
        blocks = dc_blocks(pid, b, expect)
        if pid == "delay-control-core":
            blocks.append(registration(pid, 0x4000, built["delay-control-core"]["syms"]["dc_core_run"],
                                       "DC_REG_CORE = dc_core_run (mix hook calls it when nonzero)"))
        if pid == "delay-control-drive":
            blocks.append(registration(pid, 0x4004, built["delay-control-drive"]["syms"]["dc_drive_run"],
                                       "DC_REG_DRIVE = dc_drive_run (mix hook calls it when nonzero)"))
        blocks += area_blocks(pid, b)
        docs[pid] = package(pid, blocks)
        info[pid] = {"area": len(b["blob"]), "text": b["text"], "rodata": b["rodata"], "data": b["data"]}
    return docs, info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=PATCHES, help="output directory (default web/patches)")
    args = ap.parse_args(argv)
    stock_env = os.environ.get("SYNTAKT_STOCK")
    docs, info = make(Path(stock_env) if stock_env else None)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {"packages": []}
    for pid in ORDER:
        file, title = PACKAGES[pid][0], PACKAGES[pid][1]
        (args.out / file).write_text(json.dumps(docs[pid], indent=1) + "\n", encoding="utf-8")
        manifest["packages"].append({"id": pid, "file": file, "title": title})
        n = sum(len(u["blocks"]) for u in docs[pid]["units"])
        extra = info.get(pid, {})
        print(f"{file}: {n} blocks" + (f", area {extra['area']} B (.text {extra['text']}, .rodata {extra['rodata']}, "
                                          f".data {extra['data']})" if extra else ""))
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
