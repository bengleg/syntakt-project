"""Structural checker for a .sypatch file (schema 1). Reads no firmware.

    python tools/sypatch/check_patch.py patch.sypatch
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

STOCK_SHA256 = "8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e"
HEX = re.compile(r"^(?:[0-9a-f]{2})*$")
SHA = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"[a-z0-9][a-z0-9-]*")
LOAD = 0x4000_0400


class PatchError(ValueError):
    pass


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _int(v, what: str) -> int:
    try:
        return int(v, 16) if isinstance(v, str) and v.lower().startswith("0x") else int(v)
    except (TypeError, ValueError):
        raise PatchError(f"{what}: not a number: {v!r}")


def _is_whole(v) -> bool:
    return (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer())


def _check_info(info, pid: str) -> None:
    """The optional notes (`info`). Mirrors checkInfo in tools/sypatch/merge.mjs: keep the two in step."""
    if not isinstance(info, dict):
        raise PatchError("info must be an object")
    if "summary" in info and (not isinstance(info["summary"], str) or len(info["summary"]) > 200):
        raise PatchError("info summary must be text of 200 characters or fewer")
    if "claims" in info and (not isinstance(info["claims"], list) or not all(isinstance(c, str) for c in info["claims"])):
        raise PatchError("info claims must be a list of text")
    if "conflicts" in info:
        cs = info["conflicts"]
        if not isinstance(cs, list) or not all(isinstance(c, str) and ID.fullmatch(c) for c in cs):
            raise PatchError("info conflicts must be a list of package ids")
        if pid in cs:
            raise PatchError("info conflicts cannot name the package itself")
    if "cost" in info and info["cost"] is not None:
        c = info["cost"]
        if not isinstance(c, dict):
            raise PatchError("info cost must be null or an object")
        ipb = c.get("instructionsPerBlock")
        if not _is_whole(ipb) or ipb < 0:
            raise PatchError("info cost instructionsPerBlock must be a whole number, 0 or more")
        if not isinstance(c.get("measured"), str):
            raise PatchError("info cost measured must be text")


def check(doc: dict) -> list[dict]:
    """Validate a parsed patch set. Returns its replace blocks as dicts with
    'start', 'end' (offsets into section 3, from LOAD). Raises PatchError."""
    if not isinstance(doc, dict):
        raise PatchError("not a synthack-patchset schema 1 file")
    if doc.get("format") != "synthack-patchset" or doc.get("schema") != 1:
        raise PatchError("not a synthack-patchset schema 1 file")
    if doc.get("encoding") != "lowercase-hex":
        raise PatchError("encoding must be lowercase-hex")
    t = doc.get("target", {})
    if t.get("device") != "Syntakt" or t.get("os") != "1.41":
        raise PatchError("target must be Syntakt OS 1.41")
    if t.get("stock_sha256") != STOCK_SHA256:
        raise PatchError("target.stock_sha256 is not the OS 1.41 hash")
    pid = doc.get("id")
    if not isinstance(pid, str) or not ID.fullmatch(pid):
        raise PatchError("id must be a lowercase name, such as delay-control-core")
    requires = doc.get("requires")
    if requires is None:
        requires = []
    if not isinstance(requires, list) or not all(isinstance(r, str) and ID.fullmatch(r) for r in requires):
        raise PatchError("requires must be a list of package ids")
    if pid in requires:
        raise PatchError("a package cannot require itself")
    if "info" in doc:
        _check_info(doc["info"], pid)

    area = doc.get("area")
    area_size = 0
    if area is not None:
        if area.get("compress") != "shlz":
            raise PatchError("area.compress must be shlz")
        area_size = _int(area.get("size"), "area.size")

    ids: set[str] = set()
    spans: list[tuple[int, int, str]] = []
    area_spans: list[tuple[int, int, str]] = []
    for unit in doc.get("units", []):
        for b in unit.get("blocks", []):
            bid = b.get("id")
            if not bid or bid in ids:
                raise PatchError(f"block id missing or repeated: {bid!r}")
            ids.add(bid)
            mode = b.get("mode")
            if mode not in ("replace", "area"):
                raise PatchError(f"{bid}: mode must be replace or area")
            if b.get("kind") not in ("code", "data", "free-code"):
                raise PatchError(f"{bid}: kind must be code, data or free-code")
            if mode == "area":
                if area is None:
                    raise PatchError(f"{bid}: area blocks need a top-level area")
                if b.get("kind") == "free-code" or "addr" in b or "section" in b or "stock_sha256" in b:
                    raise PatchError(f"{bid}: an area block has an offset, not an addr, section or stock_sha256")
                off = _int(b.get("offset"), f"{bid} offset")
                n = _int(b.get("len"), f"{bid} len")
                if n <= 0 or off < 0 or off + n > area_size:
                    raise PatchError(f"{bid}: offset outside the mod area")
                area_spans.append((off, off + n, bid))
            else:
                if b.get("section") not in (3, 7):
                    raise PatchError(f"{bid}: section must be 3 or 7")
                addr = _int(b.get("addr"), f"{bid} addr")
                n = _int(b.get("len"), f"{bid} len")
                if n <= 0 or addr < LOAD:
                    raise PatchError(f"{bid}: bad address or length")
                if not SHA.match(b.get("stock_sha256", "")):
                    raise PatchError(f"{bid}: stock_sha256 malformed")
                spans.append((addr - LOAD, addr - LOAD + n, bid))
            new = bytearray()
            total = 0
            for p in b.get("new", []):
                if p and p[0] == "hex" and len(p) == 2:
                    if not HEX.match(p[1]):
                        raise PatchError(f"{bid}: hex part is not lowercase hex")
                    new += bytes.fromhex(p[1])
                    total += len(p[1]) // 2
                elif p and p[0] == "stock" and len(p) == 4 and mode == "replace":
                    k = _int(p[2], f"{bid} stock len")
                    if k <= 0:
                        raise PatchError(f"{bid}: empty stock part")
                    total += k
                    new += b"\x00" * k  # placeholder; filled from the stock file at build time
                else:
                    raise PatchError(f"{bid}: unknown part {p!r}")
            if total != n:
                raise PatchError(f"{bid}: parts add to {total}, len is {n}")
            if b.get("new_sha256") and not SHA.match(b["new_sha256"]):
                raise PatchError(f"{bid}: new_sha256 malformed")
            if all(p[0] == "hex" for p in b["new"]) and (mode == "replace" or b.get("new_sha256") is not None):
                if _sha(bytes(new)) != b.get("new_sha256"):
                    raise PatchError(f"{bid}: new_sha256 does not match its bytes")

    for group in (sorted(spans), sorted(area_spans)):
        for (a0, a1, aid), (b0, b1, bid) in zip(group, group[1:]):
            if b0 < a1:
                raise PatchError(f"{aid} and {bid} change the same bytes")
    return [{"id": bid, "start": a, "end": b} for a, b, bid in sorted(spans)]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    try:
        check(json.loads(Path(argv[0]).read_text(encoding="utf-8-sig")))
    except (PatchError, json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"REJECTED: {e}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
