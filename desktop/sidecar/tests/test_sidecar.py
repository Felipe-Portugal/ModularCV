"""The packaged engine (`mcv-engine.exe`, PyInstaller onedir) end to end, in a scrubbed environment.

Run by `desktop/verify.ps1` after the sidecar is built (MODULARCV_TEST_SIDECAR). Every run uses a minimal environment: no
Python on PATH, no MODULARCV_* variable, the executable copied away from the repository. Data is fictional and lives in
temporary folders; approvals here are clearly fictional engine-level ones, never real.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "workspace"
GIT = shutil.which("git")
PDFLATEX = shutil.which("pdflatex")


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    configured = os.environ.get("MODULARCV_TEST_SIDECAR")
    if not configured or not Path(configured).is_file():
        if os.environ.get("MODULARCV_REQUIRE_SIDECAR"):
            pytest.fail("the embedded engine is required but missing")
        pytest.skip("embedded engine not built")
    # prove independence from the build folder and from the repository: run a copy from somewhere else
    target = tmp_path_factory.mktemp("installed") / "engine"
    shutil.copytree(Path(configured).parent, target)
    return target / "mcv-engine.exe"


def environment(*tools):
    """A scrubbed environment: no Python, no Node, no MODULARCV_* ; only the directories of the tools asked for."""
    dirs = [str(Path(shutil.which(t)).parent) for t in tools if shutil.which(t)]
    return {"SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"), "PATH": os.pathsep.join(dirs),
            "TEMP": os.environ.get("TEMP", ""), "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
            "USERPROFILE": os.environ.get("USERPROFILE", ""), "APPDATA": os.environ.get("APPDATA", "")}


def run(engine, args, request=None, tools=(), cwd=None):
    stdin = None if request is None else json.dumps(request).encode()
    return subprocess.run([str(engine), *args], input=stdin, capture_output=True, timeout=240, env=environment(*tools),
                          cwd=str(cwd or engine.parent), stdin=None if stdin else subprocess.DEVNULL)


def adapter(engine, tools=(), **request):
    done = run(engine, ["adapter"], request, tools)
    assert done.returncode == 0, done.stderr
    assert done.stderr == b"", "the embedded engine must not log"
    return json.loads(done.stdout)


def git(ws, *args):
    return subprocess.run(["git", *args], cwd=str(ws), capture_output=True, check=True, text=True,
                          env=dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test", GIT_COMMITTER_NAME="Test",
                                   GIT_COMMITTER_EMAIL="test")).stdout.strip()


@pytest.fixture()
def ws(tmp_path):
    target = tmp_path / "ws"
    shutil.copytree(EXAMPLE, target)
    return target


@pytest.fixture()
def git_ws(ws):
    if GIT is None:
        pytest.skip("git is not installed on this machine")
    git(ws, "init", "-q")
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", "fictional test sources")
    return ws


# ------------------------------------------------------------------ the entry point is closed

def test_version_and_embedded_python(engine):
    done = run(engine, ["version"])
    assert done.returncode == 0 and json.loads(done.stdout) == {"engine": "0.2.0"}


@pytest.mark.parametrize("args", [[], ["rm", "-rf"], ["cli", "privacy", "--root", "."], ["cli", "facts", "check"], ["python", "-c", "print(1)"],
                                  ["adapter", "extra"], ["-c", "print(1)"], ["diagnose", "--evil"], ["cli", "facts", "check", "--root", "a", "b"]])
def test_unknown_modes_are_refused(engine, args):
    done = run(engine, args, request={} if args[:1] == ["adapter"] else None)
    assert done.returncode == 2 and b"OPERATION_NOT_ALLOWED" in done.stderr and not done.stdout.strip()


def test_adapter_operation_list_is_closed_inside_the_package(engine, ws):
    for op in ("run_shell", "approve", "record_review", "exec", "__import__"):
        done = adapter(engine, op=op, root=str(ws))
        assert not done["ok"] and done["code"] == "OPERATION_NOT_ALLOWED"


# ------------------------------------------------------------------ reading, validating, writing

def test_facts_check_uses_the_engine_cli(engine, ws):
    done = run(engine, ["cli", "facts", "check", "--root", str(ws)])
    assert done.returncode == 0 and json.loads(done.stdout)["status"] == "OK"
    (ws / "facts.md").write_text("<!-- modularcv: FactBase-v1 -->\n\n- [x] NOT_A_STATUS: broken\n", encoding="utf-8")
    bad = run(engine, ["cli", "facts", "check", "--root", str(ws)])
    assert bad.returncode != 0


def test_read_and_write_through_the_packaged_adapter(engine, ws):
    state = adapter(engine, op="read", root=str(ws))
    assert state["ok"] and state["facts"]["valid"]
    sha = state["facts"]["source_sha256"]
    implicit = adapter(engine, op="save_fact", root=str(ws), expected_sha256=sha, mode="update",
                       fact={"id": "exp.junior-dev.speed", "status": "CONFIRMED", "text": "Improved."})
    assert implicit["code"] == "CONFIRMATION_REQUIRED"
    saved = adapter(engine, op="save_fact", root=str(ws), expected_sha256=sha, mode="update",
                    fact={"id": "exp.junior-dev.speed", "status": "NOT_CONFIRMED", "text": "Improved, unmeasured."})
    assert saved["ok"]
    stale = adapter(engine, op="save_fact", root=str(ws), expected_sha256=sha, mode="update",
                    fact={"id": "exp.junior-dev.speed", "status": "NOT_CONFIRMED", "text": "Again."})
    assert stale["code"] == "CONFLICT"


def test_offer_matrix_plan_and_tex(engine, ws):
    offers = adapter(engine, op="offers_list", root=str(ws))
    assert offers["ok"] and any(o["file"] == "backend-intern.json" for o in offers["offers"])
    matrix = adapter(engine, op="matrix", root=str(ws), offer_file="backend-intern.json")
    assert matrix["ok"] and {r["state"] for r in matrix["matrix"]["requirements"]} & {"DIRECT", "ADJACENT", "ABSENT"}
    plan = adapter(engine, op="plan", root=str(ws), offer_file="backend-intern.json", write=True)
    assert plan["ok"]
    tex = adapter(engine, op="render", root=str(ws), offer_file="backend-intern.json", plan_file=plan["written"]["file"])
    assert tex["ok"] and tex["ready_to_send"] is False and (ws / tex["tex"]["file"]).is_file()
    again = adapter(engine, op="render", root=str(ws), offer_file="backend-intern.json", plan_file=plan["written"]["file"])
    assert again["code"] == "OUTPUT_EXISTS"


# ------------------------------------------------------------------ dependencies are reported, never hidden

def test_diagnostics_without_git_or_latex(engine, git_ws):
    done = run(engine, ["diagnose", "--root", str(git_ws)], tools=())
    d = json.loads(done.stdout)
    assert d["ok"] and d["engine"]["embedded"] is True and d["engine"]["version"] == "0.2.0"
    assert d["git"]["status"] == "ABSENT" and d["latex"]["pdflatex"] == "ABSENT" and d["latex"]["compile"] == "UNAVAILABLE"
    assert d["provenance"] == {"status": "UNVERIFIABLE", "code": "GIT_UNAVAILABLE", "reason": None}
    assert str(git_ws) not in done.stdout.decode()


def test_diagnostics_with_git(engine, git_ws):
    d = json.loads(run(engine, ["diagnose", "--root", str(git_ws)], tools=("git",)).stdout)
    assert d["git"]["status"] == "FOUND" and d["provenance"]["status"] == "VERIFIED"
    (git_ws / "facts.md").write_bytes((git_ws / "facts.md").read_bytes() + b"\n<!-- edit -->\n")
    dirty = json.loads(run(engine, ["diagnose", "--root", str(git_ws)], tools=("git",)).stdout)
    assert dirty["provenance"]["status"] == "UNVERIFIABLE" and dirty["provenance"]["code"] == "SOURCE_NOT_AT_COMMIT"


def test_diagnostics_outside_a_repository_and_without_workspace(engine, ws):
    d = json.loads(run(engine, ["diagnose", "--root", str(ws)], tools=("git",)).stdout)
    assert d["provenance"]["status"] == "UNVERIFIABLE" and d["provenance"]["code"]
    nothing = json.loads(run(engine, ["diagnose"], tools=("git",)).stdout)
    assert nothing["provenance"]["status"] == "NOT_CHECKED"


def test_missing_latex_does_not_prevent_the_tex(engine, ws):
    plan = adapter(engine, op="plan", root=str(ws), offer_file="backend-intern.json", write=True)
    done = adapter(engine, op="render", root=str(ws), offer_file="backend-intern.json", plan_file=plan["written"]["file"], compile=True)
    assert done["ok"] and (ws / done["tex"]["file"]).is_file()
    assert done["pdf"]["status"] == "UNAVAILABLE" and done["ready_to_send"] is False
    assert adapter(engine, op="offers_list", root=str(ws))["ok"] and adapter(engine, op="read", root=str(ws))["ok"]


def test_missing_git_gives_a_clear_provenance_refusal(engine, ws):
    if PDFLATEX is None:
        pytest.skip("pdflatex is not installed on this machine")
    plan = adapter(engine, op="plan", root=str(ws), offer_file="backend-intern.json", write=True)
    tex = adapter(engine, op="render", root=str(ws), offer_file="backend-intern.json", plan_file=plan["written"]["file"])
    done = adapter(engine, tools=("pdflatex",), op="package_create", root=str(ws), name="no-git-cv", offer_file="backend-intern.json",
                   plan_file=plan["written"]["file"], tex_file=tex["tex"]["file"].split("/")[-1])
    assert not done["ok"] and done["code"] == "PROVENANCE_REFUSED"
    assert not (ws / "packages" / "no-git-cv").exists()


# ------------------------------------------------------------------ the whole chain through the packaged engine

@pytest.mark.skipif(PDFLATEX is None, reason="pdflatex is not installed on this machine")
def test_pdf_package_review_and_approval_chain(engine, git_ws):
    head = git(git_ws, "rev-parse", "HEAD")
    tools = ("git", "pdflatex")
    plan = adapter(engine, tools, op="plan", root=str(git_ws), offer_file="backend-intern.json", write=True)
    pdf_done = adapter(engine, tools, op="render", root=str(git_ws), offer_file="backend-intern.json", plan_file=plan["written"]["file"],
                       compile=True)
    assert pdf_done["pdf"]["status"] == "COMPILED", pdf_done
    tex_name = pdf_done["tex"]["file"].split("/")[-1]
    created = adapter(engine, tools, op="package_create", root=str(git_ws), name="installed-cv", offer_file="backend-intern.json",
                      plan_file=plan["written"]["file"], tex_file=tex_name)
    assert created["ok"] and created["ready_to_send"] is False and created["package"]["pdf_origin"] == "COMPILED_FROM_VERIFIED_TEX"
    review = adapter(engine, tools, op="package_review", root=str(git_ws), name="installed-cv")
    assert review["ok"] and review["status"]["status"] == "NEEDS_REVIEW"
    pdf_bytes = base64.b64decode(adapter(engine, tools, op="pdf_read", root=str(git_ws), package="installed-cv")["base64"])
    assert pdf_bytes.startswith(b"%PDF-")
    sha = review["summary"]["document"]["sha256"]
    # the explicit confirmations are required, through the packaged engine too
    refused = adapter(engine, tools, op="package_approve", root=str(git_ws), name="installed-cv", decision="APPROVED",
                      reviewer="Fictional Reviewer", confirm_examined=False, confirm_final=True, context=review["context"],
                      viewed_sha256=sha, typed_prefix=sha[:12])
    assert refused["code"] == "CONFIRMATION_REQUIRED"
    done = adapter(engine, tools, op="package_approve", root=str(git_ws), name="installed-cv", decision="APPROVED",
                   reviewer="Fictional Reviewer", confirm_examined=True, confirm_final=True, context=review["context"],
                   viewed_sha256=sha, typed_prefix=sha[:12])
    assert done["ok"] and done["status"]["status"] == "READY_TO_SEND"
    assert adapter(engine, tools, op="package_status", root=str(git_ws), name="installed-cv")["status"]["status"] == "READY_TO_SEND"
    # revocation
    target = git_ws / "applications" / "installed-cv" / "cv" / "resume.pdf"
    target.write_bytes(target.read_bytes() + b"\n%changed")
    assert adapter(engine, tools, op="package_status", root=str(git_ws), name="installed-cv")["status"]["status"] != "READY_TO_SEND"
    assert git(git_ws, "rev-parse", "HEAD") == head
    assert not (git_ws / ".modularcv-desktop.lock").exists()
