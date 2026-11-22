"""Tests for tools/modsdk (the mod SDK). Synthetic data only; no firmware and no OS file.

Tests that need the WSL m68k toolchain are skipped when it is not there.
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "modsdk"))
import modsdk  # noqa: E402
import check_patch as cp  # noqa: E402

TOOL_OK, TOOL_WHY = modsdk.toolchain_status()
needs_toolchain = pytest.mark.skipif(
    not TOOL_OK, reason=f"no WSL m68k toolchain, so the C code cannot be built: {TOOL_WHY}")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node.js is not installed, so the page check cannot run")

BASE = {
    "id": "demo-mod", "title": "Demo", "version": "0.1", "author": "test",
    "target": {"device": "Syntakt", "os": "1.41"}, "requires": [], "sources": ["main.c"],
    "entry": "demo_entry", "slot": "dev", "hooks": [],
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "mod"
    folder.mkdir()
    (folder / "main.c").write_text("int demo_entry(void) { return 0; }\n", encoding="utf-8")
    return folder


def hook(**kw) -> dict:
    h = {"id": "demo-hook", "addr": "0x400004b2", "len": 8, "stock_sha256": _sha(b"\x11" * 8),
         "call": "demo_entry", "why": "test hook"}
    h.update(kw)
    return h


def synthetic_doc(tmp_path: Path) -> tuple[dict, dict]:
    folder = write_folder(tmp_path)
    info = modsdk.validate_info({**BASE, "hooks": [hook()]}, folder)
    blob = bytes.fromhex("4e754e75") + bytes.fromhex("0102")
    doc = modsdk.make_package(info, blob, 4, 0x2000, {"demo_entry": 0x46002000})
    return info, doc


def write_doc(path: Path, doc: dict) -> Path:
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return path


def test_mod_json_with_a_byte_order_mark_is_read(tmp_path):
    folder = write_folder(tmp_path)
    (folder / "mod.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(BASE).encode("utf-8"))
    assert modsdk.read_info(folder)["id"] == BASE["id"]


def test_package_file_with_a_byte_order_mark_passes_the_python_check(tmp_path, capsys):
    _, doc = synthetic_doc(tmp_path)
    path = tmp_path / "bom.sypatch.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(doc).encode("utf-8"))
    assert cp.main([str(path)]) == 0


def test_missing_field_error_is_plain(tmp_path):
    info = dict(BASE)
    del info["title"]
    with pytest.raises(modsdk.ModError, match='missing the field "title"'):
        modsdk.validate_info(info, write_folder(tmp_path))


def test_unknown_field_refused(tmp_path):
    with pytest.raises(modsdk.ModError, match='unknown field "titel"'):
        modsdk.validate_info({**BASE, "titel": "typo"}, write_folder(tmp_path))


def test_bad_id_refused(tmp_path):
    with pytest.raises(modsdk.ModError, match="lowercase letters, digits and hyphens"):
        modsdk.validate_info({**BASE, "id": "Bad_Id"}, write_folder(tmp_path))


def test_odd_hook_len_refused(tmp_path):
    with pytest.raises(modsdk.ModError, match="even number"):
        modsdk.validate_info({**BASE, "hooks": [hook(len=7)]}, write_folder(tmp_path))


def test_short_hook_len_refused(tmp_path):
    with pytest.raises(modsdk.ModError, match="at least 6 bytes"):
        modsdk.validate_info({**BASE, "hooks": [hook(len=4)]}, write_folder(tmp_path))


def test_missing_stock_sha256_refused(tmp_path):
    h = hook()
    del h["stock_sha256"]
    with pytest.raises(modsdk.ModError, match="stock_sha256"):
        modsdk.validate_info({**BASE, "hooks": [h]}, write_folder(tmp_path))


def test_hook_defaults_section_three(tmp_path):
    info = modsdk.validate_info({**BASE, "hooks": [hook()]}, write_folder(tmp_path))
    assert info["hooks"][0]["section"] == 3


def test_hook_bytes_are_jmp_then_nops():
    assert modsdk.hook_bytes(0x46002004, 6).hex() == "4ef946002004"
    assert modsdk.hook_bytes(0x46002004, 8).hex() == "4ef946002004" + "4e71"
    assert modsdk.hook_bytes(0x46002004, 10).hex() == "4ef946002004" + "4e71" * 2


def test_slot_overflow_refused():
    with pytest.raises(modsdk.ModError, match="holds 32 bytes"):
        modsdk.check_fit(64, "dev", 0x2000, 0x2020)


def test_slot_fit_accepted():
    modsdk.check_fit(32, "dev", 0x2000, 0x2020)


def test_slot_overlap_refused():
    slots = modsdk.load_slots()
    slots["registered"] = {"clash": {"start": "0x3f00", "end": "0x4100", "owner": "other"}}
    with pytest.raises(modsdk.ModError, match="overlaps"):
        modsdk.check_slot_table(slots)


def test_shipped_slot_table_is_clean():
    modsdk.check_slot_table(modsdk.load_slots())


def test_registered_slot_must_belong_to_the_mod(tmp_path):
    slots = modsdk.load_slots()
    slots["registered"] = {"fx-one": {"start": "0x8000", "end": "0x8100", "owner": "someone-else"}}
    info = modsdk.validate_info({**BASE, "slot": "fx-one"}, write_folder(tmp_path))
    with pytest.raises(modsdk.ModError, match="belongs to the mod"):
        modsdk.slot_span(info, slots)


def test_package_shape_and_hook_bytes(tmp_path):
    _, doc = synthetic_doc(tmp_path)
    assert doc["requires"] == ["modarea"]
    assert doc["area"]["img"] == "0x40348000"
    code, data, hook_block = doc["units"][0]["blocks"]
    assert code["id"] == "demo-mod-code" and code["offset"] == 0x2000 and code["kind"] == "code"
    assert data["id"] == "demo-mod-data" and data["offset"] == 0x2004 and data["kind"] == "data"
    assert hook_block["id"] == "demo-hook" and hook_block["addr"] == "0x400004b2"
    assert hook_block["new"] == [["hex", "4ef946002000" + "4e71"]]


def test_package_passes_python_checks(tmp_path):
    _, doc = synthetic_doc(tmp_path)
    cp.check(doc)


def test_tampered_new_sha_is_refused_in_plain_words(tmp_path, capsys):
    _, doc = synthetic_doc(tmp_path)
    doc["units"][0]["blocks"][0]["new_sha256"] = "ab" * 32
    path = write_doc(tmp_path / "demo-mod.sypatch.json", doc)
    assert modsdk.main(["check", str(path)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ")
    assert "new_sha256" in out
    assert "Traceback" not in out


@needs_node
def test_page_check_accepts_a_valid_package(tmp_path):
    _, doc = synthetic_doc(tmp_path)
    path = write_doc(tmp_path / "demo-mod.sypatch.json", doc)
    assert modsdk.check_package(path) == "ok"


def test_fingerprint_refuses_a_file_that_is_not_os_141(tmp_path):
    fake = tmp_path / "not-the-os.bin"
    fake.write_bytes(b"this is not the firmware")
    with pytest.raises(modsdk.ModError, match="not the Syntakt OS 1.41 file"):
        modsdk.fingerprint(fake, 0x400004B2, 8)


def test_init_makes_a_valid_folder_and_refuses_a_second_time(tmp_path):
    folder = modsdk.init_mod("my-test", tmp_path)
    info = modsdk.validate_info(modsdk.read_info(folder), folder)
    assert info["id"] == "my-test" and info["slot"] == "dev"
    with pytest.raises(modsdk.ModError, match="already exists"):
        modsdk.init_mod("my-test", tmp_path)


def test_init_refuses_a_bad_id(tmp_path):
    with pytest.raises(modsdk.ModError, match="lowercase letters"):
        modsdk.init_mod("Bad Id", tmp_path)


INFO_OK = {"summary": "A demo.", "claims": ["ui:TRIG 13-16 on the FX track"], "conflicts": ["other-mod"],
           "cost": {"instructionsPerBlock": 420, "measured": "emulator, test"}}


def test_info_block_is_copied_into_the_package(tmp_path):
    info = modsdk.validate_info({**BASE, "info": INFO_OK}, write_folder(tmp_path))
    doc = modsdk.make_package(info, bytes.fromhex("4e754e75"), 4, 0x2000, {})
    assert doc["info"] == INFO_OK
    cp.check(doc)


def test_info_block_is_optional(tmp_path):
    info = modsdk.validate_info(dict(BASE), write_folder(tmp_path))
    doc = modsdk.make_package(info, bytes.fromhex("4e754e75"), 4, 0x2000, {})
    assert "info" not in doc
    cp.check(doc)


def test_info_cost_null_is_allowed(tmp_path):
    info = modsdk.validate_info({**BASE, "info": {**INFO_OK, "cost": None}}, write_folder(tmp_path))
    assert info["info"]["cost"] is None


@pytest.mark.parametrize("notes, text", [
    ({"summary": 5}, "summary must be one sentence of text"),
    ({"summary": "x" * 201}, "200 characters or fewer"),
    ({"claims": "ui:x"}, "claims must be a list of text"),
    ({"claims": ["TRIG 13-16 on the FX track"]}, "must start with ui:, param: or audio:"),
    ({"claims": ["ui:"]}, "must start with ui:, param: or audio:"),
    ({"conflicts": ["Bad Id"]}, "conflicts must be a list of package ids"),
    ({"conflicts": ["demo-mod"]}, "cannot list this mod itself"),
    ({"cost": 300}, 'cost must be null'),
    ({"cost": {"instructionsPerBlock": -1, "measured": "x"}}, "whole number, 0 or more"),
    ({"cost": {"instructionsPerBlock": True, "measured": "x"}}, "whole number, 0 or more"),
    ({"cost": {"instructionsPerBlock": 300}}, '"measured" must be text'),
    ({"cost": {"instructionsPerBlock": 1, "measured": "x", "extra": 1}}, 'unknown field "extra"'),
    ({"colour": "red"}, 'unknown field "colour"'),
])
def test_info_bad_fields_are_refused_in_plain_words(tmp_path, notes, text):
    with pytest.raises(modsdk.ModError, match=text):
        modsdk.validate_info({**BASE, "info": notes}, write_folder(tmp_path))


@pytest.mark.parametrize("notes", [None, [], "a note"])
def test_info_that_is_not_one_object_is_refused(tmp_path, notes):
    with pytest.raises(modsdk.ModError, match='"info" must be one object'):
        modsdk.validate_info({**BASE, "info": notes}, write_folder(tmp_path))


def test_hello_sdk_info_block_is_valid():
    info = modsdk.validate_info(modsdk.read_info(ROOT / "mods" / "hello-sdk"), ROOT / "mods" / "hello-sdk")
    assert info["info"]["summary"] and info["info"]["cost"] is None


def test_init_template_info_block_is_valid(tmp_path):
    folder = modsdk.init_mod("info-check", tmp_path)
    info = modsdk.validate_info(modsdk.read_info(folder), folder)
    assert set(info["info"]) == {"summary", "claims", "conflicts", "cost"}


def test_check_refuses_a_json_list_in_plain_words(tmp_path, capsys):
    path = tmp_path / "list.sypatch.json"
    path.write_text("[]", encoding="utf-8")
    assert modsdk.main(["check", str(path)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "Traceback" not in out


def test_check_refuses_a_file_that_is_not_utf8_in_plain_words(tmp_path, capsys):
    path = tmp_path / "bytes.sypatch.json"
    path.write_bytes(b"\xff\xfe{}")
    assert modsdk.main(["check", str(path)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and "UTF-8" in out and "Traceback" not in out


def test_mod_json_that_is_not_utf8_is_refused_in_plain_words(tmp_path):
    folder = write_folder(tmp_path)
    (folder / "mod.json").write_bytes(b'{"id": "\xff"}')
    with pytest.raises(modsdk.ModError, match="UTF-8"):
        modsdk.read_info(folder)


TAKEN_SYNTH = [{"package": "synthetic-core", "addr": "0x400004b0", "len": 8,
                "area": "synthetic delay", "why": "synthetic test entry"}]


def _fake_build(monkeypatch):
    monkeypatch.setattr(modsdk, "toolchain_status", lambda: (True, ""))
    monkeypatch.setattr(modsdk, "build_code", lambda *a, **k: {
        "blob": bytes.fromhex("4e754e75"), "text": 4,
        "syms": {"demo_entry": (0x46002000, "T")}, "funcs": {"demo_entry"}})
    monkeypatch.setattr(modsdk, "load_taken", lambda: TAKEN_SYNTH)


def test_hook_on_a_taken_address_warns(tmp_path):
    warnings = modsdk.check_taken([{"id": "demo-hook", "addr": "0x400004b2", "len": 8}], TAKEN_SYNTH)
    assert len(warnings) == 1
    assert warnings[0] == ('hook "demo-hook" lands on synthetic delay, already hooked by synthetic-core. '
                           "Read builder-web\\docs\\SDK.md before you go on.")


def test_hook_elsewhere_does_not_warn(tmp_path):
    assert modsdk.check_taken([{"id": "demo-hook", "addr": "0x40001000", "len": 8}], TAKEN_SYNTH) == []


def test_hook_touching_only_the_edge_of_a_taken_range_does_not_warn():
    assert modsdk.check_taken([{"id": "demo-hook", "addr": "0x400004b8", "len": 6}], TAKEN_SYNTH) == []


def test_build_prints_the_clash_as_a_warning_and_still_succeeds(tmp_path, monkeypatch, capsys):
    _fake_build(monkeypatch)
    folder = write_folder(tmp_path)
    (folder / "mod.json").write_text(json.dumps({**BASE, "hooks": [hook()]}), encoding="utf-8")
    assert modsdk.main(["build", str(folder), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "Warning: hook \"demo-hook\" lands on synthetic delay" in out
    assert (tmp_path / "out" / "demo-mod.sypatch.json").is_file()


def test_strict_turns_the_clash_into_a_failure(tmp_path, monkeypatch, capsys):
    _fake_build(monkeypatch)
    folder = write_folder(tmp_path)
    (folder / "mod.json").write_text(json.dumps({**BASE, "hooks": [hook()]}), encoding="utf-8")
    assert modsdk.main(["build", str(folder), "--out", str(tmp_path / "out"), "--strict"]) == 1
    captured = capsys.readouterr()
    assert "already hooked by synthetic-core" in captured.err
    assert not (tmp_path / "out" / "demo-mod.sypatch.json").exists()


def test_taken_json_loads_and_every_entry_is_complete():
    data = json.loads((ROOT / "tools" / "modsdk" / "taken.json").read_text(encoding="utf-8"))
    assert data["note"] and isinstance(data["taken"], list) and data["taken"]
    for entry in data["taken"]:
        for key in ("addr", "len", "package", "area", "why"):
            assert key in entry, f"{entry} has no {key}"
        assert int(entry["addr"], 0) >= 0x40000400 and entry["len"] > 0


@needs_toolchain
def test_hello_sdk_info_reaches_the_built_package(tmp_path):
    path, _ = modsdk.build_mod(ROOT / "mods" / "hello-sdk", tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["info"] == modsdk.read_info(ROOT / "mods" / "hello-sdk")["info"]


@needs_toolchain
def test_hello_sdk_builds_twice_to_identical_bytes(tmp_path):
    a, s = modsdk.build_mod(ROOT / "mods" / "hello-sdk", tmp_path / "a")
    b, _ = modsdk.build_mod(ROOT / "mods" / "hello-sdk", tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()
    assert s["data"] > 0 and s["code"] > 0


@needs_toolchain
def test_hello_sdk_output_passes_check(tmp_path):
    path, _ = modsdk.build_mod(ROOT / "mods" / "hello-sdk", tmp_path)
    cp.check(json.loads(path.read_text(encoding="utf-8")))
    assert modsdk.check_package(path) in ("ok", "skipped")


# ---------------------------------------------------------------- hook kind (jmp or jsr)

def test_hook_without_kind_is_still_a_jump(tmp_path):
    info = modsdk.validate_info({**BASE, "hooks": [hook()]}, write_folder(tmp_path))
    assert info["hooks"][0]["kind"] == "jmp"
    doc = modsdk.make_package(info, bytes.fromhex("4e754e75"), 4, 0x2000, {"demo_entry": 0x46002000})
    assert doc["units"][0]["blocks"][-1]["new"] == [["hex", "4ef946002000" + "4e71"]]
    assert modsdk.hook_bytes(0x46002000, 8, "jmp") == modsdk.hook_bytes(0x46002000, 8)


def test_jsr_hook_bytes_are_call_then_nops():
    assert modsdk.hook_bytes(0x46002004, 6, "jsr").hex() == "4eb946002004"
    assert modsdk.hook_bytes(0x46002004, 8, "jsr").hex() == "4eb946002004" + "4e71"


def test_jsr_hook_writes_the_call_opcode_into_the_package(tmp_path):
    info = modsdk.validate_info({**BASE, "hooks": [hook(kind="jsr")]}, write_folder(tmp_path))
    doc = modsdk.make_package(info, bytes.fromhex("4e754e75"), 4, 0x2000, {"demo_entry": 0x46002000})
    assert doc["units"][0]["blocks"][-1]["new"] == [["hex", "4eb946002000" + "4e71"]]
    cp.check(doc)


def test_unknown_hook_kind_refused(tmp_path):
    with pytest.raises(modsdk.ModError, match='"kind" must be "jmp"'):
        modsdk.validate_info({**BASE, "hooks": [hook(kind="bsr")]}, write_folder(tmp_path))


# ---------------------------------------------------------------- defines

def test_defines_are_passed_to_the_compiler(tmp_path, monkeypatch):
    folder = write_folder(tmp_path)
    (folder / "mod.json").write_text(json.dumps({**BASE, "defines": ["MOD_BASE=0x4000", "DEBUG"]}), encoding="utf-8")
    commands = []

    def stop_at_the_compiler(cmd):
        commands.append(cmd)
        raise modsdk.ModError("stopped in the test")

    monkeypatch.setattr(modsdk, "toolchain_status", lambda: (True, ""))
    monkeypatch.setattr(modsdk, "wsl", stop_at_the_compiler)
    with pytest.raises(modsdk.ModError, match="stopped in the test"):
        modsdk.build_mod(folder, tmp_path / "out")
    assert "-c main.c" in commands[0]
    assert " -DMOD_BASE=0x4000 -DDEBUG " in commands[0]


@pytest.mark.parametrize("define", ["1ABC", "A B", 'A="x"', "A=1;rm", "A=", "=1", "A-B", "A=1 2", 3])
def test_bad_define_refused(tmp_path, define):
    with pytest.raises(modsdk.ModError, match="must be NAME or NAME=VALUE"):
        modsdk.validate_info({**BASE, "defines": [define]}, write_folder(tmp_path))


def test_defines_must_be_a_list(tmp_path):
    with pytest.raises(modsdk.ModError, match='"defines" must be a list'):
        modsdk.validate_info({**BASE, "defines": "DEBUG"}, write_folder(tmp_path))


# ---------------------------------------------------------------- edits

def edit(**kw) -> dict:
    e = {"id": "demo-edit", "addr": "0x400004c0", "len": 2, "stock_sha256": _sha(b"\x22\x22"),
         "hex": "00ff", "why": "test edit"}
    e.update(kw)
    return e


def test_edit_becomes_a_replace_change(tmp_path):
    info = modsdk.validate_info({**BASE, "edits": [edit()]}, write_folder(tmp_path))
    doc = modsdk.make_package(info, bytes.fromhex("4e754e75"), 4, 0x2000, {})
    block = doc["units"][0]["blocks"][-1]
    assert block["id"] == "demo-edit" and block["mode"] == "replace" and block["section"] == 3
    assert block["addr"] == "0x400004c0" and block["len"] == 2 and block["kind"] == "data"
    assert block["new"] == [["hex", "00ff"]]
    assert block["new_sha256"] == _sha(bytes.fromhex("00ff"))
    cp.check(doc)


@pytest.mark.parametrize("new, text", [
    ("00ff00", "holds 3 bytes, but"),
    ("00zz", "lowercase hex"),
    ("00FF", "lowercase hex"),
    ("00 ff", "lowercase hex"),
    ("0", "lowercase hex"),
])
def test_edit_wrong_hex_refused(tmp_path, new, text):
    with pytest.raises(modsdk.ModError, match=text):
        modsdk.validate_info({**BASE, "edits": [edit(hex=new)]}, write_folder(tmp_path))


@pytest.mark.parametrize("length, text", [(1, "at least 2 bytes"), (3, "even number of bytes")])
def test_edit_bad_length_refused(tmp_path, length, text):
    with pytest.raises(modsdk.ModError, match=text):
        modsdk.validate_info({**BASE, "edits": [edit(len=length, hex="ff" * length)]}, write_folder(tmp_path))


def test_edit_and_hook_with_the_same_id_refused(tmp_path):
    with pytest.raises(modsdk.ModError, match="two hooks or edits have the id"):
        modsdk.validate_info({**BASE, "hooks": [hook(id="same")], "edits": [edit(id="same")]}, write_folder(tmp_path))


def test_edit_overlapping_a_hook_is_refused(tmp_path, monkeypatch):
    _fake_build(monkeypatch)
    folder = write_folder(tmp_path)
    (folder / "mod.json").write_text(json.dumps({**BASE, "hooks": [hook()], "edits": [edit(addr="0x400004b4")]}),
                                     encoding="utf-8")
    with pytest.raises(modsdk.ModError, match="change the same bytes"):
        modsdk.build_mod(folder, tmp_path / "out")


def test_edit_on_a_taken_spot_warns(tmp_path, monkeypatch, capsys):
    _fake_build(monkeypatch)
    folder = write_folder(tmp_path)
    (folder / "mod.json").write_text(json.dumps({**BASE, "edits": [edit(addr="0x400004b0", len=8, hex="0011223344556677")]}),
                                     encoding="utf-8")
    assert modsdk.main(["build", str(folder), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert 'Warning: edit "demo-edit" lands on synthetic delay' in out
