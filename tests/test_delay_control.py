"""Mod delay-control, run in the emulator.

The real mod code runs against stubs: the selected trig modifier (0x40015AF6), the global accessors,
the tempo word and the event dispatcher / delay (rts). Audio is fed block by block through the FX bus.
"""

import json
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import UC_CPU_M68K_ANY, UC_M68K_REG_A6, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_SR  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "unpack")]
import eft  # noqa: E402

SY = ROOT / "firmware" / "Syntakt_OS1.41.syx"
MODS = [ROOT / "mods" / m / "patch.json" for m in ("modarea", "delay-control")]
pytestmark = pytest.mark.skipif(not (SY.exists() and all(p.exists() for p in MODS)), reason="OS or patch missing")

STACK, RET, EV, SEL = 0x5000_8000, 0x5000_F000, 0x5000_2400, 0x5000_2500
VIEW, PROJECT = 0x5000_2000, 0x5000_3000
STORE, MODV = 0x5000_3800, 0x5000_3B00
FX_BUS, DLY_IN, DLY_OUT = 0x8000_DAD0, 0x8000_DBD0, 0x8000_DCD0
TEMPO = 0x402D_7010
Q = 24000                                  # frames per beat at 120 BPM
LENS = [Q, Q // 2, Q // 4, Q // 8]         # default slots: 1/4, 1/8, 1/16, 1/32
XF = 256
EF = 128                                   # fade at freeze start / release
KEY13 = 36


class Machine:
    def __init__(self):
        sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
        spec = json.loads(MODS[1].read_text(encoding="utf-8"))
        self.sym = {k: int(v, 16) for k, v in spec["symbols"].items()}
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(0x4000_0400, sec3)
        uc.mem_map(0x4600_0000, 0x0020_0000)   # mod area + ring
        uc.mem_map(0x5000_0000, 0x4_0000)
        uc.mem_map(0x8000_0000, 0x1_0000)
        for f in MODS:
            for p in json.loads(f.read_text(encoding="utf-8"))["patches"]:
                uc.mem_write(int(p["ram"], 16) if p.get("append") else int(p["addr"], 16), bytes.fromhex(p["hex"]))
        uc.mem_write(RET, b"\x4e\x75")
        arg = b"\x20\x2f\x00\x04"                                               # move.l 4(sp),d0
        uc.mem_write(0x4001_9000, arg + b"\x4e\x75")                            # PAT_ENTRY(project) -> project
        uc.mem_write(0x4001_6056, arg + b"\x4e\x75")                            # STORE(x) -> x
        # GET_SEL(store): the selection only if store is the project, else -1 (a wrong pointer would crash)
        uc.mem_write(0x4001_5AF6, arg + struct.pack(">HIH", 0x0C80, PROJECT, 0x6608)
                     + struct.pack(">HIH", 0x2039, SEL, 0x4E75) + b"\x70\xff\x4e\x75")
        self.gets = 0
        uc.hook_add(UC_HOOK_CODE, lambda *a: setattr(self, "gets", self.gets + 1), begin=0x4001_5AF6, end=0x4001_5AF6)
        uc.mem_write(VIEW + 148, struct.pack(">I", PROJECT))
        # parameter store: 0x400186E8(project) -> STORE; STORE->vtbl[40](store, id) = MODV[id - 54]
        uc.mem_write(0x4001_86E8, struct.pack(">HIH", 0x203C, STORE, 0x4E75))      # move.l #STORE,d0 ; rts
        uc.mem_write(STORE, struct.pack(">I", STORE + 0x100))
        uc.mem_write(STORE + 0x100 + 40, struct.pack(">I", STORE + 0x200))
        uc.mem_write(STORE + 0x200, bytes.fromhex("202f0008" "048000000036" "e588")
                     + struct.pack(">HI", 0x41F9, MODV) + bytes.fromhex("20300800" "4e75"))
        self.modv(0x000, 0x200, 0x400, 0x600)
        uc.mem_write(0x4000_839E, b"\x4e\x75")                                  # dispatcher
        uc.mem_write(0x4009_6890, b"\x4e\x75")                                  # delay
        uc.mem_write(0x400C_33D0, b"\x4e\x75")                                  # popup (debug builds)
        uc.mem_write(TEMPO, struct.pack(">I", 120 * 120))
        for t in range(8, 12):                                                  # analog tracks not routed to FX
            uc.mem_write(0x8000_21B0 + 142 * t + 126, struct.pack(">H", 0x100))
        uc.mem_write(0x8000_28CA, struct.pack(">H", 0x100))                    # external in not routed
        uc.mem_write(0x8000_3146, b"\x01")                                      # external in stereo
        self.select(0)
        self.n = 0                                                              # next input frame value

    def modv(self, *v):
        self.uc.mem_write(MODV, struct.pack(">4i", *v))

    def select(self, s):
        self.uc.mem_write(SEL, struct.pack(">i", s))

    def call(self, fn, args=(), count=2_000_000):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *[a & 0xFFFFFFFF for a in args]))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        n = [0]

        def at(uc_, addr, size, _):
            n[0] += 1
        h = uc.hook_add(UC_HOOK_CODE, at)
        uc.emu_start(fn, RET, count=count)
        uc.hook_del(h)
        self.steps = n[0]
        return uc.reg_read(UC_M68K_REG_D0) & 0xFFFFFFFF, uc.reg_read(UC_M68K_REG_A7), sp

    def u32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def bus(self, base=FX_BUS):
        return list(struct.unpack(">64i", self.uc.mem_read(base, 256)))

    def block(self):
        """Feed one block (L = frame * 256, R = -L) and run dc_run. Returns (input, output)."""
        vals = []
        for i in range(32):
            v = (self.n + i) * 256
            vals += [v, -v]
        self.n += 32
        self.uc.mem_write(FX_BUS, struct.pack(">64i", *vals))
        self.call(self.sym["dc_run"])
        return vals, self.bus()

    def key(self, n, down):
        """TRIG n (13..16) through dc_kbd, as from 0x4002EA92. Returns d0 (1 consumed, -1 stock)."""
        self.uc.mem_write(EV + 12, struct.pack(">II", 23 + n, 1 if down else 0))
        d0, _, _ = self.call(self.sym["dc_kbd"], (VIEW, EV, 23 + n))
        return d0 - (1 << 32) if d0 & 0x8000_0000 else d0


@pytest.fixture()
def m():
    return Machine()


def frames(out):
    return [out[2 * i] // 256 for i in range(32)]


def test_inactive_is_stock(m):
    assert m.key(13, True) == -1
    vals, out = m.block()
    assert out == vals
    m.uc.mem_write(DLY_IN, b"\x11" * 256)
    m.call(m.sym["dc_del_hook"], (DLY_OUT, DLY_IN, 0))
    assert m.uc.mem_read(DLY_IN, 4) == b"\x11" * 4


def test_keys_consumed_and_last_pressed(m):
    m.select(3)
    assert m.key(13, True) == 1
    assert m.key(16, True) == 1
    assert m.u32(m.sym["dc_held"]) == 0b1001
    assert m.key(16, False) == 1
    assert m.key(13, False) == 1
    assert m.u32(m.sym["dc_held"]) == 0


def test_no_view_no_lookup(m):
    m.select(3)
    m.call(m.sym["dc_ev_hook"], (0, EV))                      # any key before KeyboardView was seen
    assert m.gets == 0 and m.u32(m.sym["dc_active"]) == 0


def test_entry_hook_records_view_and_replays(m):
    from unicorn.m68k_const import UC_M68K_REG_A6 as FP
    sp = STACK - 16
    m.uc.mem_write(sp, struct.pack(">IIII", 0x4002_E856, RET, VIEW, EV))   # hook return, caller return, this, event
    m.uc.reg_write(UC_M68K_REG_A7, sp)
    m.uc.reg_write(FP, 0x1234_5678)
    m.uc.emu_start(m.sym["dc_entry_hook"], 0x4002_E856, count=50)
    assert m.u32(m.sym["dc_view"]) == VIEW
    fp = m.uc.reg_read(FP)
    assert fp == sp and m.u32(fp) == 0x1234_5678                    # link fp,#-84 as at the real entry
    assert m.uc.reg_read(UC_M68K_REG_A7) == fp - 84


def test_delay_silenced_when_active(m):
    m.select(3)
    m.key(13, True), m.key(13, False)                          # KeyboardView seen
    m.call(m.sym["dc_ev_hook"], (0, EV))                      # dispatcher stub, then dc_post
    assert m.u32(m.sym["dc_active"]) == 1
    m.uc.mem_write(DLY_IN, b"\x11" * 256)
    m.uc.mem_write(DLY_OUT, b"\x22" * 256)
    _, sp_out, sp_in = m.call(m.sym["dc_del_hook"], (DLY_OUT, DLY_IN, 0))
    assert sp_out == sp_in + 4
    assert m.bus(DLY_IN) == [0] * 64 and m.bus(DLY_OUT) == [0] * 64


def run_until_full(m):
    m.select(3)
    m.key(13, True), m.key(13, False)                          # sets active
    for _ in range(Q // 32 + 40):
        vals, out = m.block()
        assert out == vals                                      # not held: dry passes
    return m.n                                                  # freeze point (exclusive)


def loop_check(m, end, length, blocks, start_pos=0, fresh=False):
    """Loop plays end-length .. end-1. fresh: the freeze starts now, skip the EF-frame fade-in."""
    pos = start_pos
    k = 0 if fresh else EF
    xf = min(XF, length // 4)
    for _ in range(blocks):
        _, out = m.block()
        for i, f in enumerate(frames(out)):
            k += 1
            if pos < length - xf and k > EF:
                assert f == end - length + pos, (pos, f)
            pos = (pos + 1) % length
    return pos


def test_freeze_loops_latest_beat(m):
    end = run_until_full(m)
    m.key(13, True)
    loop_check(m, end, LENS[0], 30, fresh=True)


def test_chop_shorter_and_lock(m):
    end = run_until_full(m)
    m.key(13, True)
    loop_check(m, end, LENS[0], 5, fresh=True)
    m.key(16, True)                                            # 1/32: chop to the latest 3000 frames
    pos = loop_check(m, end, LENS[3], 200)
    m.key(16, False)                                           # back to 13: stays locked at 1/32
    pos = loop_check(m, end, LENS[3], 50, pos)
    m.key(14, True)                                            # longer: still locked
    loop_check(m, end, LENS[3], 50, pos)


def test_release_returns_dry_and_resumes(m):
    run_until_full(m)
    m.key(13, True)
    m.block()
    m.key(13, False)
    for _ in range(EF // 32):                                  # release fade
        m.block()
    vals, out = m.block()
    assert out == vals
    for _ in range(LENS[2] // 32 + 4):                         # record past the frozen gap
        m.block()
    m.key(15, True)                                            # new freeze includes the new audio
    end = m.n
    loop_check(m, end, LENS[2], 10, fresh=True)


def test_crossfade_is_continuous(m):
    end = run_until_full(m)
    m.key(16, True)
    for _ in range(EF // 32):
        m.block()
    prev = None
    for _ in range(LENS[3] // 32 * 2):
        _, out = m.block()
        for f in frames(out):
            if prev is not None:
                assert abs(f - prev) <= LENS[3] // min(XF, LENS[3] // 4) + 2 or abs(f - prev) == 1, (prev, f)
            prev = f


def test_short_history_uses_recorded_only(m):
    m.select(3)
    m.key(13, True), m.key(13, False)
    for _ in range(10):
        m.block()
    m.key(13, True)                                            # only 320 frames recorded
    for _ in range(EF // 32):
        m.block()
    _, out = m.block()
    assert all(0 <= f < 320 for f in frames(out))


def test_mix_hook_trampoline(m):
    m.uc.reg_write(UC_M68K_REG_A6, 0x5000_3000)
    _, sp_out, sp_in = m.call(m.sym["dc_mix_hook"])
    assert sp_out == sp_in + 4 - 8                             # return popped, two pea pushed
    assert m.u32(sp_out) == 0x8000_E0F0 and m.u32(sp_out + 4) == 0x5000_3000 - 296


def test_cost_per_block(m):
    run_until_full(m)
    m.call(m.sym["dc_run"])
    idle = m.steps
    m.key(14, True)
    m.block()
    frozen = m.steps
    assert idle < 1500 and frozen < 2500, (idle, frozen)
    for t in range(8, 12):                                      # worst case: all 4 analog tracks routed
        rout(m, t, True)
    m.key(14, False)
    for _ in range(EF // 32 + 1):                               # past the release fade
        m.block()
    assert m.steps < 4000, m.steps


DRIVE = 0x8000_28F0


def drive(m, display):
    m.uc.mem_write(DRIVE, struct.pack(">H", int(0x7F00 * display / 11)))


def blend(x, display):
    lo = 0x7F00 * 5 // 11
    v = int(0x7F00 * display / 11)
    if v <= lo:
        return x
    a = min(256, (v - lo) * 256 // (0x7F00 - lo))
    r = abs(x)
    return r if a == 256 else (x >> 8) * (256 - a) + (r >> 8) * a


@pytest.mark.parametrize("display", [0, 4, 5, 6, 8, 10, 11])
def test_rectifier_blend(m, display):
    drive(m, display)
    vals, out = m.block()
    m.n = -1000                                                 # negative and positive samples next
    vals, out = m.block()
    assert out == [blend(x, display) for x in vals]


def test_rectifier_full_is_abs_and_applies_to_loop(m):
    end = run_until_full(m)
    drive(m, 11)
    m.key(16, True)
    for _ in range(EF // 32):                                   # fade-in
        m.block()
    _, out = m.block()
    assert all(x >= 0 for x in out)
    assert [out[2 * i] // 256 for i in range(32)] == [end - LENS[3] + EF + i for i in range(32)]


ADC0 = 0x8000_3950


def rout(m, t, on):
    m.uc.mem_write(0x8000_21B0 + 142 * t + 126, struct.pack(">H", 0 if on else 0x100))


def test_analog_routed_captured_and_muted(m):
    rout(m, 9, True)                                            # track 10 (ADC 1) routed, others not
    m.uc.mem_write(ADC0 + 128 * 1, struct.pack(">32i", *[7 * 256 * 256] * 32))   # x 26/256 -> +7*26*256
    m.uc.mem_write(ADC0 + 128 * 2, struct.pack(">32i", *[1000 * 256] * 32))   # not routed: ignored
    end = run_until_full(m)
    assert m.u32(m.sym["dc_amute"]) == 0
    m.key(16, True)
    for _ in range(EF // 32):                                   # fade-in
        m.block()
    _, out = m.block()
    p = end - LENS[3] + EF
    assert [out[2 * i] // 256 for i in range(32)] == [p + i + 7 * 26 for i in range(32)]
    assert [out[2 * i + 1] for i in range(32)] == [-(p + i) * 256 + 7 * 26 * 256 for i in range(32)]
    assert m.u32(m.sym["dc_amute"]) == 1 << 9
    m.key(16, False)
    m.block()
    assert m.u32(m.sym["dc_amute"]) == 0


def test_mute_hook_ors_mask(m):
    m.uc.mem_write(0x8000_3150, struct.pack(">h", 0x0101))
    m.uc.mem_write(m.sym["dc_amute"], struct.pack(">I", 0x0A00))
    m.call(m.sym["dc_mute_hook"])
    from unicorn.m68k_const import UC_M68K_REG_D1
    assert m.uc.reg_read(UC_M68K_REG_D1) & 0xFFFF == 0x0B01


def test_fades_at_freeze_and_release_are_smooth(m):
    """Live input is a constant; the loop is a different constant: both fades must ramp, no jump."""
    m.select(3)
    m.key(13, True), m.key(13, False)
    live = 1000 * 256
    for _ in range(Q // 32 + 40):
        m.uc.mem_write(FX_BUS, struct.pack(">64i", *[live, live] * 32))
        m.call(m.sym["dc_run"])
    seq = []

    def feed(v):
        m.uc.mem_write(FX_BUS, struct.pack(">64i", *[v, v] * 32))
        m.call(m.sym["dc_run"])
        seq.extend(m.bus()[0::2])
    m.key(13, True)
    for _ in range(EF // 32 + 2):
        feed(5000 * 256)                                        # live jumps; loop holds the old constant
    m.key(13, False)
    for _ in range(EF // 32 + 2):
        feed(5000 * 256)
    steps = [abs(b - a) for a, b in zip(seq, seq[1:])]
    assert max(steps) <= (4000 * 256) // EF + 512, max(steps)


def test_syn_page_slots(m):
    m.uc.mem_map(0x41B9_0000, 0x1_0000)
    m.uc.mem_write(0x41B9_F96C, struct.pack(">I", 150))
    _, sp_out, sp_in = m.call(m.sym["dc_syn_stub"])
    assert sp_out == sp_in + 4
    slots = struct.unpack(">8I", m.uc.mem_read(0x41B9_F950, 32))
    assert slots == (120, 121, 117, 152, 133, 134, 143, 150)


KIT, HW = 0x5000_4000, 0x5000_6000


def flt(m, ftype, freq, reso=0x4000, fpan=0x4000, mode=5):
    m.uc.mem_write(KIT + 1820, bytes([ftype, 0]))
    m.uc.mem_write(KIT + 1822, struct.pack(">HH", freq, reso))
    m.uc.mem_write(KIT + 1840, struct.pack(">H", fpan))
    m.uc.mem_write(0x43BD_C044, bytes([mode]))
    m.uc.mem_write(HW + 74, b"\x11" * 6)
    d0, _, _ = m.call(m.sym["dc_flt"], (HW, KIT))
    d0 = d0 - (1 << 32) if d0 & 0x8000_0000 else d0
    l, r, res = struct.unpack(">hhh", m.uc.mem_read(HW + 74, 6))
    return d0, l, r, res


@pytest.fixture()
def mf(m):
    m.uc.mem_map(0x43BD_0000, 0x1_0000)
    return m


def test_dj_only_on_type_6(mf):
    assert flt(mf, 1, 0x2000) == (-1, 0x1111, 0x1111, 0x1111)


@pytest.mark.parametrize("freq,typ,cut", [
    (0x0000, 1, -32768),            # LP closed
    (0x3F00, 1, 65024 - 32768),     # LP fully open at 63
    (0x4000, 3, -32768),            # HP fully open at 64
    (0x7F00, 3, 65024 - 32768),     # HP at the top
])
def test_dj_mapping(mf, freq, typ, cut):
    t, l, r, _ = flt(mf, 6, freq)
    assert (t, l, r) == (typ, cut, cut)


def test_dj_pan_and_reso_like_os(mf):
    b = 0x4000_0400
    sec = bytes(mf.uc.mem_read(b, 0x30_0000))
    tab = lambda a, i: struct.unpack(">h", sec[a - b + 2 * i:a - b + 2 * i + 2])[0]
    t, l, r, res = flt(mf, 6, 0x2000, reso=0x5000, fpan=0x4800)
    fp = 0x2000 * 0x7F00 // 0x3F00
    pan = 2 * (0x4800 - 16384)
    assert l == max(0, min(65024, 2 * fp - pan)) - 32768 and r == max(0, min(65024, 2 * fp + pan)) - 32768
    assert res == tab(0x4024_9D18, 0x50) - tab(0x4024_9A18, fp >> 8)
    _, _, _, res2 = flt(mf, 6, 0x2000, mode=1)                  # alternate path: reso untouched
    assert res2 == 0x1111


def test_flt_hook_sets_type_and_replays(mf):
    from unicorn.m68k_const import UC_M68K_REG_A2, UC_M68K_REG_A3, UC_M68K_REG_D1, UC_M68K_REG_D2
    for ftype, freq, want in ((6, 0x1000, 1), (6, 0x6000, 3), (4, 0x1000, 99)):
        mf.uc.mem_write(KIT + 1820, bytes([ftype, 0]))
        mf.uc.mem_write(KIT + 1822, struct.pack(">H", freq))
        mf.uc.mem_write(HW + 164, b"\x5a")
        mf.uc.reg_write(UC_M68K_REG_A2, HW)
        mf.uc.reg_write(UC_M68K_REG_A3, KIT)
        mf.uc.reg_write(UC_M68K_REG_D2, 99)
        d0, sp_out, sp_in = mf.call(mf.sym["dc_flt_hook"])
        assert sp_out == sp_in + 4
        assert mf.uc.reg_read(UC_M68K_REG_D2) == want
        assert d0 & 0xFF == 0x5A and mf.uc.reg_read(UC_M68K_REG_D1) & 0xFFFFFFFF == 0xFFFFFFF8


def test_fdraw_dj_curve_only_on_fx_track(m):
    from unicorn.m68k_const import UC_M68K_REG_A3, UC_M68K_REG_A4, UC_M68K_REG_D6
    trk = 0x5000_2600
    m.uc.mem_write(0x4001_FF74, struct.pack(">HIH", 0x2039, trk, 0x4E75))   # active track stub
    m.uc.mem_write(m.sym["dc_view"], struct.pack(">I", VIEW))
    cases = [(12, 6, 0x1F80, 1, 0x1F80 * 0x7F00 // 0x3F00),                 # FX, DJ low half -> LP2
             (12, 6, 0x6000, 3, 0x2000 * 0x7F00 // 0x3F00),                 # FX, DJ high half -> HP2
             (12, 4, 0x6000, 4, 0x6000),                                    # FX, other type untouched
             (9, 6, 0x6000, 6, 0x6000)]                                     # analog track: real LP-Notch
    for t, typ, freq, want_t, want_f in cases:
        m.uc.mem_write(0x8000_28CC, bytes([typ]))                           # engine FX filter TYPE
        m.uc.mem_write(trk, struct.pack(">I", t))
        m.uc.reg_write(UC_M68K_REG_D6, typ)
        m.uc.reg_write(UC_M68K_REG_A4, freq)
        _, sp_out, sp_in = m.call(m.sym["dc_fdraw_hook"])
        assert sp_out == sp_in + 4
        assert (m.uc.reg_read(UC_M68K_REG_D6), m.uc.reg_read(UC_M68K_REG_A4)) == (want_t, want_f), t
        assert m.uc.reg_read(UC_M68K_REG_A3) == 0x4003_9160


def test_external_in_routed_captured_and_muted(m):
    m.uc.mem_write(0x8000_28CA, struct.pack(">H", 0))           # 0 = through the FX block
    m.uc.mem_write(ADC0 + 128 * 4, struct.pack(">32i", *[3 * 256 * 256] * 32))   # L -> +3*128*256
    m.uc.mem_write(ADC0 + 128 * 5, struct.pack(">32i", *[5 * 256 * 256] * 32))   # R -> +5*128*256
    end = run_until_full(m)
    assert m.u32(m.sym["dc_emute"]) == 0
    m.key(16, True)
    for _ in range(EF // 32):
        m.block()
    _, out = m.block()
    p = end - LENS[3] + EF
    assert [out[2 * i] for i in range(32)] == [(p + i) * 256 + 3 * 128 * 256 for i in range(32)]
    assert [out[2 * i + 1] for i in range(32)] == [-(p + i) * 256 + 5 * 128 * 256 for i in range(32)]
    assert m.u32(m.sym["dc_emute"]) == 1
    m.key(16, False)
    m.block()
    assert m.u32(m.sym["dc_emute"]) == 0


def test_external_not_routed_ignored(m):
    m.uc.mem_write(ADC0 + 128 * 4, struct.pack(">32i", *[3 * 256 * 256] * 32))
    end = run_until_full(m)
    m.key(16, True)
    for _ in range(EF // 32):
        m.block()
    _, out = m.block()
    assert [out[2 * i] // 256 for i in range(32)] == [end - LENS[3] + EF + i for i in range(32)]
    assert m.u32(m.sym["dc_emute"]) == 0


def test_ext_hook_mutes_cvs(m):
    from unicorn.m68k_const import UC_M68K_REG_A3, UC_M68K_REG_D1
    hw = 0x5000_6000
    m.uc.reg_write(UC_M68K_REG_A3, hw)
    for mute, want in ((0, (0x1234, 0x5678)), (1, (0, 0))):
        m.uc.mem_write(hw + 8, struct.pack(">H", 0x1234))
        m.uc.mem_write(hw + 18, struct.pack(">H", 0x5678))
        m.uc.mem_write(m.sym["dc_emute"], struct.pack(">I", mute))
        m.call(m.sym["dc_ext_hook"])
        assert struct.unpack(">H", m.uc.mem_read(hw + 8, 2))[0] == want[0]
        assert struct.unpack(">H", m.uc.mem_read(hw + 18, 2))[0] == want[1]
        assert m.uc.reg_read(UC_M68K_REG_D1) == 32639


@pytest.mark.skip(reason="v2g feature disabled (DJ_BYPASS / CV_LEVELS = 0)")
def test_dj_bypass_zone_reso(mf):
    t, _, _, res = flt(mf, 6, 0x4000)
    assert t == 7 and res == -20000


HWB = 0x5000_7000


def set_cv(m, levels):
    m.uc.mem_write(HWB, struct.pack(">10H", *levels))
    m.uc.mem_write(m.sym["dc_hw"], struct.pack(">I", HWB))


@pytest.mark.skip(reason="v2g feature disabled (DJ_BYPASS / CV_LEVELS = 0)")
def test_analog_uses_voice_level_and_pan(m):
    rout(m, 9, True)                                            # track 10 = voice / ADC 1
    m.uc.mem_write(ADC0 + 128 * 1, struct.pack(">32i", *[7 * 256 * 256] * 32))
    cv = [0] * 10
    cv[1], cv[6] = 0x8000, 0x4000                               # voice 2: left 1/2, right 1/4
    set_cv(m, cv)
    end = run_until_full(m)
    m.key(16, True)
    for _ in range(EF // 32):
        m.block()
    _, out = m.block()
    x = 7 * 26 * 256                                            # captured sample at bus scale
    p = end - LENS[3] + EF
    assert [out[2 * i] for i in range(32)] == [(p + i) * 256 + (x >> 8) * 0x80 for i in range(32)]
    assert [out[2 * i + 1] for i in range(32)] == [-(p + i) * 256 + (x >> 8) * 0x40 for i in range(32)]


@pytest.mark.skip(reason="v2g feature disabled (DJ_BYPASS / CV_LEVELS = 0)")
def test_external_mono_uses_left_on_both_sides(m):
    m.uc.mem_write(0x8000_28CA, struct.pack(">H", 0))
    m.uc.mem_write(0x8000_3146, b"\x00")                        # EXTERNAL IN mono
    m.uc.mem_write(ADC0 + 128 * 4, struct.pack(">32i", *[3 * 256 * 256] * 32))
    m.uc.mem_write(ADC0 + 128 * 5, struct.pack(">32i", *[0] * 32))
    cv = [0] * 10
    cv[4], cv[9] = 0xFFFF, 0xFFFF
    set_cv(m, cv)
    end = run_until_full(m)
    m.key(16, True)
    for _ in range(EF // 32):
        m.block()
    _, out = m.block()
    x = (3 * 26 * 256 >> 8) * 0xFF
    p = end - LENS[3] + EF
    assert [out[2 * i] for i in range(32)] == [(p + i) * 256 + x for i in range(32)]
    assert [out[2 * i + 1] for i in range(32)] == [-(p + i) * 256 + x for i in range(32)]


def test_mute_hook_saves_cv_block(m):
    from unicorn.m68k_const import UC_M68K_REG_A3
    m.uc.reg_write(UC_M68K_REG_A3, HWB)
    m.call(m.sym["dc_mute_hook"])
    assert m.u32(m.sym["dc_hw"]) == HWB


def test_type_icon_dj_text_and_stock_forward(m):
    hits = []
    m.uc.mem_write(0x400F_8C18, b"\x4e\x75")                    # DRAW_TEXT stub
    m.uc.mem_write(0x4007_0B10, b"\x4e\x75")                    # stock icon stub
    def at(uc_, addr, size, _):
        sp = uc_.reg_read(UC_M68K_REG_A7)
        hits.append((addr, struct.unpack(">6I", uc_.mem_read(sp + 4, 24))))
    for a in (0x400F_8C18, 0x4007_0B10):
        m.uc.hook_add(UC_HOOK_CODE, at, begin=a, end=a)
    ctx, x, y = 0x5000_3300, 40, 20
    m.call(m.sym["dc_tgfx"], (0x1234, 0x600, ctx, x, y))        # DJ
    assert len(hits) == 1 and hits[0][0] == 0x400F_8C18
    a = hits[0][1]
    assert (a[0], a[1], a[2], a[3], a[4], a[5]) == (ctx, 0x402A_91C0, x + 8, y + 5, 1, 0)
    hits.clear()
    _, sp_out, sp_in = m.call(m.sym["dc_tgfx"], (0x1234, 0x300, ctx, x, y))   # HP2: stock icon
    assert len(hits) == 1 and hits[0][0] == 0x4007_0B10
    assert hits[0][1][:5] == (0x1234, 0x300, ctx, x, y) and sp_out == sp_in + 4


def test_fdraw_syn_page_uses_engine_type(m):
    """On FX SYN there is no TYPE slot: d6 arrives as 0, the engine type must be used."""
    from unicorn.m68k_const import UC_M68K_REG_A4, UC_M68K_REG_D6
    trk = 0x5000_2600
    m.uc.mem_write(0x4001_FF74, struct.pack(">HIH", 0x2039, trk, 0x4E75))
    m.uc.mem_write(m.sym["dc_view"], struct.pack(">I", VIEW))
    m.uc.mem_write(trk, struct.pack(">I", 12))
    for eng, freq, want_t in ((3, 0x5000, 3), (6, 0x1000, 1), (6, 0x6000, 3)):
        m.uc.mem_write(0x8000_28CC, bytes([eng]))
        m.uc.reg_write(UC_M68K_REG_D6, 0)
        m.uc.reg_write(UC_M68K_REG_A4, freq)
        m.call(m.sym["dc_fdraw_hook"])
        assert m.uc.reg_read(UC_M68K_REG_D6) == want_t


def test_page_hook_routes_syn_to_filter_draw(m):
    from unicorn.m68k_const import UC_M68K_REG_D0
    for page, taken in ((7, True), (32, True), (9, False), (11, False), (21, False)):
        m.uc.reg_write(UC_M68K_REG_D0, page)
        sp = STACK - 8
        m.uc.mem_write(sp, struct.pack(">II", 0x4004_293E, 0))      # return to after the replaced code
        m.uc.reg_write(UC_M68K_REG_A7, sp)
        stop = []
        def at(uc_, addr, size, _):
            if addr in (0x4004_2948, 0x4004_293E):
                stop.append(addr)
                uc_.emu_stop()
        h = m.uc.hook_add(UC_HOOK_CODE, at)
        m.uc.emu_start(m.sym["dc_page_hook"], 0, count=50)
        m.uc.hook_del(h)
        assert stop and (stop[0] == 0x4004_2948) == taken, page
        if taken:
            assert m.uc.reg_read(UC_M68K_REG_A7) == sp + 4           # return address dropped


def test_slot_rates_from_mod_b_values(m):
    m.modv(0x000, 0x500, 0x7F00, 0x400)                         # 1/4, 1/24, out of range -> 1/64, 1/16
    m.select(3)
    m.key(13, True), m.key(13, False)
    assert list(m.uc.mem_read(m.sym["dc_rate"], 4)) == [4, 24, 64, 16]
    end = run_until_full(m)
    m.key(14, True)                                             # 1/24 bar = 4/24 beat
    loop_check(m, end, Q * 4 // 24, 60, fresh=True)


def test_mod_b_box_wrappers_clamp_and_forward(m):
    m.uc.mem_map(0x41B9_0000, 0x1_0000)
    hits = []
    stub = 0x5000_3C00
    m.uc.mem_write(stub, b"\x4e\x75")
    for proto in (0x41B9_DF00, 0x41B9_D930):
        m.uc.mem_write(proto + 12, struct.pack(">I", stub))
    def at(uc_, addr, size, _):
        sp = uc_.reg_read(UC_M68K_REG_A7)
        hits.append(struct.unpack(">3I", uc_.mem_read(sp + 4, 12)))
    m.uc.hook_add(UC_HOOK_CODE, at, begin=stub, end=stub)
    for sym, proto in (("dc_mfmt", 0x41B9_DF00), ("dc_mgfx", 0x41B9_D930)):
        for v, want in ((0x200, 0x600), (0x500, 0xB00), (0x7F00, 0xF00), (-5, 0x300)):
            hits.clear()
            m.call(m.sym[sym], (0x1234, v & 0xFFFFFFFF, 0x5555))
            assert hits == [(proto, want, 0x5555)], (sym, v, hits)
