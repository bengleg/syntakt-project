"""DelayCtrl feature packages: web/patches/*.sypatch.json, built by mods/delay-control/make_features.py.

Always-run checks read only the repo. Stock checks need SYNTAKT_STOCK (the user's own OS 1.41 file) and an
elektron-firmware-tool (EFT_BIN); without them they skip with the reason. The build check needs the WSL m68k
toolchain and skips without it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "sypatch"), str(ROOT / "tools" / "unpack"), str(ROOT / "mods" / "delay-control")]
import check_patch  # noqa: E402
import eft  # noqa: E402

PATCHES = ROOT / "web" / "patches"
FEATURES = ROOT / "mods" / "delay-control" / "features"
ORDER = ["modarea", "delay-control-runtime", "delay-control-core", "delay-control-dj", "delay-control-drive",
         "delay-control-syn"]
REQUIRES = {
    "modarea": [],
    "delay-control-runtime": ["modarea"],
    "delay-control-core": ["modarea", "delay-control-runtime"],
    "delay-control-dj": ["modarea", "delay-control-runtime"],
    "delay-control-drive": ["modarea", "delay-control-runtime"],
    "delay-control-syn": ["modarea"],
}
# area offsets each package's code and data must stay in ([start, end)); modarea has no area blocks
SLOT = {
    "delay-control-runtime": (0x4010, 0x4800),
    "delay-control-core": (0x4800, 0x6000),
    "delay-control-dj": (0x6000, 0x6800),
    "delay-control-drive": (0x6800, 0x6C00),
    "delay-control-syn": (0x6C00, 0x6E00),
}
# registration words in the header, the only area blocks allowed there
REG = {"delay-control-core": 0x4000, "delay-control-drive": 0x4004}
HEADER = (0x4000, 0x400C)
RAM = 0x4600_0000
AREA_SIZE = 0x10000
LOAD = 0x4000_0400
STOCK_SHA256 = "8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e"
HEX = re.compile(r"^(?:[0-9a-f]{2})*$")
SHA = re.compile(r"^[0-9a-f]{64}$")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return _load(PATCHES / "manifest.json")


@pytest.fixture(scope="module")
def docs(manifest) -> dict[str, dict]:
    return {p["id"]: _load(PATCHES / p["file"]) for p in manifest["packages"]}


@pytest.fixture(scope="module")
def v2o_expect() -> dict[int, tuple[int, str]]:
    """Fingerprints of every replaced range of the v2o build (the reference): addr -> (len, sha256)."""
    out = {}
    for path in ("mods/delay-control/patch.json", "mods/modarea/patch.json"):
        for p in _load(ROOT / path)["patches"]:
            if not p.get("append"):
                out[int(p["addr"], 16)] = (p["len"], p["expect_sha256"])
    return out


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _blocks(doc: dict):
    for unit in doc["units"]:
        yield from unit["blocks"]


def _addr(b: dict) -> int:
    return int(b["addr"], 16)


def _area_range(b: dict) -> tuple[int, int]:
    return b["offset"], b["offset"] + b["len"]


def _words(data: bytes):
    """32-bit big-endian values at even offsets (instructions and data are 2-byte aligned)."""
    for i in range(0, len(data) - 3, 2):
        yield i, int.from_bytes(data[i:i + 4], "big")


def test_manifest_lists_the_six_packages_in_order(manifest):
    assert [p["id"] for p in manifest["packages"]] == ORDER
    assert [p["title"] for p in manifest["packages"]] == [
        "Mod area loader", "DelayCtrl runtime", "Freeze / DelayCtrl", "DJ filter", "Drive rectifier", "FX SYN page"]
    for p in manifest["packages"]:
        assert (PATCHES / p["file"]).is_file(), p["file"]


@pytest.mark.parametrize("pid", ORDER)
def test_package_header(pid, docs):
    doc = docs[pid]
    assert doc["format"] == "synthack-patchset" and doc["schema"] == 1
    assert doc["encoding"] == "lowercase-hex"
    assert doc["id"] == pid
    assert doc["requires"] == REQUIRES[pid]
    assert doc["target"] == {"device": "Syntakt", "os": "1.41", "stock_sha256": STOCK_SHA256}
    has_area = any(b["mode"] == "area" for b in _blocks(doc))
    assert ("area" in doc) == has_area
    if has_area:
        assert doc["area"] == {"img": "0x40348000", "ram": "0x46000000", "size": "0x10000", "compress": "shlz"}


@pytest.mark.parametrize("pid", ORDER)
def test_requires_name_existing_packages(pid, docs):
    for dep in docs[pid]["requires"]:
        assert dep in docs, f"{pid} requires unknown package {dep}"
        assert ORDER.index(dep) < ORDER.index(pid)


def test_checker_accepts_every_package(manifest):
    for p in manifest["packages"]:
        check_patch.check(_load(PATCHES / p["file"]))


def test_slots_are_disjoint_and_after_the_header():
    spans = sorted(SLOT.values())
    assert spans[0][0] >= HEADER[1]
    for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
        assert a1 <= b0
    assert max(hi for _, hi in spans) <= AREA_SIZE


@pytest.mark.parametrize("pid", ORDER)
def test_parts_are_lowercase_hex_and_hash_to_new_sha(pid, docs):
    for b in _blocks(docs[pid]):
        new = bytearray()
        total = 0
        for part in b["new"]:
            assert part[0] == "hex" and len(part) == 2, b["id"]
            assert HEX.match(part[1]), f"{b['id']}: not lowercase hex"
            new += bytes.fromhex(part[1])
            total += len(part[1]) // 2
        assert total == b["len"], f"{b['id']}: parts add to {total}, len is {b['len']}"
        assert SHA.match(b["new_sha256"]) and _sha(bytes(new)) == b["new_sha256"], b["id"]
        assert b["id"].startswith(pid), f"block id {b['id']} is not prefixed by {pid}"
        if b["mode"] == "replace":
            assert SHA.match(b["stock_sha256"]), b["id"]


def test_block_ids_are_unique_across_packages(docs):
    ids = [b["id"] for pid in ORDER for b in _blocks(docs[pid])]
    assert len(ids) == len(set(ids))


def test_replaced_ranges_are_the_v2o_fixed_blocks(docs, v2o_expect):
    """Every stock range the v2o build replaces is replaced once by one package, and no package replaces more."""
    seen: dict[int, tuple[int, str]] = {}
    for pid in ORDER:
        for b in _blocks(docs[pid]):
            if b["mode"] != "replace":
                continue
            addr = _addr(b)
            assert addr not in seen, f"{b['id']} replaces {addr:#x} again"
            seen[addr] = (b["len"], b["stock_sha256"])
    assert seen == v2o_expect


def test_no_overlap_between_replace_ranges(docs):
    spans = sorted((_addr(b), _addr(b) + b["len"], b["id"]) for pid in ORDER for b in _blocks(docs[pid])
                   if b["mode"] == "replace")
    for (a0, a1, aid), (b0, b1, bid) in zip(spans, spans[1:]):
        assert b0 >= a1, f"{aid} and {bid} change the same bytes"


def test_no_overlap_between_area_ranges(docs):
    spans = sorted((*_area_range(b), b["id"]) for pid in ORDER for b in _blocks(docs[pid])
                   if b["mode"] == "area")
    for (a0, a1, aid), (b0, b1, bid) in zip(spans, spans[1:]):
        assert b0 >= a1, f"{aid} and {bid} overlap in the mod area"


@pytest.mark.parametrize("pid", list(SLOT))
def test_area_blocks_inside_their_slot(pid, docs):
    lo, hi = SLOT[pid]
    blocks = [b for b in _blocks(docs[pid]) if b["mode"] == "area"]
    assert blocks, f"{pid} has no area blocks"
    for b in blocks:
        start, end = _area_range(b)
        if b["offset"] == REG.get(pid):
            assert b["len"] == 4 and b["kind"] == "data", b["id"]
            continue
        assert lo <= start and end <= hi, f"{b['id']} [{start:#x}, {end:#x}) outside [{lo:#x}, {hi:#x})"
        assert end <= AREA_SIZE


@pytest.mark.parametrize("pid", list(SLOT))
def test_area_code_then_data_split_at_text(pid, docs):
    blocks = [b for b in _blocks(docs[pid]) if b["mode"] == "area" and b["offset"] != REG.get(pid)]
    code = [b for b in blocks if b["kind"] == "code"]
    assert len(code) == 1, pid
    assert code[0]["len"] % 2 == 0, "code must be a whole number of 2-byte words"
    rest = [b for b in blocks if b["kind"] == "data"]
    assert len(rest) <= 1
    if rest:
        assert rest[0]["offset"] == code[0]["offset"] + code[0]["len"], "data must follow the code block"
    # runtime, drive and syn have no constants: their area is code only
    assert (len(rest) == 1) == (pid in ("delay-control-core", "delay-control-dj")), pid


@pytest.mark.parametrize("pid", list(REG))
def test_registration_word_points_into_its_own_code(pid, docs):
    reg = [b for b in _blocks(docs[pid]) if b["mode"] == "area" and b["offset"] == REG[pid]]
    assert len(reg) == 1 and reg[0]["kind"] == "data" and reg[0]["len"] == 4
    target = int.from_bytes(bytes.fromhex(reg[0]["new"][0][1]), "big")
    lo, hi = SLOT[pid]
    code = next(b for b in _blocks(docs[pid]) if b["mode"] == "area" and b["kind"] == "code")
    assert RAM + code["offset"] <= target < RAM + code["offset"] + code["len"], f"{pid}: entry outside its code"
    assert target % 2 == 0 and RAM + lo <= target < RAM + hi


def test_header_words_are_written_only_by_their_registration_blocks(docs):
    for pid in ORDER:
        for b in _blocks(docs[pid]):
            if b["mode"] != "area":
                continue
            start, end = _area_range(b)
            hit = start < HEADER[1] and HEADER[0] < end
            if not hit:
                continue
            assert REG.get(pid) == b["offset"] and b["len"] == 4 and b["kind"] == "data", (
                f"{b['id']} writes the mod area header")


@pytest.mark.parametrize("pid", list(SLOT))
def test_absolute_ram_references_stay_in_package(pid, docs):
    """Every 32-bit value in a package's bytes that points into the mod area points into its own slot,
    or into the header (DC_REG_CORE, DC_REG_DRIVE, DC_VIEW). Packages never call each other by symbol."""
    lo, hi = SLOT[pid]
    allowed = [(RAM + lo, RAM + hi), (RAM + HEADER[0], RAM + HEADER[1])]
    for b in _blocks(docs[pid]):
        data = bytes.fromhex("".join(p[1] for p in b["new"]))
        for _, v in _words(data):
            if RAM <= v < RAM + AREA_SIZE:
                assert any(a <= v < z for a, z in allowed), f"{b['id']} points to {v:#x} outside {pid}"


def test_hooks_land_on_their_package(docs):
    """The jmp/jsr hook operands of each replace block point into the package that owns it."""
    for pid in ORDER[1:]:
        lo, hi = SLOT[pid]
        for b in _blocks(docs[pid]):
            if b["mode"] != "replace":
                continue
            data = bytes.fromhex(b["new"][0][1])
            if data[:2] in (b"\x4e\xb9", b"\x4e\xf9"):
                target = int.from_bytes(data[2:6], "big")
                assert RAM + lo <= target < RAM + hi, f"{b['id']} jumps to {target:#x}"


def test_feature_sources_have_no_probe_code():
    for path in sorted(FEATURES.glob("*")):
        text = path.read_text(encoding="utf-8")
        for word in ("SNAP_PROBE", "DC_DEBUG", "dc_page_hook", "dc_snap", "dc_pk", "POPUP", "dc_view"):
            assert word not in text, f"{path.name} still has {word}"


def test_no_firmware_or_build_artifacts_in_the_packages():
    for path in list(PATCHES.iterdir()) + list((ROOT / "mods" / "delay-control").rglob("*")):
        assert path.suffix.lower() not in (".syx", ".smz4", ".bin", ".elemod"), path


def _stock() -> Path:
    raw = os.environ.get("SYNTAKT_STOCK")
    if not raw:
        pytest.skip("SYNTAKT_STOCK not set (the user's OS 1.41 file)")
    path = Path(raw)
    if not path.is_file():
        pytest.skip(f"SYNTAKT_STOCK does not exist: {path}")
    return path


@pytest.fixture(scope="module")
def stock_sec3(tmp_path_factory):
    path = _stock()
    if _sha(path.read_bytes()) != STOCK_SHA256:
        pytest.fail("SYNTAKT_STOCK is not the OS 1.41 file")
    try:
        eft._find_bin()
    except eft.EftError as e:
        pytest.skip(f"elektron-firmware-tool not available: {str(e).splitlines()[0]}")
    out = tmp_path_factory.mktemp("stock")
    return eft.unpack(path, out, ids=[3])[3].read_bytes()


@pytest.mark.parametrize("pid", ORDER)
def test_stock_bytes_match_each_replace_block(pid, docs, stock_sec3):
    for b in _blocks(docs[pid]):
        if b["mode"] != "replace":
            continue
        a = _addr(b) - LOAD
        assert _sha(stock_sec3[a:a + b["len"]]) == b["stock_sha256"], f"{b['id']}: stock bytes differ"


def test_build_reproduces_the_committed_packages(tmp_path):
    import make_features

    try:
        make_features.wsl("~/tools/m68k/root/usr/bin/m68k-linux-gnu-gcc-13 --version")
    except (SystemExit, OSError):
        pytest.skip("WSL m68k toolchain not available")
    make_features.main(["--out", str(tmp_path)])
    for path in sorted(tmp_path.iterdir()):
        assert path.read_bytes() == (PATCHES / path.name).read_bytes(), f"{path.name} differs from a rebuild"
