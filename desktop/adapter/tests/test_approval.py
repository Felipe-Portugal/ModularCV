"""Graphical approval through the Desktop adapter (`package_approve`): safeguards, refusals, status, revocation.

Every approval here is a clearly fictional one, written in a temporary copy of a fictional Git workspace by automated tests.
None of them is, or may be presented as, a real human approval. The engine (Python 0.2.0) is unchanged.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from test_packages import (REPO, call, copy, git, needs_tex, ready_ws, tree_hash)  # noqa: F401 - fixtures

REVIEW = Path("applications") / "fictional-cv" / "cv" / "cv-quality-review.json"
PDF = Path("applications") / "fictional-cv" / "cv" / "resume.pdf"
DESKTOP_NOTE = "Recorded through the ModularCV Desktop review screen."


def open_review(ws):
    done = call(op="package_review", root=str(ws), name="fictional-cv")
    assert done["ok"], done
    return done


def decision(ws, review=None, **over):
    """What the review screen sends, built from the review it displayed (unless overridden)."""
    review = review or open_review(ws)
    sha = review["summary"]["document"]["sha256"]
    request = dict(op="package_approve", root=str(ws), name="fictional-cv", decision="APPROVED", reviewer="Fictional Reviewer",
                   confirm_examined=True, confirm_final=True, context=review["context"], viewed_sha256=sha, typed_prefix=sha[:12])
    request.update(over)
    return call(**request)


def status(ws):
    return call(op="package_status", root=str(ws), name="fictional-cv")["status"]


def cli(ws, *args, stdin=subprocess.DEVNULL):
    done = subprocess.run([sys.executable, "-m", "modularcv", "package", *args, "--name", "fictional-cv", "--root", str(ws)],
                          cwd=str(REPO), capture_output=True, text=True, stdin=stdin, timeout=120)
    return done


# ------------------------------------------------------------------ the approved path

@needs_tex
def test_valid_approval_then_engine_status_ready(copy):
    assert status(copy)["status"] == "NEEDS_REVIEW"
    done = decision(copy)
    assert done["ok"] and done["recorded"] and done["decision"] == "APPROVED"
    assert done["status"]["status"] == "READY_TO_SEND" and done["status"]["reasons"] == []
    assert status(copy)["status"] == "READY_TO_SEND"           # recomputed, not remembered
    written = json.loads((copy / REVIEW).read_text(encoding="utf-8"))
    assert written["decision"] == "APPROVED" and written["reviewer"] == "Fictional Reviewer"
    assert written["note"] == DESKTOP_NOTE and written["document_role"] == "cv_pdf"


@needs_tex
def test_adapter_review_is_exactly_what_the_engine_builds(copy):
    sys.path.insert(0, str(REPO))
    from modularcv import package
    expected = package.build_review(package.review_summary(copy, "fictional-cv"), "APPROVED", "Fictional Reviewer", DESKTOP_NOTE)
    assert decision(copy)["ok"]
    assert json.loads((copy / REVIEW).read_text(encoding="utf-8")) == expected


@needs_tex
def test_cli_agrees_with_the_graphical_approval(copy):
    assert cli(copy, "status").returncode == 1                   # NEEDS_REVIEW
    assert decision(copy)["ok"]
    ready = cli(copy, "status")
    assert ready.returncode == 0 and json.loads(ready.stdout)["status"] == "READY_TO_SEND"


@needs_tex
def test_cli_approve_is_unchanged_and_still_needs_a_terminal(copy):
    refused = cli(copy, "approve", "--reviewer", "Fictional Reviewer")
    assert refused.returncode != 0 and "APPROVAL_REQUIRES_A_PERSON" in refused.stderr
    assert not (copy / REVIEW).exists()
    assert decision(copy)["ok"]
    assert "APPROVAL_REQUIRES_A_PERSON" in cli(copy, "approve", "--reviewer", "Fictional Reviewer").stderr


@needs_tex
def test_explicit_rejection_blocks(copy):
    done = decision(copy, decision="REJECTED", note="fictional rejection")
    assert done["ok"] and done["decision"] == "REJECTED"
    assert done["status"]["status"] == "BLOCKED" and "HUMAN_REVIEW_REJECTED" in done["status"]["reasons"]
    written = json.loads((copy / REVIEW).read_text(encoding="utf-8"))
    assert written["decision"] == "REJECTED" and written["note"].endswith("fictional rejection")
    assert cli(copy, "status").returncode == 3  # BLOCKED


@needs_tex
def test_revocation_after_the_pdf_changes(copy):
    assert decision(copy)["status"]["status"] == "READY_TO_SEND"
    (copy / PDF).write_bytes((copy / PDF).read_bytes() + b"\n%changed after approval")
    revoked = status(copy)
    assert revoked["status"] != "READY_TO_SEND" and revoked["reasons"]
    assert cli(copy, "status").returncode != 0


@needs_tex
def test_revocation_after_a_source_changes(copy):
    assert decision(copy)["status"]["status"] == "READY_TO_SEND"
    facts_file = copy / "facts.md"
    facts_file.write_bytes(facts_file.read_bytes() + b"\n<!-- fictional edit -->\n")
    assert status(copy)["status"] != "READY_TO_SEND"


@needs_tex
def test_only_the_review_file_is_written_and_nothing_stays_locked(copy):
    before = tree_hash(copy)
    head = git(copy, "rev-parse", "HEAD")
    assert decision(copy)["ok"]
    assert (copy / REVIEW).is_file() and not (copy / ".modularcv-desktop.lock").exists()
    (copy / REVIEW).unlink()
    assert tree_hash(copy) == before and git(copy, "rev-parse", "HEAD") == head


# ------------------------------------------------------------------ the person's explicit acts are required

@needs_tex
@pytest.mark.parametrize("over", [
    {"confirm_examined": False}, {"confirm_examined": None}, {"confirm_examined": "true"}, {"confirm_examined": 1},
    {"confirm_final": False}, {"confirm_final": "yes"},
])
def test_missing_or_loose_confirmation_is_refused(copy, over):
    done = decision(copy, **over)
    assert not done["ok"] and done["code"] == "CONFIRMATION_REQUIRED"
    assert not (copy / REVIEW).exists()


@needs_tex
@pytest.mark.parametrize("field", ["confirm_examined", "confirm_final", "context", "viewed_sha256", "typed_prefix"])
def test_absent_fields_are_refused(copy, field):
    review = open_review(copy)
    sha = review["summary"]["document"]["sha256"]
    request = dict(op="package_approve", root=str(copy), name="fictional-cv", decision="APPROVED", reviewer="Fictional Reviewer",
                   confirm_examined=True, confirm_final=True, context=review["context"], viewed_sha256=sha, typed_prefix=sha[:12])
    del request[field]
    done = call(**request)
    assert not done["ok"] and done["code"] == "CONFIRMATION_REQUIRED" and not (copy / REVIEW).exists()


@needs_tex
@pytest.mark.parametrize("prefix", ["", "000000000000", "abc", "x" * 12])
def test_wrong_hash_prefix_is_refused(copy, prefix):
    review = open_review(copy)
    sha = review["summary"]["document"]["sha256"]
    request_prefix = prefix if prefix else " "
    done = decision(copy, review, typed_prefix=request_prefix)
    assert not done["ok"] and done["code"] in ("CONFIRMATION_MISMATCH", "CONFIRMATION_REQUIRED")
    assert not (copy / REVIEW).exists() and sha[:12] != prefix


@needs_tex
def test_prefix_must_be_the_whole_twelve_characters(copy):
    sha = open_review(copy)["summary"]["document"]["sha256"]
    assert decision(copy, typed_prefix=sha[:11])["code"] == "CONFIRMATION_MISMATCH"
    assert decision(copy, typed_prefix=sha[:13])["code"] == "CONFIRMATION_MISMATCH"
    assert not (copy / REVIEW).exists()


@needs_tex
@pytest.mark.parametrize("value", [None, "", "approved", "APPROVE", "READY_TO_SEND", "NEEDS_REVIEW", 1])
def test_decision_must_be_explicit(copy, value):
    done = decision(copy, decision=value)
    assert not done["ok"] and done["code"] == "DECISION_INVALID" and not (copy / REVIEW).exists()


@needs_tex
@pytest.mark.parametrize("value", [None, "", "   ", "a\nb", "x" * 121, 5])
def test_reviewer_is_required(copy, value):
    done = decision(copy, reviewer=value)
    assert not done["ok"] and done["code"] == "REVIEWER_REQUIRED" and not (copy / REVIEW).exists()


@needs_tex
def test_note_is_bounded(copy):
    done = decision(copy, note="x" * 501)
    assert not done["ok"] and done["code"] == "VALIDATION_FAILED"


# ------------------------------------------------------------------ what was shown must still be what is on disk

@needs_tex
def test_pdf_modified_after_display_is_refused(copy):
    review = open_review(copy)
    (copy / PDF).write_bytes((copy / PDF).read_bytes() + b"\n%after display")
    done = decision(copy, review)
    assert not done["ok"] and done["code"] in ("PACKAGE_NOT_REVIEWABLE", "REVIEW_CONTEXT_CHANGED", "PDF_CHANGED_SINCE_VIEW")
    assert not (copy / REVIEW).exists() and status(copy)["status"] != "READY_TO_SEND"


@needs_tex
def test_sources_modified_after_display_are_refused(copy):
    review = open_review(copy)
    facts_file = copy / "facts.md"
    facts_file.write_bytes(facts_file.read_bytes() + b"\n<!-- fictional edit after display -->\n")
    done = decision(copy, review)
    assert not done["ok"] and done["code"] in ("PACKAGE_NOT_REVIEWABLE", "REVIEW_CONTEXT_CHANGED")
    assert not (copy / REVIEW).exists()


@needs_tex
def test_stale_or_altered_review_context_is_refused(copy):
    review = open_review(copy)
    done = decision(copy, review, context="0" * 64)
    assert not done["ok"] and done["code"] == "REVIEW_CONTEXT_CHANGED" and not (copy / REVIEW).exists()
    other = decision(copy, review, context=review["context"][:-1] + ("0" if review["context"][-1] != "0" else "1"))
    assert other["code"] == "REVIEW_CONTEXT_CHANGED"


@needs_tex
def test_a_different_displayed_document_hash_is_refused(copy):
    review = open_review(copy)
    done = decision(copy, review, viewed_sha256="1" * 64, typed_prefix="1" * 12)
    assert not done["ok"] and done["code"] == "PDF_CHANGED_SINCE_VIEW" and not (copy / REVIEW).exists()


@needs_tex
def test_changed_warnings_change_the_context(copy):
    """The context covers the warnings and the items to acknowledge: a different list is a different context."""
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "desktop" / "adapter"))
    import mcv_packages
    from modularcv import package
    summary = package.review_summary(copy, "fictional-cv")
    base = mcv_packages.review_context(summary)
    for mutate in (lambda s: s["to_acknowledge"]["warnings"].append("EXTRA_WARNING"),
                   lambda s: s["to_acknowledge"]["unsatisfied_required"].pop(),
                   lambda s: s["to_acknowledge"]["pending_directives"].append("d1"),
                   lambda s: s["reviewed"].update(plan_sha256="0" * 64),
                   lambda s: s["document"].update(sha256="0" * 64),
                   lambda s: s["state_now"]["reasons"].append("SOURCE_CHANGED_SINCE_PACKAGING")):
        changed = json.loads(json.dumps(summary))
        mutate(changed)
        assert mcv_context(mcv_packages, changed) != base


def mcv_context(module, summary):
    return module.review_context(summary)


# ------------------------------------------------------------------ the package must be reviewable

@needs_tex
def test_unverifiable_package_cannot_be_approved(copy):
    def writable(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    shutil.rmtree(copy / ".git", onerror=writable)
    review = open_review(copy)
    assert review["status"]["status"] == "NEEDS_REVIEW" and "SOURCE_COMMIT_UNVERIFIABLE" in review["status"]["reasons"]
    done = decision(copy, review)
    assert not done["ok"] and done["code"] == "PACKAGE_NOT_REVIEWABLE"
    assert any(d["code"] == "SOURCE_COMMIT_UNVERIFIABLE" for d in done["details"]) and not (copy / REVIEW).exists()


@needs_tex
def test_missing_pdf_cannot_be_approved(copy):
    review = open_review(copy)
    (copy / PDF).unlink()
    done = decision(copy, review)
    assert not done["ok"] and done["code"] == "FINAL_DOCUMENT_MISSING" and not (copy / REVIEW).exists()


@needs_tex
def test_package_name_must_be_valid_and_present(copy):
    for name in ("../x", "Bad Name", "no-such-package"):
        review = open_review(copy)
        done = decision(copy, review, name=name)
        assert not done["ok"] and done["code"] in ("PACKAGE_NAME_INVALID", "PACKAGE_UNREADABLE")


@needs_tex
def test_existing_review_is_never_overwritten(copy):
    assert decision(copy)["ok"]
    first = (copy / REVIEW).read_bytes()
    again = decision(copy)                                   # context of the page that was open before: stale
    assert not again["ok"] and again["code"] in ("REVIEW_EXISTS", "REVIEW_CONTEXT_CHANGED", "PACKAGE_NOT_REVIEWABLE")
    fresh = open_review(copy)
    reject = decision(copy, fresh, decision="REJECTED")      # a person cannot flip it from the screen either
    assert not reject["ok"] and reject["code"] in ("REVIEW_EXISTS", "PACKAGE_NOT_REVIEWABLE", "REVIEW_CONTEXT_CHANGED")
    assert (copy / REVIEW).read_bytes() == first and status(copy)["status"] == "READY_TO_SEND"


@needs_tex
def test_a_review_left_by_the_cli_is_not_overwritten_either(copy):
    sys.path.insert(0, str(REPO))
    from modularcv import package
    package.record_review(copy, "fictional-cv", "REJECTED", "Fictional Reviewer", "existing")   # isolated engine-level fixture
    before = (copy / REVIEW).read_bytes()
    done = decision(copy, open_review(copy))
    assert not done["ok"] and (copy / REVIEW).read_bytes() == before


# ------------------------------------------------------------------ a change while recording

@needs_tex
def test_a_review_that_does_not_match_what_was_shown_is_withdrawn(copy):
    """Simulates the residual race: the engine's own read differs from what was compared. The written file is withdrawn."""
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "desktop" / "adapter"))
    import mcv_packages
    review = open_review(copy)
    sha = review["summary"]["document"]["sha256"]
    real = mcv_packages.package.record_review

    def racing(root, name, *args, **kwargs):
        result = real(root, name, *args, **kwargs)
        target = Path(root) / REVIEW
        document = json.loads(target.read_text(encoding="utf-8"))
        document["document_sha256"] = "9" * 64                  # as if other bytes had been recorded
        target.write_text(json.dumps(document), encoding="utf-8")
        return result

    mcv_packages.package.record_review = racing
    try:
        with pytest.raises(mcv_packages.Refusal) as caught:
            mcv_packages.op_package_approve(dict(root=str(copy), name="fictional-cv", decision="APPROVED", reviewer="Fictional Reviewer",
                                                 confirm_examined=True, confirm_final=True, context=review["context"],
                                                 viewed_sha256=sha, typed_prefix=sha[:12]))
    finally:
        mcv_packages.package.record_review = real
    assert caught.value.code == "REVIEW_CONTEXT_CHANGED"
    assert not (copy / REVIEW).exists() and status(copy)["status"] == "NEEDS_REVIEW"


@needs_tex
def test_status_is_never_ready_when_the_pdf_changed_during_recording(copy):
    """A change landing right after the engine's read: the verdict is recomputed and cannot stay READY."""
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "desktop" / "adapter"))
    import mcv_packages
    review = open_review(copy)
    sha = review["summary"]["document"]["sha256"]
    real_status = mcv_packages.package.status
    calls = {"n": 0}

    def late_change(root, name):
        calls["n"] += 1
        if calls["n"] >= 4:    # the verdict computed after the review was written
            (Path(root) / PDF).write_bytes((Path(root) / PDF).read_bytes() + b"\n%late change")
        return real_status(root, name)

    mcv_packages.package.status = late_change
    try:
        done = mcv_packages.op_package_approve(dict(root=str(copy), name="fictional-cv", decision="APPROVED",
                                                    reviewer="Fictional Reviewer", confirm_examined=True, confirm_final=True,
                                                    context=review["context"], viewed_sha256=sha, typed_prefix=sha[:12]))
    finally:
        mcv_packages.package.status = real_status
    assert done["recorded"] is True and done["status"]["status"] != "READY_TO_SEND"
    assert status(copy)["status"] != "READY_TO_SEND"


@needs_tex
def test_withdrawal_never_deletes_a_file_replaced_by_another_process(copy):
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "desktop" / "adapter"))
    import mcv_packages
    review = open_review(copy)
    sha = review["summary"]["document"]["sha256"]
    real = mcv_packages.package.record_review

    def replaced(root, name, *args, **kwargs):
        result = real(root, name, *args, **kwargs)
        # another process swaps in its own review (other reviewer) and the one we wrote no longer matches what was compared
        target = Path(root) / REVIEW
        document = json.loads(target.read_text(encoding="utf-8"))
        document.update(reviewer="Somebody Else", note="written by another process", document_sha256="9" * 64)
        target.write_text(json.dumps(document), encoding="utf-8")
        return result

    mcv_packages.package.record_review = replaced
    try:
        with pytest.raises(mcv_packages.Refusal) as caught:
            mcv_packages.op_package_approve(dict(root=str(copy), name="fictional-cv", decision="APPROVED", reviewer="Fictional Reviewer",
                                                 confirm_examined=True, confirm_final=True, context=review["context"],
                                                 viewed_sha256=sha, typed_prefix=sha[:12]))
    finally:
        mcv_packages.package.record_review = real
    assert caught.value.code == "REVIEW_CONTEXT_CHANGED" and "left untouched" in caught.value.message
    kept = json.loads((copy / REVIEW).read_text(encoding="utf-8"))
    assert kept["reviewer"] == "Somebody Else"                    # not ours: never deleted
    assert status(copy)["status"] != "READY_TO_SEND"              # and its evidence does not match: never ready


def test_withdrawal_helper_only_removes_the_exact_file_it_wrote(tmp_path):
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "desktop" / "adapter"))
    import mcv_packages
    target = tmp_path / "review.json"
    ours = {"decision": "APPROVED", "reviewer": "R", "note": "n"}
    raw = json.dumps(ours).encode()
    target.write_bytes(raw)
    assert mcv_packages._withdraw_if_ours(target, raw, ours, "APPROVED", "R", "n") is False and not target.exists()
    target.write_bytes(raw + b" ")                                   # replaced since we read it
    assert mcv_packages._withdraw_if_ours(target, raw, ours, "APPROVED", "R", "n") is True and target.exists()
    other = dict(ours, reviewer="Other")                             # content is not ours
    target.write_bytes(json.dumps(other).encode())
    assert mcv_packages._withdraw_if_ours(target, json.dumps(other).encode(), other, "APPROVED", "R", "n") is True and target.exists()
    assert mcv_packages._withdraw_if_ours(target, None, None, "APPROVED", "R", "n") is True and target.exists()  # unreadable: kept
