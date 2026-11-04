"""Creation, inspection and human approval of a CV package (M7-B).

A package ties together, inside the private workspace, the plan, the assembled CV, the `.tex`, the PDF, the CV metadata
(version 3), the source snapshot and `package.json`. Layout, all workspace-relative (`<name>` is chosen by the user):

    applications/<name>/cv/{tailoring-plan.json, assembly.json, resume.tex, resume.pdf, metadata.json}
    applications/<name>/cv/cv-quality-review.json                  written later, by a person (`approve`)
    packages/<name>/package.json
    packages/<name>/provenance/source-snapshot.json

Creating a package is **never** an approval and never makes anything `READY_TO_SEND`: `package.json` carries no verdict
(`routing.workflow_state` is `UNEVALUATED`); the state is computed by `readiness` from the evidence, every time. The package
is built only from a verified plan and verified artefacts, writes only new files, and changes none of its sources.
Order of creation (see `chain.py` for the dependency graph): artefacts, metadata, snapshot, `package.json`; the review comes last
and lives outside the snapshot, so no document ever has to contain the hash of something that contains its own hash.

Data in a package is the applicant's: `.tex`, PDF, compilation logs and review files can hold personal data meant for an
employer. They belong in the private workspace, never in the generic repository.
"""
import json
import os
import shutil
from pathlib import Path

from . import (__version__, assemble as assemblemod, canonical, chain, config, facts, latex, paths, pdf, provenance, readiness,
               review, snapshot)

PACKAGE_SCHEMA = readiness.PACKAGE_V2
FILE_NAMES = {"plan": "tailoring-plan.json", "assembly": "assembly.json", "tex": "resume.tex", "pdf": "resume.pdf",
              "metadata": "metadata.json"}
PDF_LIMIT = 32 * 1024 * 1024
TEX_LIMIT = 4 * 1024 * 1024
LIMITS = (
    "An approval is a JSON file with no signature or authentication: anyone who can write to the workspace can write one. It binds"
    " a person's decision to the exact bytes of the PDF, it does not prove who decided.",
    "READY_TO_SEND proves that the process and the evidence are consistent; it does not prove that the candidate meets the"
    " requirements of the job: unsatisfied required requirements are listed in the metadata and in every review.",
    "The PDF is the document that is approved. That it was compiled from the .tex is not machine-verified (PDFs are not"
    " reproducible); the human review of the PDF is what binds the two.",
    "A reference check proves that facts exist and are CONFIRMED, not that a text means what they say; FR and EN texts are not"
    " checked for equivalence; ATS compatibility is not verified.",
    "The PDF may contain the applicant's personal data: it is never printed in a diagnostic.",
)


class PackageError(ValueError):
    """The package cannot be created or approved. `code` is a stable machine code, `details` is value-free."""

    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details or {}


def _json_bytes(document):
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _traverses_a_link(root, relative):
    """True when a component of the workspace-relative path is a symbolic link, dangling or not.

    `Path.resolve()` follows a dangling link on POSIX, so the resolved path alone would not show that a new package would be
    written through it."""
    current = os.path.abspath(str(root))
    for part in relative.split("/"):
        current = os.path.join(current, part)
        if os.path.islink(current):
            return True
    return False


def _location(root, settings, name):
    if not isinstance(name, str) or not facts.valid_id(name):
        raise PackageError("PACKAGE_NAME_INVALID", "the package name must be lowercase letters, digits, `.` and `-`")
    application = "%s/%s/cv" % (settings["applications_dir"].rstrip("/"), name)
    package = "%s/%s" % (settings["packages_dir"].rstrip("/"), name)
    if _traverses_a_link(root, application) or _traverses_a_link(root, package):
        raise PackageError("PACKAGE_PATH_UNSAFE", "a package folder may not be, or pass through, a symbolic link")
    targets = {"application": paths.resolve_inside(root, application), "package": paths.resolve_inside(root, package)}
    if None in targets.values():
        raise PackageError("PACKAGE_PATH_UNSAFE", "the package folders would leave the workspace")
    return application, package, targets


def _inside(root, path_text, what):
    """Workspace-relative POSIX path of an input file, or raise: a package refers to files by relative path only."""
    try:
        relative = Path(os.path.abspath(str(path_text))).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        raise PackageError("INPUT_OUTSIDE_WORKSPACE", "%s must be a file inside the workspace" % what)
    if paths.relative_path_problem(relative) or paths.resolve_inside(root, relative) is None:
        raise PackageError("INPUT_PATH_UNSAFE", "%s is not a safe workspace path" % what)
    return relative


def _git_files(settings, sources):
    names = list(config.provenance_files(settings["root"]))
    for relative in chain.source_paths(settings, sources).values():
        if relative not in names:
            names.append(relative)
    return names


def create(root, name, offer_path, plan_bytes, tex_bytes, pdf_bytes=None, compile_timeout=None):
    """Create the package `name` from a plan file's bytes, the `.tex` and an optional PDF. Returns a value-free summary.

    Raises `chain.ChainError` (a source does not validate), `assemblemod.AssemblyError` (the plan does not verify),
    `PackageError` and `provenance.SourceProvenanceError`. Nothing is left behind on failure."""
    root = Path(root)
    settings = config.load(root)
    if len(tex_bytes) > TEX_LIMIT or (pdf_bytes is not None and len(pdf_bytes) > PDF_LIMIT):
        raise PackageError("ARTEFACT_TOO_LARGE", "an artefact exceeds the size limit")
    application_rel, package_rel, targets = _location(root, settings, name)
    for target in targets.values():
        if os.path.lexists(str(target)):
            raise PackageError("PACKAGE_EXISTS", "the package folder already exists; a package is never overwritten")
    offer_relative = _inside(root, offer_path, "the offer")
    sources = chain.load_sources(root, settings, offer_relative)
    plan = assemblemod.load_plan(plan_bytes)
    assembly = assemblemod.assemble(plan, sources.offer, sources.taxonomy, sources.profile, sources.factbase, sources.content)
    paper = next((p for p in latex.PAPERS if latex.tex_bytes(latex.render(assembly, p)) == tex_bytes), None)
    if paper is None:
        raise PackageError("TEX_NOT_FROM_ASSEMBLY", "the .tex is not the rendering of the assembly of this plan")
    if compile_timeout is not None:
        # M8-A: the PDF is the compiler's own output for these very bytes, produced after the .tex was verified against the
        # assembly and before anything is written; no file travels between the compilation and the package.
        if pdf_bytes is not None:
            raise PackageError("PDF_SOURCE_AMBIGUOUS", "give either a PDF or a compilation, not both")
        pdf_bytes = pdf.compile_tex(tex_bytes, compile_timeout).pdf
        if len(pdf_bytes) > PDF_LIMIT:
            raise PackageError("ARTEFACT_TOO_LARGE", "an artefact exceeds the size limit")
    if pdf_bytes is not None and not pdf.looks_like_pdf(pdf_bytes):
        raise PackageError("PDF_MALFORMED", "the PDF is not a complete PDF file")
    commit = provenance.resolve_source_commit(root, _git_files(settings, sources))

    metadata_document = chain.build_metadata(plan, assembly, sources, tex_bytes, pdf_bytes, paper, commit, settings["facts"])
    files = {"plan": plan_bytes, "assembly": _json_bytes(assembly), "tex": tex_bytes, "metadata": _json_bytes(metadata_document)}
    if pdf_bytes is not None:
        files["pdf"] = pdf_bytes
    created = []
    try:
        for key, data in files.items():
            relative = "%s/%s" % (application_rel, FILE_NAMES[key])
            target = paths.resolve_inside(root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            created.append(target.parent)
            with open(str(target), "xb") as handle:
                handle.write(data)
        items = [(role, relative) for role, relative in chain.source_paths(settings, sources).items()]
        items += [("offer", offer_relative)]
        for role, key in (("tailoring_plan", "plan"), ("assembly", "assembly"), ("cv_tex", "tex"), ("cv_metadata", "metadata"),
                          ("cv_pdf", "pdf")):
            if key in files:
                items.append((role, "%s/%s" % (application_rel, FILE_NAMES[key])))
        document = snapshot.build(root, items)
        snapshot_target = paths.resolve_inside(root, package_rel + "/provenance/source-snapshot.json")
        snapshot_target.parent.mkdir(parents=True, exist_ok=True)
        created.append(snapshot_target.parent.parent)
        with open(str(snapshot_target), "xb") as handle:
            handle.write(_json_bytes(document))
        package = {
            "schema": PACKAGE_SCHEMA,
            "application": {"job_id": sources.offer.job_key},
            "artifacts": {"cv": {"tailored_cv_id": metadata_document["tailored_cv_id"], "language": plan["language"],
                                 "family": plan["family"], "document_role": review.DOCUMENT_ROLE,
                                 **{key: ("%s/%s" % (application_rel, FILE_NAMES[key]) if key in files else None)
                                    for key in ("plan", "assembly", "tex", "pdf", "metadata")}}},
            "routing": {"workflow_state": readiness.UNEVALUATED, "reasons": []},
            "validation": {"gates": {"PLAN_PASS": True, "ASSEMBLY_PASS": True, "DOCUMENT_PASS": True, "PROVENANCE_PASS": True},
                           "warnings": []},
            "snapshot_fingerprint": document["snapshot_fingerprint"],
        }
        package["package_fingerprint"] = canonical.fingerprint(package)
        with open(str(paths.resolve_inside(root, package_rel + "/package.json")), "xb") as handle:
            handle.write(_json_bytes(package))
        verdict = status(root, name)
        unexpected = [r for r in verdict["reasons"] if r not in ("HUMAN_REVIEW_REQUIRED", "FINAL_DOCUMENT_MISSING")]
        if unexpected:
            raise PackageError("PACKAGE_SELF_CHECK_FAILED", "the package just created does not verify", {"reasons": unexpected})
    except BaseException:
        for folder in (targets["application"], targets["package"]):
            if folder.exists():
                shutil.rmtree(str(folder), ignore_errors=True)
        raise
    return {"name": name, "tailored_cv_id": metadata_document["tailored_cv_id"], "state": verdict["status"],
            "reasons": verdict["reasons"], "source_commit": commit, "paper": paper, "application": application_rel,
            "package": package_rel, "plan_sha256": plan["plan_sha256"], "assembly_sha256": assembly["assembly_sha256"],
            "tex_sha256": metadata_document["tex_sha256"], "pdf_sha256": metadata_document["pdf_sha256"]}


def _load_package(root, settings, name):
    _application, package_rel, targets = _location(root, settings, name)
    path = targets["package"] / "package.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise PackageError("PACKAGE_UNREADABLE", "package.json cannot be read")
    if not isinstance(document, dict):
        raise PackageError("PACKAGE_UNREADABLE", "package.json is not a JSON object")
    return document, targets["package"]


def status(root, name):
    """The computed readiness of the package `name`: `{status, reasons, warnings, details}` (see `readiness`)."""
    root = Path(root)
    settings = config.load(root)
    package, package_dir = _load_package(root, settings, name)
    registry = root / settings["staleness_registry"]
    return readiness.assess(package, None, registry, root, package_dir)


def _metadata_of(root, settings, name):
    package, _dir = _load_package(root, settings, name)
    try:
        relative = package["artifacts"]["cv"]["metadata"]
        document = json.loads(paths.resolve_inside(root, relative).read_text(encoding="utf-8"))
    except (KeyError, TypeError, AttributeError, OSError, ValueError):
        raise PackageError("METADATA_UNREADABLE", "the CV metadata of this package cannot be read")
    return package, relative, document


def review_summary(root, name):
    """What a person needs in order to review the exact document: identities, hashes, warnings. No resume text, no contact."""
    root = Path(root)
    settings = config.load(root)
    package, metadata_relative, metadata_document = _metadata_of(root, settings, name)
    verdict = status(root, name)
    pdf_relative = package["artifacts"]["cv"].get("pdf")
    pdf_bytes = None
    if pdf_relative:
        target = paths.resolve_inside(root, pdf_relative)
        pdf_bytes = target.read_bytes() if target is not None and target.is_file() else None
    acknowledged = chain.acknowledgement(metadata_document)
    return {
        "package": name, "tailored_cv_id": metadata_document["tailored_cv_id"], "job_key": metadata_document["job_key"],
        "language": metadata_document["language"], "family": metadata_document["family"],
        "document": {"role": review.DOCUMENT_ROLE, "path": pdf_relative,
                     "sha256": None if pdf_bytes is None else canonical.sha256_bytes(pdf_bytes),
                     "bytes": None if pdf_bytes is None else len(pdf_bytes), "pages": metadata_document["pdf_pages"],
                     "page_target": metadata_document["page_target"], "page_verdict": acknowledged["page_verdict"]},
        "reviewed": {name_: metadata_document[name_] for name_ in review.REVIEWED_FIELDS},
        "to_acknowledge": acknowledged,
        "state_now": {"status": verdict["status"], "reasons": verdict["reasons"]},
        "limits": list(LIMITS),
        "approval_file": "%s/%s" % (package["artifacts"]["cv"]["metadata"].rsplit("/", 1)[0], review.FILE_NAME),
        "metadata": metadata_relative,
    }


def build_review(summary, decision, reviewer, note=None):
    """The `CVQualityReview-v2` document for `summary`. The fields are copied from the verified package: never typed."""
    if decision not in review.DECISIONS:
        raise PackageError("DECISION_INVALID", "the decision must be APPROVED or REJECTED")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise PackageError("REVIEWER_REQUIRED", "the reviewer must be named")
    if summary["document"]["sha256"] is None:
        raise PackageError("FINAL_DOCUMENT_MISSING", "the package holds no PDF: there is no document to approve")
    document = {"schema": review.SCHEMA_V2, "decision": decision, "tailored_cv_id": summary["tailored_cv_id"],
                "document_role": review.DOCUMENT_ROLE, "document_sha256": summary["document"]["sha256"],
                "reviewed": dict(summary["reviewed"]), "acknowledged": dict(summary["to_acknowledge"]),
                "reviewer": reviewer.strip()}
    if note:
        document["note"] = note
    return document


def record_review(root, name, decision, reviewer, note=None):
    """Write the review of the package `name` (a new file). The caller is responsible for the human action: this function
    only checks that the package can be reviewed (every check passes except the missing approval) and never overwrites.

    The command line (`package approve`) refuses to call it without an interactive terminal and a typed confirmation."""
    root = Path(root)
    summary = review_summary(root, name)
    if summary["document"]["sha256"] is None:
        raise PackageError("FINAL_DOCUMENT_MISSING", "the package holds no PDF: there is no document to approve")
    blocking = [r for r in summary["state_now"]["reasons"] if r != "HUMAN_REVIEW_REQUIRED"]
    if blocking:
        raise PackageError("PACKAGE_NOT_REVIEWABLE", "the package has an unresolved problem; review does not replace a check",
                           {"reasons": blocking})
    document = build_review(summary, decision, reviewer, note)
    target = paths.resolve_inside(root, summary["approval_file"])
    if target is None:
        raise PackageError("PATH_UNSAFE", "the approval file would leave the workspace")
    try:
        with open(str(target), "xb") as handle:
            handle.write(_json_bytes(document))
    except FileExistsError:
        raise PackageError("REVIEW_EXISTS", "a review file already exists; it is never overwritten (move it aside to start over)")
    except OSError as error:
        raise PackageError("OUTPUT_WRITE_FAILED", "cannot write the review: %s" % error.strerror)
    return {"approval_file": summary["approval_file"], "decision": decision, "document_sha256": document["document_sha256"],
            "tailored_cv_id": document["tailored_cv_id"], "state": status(root, name)["status"]}
