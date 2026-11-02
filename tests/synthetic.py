"""A synthetic workspace (fictional data, temporary Git repository) for readiness tests.

`Workspace(tmp_path)` builds a workspace in which a package is genuinely READY_TO_SEND:
facts committed, CV metadata naming that commit, a plan beside it, a source snapshot bound by hash,
and a human approval of the exact CV. Tests then break one piece of evidence at a time.
"""
import hashlib
import json
import subprocess
from pathlib import Path

from modularcv import canonical, readiness, review, snapshot

GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
       "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]
GATES = {"HANDOFF_PASS": True, "CV_PASS": True, "LETTER_PASS": True, "CROSS_ARTIFACT_PASS": True,
         "PDF_PASS": True, "PROVENANCE_PASS": True, "PACKAGE_MANIFEST_PASS": True,
         "CV_QUALITY_REVIEW_PASS": True}
FACTS = "<!-- modularcv: FactBase-v1 -->\n## S {#s}\n- [a.one] CONFIRMED: A synthetic fact.\n"


def git(root, *args):
    return subprocess.run(GIT + list(args), cwd=str(root), check=True,
                          capture_output=True).stdout.decode().strip()


def tree_hash(root):
    """Hash of every file under `root` (the .git directory included): proves nothing was written."""
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


class Workspace:
    def __init__(self, tmp_path, job=1, schema_version="2"):
        self.root = Path(tmp_path) / "workspace"
        self.job = job
        self.cv_id = "cv-id-%d" % job
        self.folder = "%d-co" % job
        self.app = "applications/job-%d/cv" % job
        self.meta_rel = self.app + "/metadata.json"
        self.plan_rel = self.app + "/tailoring-plan.json"
        self.cv_rel = self.app + "/cv.tex"
        self.review_rel = self.app + "/" + review.FILE_NAME
        self.package_dir = self.root / "packages" / self.folder
        self.registry = self.root / "packages" / "package-staleness.json"
        self.root.mkdir(parents=True)
        self.write("facts.md", FACTS)
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "validated sources")
        self.commit = git(self.root, "rev-parse", "HEAD")
        self.write(self.cv_rel, "\\documentclass{article}\n%% synthetic CV %d\n" % job)
        self.write_json(self.plan_rel, {"schema": "TailoringPlan-v1", "tailored_cv_id": self.cv_id})
        self.metadata = {
            "schema_version": schema_version, "job_key": "job-%d" % job, "generated_at": "2026-01-01T00:00:00Z",
            "language": "en", "family": "software", "source_commit": self.commit,
            "master_resume": "master/resume.tex", "facts_source": "facts.md", "company": "Example Corp",
            "title": "Developer", "job_sha256": "a" * 64,
            "decision": {"selected_content": [], "excluded_content": [], "human_validations_required": []}}
        self.write_metadata()
        self.package = {"application": {"job_id": job}, "routing": {"workflow_state": readiness.READY, "reasons": []},
                        "validation": {"gates": dict(GATES)}, "package_fingerprint": ("f%d" % job) * 8,
                        "artifacts": {"cv": {"tailored_cv_id": self.cv_id}}}
        self.write_registry()
        self.write_snapshot()
        self.write_review()
        self.write_package()

    # --- writers -------------------------------------------------------------------------------
    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
        return path

    def write_json(self, relative, obj):
        return self.write(relative, json.dumps(obj, indent=2))

    def write_metadata(self):
        self.write_json(self.meta_rel, self.metadata)

    def write_registry(self, *entries):
        self.write_json("packages/package-staleness.json",
                        {"registry_version": "StalePackageRegistry-v1", "packages": list(entries)})

    def items(self):
        return [("facts", "facts.md"), ("tailoring_plan", self.plan_rel), ("cv_tex", self.cv_rel),
                ("cv_metadata", self.meta_rel)]

    def write_snapshot(self, items=None):
        document = snapshot.build(self.root, items or self.items(), require_roles=items is None)
        self.write_json("packages/%s/provenance/source-snapshot.json" % self.folder, document)
        return document

    def cv_hash(self):
        return canonical.sha256_text((self.root / self.cv_rel).read_bytes())

    def write_review(self, **overrides):
        document = {"schema": review.SCHEMA, "decision": "APPROVED", "tailored_cv_id": self.cv_id,
                    "document_sha256": self.cv_hash()}
        document.update(overrides)
        self.write_json(self.review_rel, document)

    def write_package(self):
        self.write_json("packages/%s/package.json" % self.folder, self.package)

    def commit_all(self, message="change"):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)
        return git(self.root, "rev-parse", "HEAD")

    # --- verdict -------------------------------------------------------------------------------
    def assess(self, package=None):
        return readiness.assess(package or self.package, None, self.registry, self.root, self.package_dir)

    def audit(self):
        return readiness.audit_directory(self.root / "packages", None, self.root)
