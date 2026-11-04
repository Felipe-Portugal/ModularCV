"""Fail-closed readiness of an application package (0.2.0).

`READY_TO_SEND` is **computed from evidence**, never accepted because a package, an index or an
old file says so. A package is ready only if every check below finds nothing to object to:

- the declared state and the recorded gates of the package, and the staleness registry;
- the package's own source snapshot (`provenance/source-snapshot.json`), which names exactly one
  CV metadata and one tailoring plan, each bound by hash, the metadata inside the applications tree;
- the working-tree files of the snapshot, unchanged since packaging;
- the CV metadata: a readable v1/v2 document whose `source_commit` is a real commit of the
  workspace repository (never absent, never zeros, never unknown), an ancestor of HEAD, holding
  the provenance files, with each source of the snapshot equal to its content at that commit;
- the plan beside the metadata, which must name the package's `tailored_cv_id`;
- a human approval (`cv-quality-review.json`) of that exact identity and that exact document.

Without the evidence (no `root` and `package_dir`) nothing can be verified and the result is never
`READY_TO_SEND`. Reading is all this module does: it never writes, repairs or upgrades a package.
Reasons are stable machine codes, documented in `docs/design/PROVENANCE_READINESS.md` section 6.
"""
import json
from pathlib import Path

from . import canonical, chain, config, metadata, paths, provenance, review, snapshot, staleness
from .provenance import SHA_PATTERN, SourceProvenanceError, is_placeholder

READY = "READY_TO_SEND"
NEEDS_REVIEW = "NEEDS_REVIEW"
BLOCKED = "BLOCKED"

SNAPSHOT_RELATIVE = ("provenance", "source-snapshot.json")
PACKAGE_V2 = "ApplicationPackage-v2"  # carries no verdict: its state is always computed
UNEVALUATED = "UNEVALUATED"
PDF_ORIGIN_NOT_VERIFIED = "PDF_ORIGIN_NOT_VERIFIED"  # M8-A-R2: only a PDF compiled by the package command can be READY_TO_SEND

# Reasons that make a package unusable (BLOCKED) rather than merely unreviewed.
HARD_REASONS = (
    "PACKAGE_STALE", "STALENESS_REGISTRY_UNREADABLE", "PACKAGE_JSON_INVALID",
    "CV_METADATA_INVALID", "CV_METADATA_MISSING", "CV_METADATA_UNREADABLE", "CV_METADATA_AMBIGUOUS",
    "CV_METADATA_OUT_OF_SCOPE", "CV_REFERENCE_MISMATCH",
    "SNAPSHOT_MISSING", "SNAPSHOT_INVALID", "SNAPSHOT_CONTRADICTORY",
    "SOURCE_COMMIT_MISMATCH", "HUMAN_REVIEW_REJECTED", "CHAIN_INVALID",
)


class AuditError(RuntimeError):
    """The audit cannot be completed. `code` is a stable machine code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class _Verdict:
    def __init__(self):
        self.reasons, self.warnings, self.details = [], [], []

    def add(self, reason, code, message):
        self.reasons.append(reason)
        self.details.append({"reason": reason, "code": code, "message": message})

    def result(self):
        reasons = list(dict.fromkeys(self.reasons))
        if not reasons:
            status = READY
        else:
            status = BLOCKED if any(r in HARD_REASONS for r in reasons) else NEEDS_REVIEW
        return {"status": status, "reasons": reasons, "warnings": self.warnings, "details": self.details}


def _registry(path) -> tuple:
    """(registry, error). A missing registry is an empty one; an unreadable one is an error."""
    try:
        data = staleness.load(path)
        if not isinstance(data.get("packages"), list):
            raise ValueError("no packages list")
        return data, None
    except (OSError, ValueError, AttributeError) as error:
        return None, str(error)


def _cv_id(package):
    value = (package.get("artifacts", {}).get("cv", {}) or {}).get("tailored_cv_id")
    return value if isinstance(value, str) and value else None


def _load_json(path):
    """(document, bytes, error) for a file read once; the same bytes are hashed and parsed."""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        return None, None, "cannot be read: %s" % (error.strerror or error)
    try:
        return canonical.loads(data.decode("utf-8-sig")), data, None
    except (ValueError, UnicodeDecodeError) as error:
        return None, data, "is not valid JSON: %s" % error


def _declared_checks(package, registry_path, verdict):
    declared = package["routing"]["workflow_state"]
    recorded = package["validation"]["gates"]
    if package.get("schema") == PACKAGE_V2:
        if declared != UNEVALUATED:
            verdict.add("PACKAGE_JSON_INVALID", "PACKAGE_DECLARES_A_VERDICT",
                        "an ApplicationPackage-v2 must not carry a verdict: its state is computed")
    elif declared != READY:
        verdict.add("DECLARED_" + str(declared), "PACKAGE_DECLARES_NOT_READY",
                    "the package declares workflow_state %r" % (declared,))
    if not isinstance(recorded, dict):
        raise TypeError("gates")
    for name, ok in sorted(recorded.items()):
        if not ok:
            verdict.add(name, "GATE_FAILED", "the recorded gate %s is not passing" % name)
    registry, error = _registry(registry_path)
    if registry is None:
        verdict.add("STALENESS_REGISTRY_UNREADABLE", "REGISTRY_UNREADABLE", error)
        return
    fingerprint = package.get("package_fingerprint")
    cv_id = _cv_id(package)
    for entry in registry["packages"]:
        if not isinstance(entry, dict) or entry.get("status", "STALE") != "STALE":
            continue
        if (fingerprint and entry.get("package_fingerprint") == fingerprint) or (
                cv_id and entry.get("tailored_cv_id") == cv_id):
            verdict.add("PACKAGE_STALE", "REGISTERED_STALE", "the staleness registry lists this package")


def _metadata_checks(document, verdict):
    for code, message in metadata.problems(document):
        verdict.add("CV_METADATA_INVALID", code, message)


def _source_commit_checks(document, root, paths_to_check, verdict, source_entries):
    value = document.get("source_commit") if isinstance(document, dict) else None
    if value is None or value == "":
        verdict.add("CV_METADATA_INVALID", "SOURCE_COMMIT_MISSING", "source_commit is absent")
        return
    if not isinstance(value, str) or not SHA_PATTERN.match(value):
        verdict.add("CV_METADATA_INVALID", "SOURCE_COMMIT_MALFORMED",
                    "source_commit is not a full lowercase hexadecimal Git SHA")
        return
    if is_placeholder(value):
        verdict.add("SOURCE_COMMIT_PLACEHOLDER_LEGACY", "SOURCE_COMMIT_ALL_ZEROS",
                    "source_commit is an all-zero placeholder: archivable, not sendable")
        return
    try:
        provenance.verify_recorded_commit(value, root, paths_to_check)
    except SourceProvenanceError as error:
        verdict.add("SOURCE_COMMIT_UNVERIFIABLE", error.status, str(error))
        return
    for entry in source_entries:
        try:
            at_commit = provenance.hash_at_commit(value, root, entry["path"])
        except SourceProvenanceError as error:
            verdict.add("SOURCE_COMMIT_UNVERIFIABLE", error.status, str(error))
            continue
        if at_commit != entry["sha256"]:
            verdict.add("SOURCE_COMMIT_MISMATCH", "SOURCE_DIFFERS_AT_COMMIT",
                        "%s at commit %s is not the file the package was built from"
                        % (entry["path"], value[:12]))


_SNAPSHOT_STRUCTURE = {
    "SNAPSHOT_DUPLICATE_PATH": ("SNAPSHOT_CONTRADICTORY"),
    "SNAPSHOT_DUPLICATE_ENTRY": ("SNAPSHOT_CONTRADICTORY"),
}


def _snapshot_reason(problem):
    role = problem.role
    if problem.code == "SNAPSHOT_DUPLICATE_ROLE":
        return "CV_METADATA_AMBIGUOUS" if role == "cv_metadata" else "SNAPSHOT_CONTRADICTORY"
    if problem.code == "SNAPSHOT_ROLE_MISSING" and role == "cv_metadata":
        return "CV_METADATA_MISSING"
    if problem.code == "SNAPSHOT_PATH_UNSAFE" and role == "cv_metadata":
        return "CV_METADATA_OUT_OF_SCOPE"
    return _SNAPSHOT_STRUCTURE.get(problem.code, "SNAPSHOT_INVALID")


def _file_reason(problem):
    """Reason for a snapshot file that is missing, changed or out of the workspace."""
    role, code = problem.role, problem.code
    if code == "PATH_ESCAPE":
        return "CV_METADATA_OUT_OF_SCOPE" if role == "cv_metadata" else "SNAPSHOT_INVALID"
    kind = "MISSING" if code == "FILE_MISSING" else "CHANGED_SINCE_PACKAGING"
    if role == "cv_metadata":
        return "CV_METADATA_" + kind
    if role in snapshot.SOURCE_ROLES:
        return "SOURCE_" + kind
    return "ARTIFACT_" + kind


def _evidence_checks(package, root, package_dir, files, verdict):
    cv_id = _cv_id(package)
    package_dir = Path(package_dir)
    snapshot_path = package_dir.joinpath(*SNAPSHOT_RELATIVE)
    if not snapshot_path.is_file():
        verdict.add("SNAPSHOT_MISSING", "SNAPSHOT_FILE_MISSING",
                    "no %s: the CV metadata of this package cannot be established" % "/".join(SNAPSHOT_RELATIVE))
        verdict.add("CV_METADATA_MISSING", "NO_SNAPSHOT", "the metadata is resolved through the snapshot only")
        return
    document, _data, error = _load_json(snapshot_path)
    if error:
        verdict.add("SNAPSHOT_INVALID", "SNAPSHOT_UNREADABLE", "the snapshot " + error)
        return
    structure = snapshot.structure_problems(document)
    for problem in structure:
        verdict.add(_snapshot_reason(problem), problem.code, problem.message)
    if structure:
        return

    cfg = config.load(root)
    applications = cfg["applications_dir"].rstrip("/") + "/"
    meta_entry = snapshot.entries_for(document, "cv_metadata")[0]
    plan_entry = snapshot.entries_for(document, "tailoring_plan")[0]
    cv_entry = snapshot.entries_for(document, "cv_tex")[0]
    if not meta_entry["path"].startswith(applications):
        verdict.add("CV_METADATA_OUT_OF_SCOPE", "OUTSIDE_APPLICATIONS_TREE",
                    "%s is not inside %s" % (meta_entry["path"], applications))
        return

    file_problems = snapshot.verify_files(document, root)
    for problem in file_problems:
        verdict.add(_file_reason(problem), problem.code, problem.message)
    meta_dir = meta_entry["path"].rsplit("/", 1)[0]

    cv_metadata, meta_bytes, error = _load_json(paths.resolve_inside(root, meta_entry["path"]) or "")
    if error:
        reason = "CV_METADATA_MISSING" if meta_bytes is None else "CV_METADATA_UNREADABLE"
        if meta_bytes is None:
            pass  # already reported as missing/out of scope by the file check
        else:
            verdict.add(reason, "METADATA_UNREADABLE", "the CV metadata " + error)
        cv_metadata = None
    if cv_metadata is not None:
        _metadata_checks(cv_metadata, verdict)
        if isinstance(cv_metadata, dict) and cv_metadata.get("schema_version") in metadata.KNOWN_VERSIONS:
            verdict.warnings.append("LEGACY_METADATA_SCHEMA_VERSION_" + cv_metadata["schema_version"])
        facts_entries = snapshot.entries_for(document, "facts")
        facts_source = cv_metadata.get("facts_source") if isinstance(cv_metadata, dict) else None
        if isinstance(facts_source, str) and facts_entries and facts_source != facts_entries[0]["path"]:
            verdict.add("CV_REFERENCE_MISMATCH", "FACTS_SOURCE_DIFFERS",
                        "metadata facts_source %r is not the snapshot facts file %r"
                        % (facts_source, facts_entries[0]["path"]))
        sources = [entry for entry in document["entries"] if entry["role"] in snapshot.SOURCE_ROLES]
        wanted = sorted(set(files) | {entry["path"] for entry in sources})
        _source_commit_checks(cv_metadata, root, wanted, verdict, sources)

    if isinstance(cv_metadata, dict) and cv_metadata.get("schema_version") == metadata.CURRENT_VERSION \
            and not metadata.problems(cv_metadata):
        _v3_checks(package, document, cv_metadata, root, package_dir, meta_dir, file_problems, verdict)
        return
    if isinstance(cv_metadata, dict) and cv_metadata.get("schema_version") == metadata.CURRENT_VERSION:
        return  # invalid version 3 metadata: already reported as CV_METADATA_INVALID

    # Identity: the plan beside the metadata names this package's CV.
    plan_dir = plan_entry["path"].rsplit("/", 1)[0] if "/" in plan_entry["path"] else ""
    if cv_id is None:
        verdict.add("CV_REFERENCE_MISMATCH", "PACKAGE_HAS_NO_CV_ID", "the package names no tailored_cv_id")
    elif plan_dir != meta_dir:
        verdict.add("CV_REFERENCE_MISMATCH", "PLAN_NOT_BESIDE_METADATA",
                    "the tailoring plan is not in the folder of the CV metadata")
    else:
        plan, _plan_bytes, error = _load_json(paths.resolve_inside(root, plan_entry["path"]) or "")
        if error or not isinstance(plan, dict):
            verdict.add("CV_REFERENCE_MISMATCH", "PLAN_UNREADABLE", "the tailoring plan " + (error or "is not an object"))
        elif plan.get("tailored_cv_id") != cv_id:
            verdict.add("CV_REFERENCE_MISMATCH", "PLAN_NAMES_ANOTHER_CV",
                        "the plan beside the metadata names another tailored_cv_id than the package")

    if isinstance(cv_metadata, dict) and isinstance(cv_metadata.get("decision"), dict):
        pending = cv_metadata["decision"].get("human_validations_required")
        if isinstance(pending, list) and pending:
            verdict.add("FACT_VALIDATION_REQUIRED", "HUMAN_VALIDATIONS_LISTED",
                        "%d fact validation(s) are still required" % len(pending))

    # Human approval of this exact CV (identity and document), written beside the metadata.
    review_path = paths.resolve_inside(root, meta_dir + "/" + review.FILE_NAME)
    if review_path is None or not review_path.is_file():
        verdict.add("HUMAN_REVIEW_REQUIRED", "REVIEW_FILE_MISSING", "no %s beside the CV metadata" % review.FILE_NAME)
        return
    try:
        raw = review_path.read_bytes()
    except OSError as os_error:
        verdict.add("HUMAN_REVIEW_INVALID", "REVIEW_UNREADABLE", str(os_error.strerror))
        return
    approval, error = review.parse(raw)
    if error:
        verdict.add("HUMAN_REVIEW_INVALID", "REVIEW_INVALID", error)
        return
    reason = review.judge(approval, cv_id, cv_entry["sha256"])
    if reason:
        verdict.add(reason, "REVIEW_DOES_NOT_MATCH" if reason == "HUMAN_REVIEW_MISMATCH" else "REVIEW_REJECTED",
                    "the review does not approve this exact CV identity and document")


def _v3_checks(package, document, cv_metadata, root, package_dir, meta_dir, file_problems, verdict):
    """The additional proof a version 3 package needs (M7-B): intact package file, the whole chain from the sources to the
    exact PDF re-derived from the workspace, a final document, and a human approval of that exact PDF."""
    cv_id = _cv_id(package)
    settings = config.load(root)
    if package.get("schema") != PACKAGE_V2:
        verdict.add("CV_REFERENCE_MISMATCH", "PACKAGE_NOT_V2", "metadata version 3 belongs to an ApplicationPackage-v2")
    else:
        body = {key: value for key, value in package.items() if key != "package_fingerprint"}
        if package.get("package_fingerprint") != canonical.fingerprint(body):
            verdict.add("PACKAGE_JSON_INVALID", "PACKAGE_FINGERPRINT_INVALID", "package_fingerprint does not match package.json")
        if package.get("snapshot_fingerprint") != document["snapshot_fingerprint"]:
            verdict.add("SNAPSHOT_CONTRADICTORY", "SNAPSHOT_FINGERPRINT_DIFFERS_FROM_PACKAGE",
                        "the snapshot is not the one this package.json names")
        try:
            named = package["artifacts"]["cv"]
            for key, role in (("tex", "cv_tex"), ("pdf", "cv_pdf"), ("metadata", "cv_metadata"), ("plan", "tailoring_plan"),
                              ("assembly", "assembly")):
                entries = snapshot.entries_for(document, role)
                if named.get(key) != (entries[0]["path"] if entries else None):
                    verdict.add("CV_REFERENCE_MISMATCH", "PACKAGE_PATH_DIFFERS_FROM_SNAPSHOT",
                                "package.json and the snapshot name different files for `%s`" % key)
        except (KeyError, TypeError, AttributeError):
            verdict.add("PACKAGE_JSON_INVALID", "PACKAGE_JSON_INVALID", "package.json does not hold artifacts.cv")

    identity = None
    if not file_problems:
        problems, identity = chain.verify(root, document, cv_metadata, settings)
        for problem in problems:
            verdict.add(problem.reason, problem.code, problem.message)
    if cv_id is None or cv_metadata["tailored_cv_id"] != cv_id or (identity is not None and identity != cv_id):
        verdict.add("CV_REFERENCE_MISMATCH", "IDENTITY_DIFFERS",
                    "the package, the metadata and the identity recomputed from the plan do not name the same CV")

    pdf_entries = snapshot.entries_for(document, "cv_pdf")
    if not pdf_entries:
        verdict.add("FINAL_DOCUMENT_MISSING", "NO_PDF_IN_PACKAGE",
                    "the package holds no PDF: a .tex is not a document that can be approved or sent")
        return
    pdf_path = paths.resolve_inside(root, pdf_entries[0]["path"])
    try:
        pdf_bytes = pdf_path.read_bytes() if pdf_path is not None and pdf_path.is_file() else None
    except OSError:
        pdf_bytes = None
    if pdf_bytes is None:
        return  # reported as ARTIFACT_MISSING by the file check

    # A person's approval binds a decision to exact bytes; it cannot make the origin of those bytes known. Without a recorded
    # compilation by the package command (a supplied PDF, or a package made before the origin was recorded) the package stays
    # NEEDS_REVIEW whatever the approval says.
    if cv_metadata.get("pdf_origin") != chain.ORIGIN_COMPILED:
        verdict.add(PDF_ORIGIN_NOT_VERIFIED,
                    "PDF_ORIGIN_SUPPLIED" if cv_metadata.get("pdf_origin") == chain.ORIGIN_SUPPLIED else "PDF_ORIGIN_NOT_RECORDED",
                    "the PDF was not made by the package command from the verified .tex: its provenance is not demonstrated")
    review_path = paths.resolve_inside(root, meta_dir + "/" + review.FILE_NAME)
    if review_path is None or not review_path.is_file():
        verdict.add("HUMAN_REVIEW_REQUIRED", "REVIEW_FILE_MISSING", "no %s beside the CV metadata" % review.FILE_NAME)
        return
    try:
        raw = review_path.read_bytes()
    except OSError as os_error:
        verdict.add("HUMAN_REVIEW_INVALID", "REVIEW_UNREADABLE", str(os_error.strerror))
        return
    if review.schema_of(raw) == review.SCHEMA:
        verdict.add("HUMAN_REVIEW_INVALID", "REVIEW_V1_NOT_APPLICABLE",
                    "a version 3 package needs a %s that names the PDF, not a review of the source" % review.SCHEMA_V2)
        return
    approval, error = review.parse_v2(raw)
    if error:
        verdict.add("HUMAN_REVIEW_INVALID", "REVIEW_INVALID", error)
        return
    reviewed = {name: cv_metadata[name] for name in review.REVIEWED_FIELDS}
    reason = review.judge_v2(approval, cv_id, canonical.sha256_bytes(pdf_bytes), reviewed, chain.acknowledgement(cv_metadata))
    if reason:
        verdict.add(reason, "REVIEW_DOES_NOT_MATCH" if reason == "HUMAN_REVIEW_MISMATCH" else "REVIEW_REJECTED",
                    "the review does not approve this exact PDF, as presented now")


def assess(package: dict, cv_metadata, registry_path, root=None, package_dir=None, files=None) -> dict:
    """Effective status and the reasons behind it. Never returns READY on any objection.

    With `root` (the workspace) and `package_dir`, everything is resolved and verified from the
    package's own snapshot and `cv_metadata` is ignored. Without them the evidence cannot be
    checked (`SNAPSHOT_MISSING`, `SOURCE_COMMIT_UNVERIFIABLE`, `HUMAN_REVIEW_REQUIRED`) and the
    result is never READY. Raises `config.ConfigError` for an unusable `modularcv.json`.
    """
    verdict = _Verdict()
    try:
        _declared_checks(package, registry_path, verdict)
    except (KeyError, TypeError, AttributeError):
        failed = _Verdict()
        failed.add("PACKAGE_JSON_INVALID", "PACKAGE_JSON_INVALID", "routing.workflow_state or validation.gates is missing")
        return failed.result()
    if root is not None and package_dir is not None:
        provenance_files = tuple(files) if files is not None else config.provenance_files(root)
        _evidence_checks(package, Path(root), package_dir, provenance_files, verdict)
    else:
        if cv_metadata is None:
            verdict.add("CV_METADATA_MISSING", "METADATA_NOT_PROVIDED", "no CV metadata was provided")
        else:
            _metadata_checks(cv_metadata, verdict)
            value = cv_metadata.get("source_commit") if isinstance(cv_metadata, dict) else None
            if value is None or value == "":
                verdict.add("CV_METADATA_INVALID", "SOURCE_COMMIT_MISSING", "source_commit is absent")
            elif not isinstance(value, str) or not SHA_PATTERN.match(value):
                verdict.add("CV_METADATA_INVALID", "SOURCE_COMMIT_MALFORMED",
                            "source_commit is not a full lowercase hexadecimal Git SHA")
            elif is_placeholder(value):
                verdict.add("SOURCE_COMMIT_PLACEHOLDER_LEGACY", "SOURCE_COMMIT_ALL_ZEROS",
                            "source_commit is an all-zero placeholder: archivable, not sendable")
        verdict.add("SNAPSHOT_MISSING", "EVIDENCE_NOT_PROVIDED", "no workspace and package folder to verify against")
        verdict.add("SOURCE_COMMIT_UNVERIFIABLE", "EVIDENCE_NOT_PROVIDED", "the commit cannot be verified without the workspace")
        verdict.add("HUMAN_REVIEW_REQUIRED", "EVIDENCE_NOT_PROVIDED", "the human approval cannot be found without the workspace")
    return verdict.result()


def apply(package: dict, cv_metadata, registry_path, root=None, package_dir=None) -> dict:
    """Downgrade `package` in place if the assessment objects; never upgrades it."""
    verdict = assess(package, cv_metadata, registry_path, root, package_dir)
    current = package["routing"]["workflow_state"]
    rank = {READY: 0, NEEDS_REVIEW: 1, BLOCKED: 2}
    if rank.get(verdict["status"], 2) > rank.get(current, 2):
        package["routing"]["workflow_state"] = verdict["status"]
    for reason in verdict["reasons"]:
        if reason not in package["routing"]["reasons"] and not reason.startswith("DECLARED_"):
            package["routing"]["reasons"].append(reason)
    package["validation"]["warnings"] = verdict["warnings"]
    return verdict


def audit_directory(packages_dir, registry_path=None, root=None) -> dict:
    """Read-only check of every package folder and of the secondary index.

    Reports each package's effective status and every contradiction between the index (or the
    package's own declared state) and the fail-closed assessment. Raises `AuditError` when the
    audit cannot be complete (no such directory, no package found) and `config.ConfigError` for an
    unusable `modularcv.json`; a partial report is never returned as if it were whole.
    """
    packages_dir = Path(packages_dir)
    if not packages_dir.is_dir():
        raise AuditError("PACKAGES_DIR_MISSING", "%s is not a directory" % packages_dir)
    root = config.workspace_root(root)
    files = config.provenance_files(root)
    registry_path = registry_path or packages_dir / "package-staleness.json"
    packages, contradictions = [], []
    index_path = packages_dir / "application-index.json"
    index = {}
    if index_path.is_file():
        try:
            index = {row["package_fingerprint"]: row
                     for row in canonical.loads(index_path.read_text(encoding="utf-8"))["applications"]}
        except (OSError, ValueError, KeyError, TypeError) as error:
            contradictions.append({"kind": "INDEX_UNREADABLE", "detail": str(error)})
    found = sorted(packages_dir.glob("*/package.json"))
    if not found:
        raise AuditError("NO_PACKAGES", "no <folder>/package.json under %s" % packages_dir)
    for path in found:
        try:
            package = canonical.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            package = None
        if not isinstance(package, dict):
            packages.append({"folder": path.parent.name, "status": BLOCKED, "reasons": ["PACKAGE_JSON_INVALID"],
                             "warnings": [], "details": [{"reason": "PACKAGE_JSON_INVALID",
                                                          "code": "PACKAGE_JSON_UNREADABLE",
                                                          "message": "package.json is not a valid JSON object"}]})
            continue
        verdict = assess(package, None, registry_path, root, path.parent, files)
        application = package.get("application")
        row = {"folder": path.parent.name,
               "job_id": application.get("job_id") if isinstance(application, dict) else None,
               "declared": (package.get("routing") or {}).get("workflow_state") if isinstance(package.get("routing"), dict) else None,
               **verdict}
        packages.append(row)
        listed = index.get(package.get("package_fingerprint"))
        if listed and listed.get("status") == READY and verdict["status"] != READY:
            contradictions.append({"kind": "INDEX_READY_BUT_NOT_EFFECTIVELY_READY",
                                   "folder": path.parent.name, "job_id": row["job_id"],
                                   "effective": verdict["status"], "reasons": verdict["reasons"]})
        elif row["declared"] == READY and verdict["status"] != READY and not listed:
            contradictions.append({"kind": "PACKAGE_READY_BUT_NOT_EFFECTIVELY_READY",
                                   "folder": path.parent.name, "job_id": row["job_id"],
                                   "effective": verdict["status"], "reasons": verdict["reasons"]})
    counts = {state: sum(1 for p in packages if p["status"] == state) for state in (READY, NEEDS_REVIEW, BLOCKED)}
    return {"packages": packages, "contradictions": contradictions, "counts": counts,
            "ready": [p["folder"] for p in packages if p["status"] == READY]}
