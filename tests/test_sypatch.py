"""Structural tests for tools/sypatch/check_patch.py. Synthetic data only; no firmware."""

import copy
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "sypatch"))
import check_patch as cp  # noqa: E402

STOCK = cp.STOCK_SHA256
NEW = bytes.fromhex("4eb94010b0004e71")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def base():
    return {
        "format": "synthack-patchset", "schema": 1, "id": "demo", "encoding": "lowercase-hex",
        "target": {"device": "Syntakt", "os": "1.41", "stock_sha256": STOCK},
        "units": [{"id": "demo", "title": "Demo", "blocks": [
            {"id": "hook", "mode": "replace", "section": 3, "addr": "0x4010A100", "len": 8,
             "kind": "code", "stock_sha256": _sha(b"\x11" * 8),
             "new": [["hex", NEW.hex()]], "new_sha256": _sha(NEW), "why": "synthetic"},
        ]}],
    }


def test_valid_passes():
    assert cp.check(base())[0]["id"] == "hook"


def test_wrong_os_hash_refused():
    d = base()
    d["target"]["stock_sha256"] = "00" * 32
    with pytest.raises(cp.PatchError, match="stock_sha256"):
        cp.check(d)


def test_wrong_os_name_refused():
    d = base()
    d["target"]["os"] = "1.42"
    with pytest.raises(cp.PatchError, match="OS 1.41"):
        cp.check(d)


def test_length_must_match_parts():
    d = base()
    d["units"][0]["blocks"][0]["len"] = 6
    with pytest.raises(cp.PatchError, match="parts add to 8"):
        cp.check(d)


def test_uppercase_hex_refused():
    d = base()
    d["units"][0]["blocks"][0]["new"] = [["hex", NEW.hex().upper()]]
    with pytest.raises(cp.PatchError, match="lowercase"):
        cp.check(d)


def test_new_sha_mismatch_refused():
    d = base()
    d["units"][0]["blocks"][0]["new_sha256"] = "ab" * 32
    with pytest.raises(cp.PatchError, match="new_sha256"):
        cp.check(d)


def test_overlap_refused():
    d = base()
    second = copy.deepcopy(d["units"][0]["blocks"][0])
    second["id"] = "other"
    second["addr"] = "0x4010A104"
    d["units"][0]["blocks"].append(second)
    with pytest.raises(cp.PatchError, match="same bytes"):
        cp.check(d)


def test_adjacent_blocks_allowed():
    d = base()
    second = copy.deepcopy(d["units"][0]["blocks"][0])
    second["id"] = "next"
    second["addr"] = "0x4010A108"
    d["units"][0]["blocks"].append(second)
    assert len(cp.check(d)) == 2


def test_duplicate_id_refused():
    d = base()
    d["units"][0]["blocks"].append(copy.deepcopy(d["units"][0]["blocks"][0]))
    with pytest.raises(cp.PatchError, match="repeated"):
        cp.check(d)


def test_stock_part_counts_toward_length():
    d = base()
    b = d["units"][0]["blocks"][0]
    b["new"] = [["hex", "4eb94010b000"], ["stock", "0x4010A100", "2", _sha(b"\x22\x22")]]
    b["new_sha256"] = None
    b.pop("new_sha256")
    assert cp.check(d)[0]["end"] - cp.check(d)[0]["start"] == 8


AREA = {"img": "0x40348000", "ram": "0x46000000", "size": "0x10000", "compress": "shlz"}


def with_area(*blocks):
    d = base()
    d["area"] = dict(AREA)
    d["units"][0]["blocks"] = list(blocks)
    return d


def area_block(bid, offset, data, kind="code"):
    return {"id": bid, "mode": "area", "offset": offset, "len": len(data), "kind": kind,
            "new": [["hex", data.hex()]], "new_sha256": _sha(data), "why": "synthetic"}


def test_area_block_valid():
    d = with_area(area_block("code", "0x4000", NEW), area_block("data", "0x4008", b"\x01\x02"))
    d["units"][0]["blocks"].insert(0, base()["units"][0]["blocks"][0])
    assert [s["id"] for s in cp.check(d)] == ["hook"]


def test_area_block_out_of_bounds_refused():
    with pytest.raises(cp.PatchError, match="outside the mod area"):
        cp.check(with_area(area_block("code", "0xFFFC", NEW)))


def test_area_overlap_refused():
    with pytest.raises(cp.PatchError, match="same bytes"):
        cp.check(with_area(area_block("a", "0x4000", NEW), area_block("b", "0x4004", NEW)))


def test_area_needs_layout():
    d = with_area(area_block("code", "0x4000", NEW))
    del d["area"]
    with pytest.raises(cp.PatchError, match="top-level area"):
        cp.check(d)


def test_area_refuses_stock_part():
    b = area_block("code", "0x4000", NEW)
    b["new"] = [["stock", "0x4010A100", "4", _sha(b"\x22" * 4)]]
    with pytest.raises(cp.PatchError, match="unknown part"):
        cp.check(with_area(b))


def test_free_code_kind_on_replace_accepted():
    d = base()
    d["units"][0]["blocks"][0]["kind"] = "free-code"
    assert cp.check(d)[0]["id"] == "hook"


def test_missing_id_refused():
    d = base()
    del d["id"]
    with pytest.raises(cp.PatchError, match="id must be"):
        cp.check(d)


def test_bad_id_refused():
    d = base()
    d["id"] = "Not Valid+"
    with pytest.raises(cp.PatchError, match="id must be"):
        cp.check(d)


def test_requires_accepted_as_list_of_ids():
    d = base()
    d["requires"] = ["delay-control-core", "modarea"]
    assert cp.check(d)[0]["id"] == "hook"


def test_requires_must_be_a_list_of_strings():
    d = base()
    d["requires"] = "modarea"
    with pytest.raises(cp.PatchError, match="requires must be a list"):
        cp.check(d)
    d["requires"] = ["modarea", 3]
    with pytest.raises(cp.PatchError, match="requires must be a list"):
        cp.check(d)


def test_self_requirement_refused():
    d = base()
    d["requires"] = ["demo"]
    with pytest.raises(cp.PatchError, match="cannot require itself"):
        cp.check(d)


def test_shipped_v2o_reference_passes():
    path = Path(__file__).resolve().parents[1] / "web" / "patches" / "delay-control.sypatch.json"
    import json
    assert cp.check(json.loads(path.read_text(encoding="utf-8")))


def test_area_change_without_new_sha_accepted():
    b = area_block("code", "0x4000", NEW)
    del b["new_sha256"]
    assert [s["id"] for s in cp.check(with_area(b))] == []


def test_area_change_with_wrong_new_sha_refused():
    b = area_block("code", "0x4000", NEW)
    b["new_sha256"] = "ab" * 32
    with pytest.raises(cp.PatchError, match="new_sha256"):
        cp.check(with_area(b))


def with_info(info):
    d = base()
    d["info"] = info
    return d


GOOD_INFO = {
    "summary": "Freeze and beat repeat on the FX track.",
    "claims": ["ui:TRIG 13-16 on the FX track"],
    "conflicts": ["modarea"],
    "cost": {"instructionsPerBlock": 420, "measured": "emulator, 2026-11-01, one beat"},
}


def test_info_absent_and_good_info_pass():
    assert cp.check(base())[0]["id"] == "hook"
    assert cp.check(with_info(GOOD_INFO))[0]["id"] == "hook"


def test_info_cost_null_passes():
    assert cp.check(with_info({"summary": "x", "cost": None}))[0]["id"] == "hook"


def test_info_summary_limit_is_200_characters():
    assert cp.check(with_info({"summary": "x" * 200}))[0]["id"] == "hook"
    with pytest.raises(cp.PatchError, match="200 characters"):
        cp.check(with_info({"summary": "x" * 201}))
    with pytest.raises(cp.PatchError, match="summary"):
        cp.check(with_info({"summary": 5}))


def test_info_claims_must_be_a_list_of_text():
    with pytest.raises(cp.PatchError, match="claims"):
        cp.check(with_info({"claims": "ui:x"}))
    with pytest.raises(cp.PatchError, match="claims"):
        cp.check(with_info({"claims": ["ui:x", 3]}))


def test_info_conflicts_must_be_package_ids():
    with pytest.raises(cp.PatchError, match="conflicts"):
        cp.check(with_info({"conflicts": "modarea"}))
    with pytest.raises(cp.PatchError, match="conflicts"):
        cp.check(with_info({"conflicts": ["Not Valid+"]}))


def test_info_cannot_conflict_with_itself():
    with pytest.raises(cp.PatchError, match="itself"):
        cp.check(with_info({"conflicts": ["demo"]}))


def test_info_cost_checks():
    with pytest.raises(cp.PatchError, match="cost must be null or an object"):
        cp.check(with_info({"cost": 420}))
    with pytest.raises(cp.PatchError, match="instructionsPerBlock"):
        cp.check(with_info({"cost": {"instructionsPerBlock": -1, "measured": "x"}}))
    with pytest.raises(cp.PatchError, match="instructionsPerBlock"):
        cp.check(with_info({"cost": {"instructionsPerBlock": True, "measured": "x"}}))
    with pytest.raises(cp.PatchError, match="instructionsPerBlock"):
        cp.check(with_info({"cost": {"instructionsPerBlock": "420", "measured": "x"}}))
    with pytest.raises(cp.PatchError, match="measured"):
        cp.check(with_info({"cost": {"instructionsPerBlock": 420}}))


def test_info_must_be_an_object():
    with pytest.raises(cp.PatchError, match="info must be an object"):
        cp.check(with_info(None))
    with pytest.raises(cp.PatchError, match="info must be an object"):
        cp.check(with_info(["summary"]))
