"""Mod delay-control: freeze / beat repeat on MOD B. Builds patch.json from dc.c.

    python mods/delay-control/make_patch.py
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
CODE_BASE, CODE_END = MODAREA_RAM + 0x4000, MODAREA_RAM + 0x7E00   # beat-repeat's slot (never built together)
TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra" + " " + __import__("os").environ.get("DC_CFLAGS", "")
ENTRY_HOOK, ENTRY_ORIG = 0x4002_E850, "4e56ffac48d73cfc"  # link fp,#-84 ; movem.l (consumeKeyEvent entry)
KBD_HOOK, KBD_ORIG = 0x4002_EA92, "7223b2806c00010e"    # moveq #35,d1 ; cmp.l d0,d1 ; bge.w 0x4002EBA6
EV_HOOK, EV_ORIG = 0x4000_B420, "4eb94000839e"          # jsr 0x4000839e
DEL_HOOK, DEL_ORIG = 0x4008_F828, "4eb940096890"        # jsr 0x40096890 (delay)
MIX_HOOK, MIX_ORIG = 0x4008_FB04, "486efed848798000e0f0"  # pea -296(fp) ; pea 0x8000E0F0


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["bash", "-lc", cmd] if sys.platform != "win32" else ["wsl.exe", "-e", "bash", "-lc", cmd],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"command failed:\n{cmd}\n{r.stderr}")
    return r.stdout + r.stderr


def build_blob() -> tuple[bytes, dict[str, int], str]:
    with tempfile.TemporaryDirectory(prefix="dc-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "dc.c", tmp / "dc.c")
        w = eft.to_wsl_path(tmp) if sys.platform == "win32" else str(tmp)
        env = f"R={TOOLS}; cd '{w}'; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} {CFLAGS} -c dc.c -o dc.o")
        if "warning" in warn:
            raise SystemExit(warn)
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e dc_run -o dc.elf dc.o")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u dc.elf").strip()
        if undef:
            raise SystemExit(f"external symbols not allowed: {undef}")
        heads = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -h dc.elf")
        for name, size in re.findall(r"^\s*\d+\s+(\.\S+)\s+([0-9a-f]+)", heads, re.M):
            if name in (".bss", ".sbss") and int(size, 16):
                raise SystemExit("no .bss allowed")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data dc.elf dc.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm dc.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        dis = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -d dc.elf")
        blob = (tmp / "dc.bin").read_bytes()
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
         "append": True, "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(mod area) dc.c"},
        fixed(ENTRY_HOOK, jsr("dc_entry_hook") + bytes.fromhex("4e71"), "consumeKeyEvent entry: jsr dc_entry_hook ; nop", ENTRY_ORIG),
        fixed(KBD_HOOK, jmp("dc_kbd_hook") + bytes.fromhex("4e71"), "keys 13-16: jmp dc_kbd_hook ; nop", KBD_ORIG),
        fixed(EV_HOOK, jsr("dc_ev_hook"), "event dispatcher: jsr dc_ev_hook", EV_ORIG),
        fixed(DEL_HOOK, jsr("dc_del_hook"), "delay: jsr dc_del_hook (silence while active)", DEL_ORIG),
        fixed(0x4009_5FA6, jsr("dc_flt_hook"), "FX filter CVs: jsr dc_flt_hook (DJ type)", "102a00a472f8"),
        fixed(0x401D_4710, struct.pack(">I", syms["dc_s_dj"]), "filter type 6 name LPN -> DJ", "40251ba8"),
        fixed(0x4018_C794, struct.pack(">I", syms["dc_tgfx"]), "FX filter TYPE icon: invoker -> dc_tgfx (DJ text)",
              "40070b10"),
        fixed(0x4004_2646, jsr("dc_fdraw_hook"), "filter tab curve: jsr dc_fdraw_hook (DJ as LP2/HP2)", "47f940039160"),
        fixed(0x4019_5156, jsr("dc_syn_stub"), "FX SYN page init: jsr dc_syn_stub (slots 1-7)", "42b941b9f968"),
        fixed(0x4009_08FC, jsr("dc_ext_hook"), "external in level CVs: jsr dc_ext_hook (mute while frozen)", "223c00007f7f"),
        fixed(0x4009_03F8, jsr("dc_mute_hook"), "analog voice CV loop: jsr dc_mute_hook (mute mask)", "737980003150"),
        fixed(MIX_HOOK, jsr("dc_mix_hook") + bytes.fromhex("4e714e71"), "after FX bus sums: jsr dc_mix_hook ; nop ; nop", MIX_ORIG),
    ]
    if "SNAP_PROBE" in __import__("os").environ.get("DC_CFLAGS", ""):
        patches.append(fixed(0x4000_DA32, jmp("dc_snap_hook") + bytes.fromhex("4e71"),
                             "kit parameter setter entry: jmp dc_snap_hook (probe)", "2f032f02222f000c"))
    # DCTL setup page: MOD B M1-M4 (54-57) with the RETRIG look and range, DEST (53) hidden
    for pid, f_op, g_op, default in ((54, 0x4018_AD86, 0x4018_AD94, 0x000), (55, 0x4018_ADC4, 0x4018_ADD6, 0x200),
                                     (56, 0x4018_AE06, 0x4018_AE14, 0x400), (57, 0x4018_AE48, 0x4018_AE56, 0x600)):
        patches.append(fixed(f_op, struct.pack(">I", syms["dc_mfmt_proto"]), f"id {pid} +20: RETRIG formatter (clamped)",
                             "41b9dfd0"))
        patches.append(fixed(g_op, struct.pack(">I", syms["dc_mgfx_proto"]), f"id {pid} +36: RETRIG box graphic (clamped)",
                             "41b9dcd0"))
        d = 0x4022_D59C + 52 * pid
        old = {54: 0x2000, 55: 0x4000, 56: 0x6000, 57: 0x7F00}[pid]
        patches.append(fixed(d + 12, struct.pack(">II", 0x800, default), f"id {pid}: max 0x800 (9 steps), default {default:#x}",
                             struct.pack(">II", 0x7F00, old).hex()))
    patches.append(fixed(0x4019_52C4, bytes.fromhex("42b941b9fa0c"), "DCTL page slot 4: DEST hidden (clr.l)",
                         "23c141b9fa0c"))
    ptr = lambda s: struct.pack(">I", syms[s])
    for addr, old, sym, what in [(0x4004_0B74, "4024e844", "dc_s_on", "popup Mod B ON -> DelayCtrl ON"),
                                 (0x4019_52A8, "40251b5f", "dc_s_long", "name Mod B -> DelayCtrl"),
                                 (0x4019_524A, "4024f880", "dc_s_short", "page name MODB -> DCTL"),
                                 (0x4004_E9BC, "4024f880", "dc_s_short", "TrigModListView title MODB -> DCTL")]:
        patches.append(fixed(addr, ptr(sym), what, old))
    spec = {
        "name": "delay-control", "os": "1.41", "requires": ["modarea"],
        "description": "Delay Control on MOD B: rolling 1-beat buffer of the FX bus, TRIG 13-16 freeze and chop-lock, stock delay silenced.",
        "generated_by": "mods/delay-control/make_patch.py",
        "symbols": {k: f"{syms[k]:#010x}" for k in ("dc_run", "dc_kbd", "dc_ev", "dc_post", "dc_kbd_hook", "dc_ev_hook", "dc_del_hook", "dc_mix_hook", "dc_entry_hook", "dc_mute_hook", "dc_syn_stub", "dc_flt", "dc_flt_hook", "dc_s_dj", "dc_fdraw", "dc_fdraw_hook", "dc_ext_hook", "dc_emute", "dc_hw", "dc_tgfx", "dc_tgfx_dj", "dc_s_dj", "dc_page_hook", "dc_mfmt", "dc_mgfx", "dc_mfmt_proto", "dc_mgfx_proto", "dc_rate", "dc_allowed", "dc_amute", "dc_view", "dc_active", "dc_held")},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    (REPO / "out" / "delay-control").mkdir(parents=True, exist_ok=True)
    (REPO / "out" / "delay-control" / "dc.lst").write_text(dis, encoding="utf-8")
    print(f"patch.json: {len(blob)} B at {CODE_BASE:#x}..{CODE_BASE + len(blob):#x}")


if __name__ == "__main__":
    main()
