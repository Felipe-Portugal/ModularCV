"""Packages, exact-PDF reading, review and status through the Desktop adapter.

Real engine, fictional data only. The workspace under test is a throw-away copy of the public example turned into an
independent Git repository in a temporary folder (never the user's workspace, never this repository). Nothing here
fabricates a READY_TO_SEND status: the single approval written in these tests is a clearly fictional engine-level one,
in an isolated copy, used only to check that a change revokes it.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "desktop" / "adapter" / "mcv_adapter.py"
EXAMPLE = REPO / "examples" / "workspace"
PDFLATEX = shutil.which("pdflatex")
needs_tex = pytest.mark.skipif(PDFLATEX is None, reason="pdflatex is not installed")
GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test", "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test"}


def call(path=None, stderr=False, **request):
    env = {"MODULARCV_ENGINE_DIR": str(REPO), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
           "PATH": os.environ["PATH"] if path is None else path}
    done = subprocess.run([sys.executable, "-I", str(ADAPTER)], input=json.dumps(request).encode(), capture_output=True,
                          timeout=240, env=env)
    assert done.returncode == 0, done.stderr
    assert done.stderr == b"", "the adapter must not log anything"
    return json.loads(done.stdout)


def git(ws, *args):
    return subprocess.run(["git", *args], cwd=str(ws), capture_output=True, check=True, text=True,
                          env=dict(os.environ, **GIT_ENV)).stdout.strip()


def make_git_workspace(target):
    shutil.copytree(EXAMPLE, target)
    git(target, "init", "-q")
    git(target, "add", "-A")
    git(target, "commit", "-q", "-m", "fictional test sources")
    return target


def tree_hash(ws):
    digest = hashlib.sha256()
    for path in sorted(Path(ws).rglob("*")):
        if ".git" in path.parts:
            continue
        digest.update(str(path.relative_to(ws)).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def generate(ws, offer="backend-intern.json"):
    """offer -> plan -> .tex (the existing step-3 operations). Returns (plan name, tex name)."""
    plan = call(op="plan", root=str(ws), offer_file=offer, write=True)
    assert plan["ok"], plan
    plan_name = plan["written"]["file"]
    tex = call(op="render", root=str(ws), offer_file=offer, plan_file=plan_name)
    assert tex["ok"], tex
    return plan_name, tex["tex"]["file"].split("/")[-1]


def create_package(ws, name="fictional-cv", **over):
    plan_name, tex_name = generate(ws)
    request = dict(op="package_create", root=str(ws), name=name, offer_file="backend-intern.json",
                   plan_file=plan_name, tex_file=tex_name)
    request.update(over)
    return call(**request)


@pytest.fixture(scope="module")
def ready_ws(tmp_path_factory):
    """A git workspace holding one package created with the integrated compilation (not approved)."""
    if PDFLATEX is None:
        pytest.skip("pdflatex is not installed")
    ws = make_git_workspace(tmp_path_factory.mktemp("pkg") / "ws")
    done = create_package(ws)
    assert done["ok"], done
    return ws


@pytest.fixture()
def copy(ready_ws, tmp_path):
    target = tmp_path / "w"
    shutil.copytree(ready_ws, target)
    return target


# ------------------------------------------------------------------ the chain, created and reviewed

@needs_tex
def test_chain_creates_package_that_is_not_ready(ready_ws):
    review = call(op="package_review", root=str(ready_ws), name="fictional-cv")
    assert review["ok"], review
    state = review["status"]
    assert state["status"] == "NEEDS_REVIEW" and "HUMAN_REVIEW_REQUIRED" in state["reasons"]
    summary = review["summary"]
    assert summary["document"]["origin"] == "COMPILED_FROM_VERIFIED_TEX"
    assert summary["document"]["pages"] >= 1 and len(summary["document"]["sha256"]) == 64
    assert summary["limits"] and summary["to_acknowledge"]["page_verdict"]
    assert review["approval"] == {"graphical": True, "cli_available": True} and len(review["context"]) == 64
    assert not (ready_ws / "applications" / "fictional-cv" / "cv" / "cv-quality-review.json").exists()


@needs_tex
def test_creation_report_never_claims_ready(ready_ws, tmp_path):
    ws = make_git_workspace(tmp_path / "w2")
    done = create_package(ws, name="another-cv")
    assert done["ok"] and done["ready_to_send"] is False
    assert done["package"]["state"] != "READY_TO_SEND" and done["package"]["pdf_origin"] == "COMPILED_FROM_VERIFIED_TEX"
    assert done["next"] == "REVIEW_THEN_APPROVE_IN_A_TERMINAL"


@needs_tex
def test_review_summary_holds_no_resume_text(ready_ws):
    raw = json.dumps(call(op="package_review", root=str(ready_ws), name="fictional-cv"))
    assert "Built REST endpoints" not in raw and "base64" not in raw


@needs_tex
def test_status_and_review_never_modify_the_workspace(copy):
    before = tree_hash(copy)
    call(op="package_status", root=str(copy), name="fictional-cv")
    call(op="package_review", root=str(copy), name="fictional-cv")
    call(op="packages_list", root=str(copy))
    call(op="pdf_read", root=str(copy), package="fictional-cv")
    assert tree_hash(copy) == before


@needs_tex
def test_no_commit_is_ever_made(tmp_path):
    ws = make_git_workspace(tmp_path / "w3")
    head = git(ws, "rev-parse", "HEAD")
    assert create_package(ws)["ok"]
    call(op="package_review", root=str(ws), name="fictional-cv")
    assert git(ws, "rev-parse", "HEAD") == head and git(ws, "rev-list", "--count", "HEAD") == "1"


# ------------------------------------------------------------------ history

def test_history_is_empty_without_packages(tmp_path):
    ws = make_git_workspace(tmp_path / "w")
    listing = call(op="packages_list", root=str(ws))
    assert listing["ok"] and listing["packages"] == [] and listing["total"] == 0


@needs_tex
def test_history_lists_real_packages_without_invented_dates(ready_ws):
    listing = call(op="packages_list", root=str(ready_ws))
    row = next(p for p in listing["packages"] if p["name"] == "fictional-cv")
    assert row["readable"] and row["job_key"] == "example-backend-intern" and row["language"] in ("en", "fr")
    assert row["document"]["available"] and row["state"]["status"] == "NEEDS_REVIEW"
    assert not {"created", "created_at", "modified", "date", "mtime"} & set(row)


@needs_tex
def test_history_survives_a_broken_package(copy):
    broken = copy / "packages" / "broken-one"
    broken.mkdir(parents=True)
    (broken / "package.json").write_text("{not json", encoding="utf-8")
    listing = call(op="packages_list", root=str(copy))
    names = {p["name"]: p for p in listing["packages"]}
    assert names["broken-one"]["readable"] is False and names["broken-one"]["code"]
    assert names["fictional-cv"]["readable"]
    assert (names["broken-one"].get("state") or {}).get("status") != "READY_TO_SEND"


# ------------------------------------------------------------------ changes are detected by a fresh evaluation

@needs_tex
def test_modified_pdf_is_detected_on_recalculation(copy):
    pdf_path = copy / "applications" / "fictional-cv" / "cv" / "resume.pdf"
    original = pdf_path.read_bytes()
    pdf_path.write_bytes(original + b"\n%appended")
    state = call(op="package_status", root=str(copy), name="fictional-cv")["status"]
    assert state["status"] in ("NEEDS_REVIEW", "BLOCKED") and state["reasons"]


@needs_tex
def test_damaged_pdf_is_refused_when_read(copy):
    pdf_path = copy / "applications" / "fictional-cv" / "cv" / "resume.pdf"
    pdf_path.write_bytes(pdf_path.read_bytes()[:200])
    done = call(op="pdf_read", root=str(copy), package="fictional-cv")
    assert not done["ok"] and done["code"] == "PDF_MALFORMED" and "base64" not in done
    assert call(op="package_status", root=str(copy), name="fictional-cv")["status"]["status"] != "READY_TO_SEND"


@needs_tex
def test_missing_pdf(copy):
    (copy / "applications" / "fictional-cv" / "cv" / "resume.pdf").unlink()
    done = call(op="pdf_read", root=str(copy), package="fictional-cv")
    assert not done["ok"] and done["code"] == "PDF_MISSING"
    review = call(op="package_review", root=str(copy), name="fictional-cv")
    assert review["ok"] and review["summary"]["document"]["sha256"] is None
    assert review["status"]["status"] != "READY_TO_SEND"
    row = call(op="packages_list", root=str(copy))["packages"][0]
    assert row["document"]["available"] is False


@needs_tex
def test_changed_source_is_detected(copy):
    facts_file = copy / "facts.md"
    facts_file.write_bytes(facts_file.read_bytes() + b"\n<!-- fictional edit -->\n")
    state = call(op="package_status", root=str(copy), name="fictional-cv")["status"]
    assert state["status"] != "READY_TO_SEND" and state["reasons"]


@needs_tex
def test_inconsistent_snapshot_is_never_ready(copy):
    snapshot = copy / "packages" / "fictional-cv" / "provenance" / "source-snapshot.json"
    document = json.loads(snapshot.read_text(encoding="utf-8"))
    document["snapshot_fingerprint"] = "0" * 64
    snapshot.write_text(json.dumps(document), encoding="utf-8")
    state = call(op="package_status", root=str(copy), name="fictional-cv")["status"]
    assert state["status"] in ("BLOCKED", "NEEDS_REVIEW") and state["status"] != "READY_TO_SEND" and state["reasons"]


@needs_tex
def test_isolated_engine_approval_is_revoked_by_a_change(copy):
    """Engine-level only: a clearly fictional approval, in an isolated copy, to check that a change takes it away.
    The application itself has no approval operation (see test_no_graphical_approval_operation)."""
    sys.path.insert(0, str(REPO))
    from modularcv import package
    result = package.record_review(copy, "fictional-cv", "APPROVED", "Fictional Reviewer", "isolated engine test")
    assert result["state"] == "READY_TO_SEND"
    assert call(op="package_status", root=str(copy), name="fictional-cv")["status"]["status"] == "READY_TO_SEND"
    pdf_path = copy / "applications" / "fictional-cv" / "cv" / "resume.pdf"
    pdf_path.write_bytes(pdf_path.read_bytes() + b"\n%changed")
    revoked = call(op="package_status", root=str(copy), name="fictional-cv")["status"]
    assert revoked["status"] != "READY_TO_SEND"


def test_only_the_confirmed_approval_operation_exists(tmp_path):
    ws = make_git_workspace(tmp_path / "w")
    for op in ("approve", "package_review_record", "record_review", "package_set_status", "package_ready"):
        done = call(op=op, root=str(ws), name="x", decision="APPROVED", reviewer="x")
        assert not done["ok"] and done["code"] == "OPERATION_NOT_ALLOWED"


# ------------------------------------------------------------------ refusals when creating

@needs_tex
def test_existing_package_is_never_overwritten(copy):
    before = tree_hash(copy)
    done = call(op="package_create", root=str(copy), name="fictional-cv", offer_file="backend-intern.json",
                plan_file=next(p.name for p in (copy / "plans").iterdir()),
                tex_file=next(p.name for p in (copy / "out").iterdir() if p.suffix == ".tex"))
    assert not done["ok"] and done["code"] == "PACKAGE_EXISTS"
    assert tree_hash(copy) == before


def test_provenance_refused_outside_a_git_repository(tmp_path):
    if PDFLATEX is None:
        pytest.skip("pdflatex is not installed")
    ws = tmp_path / "plain"
    shutil.copytree(EXAMPLE, ws)
    done = create_package(ws)
    assert not done["ok"] and done["code"] == "PROVENANCE_REFUSED"
    assert not (ws / "applications").exists() or not any((ws / "applications").iterdir())
    assert not any((ws / "packages").glob("*")) if (ws / "packages").exists() else True


def test_uncommitted_source_refuses_the_package(tmp_path):
    if PDFLATEX is None:
        pytest.skip("pdflatex is not installed")
    ws = make_git_workspace(tmp_path / "dirty")
    plan_name, tex_name = generate(ws)
    offer = ws / "offers" / "backend-intern.json"
    offer.write_bytes(offer.read_bytes().replace(b"Backend", b"Back-end", 1))
    done = call(op="package_create", root=str(ws), name="dirty-cv", offer_file="backend-intern.json",
                plan_file=plan_name, tex_file=tex_name)
    assert not done["ok"] and done["code"] in ("PROVENANCE_REFUSED", "ASSEMBLY_REFUSED", "INPUT_INVALID", "TEX_NOT_FROM_ASSEMBLY")
    assert not (ws / "packages" / "dirty-cv").exists()
    assert git(ws, "rev-list", "--count", "HEAD") == "1"


def test_latex_unavailable_creates_nothing(tmp_path):
    ws = make_git_workspace(tmp_path / "w")
    plan_name, tex_name = generate(ws)
    done = call(path="", op="package_create", root=str(ws), name="no-tex-cv", offer_file="backend-intern.json",
                plan_file=plan_name, tex_file=tex_name)
    assert not done["ok"] and done["code"] == "PDF_UNAVAILABLE"
    assert not (ws / "packages" / "no-tex-cv").exists() and not (ws / "applications" / "no-tex-cv").exists()


@pytest.mark.parametrize("name", ["Bad Name", "../x", "a/b", "UPPER", "", ".." + os.sep + "y", "x" * 3 + "\\z"])
def test_invalid_package_names_refused(tmp_path, name):
    ws = make_git_workspace(tmp_path / "w")
    for op in ("package_review", "package_status", "pdf_read"):
        request = dict(op=op, root=str(ws), **({"package": name} if op == "pdf_read" else {"name": name}))
        done = call(**request)
        assert not done["ok"] and done["code"] == "PACKAGE_NAME_INVALID", (op, done)


def test_create_refuses_foreign_paths(tmp_path):
    ws = make_git_workspace(tmp_path / "w")
    for field, value in (("plan_file", "../facts.md"), ("tex_file", "C:\\Windows\\win.ini"), ("tex_file", "x/../y.tex"),
                         ("plan_file", "facts.md")):
        request = dict(op="package_create", root=str(ws), name="x-cv", offer_file="backend-intern.json",
                       plan_file="p.json", tex_file="t.tex")
        request[field] = value
        done = call(**request)
        assert not done["ok"] and done["code"] in ("PATH_UNSAFE", "FILE_UNREADABLE"), (field, value, done)


def test_create_never_accepts_a_supplied_pdf(tmp_path):
    """A `pdf_file` or `pdf` field is ignored: the engine's own compilation is the only source of a packaged PDF."""
    ws = make_git_workspace(tmp_path / "w")
    plan_name, tex_name = generate(ws)
    (ws / "out" / "other.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    done = call(path="", op="package_create", root=str(ws), name="x-cv", offer_file="backend-intern.json",
                plan_file=plan_name, tex_file=tex_name, pdf_file="other.pdf", pdf="other.pdf")
    assert not done["ok"] and done["code"] == "PDF_UNAVAILABLE"


# ------------------------------------------------------------------ the PDF reader is confined

@needs_tex
def test_pdf_read_returns_the_exact_bytes_and_their_hash(ready_ws):
    import base64
    done = call(op="pdf_read", root=str(ready_ws), package="fictional-cv")
    data = base64.b64decode(done["base64"])
    on_disk = (ready_ws / "applications" / "fictional-cv" / "cv" / "resume.pdf").read_bytes()
    assert data == on_disk and done["sha256"] == hashlib.sha256(on_disk).hexdigest() and done["bytes"] == len(on_disk)
    review = call(op="package_review", root=str(ready_ws), name="fictional-cv")
    assert review["summary"]["document"]["sha256"] == done["sha256"]
    meta_only = call(op="pdf_read", root=str(ready_ws), package="fictional-cv", with_bytes=False)
    assert "base64" not in meta_only and meta_only["sha256"] == done["sha256"]


@needs_tex
def test_pdf_read_of_a_generated_output(tmp_path):
    ws = make_git_workspace(tmp_path / "w")
    plan_name, _ = generate(ws)
    done = call(op="render", root=str(ws), offer_file="backend-intern.json", plan_file=plan_name, compile=True, name="my-cv-out")
    assert done["pdf"]["status"] == "COMPILED", done
    read = call(op="pdf_read", root=str(ws), output="my-cv-out")
    assert read["ok"] and read["file"] == "out/my-cv-out.pdf" and read["pages"] >= 1


@pytest.mark.parametrize("request_", [
    {"output": "../facts"}, {"output": "..\\facts"}, {"output": "C:\\Windows\\win"}, {"output": "a/b"}, {"output": "x.pdf"},
    {"output": ""}, {"package": "../../x"}, {"package": "a/../b"}, {"package": "C:"}, {},
    {"package": "x", "output": "y"}, {"package": 7}, {"output": ["a"]},
])
def test_pdf_read_cannot_leave_the_allowed_locations(tmp_path, request_):
    ws = make_git_workspace(tmp_path / "w")
    outside = tmp_path / "facts.pdf"
    outside.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Page>>endobj\n%%EOF")
    done = call(op="pdf_read", root=str(ws), **request_)
    assert not done["ok"] and "base64" not in done
    assert done["code"] in ("PATH_UNSAFE", "PACKAGE_NAME_INVALID", "BAD_REQUEST", "PDF_MISSING"), done


def test_pdf_read_refuses_a_linked_file(tmp_path):
    ws = make_git_workspace(tmp_path / "w")
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Page>>endobj\n%%EOF")
    (ws / "out").mkdir(exist_ok=True)
    try:
        os.symlink(str(secret), str(ws / "out" / "linked.pdf"))
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links need a privilege on this machine")
    done = call(op="pdf_read", root=str(ws), output="linked")
    assert not done["ok"] and done["code"] == "PATH_UNSAFE"


def test_non_pdf_content_is_refused(tmp_path):
    ws = make_git_workspace(tmp_path / "w")
    (ws / "out").mkdir(exist_ok=True)
    (ws / "out" / "fake.pdf").write_bytes(b"MZ not a pdf")
    done = call(op="pdf_read", root=str(ws), output="fake")
    assert not done["ok"] and done["code"] == "PDF_MALFORMED"
