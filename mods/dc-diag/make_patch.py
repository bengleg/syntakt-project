"""Mod dc-diag: diagnostic popups for Delay Control. Builds patch.json from diag.c.

    python mods/dc-diag/make_patch.py
"""

from __future__ import annotations

import hashlib
import json
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

LOAD = 0x4000_0400
MODAREA_RAM, MODAREA_IMG = 0x4600_0000, 0x4034_8000
CODE_BASE, CODE_END = MODAREA_RAM + 0x4000, MODAREA_RAM + 0x5000   # beat-repeat's slot (not built together)
TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra"
KBD_HOOK, KBD_ORIG = 0x4002_EA92, "7223b2806c00010e"    # moveq #35,d1 ; cmp.l d0,d1 ; bge.w 0x4002EBA6
EV_HOOK, EV_ORIG = 0x4000_B420, "4eb94000839e"          # jsr 0x4000839e


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["bash", "-lc", cmd] if sys.platform != "win32" else ["wsl.exe", "-e", "bash", "-lc", cmd],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"command failed:\n{cmd}\n{r.stderr}")
    return r.stdout + r.stderr


def build_blob() -> tuple[bytes, dict[str, int], str]:
    with tempfile.TemporaryDirectory(prefix="dg-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "diag.c", tmp / "diag.c")
        w = eft.to_wsl_path(tmp) if sys.platform == "win32" else str(tmp)
        env = f"R={TOOLS}; cd '{w}'; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} {CFLAGS} -c diag.c -o diag.o")
        if "warning" in warn:
            raise SystemExit(warn)
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e dg_ev -o diag.elf diag.o")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u diag.elf").strip()
        if undef:
            raise SystemExit(f"external symbols not allowed: {undef}")
        heads = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -h diag.elf")
        for name, size in re.findall(r"^\s*\d+\s+(\.\S+)\s+([0-9a-f]+)", heads, re.M):
            if name in (".bss", ".sbss") and int(size, 16):
                raise SystemExit("no .bss allowed")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data diag.elf diag.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm diag.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        dis = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -d diag.elf")
        blob = (tmp / "diag.bin").read_bytes()
    return blob, syms, dis


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.41.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms, dis = build_blob()
    if CODE_BASE + len(blob) > CODE_END:
        raise SystemExit(f"too big: {len(blob)} B")

    def fixed(addr: int, new: bytes, what: str, expect: str) -> dict:
        old = sec3[addr - LOAD:addr - LOAD + len(new)]
        if old.hex() != expect:
            raise SystemExit(f"{addr:#x}: unexpected bytes {old.hex()} (expected {expect})")
        return {"section": 3, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                "hex": new.hex(), "what": what}

    jsr = lambda s: struct.pack(">HI", 0x4EB9, syms[s])
    jmp = lambda s: struct.pack(">HI", 0x4EF9, syms[s])
    patches = [
        {"section": 3, "addr": f"{MODAREA_IMG + CODE_BASE - MODAREA_RAM:#010X}", "len": len(blob),
         "append": True, "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(mod area) diag.c"},
        fixed(KBD_HOOK, jmp("dg_kbd_hook") + bytes.fromhex("4e71"), "keys 13-16: jmp dg_kbd_hook ; nop", KBD_ORIG),
        fixed(EV_HOOK, jsr("dg_ev_hook"), "event dispatcher: jsr dg_ev_hook", EV_ORIG),
    ]
    spec = {
        "name": "dc-diag", "os": "1.41", "requires": ["modarea"],
        "description": "Diagnostic: popups showing key codes and held keys for keys 13-16. No behavior change.",
        "generated_by": "mods/dc-diag/make_patch.py",
        "symbols": {k: f"{syms[k]:#010x}" for k in ("dg_ev", "dg_kbd", "dg_ev_hook", "dg_kbd_hook", "dg_held")},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    (REPO / "out" / "dc-diag").mkdir(parents=True, exist_ok=True)
    (REPO / "out" / "dc-diag" / "diag.lst").write_text(dis, encoding="utf-8")
    print(f"patch.json: {len(blob)} B at {CODE_BASE:#x}..{CODE_BASE + len(blob):#x}")


if __name__ == "__main__":
    main()
