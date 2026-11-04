"""CV packages: creation, evidence chain, human approval of the exact PDF, fail-closed readiness (M7-B). Synthetic data only.

Every approval written here is a *fictional* approval inside a temporary workspace (a test fixture); nothing in this file is,
or imitates, an approval by a real person."""
import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from modularcv import __main__ as cli
from modularcv import canonical, chain, latex, metadata, package, pdf, readiness, review, snapshot
from synthetic import tree_hash

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "workspace"
GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
       "-c", "core.autocrlf=false"]
REAL_PDFLATEX = pdf.find_pdflatex() is not None
FAKE_PDF = b"%PDF-1.5\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
OTHER_PDF = b"%PDF-1.4\n% another document\n%%EOF\n"
NAME = "demo"
SECRETS = ("Example Software Inc", "Jordan Example", "jordan@example.com", "Built REST endpoints")


def git(root, *args):
    return subprocess.run(GIT + list(args), cwd=str(root), check=True, capture_output=True).stdout.decode().strip()


def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def make_pdf(tex_bytes):
    return pdf.compile_tex(tex_bytes).pdf if REAL_PDFLATEX else FAKE_PDF


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, document):
    Path(path).write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    """A committed synthetic workspace holding a plan, a .tex, a PDF and the package `demo` (not approved)."""
    root = tmp_path_factory.mktemp("pkg") / "ws"
    shutil.copytree(str(EXAMPLE_DIR), str(root))
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "sources")
    (root / "plans").mkdir()
    (root / "out").mkdir()
    offer = str(root / "offers" / "backend-intern.json")
    assert cli.main(["plan", "--offer", offer, "--root", str(root), "--out", "plans/p.json"]) == 0
    assert cli.main(["render", "--plan", str(root / "plans/p.json"), "--offer", offer, "--root", str(root), "--out", "out/cv.tex"]) == 0
    tex = (root / "out" / "cv.tex").read_bytes()
    (root / "out" / "cv.pdf").write_bytes(make_pdf(tex))
    package.create(root, NAME, offer, (root / "plans/p.json").read_bytes(), tex, (root / "out/cv.pdf").read_bytes())
    return root


@pytest.fixture
def ws(template, tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(str(template), str(root))
    return root


def offer_of(ws, name="backend-intern.json"):
    return str(ws / "offers" / name)


def status_of(ws, name=NAME):
    verdict = package.status(ws, name)
    return verdict["status"], set(verdict["reasons"]), {d["code"] for d in verdict["details"]}


def approve(ws, name=NAME):
    return package.record_review(ws, name, "APPROVED", "Fictional Reviewer")


def app_file(ws, key, name=NAME):
    return ws / "applications" / name / "cv" / package.FILE_NAMES[key]


def reseal(ws, name=NAME, drop=()):
    """Forge a *consistent* package: rebuild the snapshot and both fingerprints after an edit. Returns nothing."""
    pkg_path = ws / "packages" / name / "package.json"
    snap_path = ws / "packages" / name / "provenance" / "source-snapshot.json"
    old = read_json(snap_path)
    items = [(e["role"], e["path"]) for e in old["entries"] if e["role"] not in drop]
    new = snapshot.build(ws, items)
    write_json(snap_path, new)
    pkg = read_json(pkg_path)
    pkg["snapshot_fingerprint"] = new["snapshot_fingerprint"]
    pkg["package_fingerprint"] = canonical.fingerprint({k: v for k, v in pkg.items() if k != "package_fingerprint"})
    write_json(pkg_path, pkg)


# --- creation ---------------------------------------------------------------------------------------------------

def test_creating_a_package_is_never_an_approval(template):
    pkg = read_json(template / "packages" / NAME / "package.json")
    assert pkg["schema"] == "ApplicationPackage-v2" and pkg["routing"] == {"workflow_state": "UNEVALUATED", "reasons": []}
    assert not (template / "applications" / NAME / "cv" / review.FILE_NAME).exists()
    status, reasons, _ = status_of(template)
    assert status == readiness.NEEDS_REVIEW and reasons == {"HUMAN_REVIEW_REQUIRED"}


def test_the_files_of_a_package_and_the_snapshot_roles(template):
    cv = template / "applications" / NAME / "cv"
    assert sorted(p.name for p in cv.iterdir()) == ["assembly.json", "metadata.json", "resume.pdf", "resume.tex", "tailoring-plan.json"]
    document = read_json(template / "packages" / NAME / "provenance" / "source-snapshot.json")
    assert sorted(e["role"] for e in document["entries"]) == sorted(
        ["facts", "profile", "resume_content", "offer", "tailoring_plan", "assembly", "cv_tex", "cv_metadata", "cv_pdf"])
    kinds = {e["role"]: e["kind"] for e in document["entries"]}
    assert kinds["cv_pdf"] == "binary" and kinds["cv_tex"] == "text" and not snapshot.verify(document, template)


def test_the_metadata_is_version_3_valid_and_has_no_clock_or_personal_constant(template):
    document = read_json(template / "applications" / NAME / "cv" / "metadata.json")
    assert document["schema_version"] == "3" and metadata.problems(document) == []
    assert "generated_at" not in document and document["tex_sha256"] == canonical.sha256_bytes(app_file(template, "tex").read_bytes())
    assert document["pdf_sha256"] == canonical.sha256_bytes(app_file(template, "pdf").read_bytes())
    assert document["job_sha256"] == document["inputs"]["offer_sha256"] == read_json(app_file(template, "plan"))["inputs"]["offer_sha256"]
    assert document["unsatisfied_required"] and document["warnings"] and document["tailored_cv_id"] == chain.tailored_cv_id(
        read_json(app_file(template, "plan")), document["engine_version"])


def test_the_identity_is_stable_and_independent_of_the_package_name_and_the_location(template, tmp_path):
    other = tmp_path / "copy"
    shutil.copytree(str(template), str(other))
    offer = offer_of(other)
    summary = package.create(other, "elsewhere", offer, (other / "plans/p.json").read_bytes(), (other / "out/cv.tex").read_bytes(),
                             (other / "out/cv.pdf").read_bytes())
    assert summary["tailored_cv_id"] == read_json(app_file(template, "metadata"))["tailored_cv_id"]
    plan = read_json(app_file(template, "plan"))
    changed = copy.deepcopy(plan)
    changed["plan_sha256"] = "0" * 64
    assert chain.tailored_cv_id(changed) != chain.tailored_cv_id(plan)
    assert chain.tailored_cv_id(plan, "9.9.9") != chain.tailored_cv_id(plan)


def test_a_package_changes_none_of_its_sources(template, tmp_path):
    other = tmp_path / "copy"
    shutil.copytree(str(template), str(other))
    before = {p: (other / p).read_bytes() for p in ("facts.md", "profile.json", "content/resume.json", "offers/backend-intern.json",
                                                  "plans/p.json", "out/cv.tex", "out/cv.pdf")}
    package.create(other, "second", offer_of(other), (other / "plans/p.json").read_bytes(), (other / "out/cv.tex").read_bytes(), None)
    assert before == {p: (other / p).read_bytes() for p in before}


def test_a_package_without_a_pdf_is_never_ready_and_cannot_be_approved(template, tmp_path):
    other = tmp_path / "copy"
    shutil.copytree(str(template), str(other))
    package.create(other, "texonly", offer_of(other), (other / "plans/p.json").read_bytes(), (other / "out/cv.tex").read_bytes(), None)
    status, reasons, codes = status_of(other, "texonly")
    assert status == readiness.NEEDS_REVIEW and "FINAL_DOCUMENT_MISSING" in reasons
    with pytest.raises(package.PackageError) as raised:
        package.record_review(other, "texonly", "APPROVED", "Fictional Reviewer")
    assert raised.value.code == "FINAL_DOCUMENT_MISSING"
    forged = {"schema": review.SCHEMA, "decision": "APPROVED", "tailored_cv_id": read_json(app_file(other, "metadata", "texonly"))["tailored_cv_id"],
              "document_sha256": canonical.sha256_text((other / "out/cv.tex").read_bytes())}
    write_json(other / "applications" / "texonly" / "cv" / review.FILE_NAME, forged)
    assert status_of(other, "texonly")[0] != readiness.READY


def create_args(ws, **override):
    args = {"name": "fresh", "offer_path": offer_of(ws), "plan_bytes": (ws / "plans/p.json").read_bytes(),
            "tex_bytes": (ws / "out/cv.tex").read_bytes(), "pdf_bytes": (ws / "out/cv.pdf").read_bytes()}
    args.update(override)
    return args


@pytest.mark.parametrize("override,error,code", [
    ({"name": "Bad Name"}, package.PackageError, "PACKAGE_NAME_INVALID"),
    ({"name": NAME}, package.PackageError, "PACKAGE_EXISTS"),
    ({"tex_bytes": b"\\documentclass{article}\n"}, package.PackageError, "TEX_NOT_FROM_ASSEMBLY"),
    ({"pdf_bytes": b"not a pdf"}, package.PackageError, "PDF_MALFORMED"),
    ({"plan_bytes": b"{"}, Exception, "ASSEMBLY_PLAN_NOT_JSON"),
])
def test_a_bad_input_creates_nothing(ws, override, error, code):
    before = tree_hash(ws)
    with pytest.raises(error) as raised:
        package.create(ws, **create_args(ws, **override))
    assert getattr(raised.value, "code", None) == code and tree_hash(ws) == before


def test_an_edited_plan_or_a_changed_source_creates_nothing(ws):
    plan = read_json(ws / "plans/p.json")
    plan["selected"]["bullets"][0]["gain"] = 99
    before = tree_hash(ws)
    with pytest.raises(Exception) as raised:
        package.create(ws, **create_args(ws, plan_bytes=json.dumps(plan).encode("utf-8")))
    assert raised.value.code == "ASSEMBLY_PLAN_FINGERPRINT" and tree_hash(ws) == before
    (ws / "facts.md").write_text((ws / "facts.md").read_text(encoding="utf-8") + "\n", encoding="utf-8")
    before = tree_hash(ws)
    with pytest.raises(Exception) as raised:
        package.create(ws, **create_args(ws))
    assert raised.value.code == "ASSEMBLY_SOURCE_MISMATCH" and tree_hash(ws) == before


def test_a_workspace_that_is_not_the_committed_state_creates_nothing(ws):
    (ws / "content" / "resume.json").write_text((ws / "content" / "resume.json").read_text(encoding="utf-8") + "\n", encoding="utf-8")
    # the new content changes the fingerprints the plan recorded, so the plan is refused first; commit it to reach Git
    before = tree_hash(ws)
    with pytest.raises(Exception):
        package.create(ws, **create_args(ws))
    assert tree_hash(ws) == before


def test_without_a_git_repository_nothing_is_created(ws):
    shutil.rmtree(str(ws / ".git"), onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    before = tree_hash(ws)
    with pytest.raises(Exception) as raised:
        package.create(ws, **create_args(ws))
    assert raised.value.status in ("GIT_REPOSITORY_UNAVAILABLE", "GIT_UNAVAILABLE", "WORKSPACE_NOT_REPOSITORY_ROOT")
    assert tree_hash(ws) == before


def test_an_uncommitted_source_is_refused_even_when_the_plan_matches(ws):
    # change the source, rebuild the plan from the changed source, but do not commit it: Git must refuse
    content_path = ws / "content" / "resume.json"
    document = read_json(content_path)
    document["blocks"][0]["bullets"][0]["text"]["en"] += " Extra."
    write_json(content_path, document)
    offer = offer_of(ws)
    assert cli.main(["plan", "--offer", offer, "--root", str(ws), "--out", "plans/q.json"]) == 0
    assert cli.main(["render", "--plan", str(ws / "plans/q.json"), "--offer", offer, "--root", str(ws), "--out", "out/q.tex"]) == 0
    before = tree_hash(ws)
    with pytest.raises(Exception) as raised:
        package.create(ws, "uncommitted", offer, (ws / "plans/q.json").read_bytes(), (ws / "out/q.tex").read_bytes(), None)
    assert raised.value.status == "SOURCE_NOT_AT_COMMIT" and tree_hash(ws) == before


def test_the_offer_must_be_inside_the_workspace(ws, tmp_path):
    outside = tmp_path / "offer.json"
    shutil.copy(offer_of(ws), str(outside))
    with pytest.raises(package.PackageError) as raised:
        package.create(ws, **create_args(ws, offer_path=str(outside)))
    assert raised.value.code == "INPUT_OUTSIDE_WORKSPACE"


def test_a_symbolic_link_cannot_lead_the_package_outside_the_workspace(ws, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(str(outside), str(ws / "applications" / "fresh"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links cannot be created here")
    with pytest.raises(package.PackageError) as raised:
        package.create(ws, **create_args(ws))
    assert raised.value.code in ("PACKAGE_PATH_UNSAFE", "PACKAGE_EXISTS") and list(outside.iterdir()) == []


@pytest.mark.parametrize("folder", ["applications", "packages"])
def test_a_dangling_symbolic_link_is_not_written_through_by_a_package(ws, folder):
    """M8-A: a package folder that is, or passes through, a link (even a dangling one inside the workspace) is refused."""
    try:
        os.symlink(str(ws / folder / "nowhere"), str(ws / folder / "fresh"))
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links cannot be created here")
    with pytest.raises(package.PackageError) as raised:
        package.create(ws, **create_args(ws))
    assert raised.value.code == "PACKAGE_PATH_UNSAFE" and not (ws / folder / "nowhere").exists()


# --- readiness: the approved document ------------------------------------------------------------------------------------

def test_a_fictional_approval_of_the_exact_pdf_makes_the_package_ready(ws):
    result = approve(ws)
    assert result["state"] == readiness.READY and status_of(ws) == (readiness.READY, set(), set())
    document = read_json(ws / result["approval_file"])
    assert document["schema"] == review.SCHEMA_V2 and document["document_role"] == "cv_pdf"
    assert document["document_sha256"] == canonical.sha256_bytes(app_file(ws, "pdf").read_bytes())
    assert document["acknowledged"]["unsatisfied_required"] == read_json(app_file(ws, "metadata"))["unsatisfied_required"]


def test_ready_does_not_hide_the_unsatisfied_required_requirements(ws):
    approve(ws)
    summary = package.review_summary(ws, NAME)
    assert summary["state_now"]["status"] == readiness.READY and summary["to_acknowledge"]["unsatisfied_required"]
    assert any("not prove" in line for line in summary["limits"])


def test_a_review_is_never_overwritten(ws):
    approve(ws)
    with pytest.raises(package.PackageError) as raised:
        package.record_review(ws, NAME, "APPROVED", "Another Reviewer")
    assert raised.value.code == "REVIEW_EXISTS"


def test_a_rejection_blocks(ws):
    package.record_review(ws, NAME, "REJECTED", "Fictional Reviewer")
    status, reasons, _ = status_of(ws)
    assert status == readiness.BLOCKED and "HUMAN_REVIEW_REJECTED" in reasons


def test_the_pdf_changed_after_the_approval_voids_it(ws):
    approve(ws)
    assert status_of(ws)[0] == readiness.READY
    target = app_file(ws, "pdf")
    target.write_bytes(target.read_bytes() + b"\n% added after the approval\n")
    status, reasons, codes = status_of(ws)
    assert status != readiness.READY and "ARTIFACT_CHANGED_SINCE_PACKAGING" in reasons and "HUMAN_REVIEW_MISMATCH" in reasons
    target.write_bytes(OTHER_PDF)
    assert status_of(ws)[0] != readiness.READY


def test_a_pdf_swapped_with_a_consistent_snapshot_still_voids_the_approval(ws):
    approve(ws)
    app_file(ws, "pdf").write_bytes(OTHER_PDF)
    reseal(ws)                                   # the snapshot now agrees with the new PDF; the metadata and the approval do not
    status, reasons, codes = status_of(ws)
    assert status != readiness.READY and ("CV_REFERENCE_MISMATCH" in reasons or "HUMAN_REVIEW_MISMATCH" in reasons)


def review_edit(ws, change):
    path = ws / "applications" / NAME / "cv" / review.FILE_NAME
    document = read_json(path)
    change(document)
    write_json(path, document)


@pytest.mark.parametrize("change,reason", [
    (lambda d: d.update(document_sha256=canonical.sha256_text(b"another document")), "HUMAN_REVIEW_MISMATCH"),
    (lambda d: d.update(tailored_cv_id="1" * 64), "HUMAN_REVIEW_MISMATCH"),
    (lambda d: d["reviewed"].update(tex_sha256="2" * 64), "HUMAN_REVIEW_MISMATCH"),
    (lambda d: d["reviewed"].update(plan_sha256="2" * 64), "HUMAN_REVIEW_MISMATCH"),
    (lambda d: d["acknowledged"].update(warnings=[]), "HUMAN_REVIEW_MISMATCH"),
    (lambda d: d["acknowledged"].update(unsatisfied_required=[]), "HUMAN_REVIEW_MISMATCH"),
    (lambda d: d["acknowledged"].update(page_verdict="TARGET_MET" if d["acknowledged"]["page_verdict"] != "TARGET_MET" else "X"), "HUMAN_REVIEW_MISMATCH"),
    (lambda d: d.update(decision="REJECTED"), "HUMAN_REVIEW_REJECTED"),
    (lambda d: d.update(document_role="cv_tex"), "HUMAN_REVIEW_INVALID"),
    (lambda d: d.pop("reviewer"), "HUMAN_REVIEW_INVALID"),
    (lambda d: d.update(extra="x"), "HUMAN_REVIEW_INVALID"),
    (lambda d: d.update(decision="MAYBE"), "HUMAN_REVIEW_INVALID"),
    (lambda d: d.update(document_sha256="short"), "HUMAN_REVIEW_INVALID"),
    (lambda d: d.update(reviewer=""), "HUMAN_REVIEW_INVALID"),
    (lambda d: d.update(schema=review.SCHEMA), "HUMAN_REVIEW_INVALID"),
])
def test_a_review_that_does_not_approve_exactly_this_pdf_is_not_an_approval(ws, change, reason):
    approve(ws)
    review_edit(ws, change)
    status, reasons, _ = status_of(ws)
    assert status != readiness.READY and reason in reasons


def test_an_unreadable_or_foreign_review_file_is_not_an_approval(ws):
    path = ws / "applications" / NAME / "cv" / review.FILE_NAME
    for data in (b"{", b"[]", b"\xff\xfe", b""):
        path.write_bytes(data)
        status, reasons, _ = status_of(ws)
        assert status != readiness.READY and "HUMAN_REVIEW_INVALID" in reasons, data


def test_an_old_review_cannot_be_reused_for_another_cv(template, tmp_path):
    other = tmp_path / "copy"
    shutil.copytree(str(template), str(other))
    approve(other)
    fr = offer_of(other, "backend-intern.fr.json")
    assert cli.main(["plan", "--offer", fr, "--root", str(other), "--out", "plans/fr.json"]) == 0
    assert cli.main(["render", "--plan", str(other / "plans/fr.json"), "--offer", fr, "--root", str(other), "--out", "out/fr.tex"]) == 0
    (other / "out" / "fr.pdf").write_bytes(make_pdf((other / "out/fr.tex").read_bytes()))
    package.create(other, "french", fr, (other / "plans/fr.json").read_bytes(), (other / "out/fr.tex").read_bytes(), (other / "out/fr.pdf").read_bytes())
    shutil.copy(str(other / "applications" / NAME / "cv" / review.FILE_NAME), str(other / "applications" / "french" / "cv" / review.FILE_NAME))
    status, reasons, _ = status_of(other, "french")
    assert status != readiness.READY and "HUMAN_REVIEW_MISMATCH" in reasons
    assert status_of(other, NAME)[0] == readiness.READY                     # the first package is untouched


# --- readiness: substitutions after the package was created --------------------------------------------------------------

def edit_file(ws, relative, change):
    path = ws / relative
    data = path.read_text(encoding="utf-8")
    path.write_text(change(data), encoding="utf-8")


def edit_json(ws, relative, change):
    path = ws / relative
    document = read_json(path)
    change(document)
    write_json(path, document)


SUBSTITUTIONS = {
    "a bullet of the content": lambda ws: edit_json(ws, "content/resume.json", lambda d: d["blocks"][0]["bullets"][0]["text"].update(en="Changed bullet.")),
    "a heading of the content": lambda ws: edit_json(ws, "content/resume.json", lambda d: d["blocks"][0]["heading"]["en"].update(subtitle="Another employer")),
    "a fact": lambda ws: edit_file(ws, "facts.md", lambda t: t.replace("CONFIRMED", "WITHDRAWN", 1)),
    "the employer in the offer": lambda ws: edit_json(ws, "offers/backend-intern.json", lambda d: d.update(company="Another Company (fictional)")),
    "the job title in the offer": lambda ws: edit_json(ws, "offers/backend-intern.json", lambda d: d.update(title="Another title")),
    "the profile": lambda ws: edit_json(ws, "profile.json", lambda d: d["policy"].update(never_publish_terms=["salary expectation", "Python"])),
    "the plan (another valid plan)": lambda ws: shutil.copy(str(ws / "plans" / "fr.json"), str(app_file(ws, "plan"))),
    "the .tex (valid LaTeX)": lambda ws: app_file(ws, "tex").write_bytes(b"\\documentclass{article}\\begin{document}Hello\\end{document}\n"),
    "the PDF": lambda ws: app_file(ws, "pdf").write_bytes(OTHER_PDF),
    "the metadata (valid JSON)": lambda ws: edit_json(ws, "applications/demo/cv/metadata.json", lambda d: d.update(company="Another")),
    "the assembly (valid JSON)": lambda ws: edit_json(ws, "applications/demo/cv/assembly.json", lambda d: d["header"].update(display_name="Someone Else")),
    "the snapshot (deleted)": lambda ws: (ws / "packages" / NAME / "provenance" / "source-snapshot.json").unlink(),
    "the snapshot (a hash)": lambda ws: edit_json(ws, "packages/demo/provenance/source-snapshot.json", lambda d: d["entries"][0].update(sha256="3" * 64)),
    "the package file": lambda ws: edit_json(ws, "packages/demo/package.json", lambda d: d["application"].update(job_id="other")),
    "the review (deleted)": lambda ws: (ws / "applications" / NAME / "cv" / review.FILE_NAME).unlink(missing_ok=True),
}


@pytest.mark.parametrize("what", sorted(SUBSTITUTIONS))
@pytest.mark.parametrize("approved", [False, True])
def test_every_substitution_removes_readiness(template, tmp_path, what, approved):
    ws = tmp_path / "ws"
    shutil.copytree(str(template), str(ws))
    fr = offer_of(ws, "backend-intern.fr.json")
    assert cli.main(["plan", "--offer", fr, "--root", str(ws), "--out", "plans/fr.json"]) == 0
    if approved:
        approve(ws)
        assert status_of(ws)[0] == readiness.READY
    SUBSTITUTIONS[what](ws)
    status, reasons, _ = status_of(ws)
    if what == "the review (deleted)" and not approved:
        assert reasons == {"HUMAN_REVIEW_REQUIRED"}
    assert status != readiness.READY, what


def test_a_committed_source_change_is_detected_by_the_snapshot_and_by_git(ws):
    approve(ws)
    edit_json(ws, "content/resume.json", lambda d: d["blocks"][0]["bullets"][0]["text"].update(en="Changed bullet."))
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", "change the content")
    status, reasons, codes = status_of(ws)
    assert status != readiness.READY and "SOURCE_CHANGED_SINCE_PACKAGING" in reasons


def test_a_taxonomy_file_is_part_of_the_evidence(template, tmp_path):
    ws = tmp_path / "ws"
    shutil.copytree(str(template), str(ws))
    shutil.copy(str(EXAMPLE_DIR.parent / "taxonomy.generic-v1.json"), str(ws / "taxo.json"))
    edit_json(ws, "profile.json", lambda d: d.update(taxonomy="taxo.json"))
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", "taxonomy file")
    offer = offer_of(ws)
    assert cli.main(["plan", "--offer", offer, "--root", str(ws), "--out", "plans/t.json"]) == 0
    assert cli.main(["render", "--plan", str(ws / "plans/t.json"), "--offer", offer, "--root", str(ws), "--out", "out/t.tex"]) == 0
    summary = package.create(ws, "withtaxo", offer, (ws / "plans/t.json").read_bytes(), (ws / "out/t.tex").read_bytes(), FAKE_PDF)
    assert summary["state"] == readiness.NEEDS_REVIEW
    document = read_json(ws / "packages" / "withtaxo" / "provenance" / "source-snapshot.json")
    assert "taxonomy" in {e["role"] for e in document["entries"]}
    package.record_review(ws, "withtaxo", "APPROVED", "Fictional Reviewer")
    assert status_of(ws, "withtaxo")[0] == readiness.READY
    edit_json(ws, "taxo.json", lambda d: d["terms"].append({"id": "zzz", "kind": "technology", "name": "Zzz"}))
    status, reasons, _ = status_of(ws, "withtaxo")
    assert status != readiness.READY and "SOURCE_CHANGED_SINCE_PACKAGING" in reasons


def test_a_workspace_without_a_valid_git_history_is_not_ready(ws):
    approve(ws)
    shutil.rmtree(str(ws / ".git"), onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    status, reasons, _ = status_of(ws)
    assert status != readiness.READY and "SOURCE_COMMIT_UNVERIFIABLE" in reasons


def test_a_commit_that_git_does_not_know_is_not_ready(ws):
    approve(ws)
    edit_json(ws, "applications/demo/cv/metadata.json", lambda d: d.update(source_commit="a" * 40))
    reseal(ws)
    status, reasons, _ = status_of(ws)
    assert status != readiness.READY and reasons & {"SOURCE_COMMIT_UNVERIFIABLE", "CV_REFERENCE_MISMATCH"}


# --- forged but internally consistent packages -------------------------------------------------------------------------------

def test_a_forged_metadata_with_a_resealed_snapshot_is_blocked(ws):
    approve(ws)
    edit_json(ws, "applications/demo/cv/metadata.json", lambda d: d.update(company="Another Company (fictional)"))
    reseal(ws)
    status, reasons, codes = status_of(ws)
    assert status == readiness.BLOCKED and "CV_REFERENCE_MISMATCH" in reasons and "METADATA_DIFFERS_FROM_CHAIN" in codes


def test_a_forged_plan_with_a_recomputed_hash_and_a_resealed_snapshot_is_blocked(ws):
    approve(ws)

    def add_bullet(plan):
        plan["selected"]["bullets"].append(dict(plan["selected"]["bullets"][0], id="junior-dev.05"))
        plan["selected"]["blocks"][0]["bullets"].append("junior-dev.05")
        plan["plan_sha256"] = canonical.fingerprint({k: v for k, v in plan.items() if k != "plan_sha256"})

    edit_json(ws, "applications/demo/cv/tailoring-plan.json", add_bullet)
    reseal(ws)
    status, reasons, codes = status_of(ws)
    assert status == readiness.BLOCKED and "CHAIN_INVALID" in reasons


def test_a_substituted_tex_with_updated_hashes_is_blocked(ws):
    approve(ws)
    app_file(ws, "tex").write_bytes(b"\\documentclass{article}\\begin{document}Hello\\end{document}\n")
    edit_json(ws, "applications/demo/cv/metadata.json",
              lambda d: d.update(tex_sha256=canonical.sha256_bytes(app_file(ws, "tex").read_bytes())))
    reseal(ws)
    status, reasons, codes = status_of(ws)
    assert status == readiness.BLOCKED and "CHAIN_TEX_MISMATCH" in codes


def test_a_substituted_pdf_with_updated_hashes_still_needs_a_new_approval(ws):
    approve(ws)
    app_file(ws, "pdf").write_bytes(OTHER_PDF)
    edit_json(ws, "applications/demo/cv/metadata.json",
              lambda d: d.update(pdf_sha256=canonical.sha256_bytes(OTHER_PDF), pdf_pages=None))
    reseal(ws)
    status, reasons, _ = status_of(ws)
    assert status != readiness.READY and "HUMAN_REVIEW_MISMATCH" in reasons


def test_a_package_that_declares_a_verdict_is_blocked(ws):
    approve(ws)
    edit_json(ws, "packages/demo/package.json", lambda d: d["routing"].update(workflow_state="READY_TO_SEND"))
    pkg_path = ws / "packages" / NAME / "package.json"
    pkg = read_json(pkg_path)
    pkg["package_fingerprint"] = canonical.fingerprint({k: v for k, v in pkg.items() if k != "package_fingerprint"})
    write_json(pkg_path, pkg)
    status, reasons, codes = status_of(ws)
    assert status == readiness.BLOCKED and "PACKAGE_DECLARES_A_VERDICT" in codes


def test_the_stale_registry_still_blocks_a_version_3_package(ws):
    approve(ws)
    cv_id = read_json(app_file(ws, "metadata"))["tailored_cv_id"]
    write_json(ws / "packages" / "package-staleness.json", {"registry_version": "StalePackageRegistry-v1", "packages": [
        {"job_id": "x", "package_fingerprint": "f" * 64, "tailored_cv_id": cv_id, "status": "STALE"}]})
    assert status_of(ws)[0] == readiness.BLOCKED


# --- compatibility with the M3 formats ---------------------------------------------------------------------------------------

def test_historical_metadata_versions_stay_readable_and_never_become_ready_by_themselves():
    base = {"schema_version": "1", "job_key": "j", "generated_at": "2026-01-01T00:00:00Z", "language": "en", "family": "f",
            "source_commit": "a" * 40, "master_resume": "m.tex", "facts_source": "facts.md", "company": "c", "title": "t",
            "job_sha256": "b" * 64, "decision": {"selected_content": [], "excluded_content": [], "human_validations_required": []}}
    for version in ("1", "2"):
        assert metadata.problems(dict(base, schema_version=version)) == []
    assert metadata.problems(dict(base, schema_version="4"))[0][0] == "METADATA_SCHEMA_VERSION"
    assert metadata.problems(dict(base, schema_version="3"))[0][0] == "METADATA_FIELD_MISSING"        # v1 fields are not v3


@pytest.mark.parametrize("change,field", [
    (lambda d: d.pop("tex_sha256"), "tex_sha256"), (lambda d: d.update(extra=1), "unknown"), (lambda d: d.update(tex_sha256="x"), "tex_sha256"),
    (lambda d: d.update(pdf_sha256="x"), "pdf_sha256"), (lambda d: d.update(pdf_pages=0, pdf_sha256="a" * 64), "pdf_pages"),
    (lambda d: d.update(pdf_sha256=None, pdf_pages=2), "pdf_pages"), (lambda d: d.update(paper="a0paper"), "paper"),
    (lambda d: d.update(page_target=9), "page_target"), (lambda d: d.update(language="de"), "language"),
    (lambda d: d["inputs"].pop("offer_sha256"), "inputs"), (lambda d: d.update(decision=[]), "decision"),
    (lambda d: d.update(warnings="x"), "warnings"), (lambda d: d.update(company=" "), "company"),
])
def test_invalid_version_3_metadata_is_refused(template, change, field):
    document = read_json(app_file(template, "metadata"))
    change(document)
    problems = metadata.problems(document)
    assert problems and any(field in message or field == "unknown" for _code, message in problems)


# --- command line ---------------------------------------------------------------------------------------------------------------

def cli_ws(template, tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(str(template), str(root))
    shutil.rmtree(str(root / "applications"))
    shutil.rmtree(str(root / "packages"))
    git(root, "add", "-A")
    return root


def test_the_command_line_workflow_with_a_person_at_the_terminal(template, tmp_path, capsys, monkeypatch):
    root = cli_ws(template, tmp_path)
    offer = offer_of(root)
    code, out, err = run(capsys, "package", "create", "--name", "job1", "--plan", str(root / "plans/p.json"), "--offer", offer,
                         "--tex", str(root / "out/cv.tex"), "--pdf", str(root / "out/cv.pdf"), "--root", str(root))
    created = json.loads(out)
    assert code == 0 and created["state"] == readiness.NEEDS_REVIEW and created["ready_to_send"] is False
    assert not any(secret in out + err for secret in SECRETS)
    code, out, _ = run(capsys, "package", "status", "--name", "job1", "--root", str(root))
    report = json.loads(out)
    assert code == 1 and report["status"] == readiness.NEEDS_REVIEW and report["to_acknowledge"]["unsatisfied_required"]
    assert not any(secret in out for secret in SECRETS)
    code, out, _ = run(capsys, "package", "review", "--name", "job1", "--root", str(root))
    summary = json.loads(out)
    assert code == 0 and summary["document"]["sha256"] == created["pdf_sha256"] and not any(secret in out for secret in SECRETS)
    # no terminal: refused, nothing written
    before = tree_hash(root)
    code, out, err = run(capsys, "package", "approve", "--name", "job1", "--reviewer", "Fictional Reviewer", "--root", str(root))
    assert code == 2 and "APPROVAL_REQUIRES_A_PERSON" in err and tree_hash(root) == before
    # a terminal, wrong confirmation: refused
    monkeypatch.setattr(cli, "_stdin_is_terminal", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "000000000000")
    code, _out, err = run(capsys, "package", "approve", "--name", "job1", "--reviewer", "Fictional Reviewer", "--root", str(root))
    assert code == 2 and "CONFIRMATION_MISMATCH" in err and tree_hash(root) == before
    # a terminal, the exact confirmation: recorded
    monkeypatch.setattr("builtins.input", lambda prompt="": created["pdf_sha256"][:12])
    code, out, _ = run(capsys, "package", "approve", "--name", "job1", "--reviewer", "Fictional Reviewer", "--root", str(root))
    assert code == 0 and "READY_TO_SEND" in out
    code, out, _ = run(capsys, "package", "status", "--name", "job1", "--root", str(root))
    assert code == 0 and json.loads(out)["status"] == readiness.READY
    code, _out, err = run(capsys, "package", "approve", "--name", "job1", "--reviewer", "Fictional Reviewer", "--root", str(root))
    assert code == 2 and "REVIEW_EXISTS" in err


def test_the_command_line_refuses_what_the_library_refuses(template, tmp_path, capsys):
    root = cli_ws(template, tmp_path)
    def create(plan, tex):
        return ["package", "create", "--name", "job1", "--plan", str(plan), "--offer", offer_of(root), "--tex", str(tex),
                "--root", str(root)]

    (root / "out" / "bad.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    code, _out, err = run(capsys, *create(root / "plans/p.json", root / "out/bad.tex"))
    assert code == 1 and "TEX_NOT_FROM_ASSEMBLY" in err
    code, _out, err = run(capsys, *create(root / "missing.json", root / "out/cv.tex"))
    assert code == 2 and "INPUT_UNREADABLE" in err
    code, _out, err = run(capsys, "package", "status", "--name", "nothing", "--root", str(root))
    assert code == 2 and "PACKAGE_UNREADABLE" in err
    code, _out, err = run(capsys, "package", "status", "--name", "Bad Name", "--root", str(root))
    assert code == 2 and "PACKAGE_NAME_INVALID" in err


def compile_args(root, name="job2", *extra):
    return ["package", "create", "--name", name, "--plan", str(root / "plans/p.json"), "--offer", offer_of(root),
            "--tex", str(root / "out/cv.tex"), "--root", str(root), *extra]


@pytest.mark.skipif(not REAL_PDFLATEX, reason="pdflatex is not installed")
def test_create_with_compile_packages_the_compiler_output_of_the_verified_tex(template, tmp_path, capsys):
    """M8-A: no file travels between the compilation and the package; the PDF is compiled from the verified bytes."""
    root = cli_ws(template, tmp_path)
    code, out, err = run(capsys, *compile_args(root, "job2", "--compile"))
    assert code == 0, err
    summary = json.loads(out)
    assert summary["state"] == readiness.NEEDS_REVIEW and summary["reasons"] == ["HUMAN_REVIEW_REQUIRED"]
    pdf_bytes = (root / "applications" / "job2" / "cv" / "resume.pdf").read_bytes()
    assert pdf.looks_like_pdf(pdf_bytes) and pdf.count_pages(pdf_bytes) == 1
    assert canonical.sha256_bytes(pdf_bytes) == summary["pdf_sha256"]
    assert read_json(root / "applications" / "job2" / "cv" / "metadata.json")["pdf_pages"] == 1


def test_create_with_compile_needs_a_compiler_and_leaves_nothing_behind(template, tmp_path, capsys, monkeypatch):
    root = cli_ws(template, tmp_path)
    monkeypatch.setattr(pdf, "find_pdflatex", lambda: None)
    before = tree_hash(root)
    code, _out, err = run(capsys, *compile_args(root, "job2", "--compile"))
    assert code == cli.PDF_UNAVAILABLE_EXIT and "PDF_UNAVAILABLE" in err and tree_hash(root) == before


def test_create_with_compile_reports_a_failed_compilation_and_leaves_nothing_behind(template, tmp_path, capsys, monkeypatch):
    root = cli_ws(template, tmp_path)

    def failing(tex, timeout=pdf.DEFAULT_TIMEOUT, executable=None):
        raise pdf.PdfError([pdf._problem("COMPILE_FAILED", "the compiler reported an error")])
    monkeypatch.setattr(pdf, "compile_tex", failing)
    before = tree_hash(root)
    code, _out, err = run(capsys, *compile_args(root, "job2", "--compile"))
    assert code == cli.PDF_FAILED_EXIT and "PDF_COMPILE_FAILED" in err and tree_hash(root) == before


def test_create_with_compile_never_compiles_a_tex_that_is_not_the_rendering(template, tmp_path, capsys, monkeypatch):
    """The compiler is only run on bytes already verified against the assembly of the plan."""
    root = cli_ws(template, tmp_path)
    (root / "out" / "bad.tex").write_text("\\documentclass{article}\n\\begin{document}x\\end{document}\n", encoding="utf-8")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("the compiler must not run on an unverified .tex")
    monkeypatch.setattr(pdf, "compile_tex", forbidden)
    args = compile_args(root, "job2", "--compile")
    args[args.index("--tex") + 1] = str(root / "out" / "bad.tex")
    before = tree_hash(root)
    code, _out, err = run(capsys, *args)
    assert code == 1 and "TEX_NOT_FROM_ASSEMBLY" in err and tree_hash(root) == before


def test_create_refuses_both_a_pdf_and_a_compilation(template, tmp_path, capsys):
    root = cli_ws(template, tmp_path)
    before = tree_hash(root)
    code, _out, err = run(capsys, *compile_args(root, "job2", "--compile", "--pdf", str(root / "out/cv.pdf")))
    assert code == 2 and "PDF_SOURCE_AMBIGUOUS" in err and tree_hash(root) == before
    with pytest.raises(package.PackageError) as raised:
        package.create(root, "job2", offer_of(root), (root / "plans/p.json").read_bytes(), (root / "out/cv.tex").read_bytes(),
                       FAKE_PDF, compile_timeout=5)
    assert raised.value.code == "PDF_SOURCE_AMBIGUOUS" and tree_hash(root) == before


def test_status_exit_codes_follow_the_computed_state(template, tmp_path, capsys):
    root = tmp_path / "ws"
    shutil.copytree(str(template), str(root))
    assert run(capsys, "package", "status", "--name", NAME, "--root", str(root))[0] == 1
    approve(root)
    assert run(capsys, "package", "status", "--name", NAME, "--root", str(root))[0] == 0
    app_file(root, "pdf").write_bytes(OTHER_PDF)
    assert run(capsys, "package", "status", "--name", NAME, "--root", str(root))[0] == 1
    (root / "packages" / NAME / "provenance" / "source-snapshot.json").unlink()
    assert run(capsys, "package", "status", "--name", NAME, "--root", str(root))[0] == 3


def test_check_packages_agrees_with_the_package_status(ws, capsys):
    approve(ws)
    code, out, _ = run(capsys, "check-packages", str(ws / "packages"), "--root", str(ws))
    assert code == 0 and json.loads(out)["ready"] == [NAME]
    app_file(ws, "pdf").write_bytes(OTHER_PDF)
    code, out, _ = run(capsys, "check-packages", str(ws / "packages"), "--root", str(ws))
    assert json.loads(out)["ready"] == []


def test_diagnostics_never_repeat_the_private_text(ws, capsys):
    approve(ws)
    for change in (lambda: app_file(ws, "pdf").write_bytes(OTHER_PDF),
                   lambda: edit_json(ws, "applications/demo/cv/metadata.json", lambda d: d.update(company="Another")),
                   lambda: edit_json(ws, "content/resume.json", lambda d: d["blocks"][0]["bullets"][0]["text"].update(en="Changed bullet."))):
        change()
        code, out, err = run(capsys, "package", "status", "--name", NAME, "--root", str(ws))
        assert code != 0 and not any(secret in out + err for secret in SECRETS + ("Changed bullet.", "Another"))


# --- pages and the real compiler ------------------------------------------------------------------------------------------------

needs_pdflatex = pytest.mark.skipif(not REAL_PDFLATEX, reason="pdflatex is not installed: real PDF compilation not exercised")


@needs_pdflatex
def test_the_page_count_is_read_from_a_real_pdf_and_the_real_package_is_ready_after_a_fictional_approval(ws):
    metadata_document = read_json(app_file(ws, "metadata"))
    assert metadata_document["pdf_pages"] == 1 == pdf.count_pages(app_file(ws, "pdf").read_bytes())
    result = pdf.compile_tex(b"\\documentclass{article}\\begin{document}A\\newpage B\\newpage C\\end{document}\n")
    assert pdf.count_pages(result.pdf) == 3 == result.pages
    approve(ws)
    assert status_of(ws) == (readiness.READY, set(), set())


def test_the_page_count_of_a_pdf_without_a_page_tree_is_unknown():
    assert pdf.count_pages(FAKE_PDF) is None and pdf.count_pages(b"not a pdf") is None and pdf.count_pages(b"") is None
    tree = b"%PDF-1.4\n1 0 obj\n<</Type/Pages/Count 2/Kids[2 0 R 3 0 R]>>\nendobj\n%%EOF\n"
    assert pdf.count_pages(tree) == 2


def test_an_over_target_pdf_is_shown_to_the_reviewer_and_is_part_of_what_is_approved(template, tmp_path):
    ws = tmp_path / "ws"
    shutil.copytree(str(template), str(ws))
    summary = package.review_summary(ws, NAME)
    assert summary["document"]["page_target"] == 1 and summary["to_acknowledge"]["page_verdict"] in ("TARGET_MET", "NOT_COMPILED")
    if not REAL_PDFLATEX:
        assert summary["to_acknowledge"]["page_verdict"] == "NOT_COMPILED"


# --- invariants ---------------------------------------------------------------------------------------------------------------------

def test_a_package_is_ready_only_if_every_piece_of_evidence_is_intact(ws):
    approve(ws)
    artefacts = [app_file(ws, k) for k in ("plan", "assembly", "tex", "pdf", "metadata")]
    artefacts += [ws / "facts.md", ws / "profile.json", ws / "content" / "resume.json", ws / "offers" / "backend-intern.json"]
    for piece in artefacts:
        original = piece.read_bytes()
        piece.write_bytes(original + b"\n ")
        flipped = status_of(ws)[0] != readiness.READY
        piece.write_bytes(original)
        assert flipped, piece.name
        assert status_of(ws)[0] == readiness.READY, piece.name
    documents = [ws / "packages" / NAME / "package.json", ws / "packages" / NAME / "provenance" / "source-snapshot.json",
                 ws / "applications" / NAME / "cv" / review.FILE_NAME]
    for piece in documents:
        original = piece.read_bytes()
        document = json.loads(original.decode("utf-8"))
        document["x-added"] = 1
        piece.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        flipped = status_of(ws)[0] != readiness.READY
        piece.write_bytes(original)
        assert flipped, piece.name
        assert status_of(ws)[0] == readiness.READY, piece.name


def test_a_broken_package_cannot_be_approved_and_an_approval_never_replaces_a_check(ws):
    edit_json(ws, "content/resume.json", lambda d: d["blocks"][0]["bullets"][0]["text"].update(en="Changed bullet."))
    before = tree_hash(ws)
    with pytest.raises(package.PackageError) as raised:
        package.record_review(ws, NAME, "APPROVED", "Fictional Reviewer")
    assert raised.value.code == "PACKAGE_NOT_REVIEWABLE" and "SOURCE_CHANGED_SINCE_PACKAGING" in raised.value.details["reasons"]
    assert tree_hash(ws) == before


def test_the_reviewer_and_the_decision_are_required(ws):
    for reviewer in ("", "  ", None):
        with pytest.raises(package.PackageError) as raised:
            package.record_review(ws, NAME, "APPROVED", reviewer)
        assert raised.value.code == "REVIEWER_REQUIRED"
    with pytest.raises(package.PackageError) as raised:
        package.record_review(ws, NAME, "MAYBE", "Fictional Reviewer")
    assert raised.value.code == "DECISION_INVALID"


def test_a_snapshot_that_is_not_the_one_the_package_names_is_a_contradiction(ws):
    approve(ws)
    app_file(ws, "pdf").write_bytes(OTHER_PDF)
    snap_path = ws / "packages" / NAME / "provenance" / "source-snapshot.json"
    items = [(e["role"], e["path"]) for e in read_json(snap_path)["entries"]]
    write_json(snap_path, snapshot.build(ws, items))                       # valid and consistent, but not the one package.json names
    status, reasons, codes = status_of(ws)
    assert status != readiness.READY and "SNAPSHOT_FINGERPRINT_DIFFERS_FROM_PACKAGE" in codes


def test_a_package_that_names_another_identity_than_its_metadata_is_blocked(ws):
    approve(ws)
    pkg_path = ws / "packages" / NAME / "package.json"
    pkg = read_json(pkg_path)
    pkg["artifacts"]["cv"]["tailored_cv_id"] = "9" * 64
    pkg["package_fingerprint"] = canonical.fingerprint({k: v for k, v in pkg.items() if k != "package_fingerprint"})
    write_json(pkg_path, pkg)
    status, reasons, codes = status_of(ws)
    assert status == readiness.BLOCKED and "IDENTITY_DIFFERS" in codes
