"""`source_commit` is a real, verified Git commit; placeholders are refused (never invented)."""
import hashlib
import json
import subprocess

import pytest

from modularcv import provenance
from modularcv.provenance import (SourceProvenanceError, inventory_placeholders, is_placeholder,
                                  resolve_source_commit, validate_sha, verify_source_commit)

FILES = ("masters/master.tex", "baselines/software.tex", "facts.md")
GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
       "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]


def run(root, *args):
    return subprocess.run(GIT + list(args), cwd=str(root), check=True,
                          capture_output=True).stdout.decode().strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "workspace"
    for relative in FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("validated content of %s\n" % relative).encode("utf-8"))
    run(root, "init", "-q")
    run(root, "add", "-A")
    run(root, "commit", "-q", "-m", "validated sources")
    return root


def test_a_clean_repository_yields_its_real_head(repo):
    sha = resolve_source_commit(repo, FILES)
    assert sha == run(repo, "rev-parse", "HEAD") and len(sha) == 40
    assert not is_placeholder(sha)


def test_the_configured_provenance_files_are_used(repo):
    (repo / "modularcv.json").write_text(json.dumps({"provenance_files": list(FILES[:2])}),
                                         encoding="utf-8")
    run(repo, "add", "-A")
    run(repo, "commit", "-q", "-m", "config")
    assert resolve_source_commit(repo) == run(repo, "rev-parse", "HEAD")


def test_line_endings_do_not_break_the_comparison(repo):
    path = repo / FILES[0]
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert resolve_source_commit(repo, FILES) == run(repo, "rev-parse", "HEAD")


def test_an_earlier_commit_that_holds_the_same_sources_is_accepted(repo):
    first = run(repo, "rev-parse", "HEAD")
    (repo / "notes.txt").write_text("unrelated", encoding="utf-8")
    run(repo, "add", "-A")
    run(repo, "commit", "-q", "-m", "unrelated change")
    assert verify_source_commit(first, repo, FILES) == first


@pytest.mark.parametrize("value", [None, "", "0" * 40, "0" * 64, "abc", "G" * 40,
                                   "A" * 40, "1" * 39, "1" * 41, 12345])
def test_an_invalid_sha_is_refused(value):
    with pytest.raises(SourceProvenanceError) as caught:
        validate_sha(value)
    assert caught.value.status == "INVALID_SOURCE_COMMIT"


def test_a_modified_source_is_refused(repo):
    (repo / FILES[1]).write_text("edited after the last commit\n", encoding="utf-8")
    with pytest.raises(SourceProvenanceError) as caught:
        resolve_source_commit(repo, FILES)
    assert caught.value.status == "SOURCE_NOT_AT_COMMIT" and FILES[1] in str(caught.value)


def test_a_source_that_is_not_in_the_commit_is_refused(repo):
    new = "baselines/devops.tex"
    (repo / new).write_text("never committed\n", encoding="utf-8")
    with pytest.raises(SourceProvenanceError) as caught:
        resolve_source_commit(repo, FILES + (new,))
    assert caught.value.status == "SOURCE_NOT_AT_COMMIT"


def test_a_missing_source_file_is_refused(repo):
    (repo / FILES[2]).unlink()
    with pytest.raises(SourceProvenanceError) as caught:
        resolve_source_commit(repo, FILES)
    assert caught.value.status == "SOURCE_NOT_AT_COMMIT"


def test_an_unknown_sha_is_refused(repo):
    with pytest.raises(SourceProvenanceError) as caught:
        verify_source_commit("a" * 40, repo, FILES)
    assert caught.value.status == "SOURCE_COMMIT_UNKNOWN"


def test_a_commit_outside_the_current_history_is_refused(repo):
    main = run(repo, "rev-parse", "HEAD")
    run(repo, "checkout", "-q", "--orphan", "elsewhere")
    run(repo, "commit", "-q", "-m", "parallel root", "--allow-empty")
    other = run(repo, "rev-parse", "HEAD")
    run(repo, "checkout", "-q", "-f", main)
    with pytest.raises(SourceProvenanceError) as caught:
        verify_source_commit(other, repo, ())
    assert caught.value.status == "SOURCE_COMMIT_NOT_IN_HISTORY"


def test_a_directory_that_is_not_a_repository_is_refused(tmp_path):
    with pytest.raises(SourceProvenanceError) as caught:
        resolve_source_commit(tmp_path, ())
    assert caught.value.status == "GIT_REPOSITORY_UNAVAILABLE"


def test_absent_git_is_a_clear_refusal_not_a_silent_placeholder(repo, monkeypatch):
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")
    monkeypatch.setattr(provenance.subprocess, "run", no_git)
    with pytest.raises(SourceProvenanceError) as caught:
        resolve_source_commit(repo, FILES)
    assert caught.value.status == "GIT_UNAVAILABLE" and "Git is not available" in str(caught.value)


def test_the_inventory_reads_without_rewriting(tmp_path):
    root = tmp_path / "ws"
    layout = {"a/one": "0" * 40, "a/two": "1" * 40, "b/three": "0" * 40, "b/four": None}
    for folder, value in layout.items():
        path = root / "applications" / folder / "metadata.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({} if value is None else {"source_commit": value}),
                        encoding="utf-8")
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (root / "applications").rglob("metadata.json")}
    report = inventory_placeholders(root)
    assert report["placeholder_count"] == 2 and report["real_count"] == 1
    assert report["placeholders"] == ["applications/a/one/metadata.json",
                                      "applications/b/three/metadata.json"]
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (root / "applications").rglob("metadata.json")}
