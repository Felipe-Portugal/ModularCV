"""Source provenance for generated documents.

Every generated metadata file carries a `source_commit`. Contract: it is a real Git commit
that contains the sources the document was built from (the fact base, the master and the
baselines). This module establishes that or refuses; it never invents a SHA and never
returns a placeholder.

A commit qualifies as the provenance of a generation when
1. Git is available and `commit` is a full 40- or 64-digit lowercase hexadecimal SHA that
   is not all zeros;
2. the object exists and is a commit reachable from the current HEAD;
3. every provenance file exists at that commit and equals the working-tree copy that was
   read (line endings ignored), so the commit really identifies the sources used.

Historical metadata written before this check existed is never touched; see
`inventory_placeholders` for a read-only report.
"""
import json
import re
import subprocess
from pathlib import Path

from . import config

SHA_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class SourceProvenanceError(RuntimeError):
    """The source commit cannot be established. `status` is a stable machine code."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def is_placeholder(value) -> bool:
    """True for an absent value or one made only of zeros."""
    return not value or set(str(value)) == {"0"}


def validate_sha(value) -> str:
    """Format check only: returns the SHA or raises INVALID_SOURCE_COMMIT."""
    if not isinstance(value, str) or not SHA_PATTERN.match(value):
        raise SourceProvenanceError(
            "INVALID_SOURCE_COMMIT",
            "source_commit must be a full 40/64-digit lowercase hexadecimal Git SHA, got %r"
            % (value,))
    if is_placeholder(value):
        raise SourceProvenanceError(
            "INVALID_SOURCE_COMMIT", "source_commit is an all-zero placeholder, not a commit")
    return value


def _git(root: Path, *args):
    try:
        return subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True)
    except FileNotFoundError as error:
        raise SourceProvenanceError(
            "GIT_UNAVAILABLE",
            "Git is not available, so the source commit cannot be established: %s" % error)


def _normal(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def verify_source_commit(commit: str, root=None, files=None) -> str:
    """Return `commit` if it satisfies the contract for the working tree, else raise."""
    root = config.workspace_root(root)
    validate_sha(commit)
    if _git(root, "cat-file", "-e", commit + "^{commit}").returncode != 0:
        raise SourceProvenanceError(
            "SOURCE_COMMIT_UNKNOWN", "Commit %s does not exist in this repository" % commit)
    if _git(root, "merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
        raise SourceProvenanceError(
            "SOURCE_COMMIT_NOT_IN_HISTORY", "Commit %s is not an ancestor of HEAD" % commit)
    names = files if files is not None else config.provenance_files(root)
    for relative in names:
        shown = _git(root, "show", "%s:%s" % (commit, relative))
        if shown.returncode != 0:
            raise SourceProvenanceError(
                "SOURCE_NOT_AT_COMMIT", "%s does not exist at commit %s" % (relative, commit[:12]))
        path = root / relative
        if not path.is_file():
            raise SourceProvenanceError("SOURCE_NOT_AT_COMMIT", "%s is missing" % relative)
        if _normal(shown.stdout) != _normal(path.read_bytes()):
            raise SourceProvenanceError(
                "SOURCE_NOT_AT_COMMIT",
                "%s differs from commit %s: commit the validated sources before generating"
                % (relative, commit[:12]))
    return commit


_cache = {}


def resolve_source_commit(root=None, files=None) -> str:
    """HEAD, verified against the contract. Raises SourceProvenanceError otherwise."""
    root = config.workspace_root(root)
    head = _git(root, "rev-parse", "HEAD")
    if head.returncode != 0:
        raise SourceProvenanceError(
            "GIT_REPOSITORY_UNAVAILABLE", "No Git commit could be read in %s: %s"
            % (root, head.stderr.decode("utf-8", "replace").strip()))
    sha = head.stdout.decode("ascii").strip()
    names = tuple(files if files is not None else config.provenance_files(root))
    signature = (str(root), sha, names, tuple(
        (p.stat().st_mtime_ns, p.stat().st_size) if p.is_file() else None
        for p in (root / n for n in names)))
    if signature not in _cache:
        _cache[signature] = verify_source_commit(sha, root, names)
    return _cache[signature]


def inventory_placeholders(root=None, folder: str = "applications") -> dict:
    """Read-only inventory of `metadata.json` files whose `source_commit` is not a real commit.

    Nothing is rewritten. Returns counts and the list of affected paths.
    """
    root = config.workspace_root(root)
    placeholders, real, unreadable = [], [], []
    for path in sorted((root / folder).rglob("metadata.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("source_commit")
        except (OSError, ValueError):
            unreadable.append(path.relative_to(root).as_posix())
            continue
        if value is None:
            continue
        (placeholders if is_placeholder(value) else real).append(path.relative_to(root).as_posix())
    return {"placeholder_count": len(placeholders), "real_count": len(real),
            "unreadable": unreadable, "placeholders": placeholders}
