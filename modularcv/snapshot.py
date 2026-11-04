"""SourceSnapshot-v1: the files a package was built from, named by path, role and hash.

Contract: `docs/design/PROVENANCE_READINESS.md` section 5. A snapshot links the workspace
sources, the CV identity, its metadata and the final package, deterministically. Verifying one
only reads files: it never writes, repairs or re-hashes anything into the snapshot.

Hash kinds (`CONTRACTS.md` 0.1): a `text` entry carries the normalised-source hash (BOM and line
endings removed, nothing else); a `binary` entry carries the exact-bytes hash. The kind of a role
is fixed by this module, so a text file can never be hashed as binary to dodge normalisation.
"""
from collections import namedtuple

from . import canonical, paths

SCHEMA = "SourceSnapshot-v1"

# Roles covered by the workspace commit: they must also exist, unchanged, at `source_commit`.
SOURCE_ROLES = ("facts", "profile", "resume_content", "template_override", "taxonomy")
# Roles produced by the engine for one package.
ARTIFACT_ROLES = ("offer", "tailoring_plan", "assembly", "cv_tex", "cv_metadata", "cv_validation_report", "cv_pdf")
ROLES = SOURCE_ROLES + ARTIFACT_ROLES
ROLE_KIND = {role: ("binary" if role == "cv_pdf" else "text") for role in ROLES}
REQUIRED_ROLES = ("facts", "tailoring_plan", "cv_tex", "cv_metadata")
MULTIPLE_ROLES = ("resume_content", "template_override")

ENTRY_FIELDS = ("role", "path", "sha256", "size", "kind")
DOC_FIELDS = ("schema", "entries", "snapshot_fingerprint")

Problem = namedtuple("Problem", "code message role path")


class SnapshotError(ValueError):
    """A snapshot cannot be built. `code` is a stable machine code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def hash_for(kind, data):
    """The hash recorded for `data` under `kind` (`text` or `binary`)."""
    if kind == "binary":
        return canonical.sha256_bytes(data)
    return canonical.sha256_text(data)


def make_entry(role, path, data):
    if role not in ROLE_KIND:
        raise SnapshotError("SNAPSHOT_UNKNOWN_ROLE", "unknown role `%s`" % role)
    problem = paths.relative_path_problem(path)
    if problem:
        raise SnapshotError("SNAPSHOT_PATH_UNSAFE", "%s: %s" % (path, problem))
    kind = ROLE_KIND[role]
    return {"role": role, "path": path, "sha256": hash_for(kind, data), "size": len(data), "kind": kind}


def _sort_key(entry):
    return (str(entry.get("role")), str(entry.get("path")))


def fingerprint(entries):
    """Canonical fingerprint of the entries (order independent)."""
    return canonical.fingerprint({"schema": SCHEMA, "entries": sorted(entries, key=_sort_key)})


def assemble(entries):
    entries = sorted(entries, key=_sort_key)
    return {"schema": SCHEMA, "entries": entries, "snapshot_fingerprint": fingerprint(entries)}


def build(root, items, require_roles=True):
    """Snapshot of `items` = [(role, relative_path)] read from the workspace. Read-only.

    Refuses an inconsistent snapshot (unknown role, unsafe path, duplicate role, missing required
    role unless `require_roles` is False, for tests that need an incomplete one).
    """
    entries = []
    for role, relative in items:
        target = paths.resolve_inside(root, relative)
        if target is None:
            raise SnapshotError("SNAPSHOT_PATH_UNSAFE", "%s is not a safe path inside the workspace" % relative)
        if not target.is_file():
            raise SnapshotError("FILE_MISSING", "%s does not exist" % relative)
        entries.append(make_entry(role, relative, target.read_bytes()))
    document = assemble(entries)
    problems = structure_problems(document, require_roles)
    if problems:
        raise SnapshotError(problems[0].code, problems[0].message)
    return document


def entries_for(document, role):
    return [entry for entry in document.get("entries", []) if isinstance(entry, dict) and entry.get("role") == role]


def structure_problems(document, require_roles=True):
    """Everything wrong with the snapshot itself, before any file is looked at."""
    def problem(code, message, role=None, path=None):
        problems.append(Problem(code, message, role, path))

    problems = []
    if not isinstance(document, dict):
        return [Problem("SNAPSHOT_NOT_OBJECT", "the snapshot is not a JSON object", None, None)]
    if document.get("schema") != SCHEMA:
        return [Problem("SNAPSHOT_SCHEMA", "schema must be `%s`" % SCHEMA, None, None)]
    extra = sorted(set(document) - set(DOC_FIELDS))
    missing = sorted(set(DOC_FIELDS) - set(document))
    if extra or missing:
        return [Problem("SNAPSHOT_FIELDS", "unknown fields %s, missing fields %s" % (extra, missing), None, None)]
    entries = document["entries"]
    if not isinstance(entries, list):
        return [Problem("SNAPSHOT_FIELDS", "`entries` must be a list", None, None)]

    well_formed = []
    for index, entry in enumerate(entries):
        where = "entry %d" % index
        if not isinstance(entry, dict) or set(entry) != set(ENTRY_FIELDS):
            problem("SNAPSHOT_ENTRY_INVALID", "%s must hold exactly %s" % (where, ", ".join(ENTRY_FIELDS)))
            continue
        role, path, digest, size, kind = (entry[name] for name in ENTRY_FIELDS)
        if not isinstance(role, str) or role not in ROLE_KIND:
            problem("SNAPSHOT_UNKNOWN_ROLE", "%s: unknown role" % where)
            continue
        bad = paths.relative_path_problem(path)
        if bad:
            problem("SNAPSHOT_PATH_UNSAFE", "%s: %s" % (where, bad), role)
            continue
        if kind != ROLE_KIND[role]:
            problem("SNAPSHOT_KIND_MISMATCH", "%s: role `%s` must be `%s`" % (where, role, ROLE_KIND[role]), role, path)
            continue
        valid_hash = isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
        if not valid_hash or isinstance(size, bool) or not isinstance(size, int) or size < 0:
            problem("SNAPSHOT_ENTRY_INVALID", "%s: bad sha256 or size" % where, role, path)
            continue
        well_formed.append(entry)

    seen_paths = {}
    for entry in well_formed:
        previous = seen_paths.get(entry["path"])
        if previous is None:
            seen_paths[entry["path"]] = entry
        elif previous["sha256"] != entry["sha256"] or previous["role"] != entry["role"]:
            problem("SNAPSHOT_DUPLICATE_PATH", "path listed twice with different content or role", entry["role"], entry["path"])
        else:
            problem("SNAPSHOT_DUPLICATE_ENTRY", "the same entry is listed twice", entry["role"], entry["path"])
    for role in ROLES:
        count = sum(1 for entry in well_formed if entry["role"] == role)
        if count > 1 and role not in MULTIPLE_ROLES:
            problem("SNAPSHOT_DUPLICATE_ROLE", "role `%s` must appear once, found %d" % (role, count), role)
        if count == 0 and require_roles and role in REQUIRED_ROLES:
            problem("SNAPSHOT_ROLE_MISSING", "role `%s` is required" % role, role)
    if len(well_formed) == len(entries) and document["snapshot_fingerprint"] != fingerprint(entries):
        problem("SNAPSHOT_FINGERPRINT", "snapshot_fingerprint does not match the entries")
    return problems


def verify_files(document, root):
    """Compare each entry with the file now in the workspace. Read-only.

    Returns problems with code `FILE_MISSING`, `FILE_CHANGED` or `PATH_ESCAPE`. Entries that are
    malformed are skipped (see `structure_problems`).
    """
    problems = []
    for entry in document.get("entries", []):
        if not isinstance(entry, dict) or entry.get("role") not in ROLE_KIND:
            continue
        path = entry.get("path")
        if paths.relative_path_problem(path):
            continue
        role = entry["role"]
        target = paths.resolve_inside(root, path)
        if target is None:
            problems.append(Problem("PATH_ESCAPE", "%s resolves outside the workspace" % path, role, path))
            continue
        try:
            data = target.read_bytes() if target.is_file() else None
        except OSError:
            data = None
        if data is None:
            problems.append(Problem("FILE_MISSING", "%s does not exist or cannot be read" % path, role, path))
        elif hash_for(ROLE_KIND[role], data) != entry.get("sha256"):
            problems.append(Problem("FILE_CHANGED", "%s differs from the snapshot" % path, role, path))
    return problems


def verify(document, root, require_roles=True):
    """Structure and files together."""
    problems = structure_problems(document, require_roles)
    if not any(p.code in ("SNAPSHOT_NOT_OBJECT", "SNAPSHOT_SCHEMA", "SNAPSHOT_FIELDS") for p in problems):
        problems.extend(verify_files(document, root))
    return problems
