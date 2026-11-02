"""SourceSnapshot-v1, workspace paths, CV metadata and review parsing (all synthetic)."""
import json
import os
import subprocess
import sys

import pytest

from modularcv import __main__ as cli
from modularcv import canonical, config, metadata, paths, provenance, review, snapshot
from synthetic import Workspace, git, tree_hash


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path)


def codes(problems):
    return [p.code for p in problems]


# --- paths: the same answer on Windows and Linux ------------------------------------------------------

@pytest.mark.parametrize("value", ["facts.md", "a/b/c.json", "applications/job-1/cv/metadata.json", "a.b/c-d_e"])
def test_safe_paths(value):
    assert paths.relative_path_problem(value) is None


@pytest.mark.parametrize("value", [
    "", None, 5, "/etc/passwd", "C:/Temp/x", "c:\\Temp\\x", "C:relative", "a\\b", "..", "../x", "a/../b", "a//b",
    "a/./b", "./a", "a/", "a/b/", "a:b", "file.txt:stream", "dir /x", "x/name.", "a\x00b", "a\nb", "\\\\server\\share\\x"])
def test_unsafe_paths_are_refused_everywhere(value):
    assert paths.relative_path_problem(value)


def test_resolve_inside_refuses_an_escape_by_symlink(tmp_path):
    root, outside = tmp_path / "ws", tmp_path / "outside"
    root.mkdir(), outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    try:
        os.symlink(str(outside), str(root / "link"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    assert paths.resolve_inside(root, "link/secret.txt") is None
    (root / "real.txt").write_text("x", encoding="utf-8")
    assert paths.resolve_inside(root, "real.txt") == (root / "real.txt").resolve()


# --- snapshot: build, structure, verification ------------------------------------------------------------

def test_a_built_snapshot_is_consistent_and_deterministic(ws):
    first, second = snapshot.build(ws.root, ws.items()), snapshot.build(ws.root, list(reversed(ws.items())))
    assert first == second
    assert snapshot.verify(first, ws.root) == []
    assert [e["role"] for e in first["entries"]] == sorted(e["role"] for e in first["entries"])
    assert first["snapshot_fingerprint"] == snapshot.fingerprint(first["entries"])


def test_entries_record_kind_hash_and_size(ws):
    entry = next(e for e in snapshot.build(ws.root, ws.items())["entries"] if e["role"] == "cv_tex")
    data = (ws.root / ws.cv_rel).read_bytes()
    assert entry == {"role": "cv_tex", "path": ws.cv_rel, "sha256": canonical.sha256_text(data),
                     "size": len(data), "kind": "text"}


def test_text_hashes_ignore_line_endings_and_bom_but_binary_hashes_do_not(ws):
    document = snapshot.build(ws.root, ws.items())
    path = ws.root / ws.cv_rel
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes().replace(b"\n", b"\r\n"))
    assert snapshot.verify(document, ws.root) == []  # text: same normalised-source hash
    pdf = b"%PDF-1.4\r\nbinary\r\n"
    ws.write("applications/job-1/cv/cv.pdf", pdf)
    items = ws.items() + [("cv_pdf", "applications/job-1/cv/cv.pdf")]
    with_pdf = snapshot.build(ws.root, items)
    entry = next(e for e in with_pdf["entries"] if e["role"] == "cv_pdf")
    assert entry["kind"] == "binary" and entry["sha256"] == canonical.sha256_bytes(pdf)
    ws.write("applications/job-1/cv/cv.pdf", pdf.replace(b"\r\n", b"\n"))
    assert codes(snapshot.verify(with_pdf, ws.root)) == ["FILE_CHANGED"]


def test_lf_crlf_cr_and_bom_copies_of_a_source_verify(ws):
    document = snapshot.build(ws.root, ws.items())
    original = (ws.root / "facts.md").read_bytes()
    for variant in (original.replace(b"\n", b"\r\n"), original.replace(b"\n", b"\r"), b"\xef\xbb\xbf" + original):
        (ws.root / "facts.md").write_bytes(variant)
        assert snapshot.verify(document, ws.root) == []


def test_any_other_edit_is_detected(ws):
    document = snapshot.build(ws.root, ws.items())
    (ws.root / "facts.md").write_bytes((ws.root / "facts.md").read_bytes() + b"\n\n")
    problems = snapshot.verify(document, ws.root)
    assert codes(problems) == ["FILE_CHANGED"] and problems[0].role == "facts" and problems[0].path == "facts.md"


def test_a_substituted_file_and_a_missing_file_are_detected(ws):
    document = snapshot.build(ws.root, ws.items())
    ws.write(ws.plan_rel, json.dumps({"tailored_cv_id": "another"}))
    os.remove(str(ws.root / ws.cv_rel))
    assert sorted(codes(snapshot.verify(document, ws.root))) == ["FILE_CHANGED", "FILE_MISSING"]


def test_a_directory_in_place_of_a_file_is_missing(ws):
    document = snapshot.build(ws.root, ws.items())
    os.remove(str(ws.root / "facts.md"))
    (ws.root / "facts.md").mkdir()
    assert codes(snapshot.verify(document, ws.root)) == ["FILE_MISSING"]


def test_tampering_with_the_document_without_the_fingerprint_is_detected(ws):
    document = snapshot.build(ws.root, ws.items())
    document["entries"][0]["sha256"] = "1" * 64
    assert "SNAPSHOT_FINGERPRINT" in codes(snapshot.verify(document, ws.root))


def test_build_refuses_unknown_roles_unsafe_paths_missing_files_and_duplicates(ws):
    with pytest.raises(snapshot.SnapshotError) as caught:
        snapshot.build(ws.root, ws.items() + [("surprise", "facts.md")])
    assert caught.value.code == "SNAPSHOT_UNKNOWN_ROLE"
    with pytest.raises(snapshot.SnapshotError) as caught:
        snapshot.build(ws.root, ws.items() + [("resume_content", "../x.json")])
    assert caught.value.code == "SNAPSHOT_PATH_UNSAFE"
    with pytest.raises(snapshot.SnapshotError) as caught:
        snapshot.build(ws.root, ws.items() + [("resume_content", "absent.json")])
    assert caught.value.code == "FILE_MISSING"
    with pytest.raises(snapshot.SnapshotError) as caught:
        snapshot.build(ws.root, ws.items() + [("facts", "facts.md")])
    assert caught.value.code in ("SNAPSHOT_DUPLICATE_ROLE", "SNAPSHOT_DUPLICATE_ENTRY")


def test_multiple_resume_content_files_are_allowed(ws):
    ws.write("content/a.json", "{}"), ws.write("content/b.json", "{}")
    document = snapshot.build(ws.root, ws.items() + [("resume_content", "content/a.json"),
                                                     ("resume_content", "content/b.json")])
    assert snapshot.verify(document, ws.root) == []


def test_verification_does_not_write(ws):
    document = snapshot.build(ws.root, ws.items())
    before = tree_hash(ws.root)
    snapshot.verify(document, ws.root), snapshot.verify(document, ws.root)
    assert tree_hash(ws.root) == before


def test_a_snapshot_path_escaping_by_symlink_is_a_problem(ws, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.json").write_text("{}", encoding="utf-8")
    try:
        os.symlink(str(outside), str(ws.root / "linked"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    document = snapshot.assemble([snapshot.make_entry("resume_content", "linked/x.json", b"{}")])
    assert codes(snapshot.verify_files(document, ws.root)) == ["PATH_ESCAPE"]


@pytest.mark.parametrize("document,code", [
    ([], "SNAPSHOT_NOT_OBJECT"), ({}, "SNAPSHOT_SCHEMA"), ({"schema": "SourceSnapshot-v1"}, "SNAPSHOT_FIELDS"),
    ({"schema": "SourceSnapshot-v1", "entries": {}, "snapshot_fingerprint": "x"}, "SNAPSHOT_FIELDS")])
def test_structurally_unusable_snapshots(document, code):
    assert codes(snapshot.structure_problems(document)) == [code]


@pytest.mark.parametrize("entry", [
    {"role": "facts"}, {"role": "facts", "path": "f", "sha256": "z" * 64, "size": 1, "kind": "text"},
    {"role": "facts", "path": "f", "sha256": "a" * 63, "size": 1, "kind": "text"},
    {"role": "facts", "path": "f", "sha256": "a" * 64, "size": -1, "kind": "text"},
    {"role": "facts", "path": "f", "sha256": "a" * 64, "size": True, "kind": "text"},
    {"role": "facts", "path": "f", "sha256": "A" * 64, "size": 1, "kind": "text"}, "text", None])
def test_malformed_entries(entry):
    document = {"schema": snapshot.SCHEMA, "entries": [entry], "snapshot_fingerprint": "0" * 64}
    assert "SNAPSHOT_ENTRY_INVALID" in codes(snapshot.structure_problems(document, False))


# --- snapshot CLI ------------------------------------------------------------------------------------------

def test_snapshot_verify_command(ws, capsys):
    path = ws.package_dir / "provenance" / "source-snapshot.json"
    assert cli.main(["snapshot", "verify", str(path), "--root", str(ws.root)]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "OK", "problems": []}
    ws.write("facts.md", "changed\n")
    assert cli.main(["snapshot", "verify", str(path), "--root", str(ws.root)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "INVALID" and report["problems"][0]["code"] == "FILE_CHANGED"
    assert cli.main(["snapshot", "verify", str(ws.root / "absent.json"), "--root", str(ws.root)]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "SNAPSHOT_UNREADABLE"


# --- metadata -----------------------------------------------------------------------------------------------

def test_the_published_template_style_document_is_valid_v2():
    document = json.loads(open("templates/application_metadata.template.json", encoding="utf-8").read())
    document.update(job_key="k", generated_at="2026-01-01T00:00:00Z", family="software",
                    job_sha256="a" * 64, company="Example", title="Dev")
    assert metadata.problems(document) == []
    document["schema_version"] = "1"
    assert metadata.problems(document) == []


@pytest.mark.parametrize("change,code", [
    ({"language": "de"}, "METADATA_FIELD_TYPE"), ({"job_sha256": "xyz"}, "METADATA_FIELD_TYPE"),
    ({"master_resume": "resume.docx"}, "METADATA_FIELD_TYPE"), ({"base_resume": "x.docx"}, "METADATA_FIELD_TYPE"),
    ({"recommended_length_pages": 3}, "METADATA_FIELD_TYPE"), ({"recommended_length_pages": True}, "METADATA_FIELD_TYPE"),
    ({"decision": []}, "METADATA_FIELD_TYPE"), ({"decision": {"selected_content": "x"}}, "METADATA_FIELD_TYPE"),
    ({"job_key": " "}, "METADATA_FIELD_TYPE"), ({"company": 3}, "METADATA_FIELD_TYPE"),
    ({"schema_version": "3"}, "METADATA_SCHEMA_VERSION")])
def test_invalid_metadata_variants(ws, change, code):
    document = dict(ws.metadata, **change)
    assert code in [c for c, _ in metadata.problems(document)]


def test_metadata_must_be_an_object():
    assert metadata.problems([]) == [("METADATA_NOT_OBJECT", "metadata must be a JSON object")]


# --- review ------------------------------------------------------------------------------------------------

def test_review_parse_and_judge():
    good = json.dumps({"schema": review.SCHEMA, "decision": "APPROVED", "tailored_cv_id": "a", "document_sha256": "b",
                       "note": "ok", "reviewer": "someone"}).encode("utf-8")
    document, error = review.parse(good)
    assert error is None and review.judge(document, "a", "b") is None
    assert review.judge(document, "a2", "b") == "HUMAN_REVIEW_MISMATCH"
    assert review.judge(document, "a", "b2") == "HUMAN_REVIEW_MISMATCH"
    assert review.judge(dict(document, decision="REJECTED"), "a", "b") == "HUMAN_REVIEW_REJECTED"


@pytest.mark.parametrize("raw", [b"\xff\xfe", b"[]", b"{}", json.dumps({"schema": review.SCHEMA}).encode(),
                                 json.dumps({"schema": review.SCHEMA, "decision": "APPROVED", "tailored_cv_id": "",
                                             "document_sha256": "b"}).encode(),
                                 json.dumps({"schema": review.SCHEMA, "decision": "APPROVED", "tailored_cv_id": "a",
                                             "document_sha256": "b", "extra": 1}).encode(),
                                 json.dumps({"schema": review.SCHEMA, "decision": "APPROVED", "tailored_cv_id": "a",
                                             "document_sha256": "b", "note": 3}).encode()])
def test_review_parse_refuses_invalid_files(raw):
    document, error = review.parse(raw)
    assert document is None and error


# --- provenance additions ------------------------------------------------------------------------------------

def test_recorded_commit_does_not_compare_the_working_tree(ws):
    ws.write("facts.md", "edited since\n")
    assert provenance.verify_recorded_commit(ws.commit, ws.root, ["facts.md"]) == ws.commit
    with pytest.raises(provenance.SourceProvenanceError) as caught:
        provenance.verify_source_commit(ws.commit, ws.root, ["facts.md"])
    assert caught.value.status == "SOURCE_NOT_AT_COMMIT" and caught.value.reason == "MODIFIED"
    assert caught.value.path == "facts.md"


def test_recorded_commit_refusals(ws):
    for commit, status in (("0" * 40, "INVALID_SOURCE_COMMIT"), ("b" * 40, "SOURCE_COMMIT_UNKNOWN"), (None, "INVALID_SOURCE_COMMIT")):
        with pytest.raises(provenance.SourceProvenanceError) as caught:
            provenance.verify_recorded_commit(commit, ws.root, ["facts.md"])
        assert caught.value.status == status
    with pytest.raises(provenance.SourceProvenanceError) as caught:
        provenance.verify_recorded_commit(ws.commit, ws.root, ["never-committed.md"])
    assert caught.value.status == "SOURCE_NOT_AT_COMMIT" and caught.value.reason == "NOT_IN_COMMIT"
    for bad in ("../x", "/abs", "a\\b"):
        with pytest.raises(provenance.SourceProvenanceError) as caught:
            provenance.verify_recorded_commit(ws.commit, ws.root, [bad])
        assert caught.value.reason == "UNSAFE_PATH"


def test_untracked_missing_and_modified_sources_are_told_apart(ws):
    ws.write("notes.md", "untracked\n")
    with pytest.raises(provenance.SourceProvenanceError) as caught:
        provenance.verify_source_commit(ws.commit, ws.root, ["facts.md", "notes.md"])
    assert caught.value.reason == "UNTRACKED"
    os.remove(str(ws.root / "facts.md"))
    with pytest.raises(provenance.SourceProvenanceError) as caught:
        provenance.verify_source_commit(ws.commit, ws.root, ["facts.md"])
    assert caught.value.reason == "MISSING"


def test_bom_and_lone_cr_do_not_break_the_working_tree_comparison(ws):
    original = (ws.root / "facts.md").read_bytes()
    for variant in (b"\xef\xbb\xbf" + original, original.replace(b"\n", b"\r"), original.replace(b"\n", b"\r\n")):
        (ws.root / "facts.md").write_bytes(variant)
        assert provenance.verify_source_commit(ws.commit, ws.root, ["facts.md"]) == ws.commit


def test_hash_at_commit_is_the_normalised_source_hash(ws):
    assert provenance.hash_at_commit(ws.commit, ws.root, "facts.md") == canonical.sha256_text(
        (ws.root / "facts.md").read_bytes())


def test_the_workspace_must_be_a_repository_of_its_own(ws):
    sub = ws.root / "sub"
    sub.mkdir()
    (sub / "facts.md").write_text("x\n", encoding="utf-8")
    with pytest.raises(provenance.SourceProvenanceError) as caught:
        provenance.verify_recorded_commit(ws.commit, sub, ["facts.md"])
    assert caught.value.status == "WORKSPACE_NOT_REPOSITORY_ROOT"
    with pytest.raises(provenance.SourceProvenanceError) as caught:
        provenance.resolve_source_commit(sub, ["facts.md"])
    assert caught.value.status == "WORKSPACE_NOT_REPOSITORY_ROOT"


def test_provenance_commands_never_write_the_workspace(ws):
    before = tree_hash(ws.root)
    provenance.verify_recorded_commit(ws.commit, ws.root, ["facts.md"])
    provenance.verify_source_commit(ws.commit, ws.root, ["facts.md"])
    provenance.hash_at_commit(ws.commit, ws.root, "facts.md")
    provenance.resolve_source_commit(ws.root, ["facts.md"])
    assert tree_hash(ws.root) == before


def test_provenance_command_verify_options(ws, capsys):
    assert cli.main(["provenance", "--root", str(ws.root), "--verify", ws.commit, "--recorded"]) == 0
    assert capsys.readouterr().out.strip() == ws.commit
    assert cli.main(["provenance", "--root", str(ws.root), "--verify", "a" * 40]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "SOURCE_COMMIT_UNKNOWN"
    assert cli.main(["provenance", "--root", str(ws.root), "--verify", "0" * 40]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "INVALID_SOURCE_COMMIT"


# --- configuration ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("content", ["{ nope", "[]", json.dumps({"surprise": 1}),
                                     json.dumps({"facts": "../facts.md"}), json.dumps({"facts": "/etc/x"}),
                                     json.dumps({"applications_dir": "C:/apps"}), json.dumps({"packages_dir": 3}),
                                     json.dumps({"provenance_files": "x"}), json.dumps({"provenance_files": ["../x"]})])
def test_configuration_errors_are_refused(tmp_path, content):
    (tmp_path / "modularcv.json").write_text(content, encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)


def test_a_custom_applications_dir_is_honoured(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.assess()["status"] == "READY_TO_SEND"
    (ws.root / "modularcv.json").write_text(json.dumps({"applications_dir": "elsewhere"}), encoding="utf-8")
    verdict = ws.assess()
    assert verdict["status"] == "BLOCKED" and "CV_METADATA_OUT_OF_SCOPE" in verdict["reasons"]


def test_the_engine_makes_no_network_import():
    banned = {"socket", "urllib", "http", "requests", "ssl", "ftplib", "smtplib"}
    import ast
    import inspect
    from modularcv import readiness
    for module in (readiness, snapshot, provenance, metadata, review, paths):
        tree = ast.parse(inspect.getsource(module))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
        assert not names & banned, (module.__name__, names & banned)
