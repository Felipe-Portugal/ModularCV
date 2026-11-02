"""A package is never READY_TO_SEND unless verifiable evidence supports it (fail-closed, 0.2.0).

Tests that used to expect READY from a declared state plus a well-formed SHA (the 0.1.0 fail-open
behaviour) now build a real synthetic workspace with `synthetic.Workspace`.
"""
import copy
import json
import os

import pytest

from modularcv import __main__ as cli
from modularcv import canonical, readiness, review, staleness
from modularcv.readiness import BLOCKED, NEEDS_REVIEW, READY, apply, assess, audit_directory
from synthetic import GATES, Workspace, git, tree_hash


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path)


def verdict_of(ws):
    return ws.assess()


def has(verdict, reason, code=None):
    return reason in verdict["reasons"] and (
        code is None or any(d["reason"] == reason and d["code"] == code for d in verdict["details"]))


# --- the one way to be READY ------------------------------------------------------------------------

def test_a_package_with_complete_evidence_is_ready(ws):
    verdict = verdict_of(ws)
    assert verdict["status"] == READY and verdict["reasons"] == [] and verdict["details"] == []
    assert verdict["warnings"] == ["LEGACY_METADATA_SCHEMA_VERSION_2"]


def test_without_a_workspace_nothing_can_be_ready(ws):
    verdict = assess(ws.package, ws.metadata, ws.registry)
    assert verdict["status"] != READY
    assert {"SNAPSHOT_MISSING", "SOURCE_COMMIT_UNVERIFIABLE", "HUMAN_REVIEW_REQUIRED"} <= set(verdict["reasons"])


def test_a_package_that_declares_ready_proves_nothing(tmp_path):
    ws = Workspace(tmp_path)
    (ws.package_dir / "provenance" / "source-snapshot.json").unlink()
    verdict = ws.assess()
    assert ws.package["routing"]["workflow_state"] == READY
    assert verdict["status"] == BLOCKED and has(verdict, "SNAPSHOT_MISSING")


# --- the nine fail-open cases (A to I) ----------------------------------------------------------------

def test_A_absent_metadata(ws):
    assert assess(ws.package, None, ws.registry)["status"] == BLOCKED
    assert has(assess(ws.package, None, ws.registry), "CV_METADATA_MISSING")
    (ws.root / ws.meta_rel).unlink()
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "CV_METADATA_MISSING")


def test_A_snapshot_without_a_metadata_entry(ws):
    ws.write_snapshot([i for i in ws.items() if i[0] != "cv_metadata"])
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "CV_METADATA_MISSING", "SNAPSHOT_ROLE_MISSING")


@pytest.mark.parametrize("value", [None, ""])
def test_B_absent_source_commit(ws, value):
    ws.metadata.pop("source_commit") if value is None else ws.metadata.update(source_commit=value)
    ws.write_metadata()
    ws.write_snapshot()
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "CV_METADATA_INVALID", "SOURCE_COMMIT_MISSING")
    assert has(verdict, "CV_METADATA_INVALID", "METADATA_FIELD_MISSING") or value == ""


@pytest.mark.parametrize("value", ["abc", "G" * 40, "A" * 40, "1" * 41, 7, ["x"]])
def test_B_malformed_source_commit(ws, value):
    ws.metadata["source_commit"] = value
    ws.write_metadata()
    ws.write_snapshot()
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "CV_METADATA_INVALID", "SOURCE_COMMIT_MALFORMED")


@pytest.mark.parametrize("zeros", ["0" * 40, "0" * 64])
def test_C_all_zero_source_commit(ws, zeros):
    ws.metadata["source_commit"] = zeros
    ws.write_metadata()
    ws.write_snapshot()
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW and has(verdict, "SOURCE_COMMIT_PLACEHOLDER_LEGACY")
    assert json.loads((ws.root / ws.meta_rel).read_text(encoding="utf-8"))["source_commit"] == zeros


def test_D_well_formed_but_unknown_sha(ws):
    ws.metadata["source_commit"] = "a" * 40
    ws.write_metadata()
    ws.write_snapshot()
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW and has(verdict, "SOURCE_COMMIT_UNVERIFIABLE", "SOURCE_COMMIT_UNKNOWN")
    assert ws.metadata["source_commit"] == "a" * 40  # never replaced silently


def test_D_a_tree_object_is_not_a_commit(ws):
    tree = git(ws.root, "rev-parse", "HEAD^{tree}")
    ws.metadata["source_commit"] = tree
    ws.write_metadata()
    ws.write_snapshot()
    assert has(ws.assess(), "SOURCE_COMMIT_UNVERIFIABLE", "SOURCE_COMMIT_UNKNOWN")


def test_E_commit_outside_the_history_of_head(ws):
    git(ws.root, "checkout", "-q", "--orphan", "elsewhere")
    git(ws.root, "commit", "-q", "-m", "parallel root", "--allow-empty")
    other = git(ws.root, "rev-parse", "HEAD")
    git(ws.root, "checkout", "-q", "-f", "master" if "master" in git(ws.root, "branch", "--list", "master") else "main")
    ws.metadata["source_commit"] = other
    ws.write_metadata()
    ws.write_snapshot()
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW and has(verdict, "SOURCE_COMMIT_UNVERIFIABLE", "SOURCE_COMMIT_NOT_IN_HISTORY")


def test_E_commit_that_does_not_hold_the_provenance_files(ws):
    git(ws.root, "checkout", "-q", "--orphan", "bare")
    git(ws.root, "rm", "-rq", "--cached", ".")
    git(ws.root, "commit", "-q", "-m", "empty root", "--allow-empty")
    bare = git(ws.root, "rev-parse", "HEAD")
    git(ws.root, "checkout", "-q", "-f", ws.commit)
    git(ws.root, "merge", "-q", "--no-edit", "--allow-unrelated-histories", bare)
    ws.metadata["source_commit"] = bare
    ws.write_metadata()
    ws.write_snapshot()
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW and has(verdict, "SOURCE_COMMIT_UNVERIFIABLE", "SOURCE_NOT_AT_COMMIT")


def test_F_source_modified_in_the_workspace_since_packaging(ws):
    ws.write("facts.md", "<!-- modularcv: FactBase-v1 -->\n## S {#s}\n- [a.one] CONFIRMED: Edited later.\n")
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW and has(verdict, "SOURCE_CHANGED_SINCE_PACKAGING", "FILE_CHANGED")


def test_F_source_deleted_since_packaging(ws):
    os.remove(str(ws.root / "facts.md"))
    verdict = ws.assess()
    assert verdict["status"] != READY and has(verdict, "SOURCE_MISSING", "FILE_MISSING")


def test_F_snapshot_built_from_content_that_the_recorded_commit_does_not_hold(ws):
    ws.write("facts.md", "<!-- modularcv: FactBase-v1 -->\n## S {#s}\n- [a.one] CONFIRMED: Uncommitted edit.\n")
    ws.write_snapshot()  # the package was built from an uncommitted facts.md
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "SOURCE_COMMIT_MISMATCH", "SOURCE_DIFFERS_AT_COMMIT")


def test_F_a_source_committed_later_is_not_the_recorded_commit(ws):
    ws.write("facts.md", "<!-- modularcv: FactBase-v1 -->\n## S {#s}\n- [a.one] CONFIRMED: Committed later.\n")
    ws.commit_all("edit facts")
    ws.write_snapshot()
    assert has(ws.assess(), "SOURCE_COMMIT_MISMATCH")


@pytest.mark.parametrize("mutate,reason,code", [
    ("delete", "SNAPSHOT_MISSING", "SNAPSHOT_FILE_MISSING"),
    ("garbage", "SNAPSHOT_INVALID", "SNAPSHOT_UNREADABLE"),
    ("not_object", "SNAPSHOT_INVALID", "SNAPSHOT_NOT_OBJECT"),
    ("wrong_schema", "SNAPSHOT_INVALID", "SNAPSHOT_SCHEMA"),
    ("bad_fingerprint", "SNAPSHOT_INVALID", "SNAPSHOT_FINGERPRINT"),
    ("extra_field", "SNAPSHOT_INVALID", "SNAPSHOT_FIELDS"),
    ("missing_plan", "SNAPSHOT_INVALID", "SNAPSHOT_ROLE_MISSING"),
    ("two_metadata", "CV_METADATA_AMBIGUOUS", "SNAPSHOT_DUPLICATE_ROLE"),
    ("two_plans", "SNAPSHOT_CONTRADICTORY", "SNAPSHOT_DUPLICATE_ROLE"),
    ("same_path_two_hashes", "SNAPSHOT_CONTRADICTORY", "SNAPSHOT_DUPLICATE_PATH"),
    ("wrong_kind", "SNAPSHOT_INVALID", "SNAPSHOT_KIND_MISMATCH"),
    ("unknown_role", "SNAPSHOT_INVALID", "SNAPSHOT_UNKNOWN_ROLE"),
    ("unsafe_path", "SNAPSHOT_INVALID", "SNAPSHOT_PATH_UNSAFE"),
])
def test_G_snapshot_absent_invalid_or_contradictory(ws, mutate, reason, code):
    path = ws.package_dir / "provenance" / "source-snapshot.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    entries = doc["entries"]

    def rewrite(document, refingerprint=True):
        if refingerprint:
            from modularcv import snapshot
            document["snapshot_fingerprint"] = snapshot.fingerprint(document["entries"])
        path.write_text(json.dumps(document), encoding="utf-8")

    plan = next(e for e in entries if e["role"] == "cv_tex")
    if mutate == "delete":
        path.unlink()
    elif mutate == "garbage":
        path.write_text("{ nope", encoding="utf-8")
    elif mutate == "not_object":
        path.write_text("[]", encoding="utf-8")
    elif mutate == "wrong_schema":
        doc["schema"] = "SourceSnapshot-v9"
        rewrite(doc, False)
    elif mutate == "bad_fingerprint":
        doc["snapshot_fingerprint"] = "0" * 64
        rewrite(doc, False)
    elif mutate == "extra_field":
        doc["extra"] = 1
        rewrite(doc, False)
    elif mutate == "missing_plan":
        doc["entries"] = [e for e in entries if e["role"] != "tailoring_plan"]
        rewrite(doc)
    elif mutate == "two_metadata":
        extra = dict(next(e for e in entries if e["role"] == "cv_metadata"), path="applications/job-1/cv/other.json")
        doc["entries"].append(extra)
        rewrite(doc)
    elif mutate == "two_plans":
        extra = dict(next(e for e in entries if e["role"] == "tailoring_plan"), path="applications/job-1/cv/plan2.json")
        doc["entries"].append(extra)
        rewrite(doc)
    elif mutate == "same_path_two_hashes":
        doc["entries"].append(dict(plan, sha256="1" * 64))
        rewrite(doc)
    elif mutate == "wrong_kind":
        plan["kind"] = "binary"
        rewrite(doc)
    elif mutate == "unknown_role":
        doc["entries"].append(dict(plan, role="surprise", path="x.txt"))
        rewrite(doc)
    elif mutate == "unsafe_path":
        doc["entries"].append(dict(plan, role="resume_content", path="../outside.json"))
        rewrite(doc)
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, reason, code)


def test_H_metadata_substituted_after_packaging(ws):
    ws.metadata["title"] = "Another title"
    ws.write_metadata()
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW
    assert has(verdict, "CV_METADATA_CHANGED_SINCE_PACKAGING", "FILE_CHANGED")


def test_H_plan_beside_the_metadata_names_another_cv(ws):
    ws.write_json(ws.plan_rel, {"schema": "TailoringPlan-v1", "tailored_cv_id": "cv-of-another-package"})
    ws.write_snapshot()
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "CV_REFERENCE_MISMATCH", "PLAN_NAMES_ANOTHER_CV")


def test_H_package_names_another_cv_than_the_plan(ws):
    package = copy.deepcopy(ws.package)
    package["artifacts"]["cv"]["tailored_cv_id"] = "cv-id-99"
    verdict = ws.assess(package)
    assert verdict["status"] == BLOCKED and has(verdict, "CV_REFERENCE_MISMATCH")


def test_H_package_without_a_cv_identity(ws):
    package = copy.deepcopy(ws.package)
    del package["artifacts"]["cv"]["tailored_cv_id"]
    assert has(ws.assess(package), "CV_REFERENCE_MISMATCH", "PACKAGE_HAS_NO_CV_ID")


def test_H_plan_in_another_folder_than_the_metadata(ws):
    ws.write_json("applications/job-1/plan-elsewhere.json", {"tailored_cv_id": ws.cv_id})
    items = [i if i[0] != "tailoring_plan" else ("tailoring_plan", "applications/job-1/plan-elsewhere.json")
             for i in ws.items()]
    ws.write_snapshot(items)
    assert has(ws.assess(), "CV_REFERENCE_MISMATCH", "PLAN_NOT_BESIDE_METADATA")


def test_H_metadata_outside_the_applications_tree(ws):
    ws.write_json("elsewhere/metadata.json", ws.metadata)
    items = [i if i[0] != "cv_metadata" else ("cv_metadata", "elsewhere/metadata.json") for i in ws.items()]
    ws.write_snapshot(items)
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "CV_METADATA_OUT_OF_SCOPE", "OUTSIDE_APPLICATIONS_TREE")


def test_H_metadata_facts_source_differs_from_the_snapshot_facts(ws):
    ws.metadata["facts_source"] = "other-facts.md"
    ws.write_metadata()
    ws.write_snapshot()
    assert has(ws.assess(), "CV_REFERENCE_MISMATCH", "FACTS_SOURCE_DIFFERS")


def test_H_unreadable_metadata(ws):
    ws.write(ws.meta_rel, "{ not json")
    ws.write_snapshot()
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "CV_METADATA_UNREADABLE")


def test_I_no_human_approval(ws):
    os.remove(str(ws.root / ws.review_rel))
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW and has(verdict, "HUMAN_REVIEW_REQUIRED", "REVIEW_FILE_MISSING")


def test_I_approval_of_another_identity(ws):
    ws.write_review(tailored_cv_id="an-older-cv-id")
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW and has(verdict, "HUMAN_REVIEW_MISMATCH")


def test_I_approval_of_an_older_version_of_the_same_identity(ws):
    ws.write(ws.cv_rel, "\\documentclass{article}\n% edited after approval\n")
    ws.write_snapshot()  # repackaged, same tailored_cv_id, new document
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW and has(verdict, "HUMAN_REVIEW_MISMATCH")


def test_I_document_edited_after_packaging_and_approval(ws):
    ws.write(ws.cv_rel, "\\documentclass{article}\n% tampered\n")
    verdict = ws.assess()
    assert verdict["status"] != READY and has(verdict, "ARTIFACT_CHANGED_SINCE_PACKAGING")


def test_I_rejected_review_blocks(ws):
    ws.write_review(decision="REJECTED")
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "HUMAN_REVIEW_REJECTED")


@pytest.mark.parametrize("text", ["{ no", "[]", json.dumps({"schema": "CVQualityReview-v1"}),
                                  json.dumps({"schema": "CVQualityReview-v1", "decision": "MAYBE",
                                              "tailored_cv_id": "x", "document_sha256": "y"})])
def test_I_invalid_review_file_does_not_approve(ws, text):
    ws.write(ws.review_rel, text)
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW and has(verdict, "HUMAN_REVIEW_INVALID")


def test_pending_fact_validations_prevent_readiness(ws):
    ws.metadata["decision"]["human_validations_required"] = ["fact a.one needs a decision"]
    ws.write_metadata()
    ws.write_snapshot()
    ws.write_review()
    verdict = ws.assess()
    assert verdict["status"] == NEEDS_REVIEW and has(verdict, "FACT_VALIDATION_REQUIRED")


# --- historical metadata: readable, never automatically ready ------------------------------------------

@pytest.mark.parametrize("version", ["1", "2"])
def test_v1_and_v2_are_readable_and_ready_only_with_full_evidence(tmp_path, version):
    ws = Workspace(tmp_path, schema_version=version)
    assert ws.assess()["status"] == READY
    os.remove(str(ws.root / ws.review_rel))
    assert ws.assess()["status"] == NEEDS_REVIEW
    (ws.package_dir / "provenance" / "source-snapshot.json").unlink()
    assert ws.assess()["status"] == BLOCKED


@pytest.mark.parametrize("version", ["3", "4", "", None, 2])
def test_unknown_schema_versions_are_refused_not_guessed(ws, version):
    ws.metadata["schema_version"] = version
    ws.write_metadata()
    ws.write_snapshot()
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "CV_METADATA_INVALID", "METADATA_SCHEMA_VERSION")


@pytest.mark.parametrize("field", ["job_key", "generated_at", "language", "family", "master_resume",
                                   "facts_source", "company", "title", "job_sha256", "decision"])
def test_a_missing_required_metadata_field_blocks(ws, field):
    del ws.metadata[field]
    ws.write_metadata()
    ws.write_snapshot()
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and has(verdict, "CV_METADATA_INVALID", "METADATA_FIELD_MISSING")


# --- declared state, gates, registry (unchanged behaviour) ----------------------------------------------

def entry(package, status="STALE"):
    return {"job_id": package["application"]["job_id"], "status": status,
            "package_fingerprint": package["package_fingerprint"],
            "tailored_cv_id": package["artifacts"]["cv"]["tailored_cv_id"]}


def test_a_missing_registry_is_an_empty_registry(ws):
    ws.registry.unlink()
    assert ws.assess()["status"] == READY


def test_a_stale_fingerprint_blocks_even_if_everything_else_passes(ws):
    ws.write_registry(entry(ws.package))
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and "PACKAGE_STALE" in verdict["reasons"]


def test_a_stale_cv_identity_blocks_a_package_with_a_new_fingerprint(ws):
    old = copy.deepcopy(ws.package)
    old["package_fingerprint"] = "a" * 64
    ws.write_registry(entry(old))
    package = copy.deepcopy(ws.package)
    package["package_fingerprint"] = "b" * 64
    assert ws.assess(package)["status"] == BLOCKED


def test_another_job_that_is_stale_does_not_block_this_one(tmp_path):
    ws = Workspace(tmp_path)
    other = copy.deepcopy(ws.package)
    other.update(application={"job_id": 2}, package_fingerprint="9" * 64)
    other["artifacts"]["cv"]["tailored_cv_id"] = "cv-id-2"
    ws.write_registry(entry(other))
    assert ws.assess()["status"] == READY


def test_a_resolved_registry_entry_does_not_block(ws):
    ws.write_registry(entry(ws.package, status="RESOLVED"))
    assert ws.assess()["status"] == READY


@pytest.mark.parametrize("state", [NEEDS_REVIEW, BLOCKED, "APPLIED", None])
def test_only_a_declared_ready_package_can_be_ready(ws, state):
    package = copy.deepcopy(ws.package)
    package["routing"]["workflow_state"] = state
    assert ws.assess(package)["status"] != READY


@pytest.mark.parametrize("gate", sorted(GATES))
def test_every_failed_gate_prevents_readiness(ws, gate):
    package = copy.deepcopy(ws.package)
    package["validation"]["gates"][gate] = False
    verdict = ws.assess(package)
    assert verdict["status"] != READY and gate in verdict["reasons"]


def test_an_unreadable_registry_fails_closed(ws):
    ws.registry.write_text("{ not json", encoding="utf-8")
    verdict = ws.assess()
    assert verdict["status"] == BLOCKED and verdict["reasons"] == ["STALENESS_REGISTRY_UNREADABLE"]


def test_a_registry_without_a_package_list_fails_closed(ws):
    ws.registry.write_text(json.dumps({"registry_version": "x"}), encoding="utf-8")
    assert ws.assess()["status"] == BLOCKED


@pytest.mark.parametrize("bad", [{"routing": {}}, None, {"routing": {"workflow_state": READY},
                                                          "validation": {"gates": []}}])
def test_a_malformed_package_is_blocked(ws, bad):
    verdict = ws.assess(bad) if bad is not None else assess(None, None, ws.registry)
    assert verdict["status"] == BLOCKED and verdict["reasons"] == ["PACKAGE_JSON_INVALID"]


def test_apply_downgrades_a_package_and_records_why(ws):
    ws.write_registry(entry(ws.package))
    package = copy.deepcopy(ws.package)
    apply(package, None, ws.registry, ws.root, ws.package_dir)
    assert package["routing"]["workflow_state"] == BLOCKED
    assert "PACKAGE_STALE" in package["routing"]["reasons"]


def test_apply_never_upgrades_a_package(ws):
    for state in (NEEDS_REVIEW, BLOCKED):
        package = copy.deepcopy(ws.package)
        package["routing"]["workflow_state"] = state
        apply(package, None, ws.registry, ws.root, ws.package_dir)
        assert package["routing"]["workflow_state"] == state


def test_marking_a_package_stale_blocks_it(ws, tmp_path):
    path = tmp_path / "reg" / "package-staleness.json"
    staleness.mark(ws.package, "recalibrated", "cv-new", path)
    assert assess(ws.package, None, path, ws.root, ws.package_dir)["status"] == BLOCKED


# --- the audit -------------------------------------------------------------------------------------------

def test_the_audit_reports_ready_and_not_ready_packages(tmp_path):
    good = Workspace(tmp_path)
    good.write_json("packages/application-index.json", {"applications": [
        {"job_id": 1, "status": READY, "package_fingerprint": good.package["package_fingerprint"]}]})
    report = good.audit()
    assert report["ready"] == ["1-co"] and report["counts"] == {READY: 1, NEEDS_REVIEW: 0, BLOCKED: 0}
    assert report["contradictions"] == []


def test_the_audit_flags_an_index_that_says_ready_for_a_package_without_evidence(ws):
    (ws.package_dir / "provenance" / "source-snapshot.json").unlink()
    ws.write_json("packages/application-index.json", {"applications": [
        {"job_id": 1, "status": READY, "package_fingerprint": ws.package["package_fingerprint"]}]})
    report = ws.audit()
    assert report["packages"][0]["status"] == BLOCKED and report["ready"] == []
    assert report["contradictions"][0]["kind"] == "INDEX_READY_BUT_NOT_EFFECTIVELY_READY"
    assert "SNAPSHOT_MISSING" in report["contradictions"][0]["reasons"]


def test_the_audit_flags_a_declared_ready_package_without_evidence(ws):
    os.remove(str(ws.root / ws.review_rel))
    report = ws.audit()
    assert report["contradictions"][0]["kind"] == "PACKAGE_READY_BUT_NOT_EFFECTIVELY_READY"


def test_the_audit_reports_an_unreadable_package_and_keeps_going(ws):
    (ws.package_dir / "package.json").write_text("{", encoding="utf-8")
    report = ws.audit()
    assert report["packages"][0]["status"] == BLOCKED and report["ready"] == []
    assert report["packages"][0]["details"][0]["code"] == "PACKAGE_JSON_UNREADABLE"


def test_the_audit_is_incomplete_when_the_directory_is_missing_or_empty(ws, tmp_path):
    with pytest.raises(readiness.AuditError) as caught:
        audit_directory(tmp_path / "nope", None, ws.root)
    assert caught.value.code == "PACKAGES_DIR_MISSING"
    (tmp_path / "empty").mkdir()
    with pytest.raises(readiness.AuditError) as caught:
        audit_directory(tmp_path / "empty", None, ws.root)
    assert caught.value.code == "NO_PACKAGES"


def test_the_audit_is_read_only_and_idempotent(ws):
    before = tree_hash(ws.root)
    first, second = ws.audit(), ws.audit()
    assert tree_hash(ws.root) == before and first == second
    ws.assess()
    assert tree_hash(ws.root) == before


def test_assess_never_writes_in_failing_cases_either(ws):
    ws.metadata["source_commit"] = "a" * 40
    ws.write_metadata()
    ws.write_snapshot()
    before = tree_hash(ws.root)
    assert ws.assess()["status"] != READY
    assert tree_hash(ws.root) == before


def test_a_configuration_error_stops_the_audit(ws):
    (ws.root / "modularcv.json").write_text("{ nope", encoding="utf-8")
    from modularcv import config
    with pytest.raises(config.ConfigError):
        ws.audit()


def test_a_workspace_that_is_not_a_repository_cannot_verify_a_commit(tmp_path):
    ws = Workspace(tmp_path)
    import shutil
    shutil.rmtree(str(ws.root / ".git"), onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    verdict = ws.assess()
    assert verdict["status"] != READY and has(verdict, "SOURCE_COMMIT_UNVERIFIABLE", "GIT_REPOSITORY_UNAVAILABLE")


def test_two_packages_cannot_hide_each_other(tmp_path):
    ws = Workspace(tmp_path)
    second = copy.deepcopy(ws.package)
    second.update(application={"job_id": 2}, package_fingerprint="2" * 64)
    second["artifacts"]["cv"]["tailored_cv_id"] = "cv-id-2"
    folder = ws.root / "packages" / "2-co"
    folder.mkdir(parents=True)
    (folder / "package.json").write_text(json.dumps(second), encoding="utf-8")
    report = ws.audit()
    states = {p["folder"]: p["status"] for p in report["packages"]}
    assert states["1-co"] == READY and states["2-co"] == BLOCKED
    assert report["ready"] == ["1-co"]


def test_the_check_command_exit_codes(ws, capsys):
    root = str(ws.root)
    assert cli.main(["check-packages", str(ws.root / "packages"), "--root", root]) == 0
    capsys.readouterr()
    os.remove(str(ws.root / ws.review_rel))
    assert cli.main(["check-packages", str(ws.root / "packages"), "--root", root]) == 1
    assert json.loads(capsys.readouterr().out)["contradictions"][0]["job_id"] == 1
    assert cli.main(["check-packages", str(ws.root / "missing"), "--root", root]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "PACKAGES_DIR_MISSING"
    (ws.root / "modularcv.json").write_text("{ nope", encoding="utf-8")
    assert cli.main(["check-packages", str(ws.root / "packages"), "--root", root]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "CONFIG_ERROR"
