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
import os
import re
import subprocess
from pathlib import Path

from . import canonical, config, paths

SHA_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class SourceProvenanceError(RuntimeError):
    """The source commit cannot be established. `status` is a stable machine code.

    For `SOURCE_NOT_AT_COMMIT`, `reason` says why (`MISSING`, `UNTRACKED`, `MODIFIED`,
    `NOT_IN_COMMIT`, `UNSAFE_PATH`) and `path` names the file.
    """

    def __init__(self, status: str, message: str, reason=None, path=None):
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.path = path


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
    """The text comparison of provenance: BOM removed, CRLF and lone CR turned into LF."""
    return canonical.normalise_source_bytes(data)


def _require_workspace_repository(root: Path):
    """The workspace must itself be the top level of a Git repository, never a folder that merely
    sits inside another one (the engine's, for example)."""
    top = _git(root, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise SourceProvenanceError(
            "GIT_REPOSITORY_UNAVAILABLE", "%s is not inside a Git repository: %s"
            % (root, top.stderr.decode("utf-8", "replace").strip()))
    reported = top.stdout.decode("utf-8", "replace").strip()
    try:
        same = os.path.samefile(reported, str(root))
    except OSError:
        same = False
    if not same:
        raise SourceProvenanceError(
            "WORKSPACE_NOT_REPOSITORY_ROOT",
            "%s is inside the Git repository %s but is not its root; the workspace must be a "
            "repository of its own" % (root, reported))


def _check_commit(commit: str, root: Path):
    validate_sha(commit)
    _require_workspace_repository(root)
    if _git(root, "cat-file", "-e", commit + "^{commit}").returncode != 0:
        raise SourceProvenanceError(
            "SOURCE_COMMIT_UNKNOWN", "Commit %s does not exist in this repository" % commit)
    if _git(root, "merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
        raise SourceProvenanceError(
            "SOURCE_COMMIT_NOT_IN_HISTORY", "Commit %s is not an ancestor of HEAD" % commit)


def _safe(relative: str):
    problem = paths.relative_path_problem(relative)
    if problem:
        raise SourceProvenanceError(
            "SOURCE_NOT_AT_COMMIT", "%r is not a safe workspace path: %s" % (relative, problem),
            "UNSAFE_PATH", relative if isinstance(relative, str) else None)


def verify_recorded_commit(commit: str, root=None, files=None) -> str:
    """For a document that already exists: the commit exists, is an ancestor of HEAD and holds
    every provenance file. The working tree is **not** compared (sources may have moved on)."""
    root = config.workspace_root(root)
    _check_commit(commit, root)
    names = files if files is not None else config.provenance_files(root)
    for relative in names:
        _safe(relative)
        if _git(root, "cat-file", "-e", "%s:%s" % (commit, relative)).returncode != 0:
            raise SourceProvenanceError(
                "SOURCE_NOT_AT_COMMIT", "%s does not exist at commit %s" % (relative, commit[:12]),
                "NOT_IN_COMMIT", relative)
    return commit


def hash_at_commit(commit: str, root, relative: str) -> str:
    """Normalised-source hash of `relative` as stored in `commit` (read-only)."""
    _safe(relative)
    shown = _git(Path(root), "show", "%s:%s" % (commit, relative))
    if shown.returncode != 0:
        raise SourceProvenanceError(
            "SOURCE_NOT_AT_COMMIT", "%s does not exist at commit %s" % (relative, commit[:12]),
            "NOT_IN_COMMIT", relative)
    return canonical.sha256_text(shown.stdout)


def verify_source_commit(commit: str, root=None, files=None) -> str:
    """Return `commit` if it satisfies the contract for the working tree, else raise."""
    root = config.workspace_root(root)
    _check_commit(commit, root)
    names = files if files is not None else config.provenance_files(root)
    for relative in names:
        _safe(relative)
        shown = _git(root, "show", "%s:%s" % (commit, relative))
        path = root / relative
        in_commit = shown.returncode == 0
        if not path.is_file():
            reason = "MISSING"
            message = "%s is missing from the working tree" % relative
        elif not in_commit:
            reason = "UNTRACKED"
            message = "%s exists but is not part of commit %s (untracked or added later)" % (
                relative, commit[:12])
        elif _normal(shown.stdout) != _normal(path.read_bytes()):
            reason = "MODIFIED"
            message = ("%s differs from commit %s: commit the validated sources before generating"
                       % (relative, commit[:12]))
        else:
            continue
        raise SourceProvenanceError("SOURCE_NOT_AT_COMMIT", message, reason, relative)
    return commit


_cache = {}


def resolve_source_commit(root=None, files=None) -> str:
    """HEAD, verified against the contract. Raises SourceProvenanceError otherwise."""
    root = config.workspace_root(root)
    _require_workspace_repository(root)
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
            value = canonical.loads(path.read_text(encoding="utf-8")).get("source_commit")
        except (OSError, ValueError):
            unreadable.append(path.relative_to(root).as_posix())
            continue
        if value is None:
            continue
        (placeholders if is_placeholder(value) else real).append(path.relative_to(root).as_posix())
    return {"placeholder_count": len(placeholders), "real_count": len(real),
            "unreadable": unreadable, "placeholders": placeholders}
