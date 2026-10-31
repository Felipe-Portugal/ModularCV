"""Fail-closed readiness of an application package.

Rule: a package is `READY_TO_SEND` only if *every* independent source of truth agrees.
A stale package, a package whose CV metadata is invalid, one that still waits for a human
review, or one whose staleness registry cannot be read is NEVER ready, whatever a secondary
index or an old `package.json` says.

Sources consulted (any single objection blocks):
- the declared `routing.workflow_state` and the recorded gates of the package;
- the staleness registry, by package fingerprint and by tailored CV identity;
- the CV `metadata.json`: `source_commit` must at least be a well-formed SHA.

An all-zero `source_commit` (a legacy placeholder generated before the provenance check) is
reported as a warning and is *not* silently repaired.
"""
import json
from pathlib import Path

from . import staleness
from .provenance import SHA_PATTERN, is_placeholder

READY = "READY_TO_SEND"
NEEDS_REVIEW = "NEEDS_REVIEW"
BLOCKED = "BLOCKED"

# Reasons that make a package unusable (BLOCKED) rather than merely unreviewed.
HARD_REASONS = ("PACKAGE_STALE", "STALENESS_REGISTRY_UNREADABLE",
                "CV_METADATA_INVALID", "PACKAGE_JSON_INVALID")


def _registry(path) -> tuple:
    """(registry, error). A missing registry is an empty one; an unreadable one is an error."""
    try:
        data = staleness.load(path)
        if not isinstance(data.get("packages"), list):
            raise ValueError("no packages list")
        return data, None
    except (OSError, ValueError, AttributeError) as error:
        return None, str(error)


def assess(package: dict, cv_metadata: dict, registry_path) -> dict:
    """Effective status and the reasons behind it. Never returns READY on any objection."""
    reasons, warnings = [], []
    try:
        declared = package["routing"]["workflow_state"]
        recorded = package["validation"]["gates"]
    except (KeyError, TypeError):
        return {"status": BLOCKED, "reasons": ["PACKAGE_JSON_INVALID"], "warnings": []}
    if declared != READY:
        reasons.append("DECLARED_" + str(declared))
    reasons.extend(name for name, ok in sorted(recorded.items()) if not ok)

    registry, _error = _registry(registry_path)
    if registry is None:
        reasons.append("STALENESS_REGISTRY_UNREADABLE")
    else:
        fingerprint = package.get("package_fingerprint")
        cv_id = (package.get("artifacts", {}).get("cv", {}) or {}).get("tailored_cv_id")
        for entry in registry["packages"]:
            if entry.get("status", "STALE") != "STALE":
                continue
            if (fingerprint and entry.get("package_fingerprint") == fingerprint) or (
                    cv_id and entry.get("tailored_cv_id") == cv_id):
                reasons.append("PACKAGE_STALE")

    if cv_metadata is not None:
        value = cv_metadata.get("source_commit")
        if not isinstance(value, str) or not SHA_PATTERN.match(value):
            reasons.append("CV_METADATA_INVALID")
        elif is_placeholder(value):
            warnings.append("SOURCE_COMMIT_PLACEHOLDER_LEGACY")

    reasons = list(dict.fromkeys(reasons))
    if not reasons:
        return {"status": READY, "reasons": [], "warnings": warnings}
    hard = any(r in HARD_REASONS for r in reasons)
    return {"status": BLOCKED if hard else NEEDS_REVIEW, "reasons": reasons,
            "warnings": warnings}


def apply(package: dict, cv_metadata: dict, registry_path) -> dict:
    """Downgrade `package` in place if the assessment objects; never upgrades it."""
    verdict = assess(package, cv_metadata, registry_path)
    current = package["routing"]["workflow_state"]
    rank = {READY: 0, NEEDS_REVIEW: 1, BLOCKED: 2}
    if rank.get(verdict["status"], 2) > rank.get(current, 2):
        package["routing"]["workflow_state"] = verdict["status"]
    for reason in verdict["reasons"]:
        if reason not in package["routing"]["reasons"] and not reason.startswith("DECLARED_"):
            package["routing"]["reasons"].append(reason)
    package["validation"]["warnings"] = verdict["warnings"]
    return verdict


def audit_directory(packages_dir, registry_path=None) -> dict:
    """Read-only check of every package folder and of the secondary index.

    Reports each package's effective status and every contradiction between the index (or
    the package's own declared state) and the fail-closed assessment.
    """
    packages_dir = Path(packages_dir)
    registry_path = registry_path or packages_dir / "package-staleness.json"
    packages, contradictions = [], []
    index_path = packages_dir / "application-index.json"
    index = {}
    if index_path.is_file():
        try:
            index = {row["package_fingerprint"]: row
                     for row in json.loads(index_path.read_text(encoding="utf-8"))["applications"]}
        except (OSError, ValueError, KeyError) as error:
            contradictions.append({"kind": "INDEX_UNREADABLE", "detail": str(error)})
    for path in sorted(packages_dir.glob("*/package.json")):
        try:
            package = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            packages.append({"folder": path.parent.name, "status": BLOCKED,
                             "reasons": ["PACKAGE_JSON_INVALID"], "warnings": []})
            continue
        verdict = assess(package, None, registry_path)
        row = {"folder": path.parent.name, "job_id": package.get("application", {}).get("job_id"),
               "declared": package.get("routing", {}).get("workflow_state"), **verdict}
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
    return {"packages": packages, "contradictions": contradictions,
            "ready": [p["folder"] for p in packages if p["status"] == READY]}
