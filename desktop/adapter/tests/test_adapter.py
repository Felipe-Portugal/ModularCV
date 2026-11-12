"""Tests of the Desktop adapter against the real engine, with the public fictional example workspace."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "desktop" / "adapter" / "mcv_adapter.py"
EXAMPLE = REPO / "examples" / "workspace"


def call(**request):
    done = subprocess.run([sys.executable, "-I", str(ADAPTER)], input=json.dumps(request).encode(),
                          capture_output=True, timeout=60, env={"MODULARCV_ENGINE_DIR": str(REPO), "SYSTEMROOT": "C:\\Windows"})
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture()
def ws(tmp_path):
    target = tmp_path / "ws"
    shutil.copytree(EXAMPLE, target)
    return target


def read(ws):
    return call(op="read", root=str(ws))


def fact_payload(state, fact_id, **over):
    fact = next(f for f in state["facts"]["facts"] if f["id"] == fact_id)
    data = {k: fact[k] for k in ("id", "status", "text", "lang", "confirmed_on", "technologies", "capabilities", "source", "supersedes", "note")}
    data.update(over)
    return data


def test_read_example(ws):
    state = read(ws)
    assert state["ok"] and state["facts"]["valid"] and state["profile"]["valid"] and state["content"]["valid"]
    assert len(state["facts"]["facts"]) == 9
    assert {s["id"] for s in state["facts"]["sections"]} >= {"experience", "education", "skills"}
    assert state["profile"]["data"]["identity"]["display_name"]["value"] == "Jordan Example"
    python = state["content"]["skills"][0]["items"][0]
    assert python["supports"] == [{"id": "skill.python", "status": "CONFIRMED"}]


def test_missing_and_unreadable_workspace(tmp_path):
    assert call(op="read", root=str(tmp_path / "nope"))["code"] == "WORKSPACE_MISSING"
    state = read(tmp_path)  # empty folder: no files, no crash, nothing editable
    assert state["ok"] and not state["facts"]["present"]
    assert call(op="save_fact", root=str(tmp_path), expected_sha256="x", mode="update", fact={})["code"] == "FILE_UNREADABLE"


def test_unknown_operation_refused(ws):
    assert call(op="run_shell", root=str(ws))["code"] == "OPERATION_NOT_ALLOWED"


def test_edit_fact_preserves_everything_else(ws):
    before = (ws / "facts.md").read_text(encoding="utf-8")
    state = read(ws)
    payload = fact_payload(state, "exp.junior-dev.speed", text="Improved response time, not measured.")
    done = call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="update", fact=payload)
    assert done["ok"], done
    after = (ws / "facts.md").read_text(encoding="utf-8")
    old_lines, new_lines = before.split("\n"), after.split("\n")
    changed = [n for n, o in zip(old_lines, new_lines) if n != o]
    assert len(changed) == 1 and "not measured" in after
    assert new_lines[:2] == old_lines[:2] and "<!--" in new_lines[1]  # marker and comment block intact
    again = read(ws)
    assert again["facts"]["valid"]
    speed = next(f for f in again["facts"]["facts"] if f["id"] == "exp.junior-dev.speed")
    assert speed["status"] == "NOT_CONFIRMED" and "not measured" in speed["text"]
    # every other fact is unchanged
    others = lambda s: [dict(f, line=0) for f in s["facts"]["facts"] if f["id"] != "exp.junior-dev.speed"]
    assert others(again) == others(state)


def test_confirmed_text_change_needs_explicit_confirmation(ws):
    state = read(ws)
    payload = fact_payload(state, "exp.junior-dev.api", text="Built REST endpoints and a CLI.")
    refused = call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="update", fact=payload)
    assert refused["code"] == "CONFIRMATION_REQUIRED"
    refused = call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="update", fact=payload, confirm=True)
    assert refused["code"] == "CONFIRMATION_REQUIRED"  # a bare flag is not a dated decision
    ok = call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="update",
              fact=payload, confirm={"confirmed_on": "2026-03-01"})
    assert ok["ok"], ok
    assert next(f for f in read(ws)["facts"]["facts"] if f["id"] == "exp.junior-dev.api")["confirmed_on"] == "2026-03-01"


def test_no_automatic_promotion(ws):
    state = read(ws)
    before = (ws / "facts.md").read_bytes()
    for fact_id in ("exp.junior-dev.speed", "exp.junior-dev.lead-v2"):
        payload = fact_payload(state, fact_id, status="CONFIRMED")
        assert call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="update", fact=payload)["code"] == "CONFIRMATION_REQUIRED"
    # a new fact asked as CONFIRMED without confirmation is refused too
    new = {"id": "skill.docker", "status": "CONFIRMED", "text": "Docker basics.", "section": "skills"}
    assert call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="create", fact=new)["code"] == "CONFIRMATION_REQUIRED"
    assert (ws / "facts.md").read_bytes() == before
    # editing the text of a non-confirmed fact never changes its status
    payload = fact_payload(state, "exp.junior-dev.speed", text="Improved response time (unmeasured).")
    assert call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="update", fact=payload)["ok"]
    assert next(f for f in read(ws)["facts"]["facts"] if f["id"] == "exp.junior-dev.speed")["status"] == "NOT_CONFIRMED"


def test_create_fact_in_section(ws):
    state = read(ws)
    new = {"id": "skill.docker", "status": "NOT_CONFIRMED", "text": "Docker basics.", "section": "skills", "technologies": ["Docker"]}
    assert call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="create", fact=new)["ok"]
    after = read(ws)
    docker = next(f for f in after["facts"]["facts"] if f["id"] == "skill.docker")
    assert docker["section"] == "skills" and docker["status"] == "NOT_CONFIRMED" and docker["technologies"] == ["Docker"]
    assert len(after["facts"]["facts"]) == 10
    dup = call(op="save_fact", root=str(ws), expected_sha256=after["facts"]["source_sha256"], mode="create", fact=new)
    assert dup["code"] == "VALIDATION_FAILED"


@pytest.mark.parametrize("override", [
    {"lang": "english"},
    {"confirmed_on": "2026-13-45"},
    {"supersedes": "does.not-exist"},
    {"text": ""},
    {"text": "bad {brace}"},
    {"status": "BOGUS"},
    {"capabilities": ["Not Valid"]},
])
def test_invalid_fact_refused_without_writing(ws, override):
    state = read(ws)
    before = (ws / "facts.md").read_bytes()
    payload = fact_payload(state, "exp.junior-dev.speed", **override)
    result = call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="update", fact=payload)
    assert not result["ok"] and result["code"] in ("VALIDATION_FAILED", "CONFIRMATION_REQUIRED")
    assert (ws / "facts.md").read_bytes() == before
    assert not list(ws.glob(".*.tmp"))


def test_concurrent_modification_refused(ws):
    state = read(ws)
    payload = fact_payload(state, "exp.junior-dev.speed", text="Changed by Desktop.")
    with open(ws / "facts.md", "a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n- [skill.extra] NOT_CONFIRMED: Added elsewhere. {technologies: X}\n")
    external = (ws / "facts.md").read_bytes()
    result = call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="update", fact=payload)
    assert result["code"] == "CONFLICT"
    assert (ws / "facts.md").read_bytes() == external


def test_crlf_file_stays_crlf(ws):
    path = ws / "facts.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    state = read(ws)
    payload = fact_payload(state, "exp.junior-dev.speed", text="Edited under CRLF.")
    assert call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="update", fact=payload)["ok"]
    data = path.read_bytes()
    assert data.count(b"\n") == data.count(b"\r\n") and b"Edited under CRLF" in data


def test_invalid_existing_file_is_not_editable(ws):
    (ws / "facts.md").write_text("<!-- modularcv: FactBase-v1 -->\n\n- [x.y] BOGUS: no section\n", encoding="utf-8")
    state = read(ws)
    assert not state["facts"]["valid"] and state["facts"]["facts"] == []
    result = call(op="save_fact", root=str(ws), expected_sha256=state["facts"]["source_sha256"], mode="create",
                  fact={"id": "a.b", "text": "x", "section": "s"})
    assert result["code"] == "FILE_NOT_EDITABLE"


def test_edit_profile_preserves_other_keys(ws):
    state = read(ws)
    original = json.loads((ws / "profile.json").read_text(encoding="utf-8"))
    changes = {"identity": {"headline": {"value": "Backend engineering student", "visibility": "public"},
                            "phone": {"value": "+1 555 0100", "visibility": "public"}},
               "default_language": "fr", "policy": {"require_confirmation_date": True}}
    done = call(op="save_profile", root=str(ws), expected_sha256=state["profile"]["source_sha256"], changes=changes)
    assert done["ok"], done
    new = json.loads((ws / "profile.json").read_text(encoding="utf-8"))
    assert new["identity"]["headline"]["value"] == "Backend engineering student"
    assert new["identity"]["phone"]["visibility"] == "public"
    assert new["default_language"] == "fr" and new["policy"]["require_confirmation_date"] is True
    for key in ("families", "availability", "taxonomy", "selection", "languages", "schema", "guidance", "precedence_rules"):
        assert new[key] == original[key]
    assert new["policy"]["never_publish_terms"] == original["policy"]["never_publish_terms"]
    assert new["identity"]["links"] == original["identity"]["links"] and new["identity"]["email"] == original["identity"]["email"]
    # downstream: require_confirmation_date now exposes confirmed facts without a date, reported not hidden
    assert any(item["code"] == "FACT_DATE_REQUIRED" or "DATE" in item["code"] for item in done["downstream"]) or done["downstream"] == []


@pytest.mark.parametrize("changes", [
    {"identity": {"email": {"value": "x@example.com", "visibility": "secret"}}},
    {"identity": {"display_name": {"value": "", "visibility": "public"}}},
    {"identity": {"favourite_colour": {"value": "x", "visibility": "public"}}},
    {"default_language": "de"},
    {"policy": {"never_publish_terms": ["hobby project"]}},  # clashes with omit_by_default_terms
    {"families": {}},
    {"policy": {"require_confirmation_date": "yes"}},
])
def test_invalid_profile_changes_refused(ws, changes):
    state = read(ws)
    before = (ws / "profile.json").read_bytes()
    result = call(op="save_profile", root=str(ws), expected_sha256=state["profile"]["source_sha256"], changes=changes)
    assert not result["ok"] and result["code"] == "VALIDATION_FAILED"
    assert (ws / "profile.json").read_bytes() == before


def test_profile_conflict_refused(ws):
    state = read(ws)
    (ws / "profile.json").write_text((ws / "profile.json").read_text(encoding="utf-8").replace("Exampleville", "Elsewhere"), encoding="utf-8")
    result = call(op="save_profile", root=str(ws), expected_sha256=state["profile"]["source_sha256"],
                  changes={"default_language": "fr"})
    assert result["code"] == "CONFLICT"
