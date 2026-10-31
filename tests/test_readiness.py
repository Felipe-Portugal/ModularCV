"""A package is never READY_TO_SEND when any source of truth objects (fail-closed)."""
import hashlib
import json

import pytest

from modularcv import __main__ as cli
from modularcv import staleness
from modularcv.readiness import BLOCKED, NEEDS_REVIEW, READY, apply, assess, audit_directory

GATES = {"HANDOFF_PASS": True, "CV_PASS": True, "LETTER_PASS": True, "CROSS_ARTIFACT_PASS": True,
         "PDF_PASS": True, "PROVENANCE_PASS": True, "PACKAGE_MANIFEST_PASS": True,
         "CV_QUALITY_REVIEW_PASS": True}
GOOD_SHA = "1" * 40


def make_package(job=1, state=READY, gates=None, fingerprint=None, cv_id=None):
    return {"application": {"job_id": job}, "routing": {"workflow_state": state, "reasons": []},
            "validation": {"gates": dict(gates or GATES)},
            "package_fingerprint": fingerprint or ("f%d" % job) * 8,
            "artifacts": {"cv": {"tailored_cv_id": cv_id or ("cv%d" % job)}}}


def write_registry(path, *entries):
    path.write_text(json.dumps({"registry_version": "StalePackageRegistry-v1",
                                "packages": list(entries)}), encoding="utf-8")
    return path


def entry(package, status="STALE"):
    return {"job_id": package["application"]["job_id"], "status": status,
            "package_fingerprint": package["package_fingerprint"],
            "tailored_cv_id": package["artifacts"]["cv"]["tailored_cv_id"]}


@pytest.fixture
def registry(tmp_path):
    return write_registry(tmp_path / "package-staleness.json")


def test_a_clean_package_is_ready(registry):
    assert assess(make_package(), {"source_commit": GOOD_SHA}, registry) == {
        "status": READY, "reasons": [], "warnings": []}


def test_a_missing_registry_is_an_empty_registry(tmp_path):
    assert assess(make_package(), None, tmp_path / "absent.json")["status"] == READY


def test_a_stale_fingerprint_blocks_even_if_everything_else_passes(tmp_path):
    package = make_package()
    path = write_registry(tmp_path / "r.json", entry(package))
    verdict = assess(package, {"source_commit": GOOD_SHA}, path)
    assert verdict["status"] == BLOCKED and "PACKAGE_STALE" in verdict["reasons"]


def test_a_stale_cv_identity_blocks_a_package_with_a_new_fingerprint(tmp_path):
    old = make_package(fingerprint="a" * 64)
    path = write_registry(tmp_path / "r.json", entry(old))
    assert assess(make_package(fingerprint="b" * 64), None, path)["status"] == BLOCKED


def test_another_job_that_is_stale_does_not_block_this_one(tmp_path):
    path = write_registry(tmp_path / "r.json", entry(make_package(job=2)))
    assert assess(make_package(job=1), None, path)["status"] == READY


def test_a_resolved_registry_entry_does_not_block(tmp_path):
    package = make_package()
    path = write_registry(tmp_path / "r.json", entry(package, status="RESOLVED"))
    assert assess(package, None, path)["status"] == READY


@pytest.mark.parametrize("state", [NEEDS_REVIEW, BLOCKED, "APPLIED", None])
def test_only_a_declared_ready_package_can_be_ready(registry, state):
    assert assess(make_package(state=state), None, registry)["status"] != READY


@pytest.mark.parametrize("gate", sorted(GATES))
def test_every_failed_gate_prevents_readiness(registry, gate):
    verdict = assess(make_package(gates=dict(GATES, **{gate: False})), None, registry)
    assert verdict["status"] != READY and gate in verdict["reasons"]


def test_an_unreadable_registry_fails_closed(tmp_path):
    path = tmp_path / "r.json"
    path.write_text("{ not json", encoding="utf-8")
    verdict = assess(make_package(), None, path)
    assert verdict["status"] == BLOCKED and verdict["reasons"] == ["STALENESS_REGISTRY_UNREADABLE"]


def test_a_registry_without_a_package_list_fails_closed(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"registry_version": "x"}), encoding="utf-8")
    assert assess(make_package(), None, path)["status"] == BLOCKED


@pytest.mark.parametrize("value", [None, "", "abc", "G" * 40, "1" * 41, 7])
def test_invalid_cv_metadata_blocks(registry, value):
    verdict = assess(make_package(), {"source_commit": value}, registry)
    assert verdict["status"] == BLOCKED and "CV_METADATA_INVALID" in verdict["reasons"]


def test_a_legacy_zero_placeholder_is_reported_not_repaired(registry):
    metadata = {"source_commit": "0" * 40}
    verdict = assess(make_package(), metadata, registry)
    assert verdict["status"] == READY and verdict["warnings"] == ["SOURCE_COMMIT_PLACEHOLDER_LEGACY"]
    assert metadata == {"source_commit": "0" * 40}


def test_a_malformed_package_is_blocked(registry):
    assert assess({"routing": {}}, None, registry)["status"] == BLOCKED
    assert assess(None, None, registry)["status"] == BLOCKED


def test_apply_downgrades_a_stale_package_and_records_why(tmp_path):
    package = make_package()
    apply(package, None, write_registry(tmp_path / "r.json", entry(package)))
    assert package["routing"]["workflow_state"] == BLOCKED
    assert "PACKAGE_STALE" in package["routing"]["reasons"]


def test_apply_never_upgrades_a_package(registry):
    review = make_package(state=NEEDS_REVIEW)
    apply(review, {"source_commit": GOOD_SHA}, registry)
    assert review["routing"]["workflow_state"] == NEEDS_REVIEW
    blocked = make_package(state=BLOCKED)
    apply(blocked, {"source_commit": GOOD_SHA}, registry)
    assert blocked["routing"]["workflow_state"] == BLOCKED


def make_directory(tmp_path, packages, stale_entries=()):
    root = tmp_path / "packages"
    rows = []
    for package in packages:
        folder = root / ("%s-co" % package["application"]["job_id"])
        folder.mkdir(parents=True)
        (folder / "package.json").write_text(json.dumps(package), encoding="utf-8")
        rows.append({"job_id": package["application"]["job_id"], "status": READY,
                     "package_fingerprint": package["package_fingerprint"]})
    (root / "application-index.json").write_text(json.dumps({"applications": rows}),
                                                 encoding="utf-8")
    write_registry(root / "package-staleness.json", *stale_entries)
    return root


def test_the_audit_flags_an_index_that_says_ready_for_a_stale_package(tmp_path):
    good, bad = make_package(job=1), make_package(job=2)
    report = audit_directory(make_directory(tmp_path, [good, bad], [entry(bad)]))
    assert {p["job_id"]: p["status"] for p in report["packages"]} == {1: READY, 2: BLOCKED}
    assert report["ready"] == ["1-co"]
    assert report["contradictions"][0]["kind"] == "INDEX_READY_BUT_NOT_EFFECTIVELY_READY"


def test_the_audit_is_clean_when_everything_agrees(tmp_path):
    assert audit_directory(make_directory(tmp_path, [make_package(job=1)]))["contradictions"] == []


def test_the_audit_reports_an_unreadable_package(tmp_path):
    root = make_directory(tmp_path, [make_package(job=1)])
    (root / "1-co" / "package.json").write_text("{", encoding="utf-8")
    report = audit_directory(root)
    assert report["packages"][0]["status"] == BLOCKED and report["ready"] == []


def test_the_audit_never_writes(tmp_path):
    bad = make_package(job=2)
    root = make_directory(tmp_path, [bad], [entry(bad)])
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    audit_directory(root)
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in root.rglob("*") if p.is_file()}


def test_the_check_command_fails_with_a_non_zero_exit_code_on_contradiction(tmp_path, capsys):
    bad = make_package(job=2)
    root = make_directory(tmp_path, [bad], [entry(bad)])
    assert cli.main(["check-packages", str(root)]) == 1
    assert json.loads(capsys.readouterr().out)["contradictions"][0]["job_id"] == 2


def test_marking_a_package_stale_blocks_it(tmp_path):
    package = make_package()
    path = tmp_path / "reg" / "package-staleness.json"
    staleness.mark(package, "recalibrated", "cv-new", path)
    assert assess(package, None, path)["status"] == BLOCKED
