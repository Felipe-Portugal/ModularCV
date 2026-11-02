# Provenance and readiness contract (M1.1 design)

Status: **implemented in `0.2.0` (milestone M3)**. Section 1 records what `0.1.0` did (observed by running it); sections 2 to 6
are the contract the code now follows; section 9 lists the breaking changes. Tests: `tests/test_readiness.py`,
`tests/test_snapshot.py` and `tests/synthetic.py` (a synthetic workspace with a temporary Git history).

## 1. ModularCV 0.1.0 compared with the validated private 6C validator

Observed by reading both code bases and by calling `modularcv.readiness.assess` on synthetic input.

| Topic | ModularCV 0.1.0 | Private validator (6C) | Gap |
|---|---|---|---|
| CV metadata absent (`None`) | `assess` skips the check: **`READY_TO_SEND`** (observed) | `CV_METADATA_MISSING`, BLOCKED | **fail-open in 0.1.0** |
| `source_commit` all zeros | `READY_TO_SEND` with a warning (observed) | `SOURCE_COMMIT_PLACEHOLDER_LEGACY`, NEEDS_REVIEW | placeholder not an objection |
| `source_commit` well-formed but unknown | `READY_TO_SEND`, no objection (observed) | `SOURCE_COMMIT_UNVERIFIABLE`, NEEDS_REVIEW | no Git verification at readiness |
| Recorded-commit check | absent | `verify_recorded_commit` (existing commit, ancestor of HEAD, provenance files present at it; working tree **not** compared) | missing |
| New-generation check | `verify_source_commit`, `resolve_source_commit` | same, plus a result cache | cache optional |
| Which metadata belongs to a package | caller passes it; `audit_directory` passes none | resolved through the package's own source snapshot: exact path, bound by SHA-256, scoped to the applications tree, plan beside it names the package's CV | **missing** |
| Snapshot of sources | absent | `ImmutableSourceSnapshot-v1` (path, role, sha256, size per file; snapshot fingerprint) | missing |
| Reasons | `PACKAGE_STALE`, `STALENESS_REGISTRY_UNREADABLE`, `CV_METADATA_INVALID`, `PACKAGE_JSON_INVALID`, `DECLARED_*`, failed gates | adds `CV_METADATA_MISSING`, `_UNREADABLE`, `_AMBIGUOUS`, `_OUT_OF_SCOPE`, `_CHANGED_SINCE_PACKAGING`, `CV_REFERENCE_MISMATCH`, `SOURCE_COMMIT_PLACEHOLDER_LEGACY`, `SOURCE_COMMIT_UNVERIFIABLE` | missing |
| Gates override, `root`, `files` parameters | none | yes | missing |
| Audit CLI | `check-packages` (index contradictions) | `--check --root` with exit code 1 when the index contradicts the effective status | partial |
| Files covered by provenance | configured list plus the fact base | hard-coded masters, baselines and fact base | 0.1.0 is the better starting point |
| Snapshot hash of text | not applicable | raw bytes (sensitive to checkout line endings) | to fix by LF normalisation |
| Line-ending rule in provenance comparisons | `_normal` replaces `\r\n` only: a lone `\r` and a BOM are not normalised | same | align with `modularcv.canonical` (M3) |

Every gap marked **missing** is closed in `0.2.0`, except the gates override and the private result cache, which are not
carried over (the contract does not need them). The table keeps the `0.1.0` observation for the record.

Consequence (for `0.1.0` only): the engine must not rely on `0.1.0` readiness for anything it generates until the gaps marked **missing** are closed.

## 2. `source_commit`

A `source_commit` is a full 40- or 64-digit lowercase hexadecimal SHA of a commit **of the workspace repository**
(the private repository that holds the user's data), never the engine's.

New generation (`verify_source_commit`): refused unless
1. Git is available in the workspace and the value is a full, non-zero SHA;
2. the commit exists and is an ancestor of `HEAD`;
3. every provenance file exists at that commit and equals the working-tree copy (LF-normalised compare).

`resolve_source_commit` returns `HEAD` only if it passes. A missing Git, an unknown SHA, a modified covered file or an
all-zero value means **no generation**. Nothing ever writes a placeholder, and old metadata is inventoried, never rewritten.

Recorded commit (`verify_recorded_commit`): for a document that already exists. Same checks 1 and 2, plus "every provenance
file exists at that commit"; the working tree is not compared (sources may have moved on legitimately).

## 3. Files covered by provenance

Workspace-local files a generation is built from, relative to the workspace root:

- the fact base (`facts.md`);
- the profile (`profile.json`);
- the resume content (`content/*.json`);
- workspace-local overrides when present: taxonomy, templates;
- every extra path listed in `modularcv.json` → `provenance_files` (as today).

Not covered by a workspace commit: the engine's built-in templates and taxonomy. They are identified by
`engine.version` and `engine.template_version` in the metadata, and by `taxonomy_sha256` in the identity. The metadata
never claims that the engine's own commit is the source commit.

## 4. Workspace distinct from the engine repository

| Question | Contract |
|---|---|
| Where is Git read? | In the workspace root (`MODULARCV_ROOT` or the current directory), never in the engine's checkout. |
| Is the workspace a Git repository? | Required for generation. Otherwise `GIT_REPOSITORY_UNAVAILABLE`, no generation. |
| Dirty covered files | Generation refused (`SOURCE_NOT_AT_COMMIT`). Unrelated dirty files do not matter. |
| Two workspaces | Each has its own history; a commit is meaningful only in the workspace that holds it. |
| Public engine, private data | The engine repository contains no workspace content; tests use synthetic workspaces created in temporary directories with their own Git history. |

## 5. Source snapshot and the link metadata ↔ CV ↔ package

`SourceSnapshot-v1` (replaces the private repository-bound variant): a list of `{role, path, sha256, size, kind}` plus
`snapshot_fingerprint`.

- `path` is relative to the workspace root, forward slashes, no `..`, not absolute.
- `sha256` is the **normalised-source hash** for `kind: text` (BOM removed, line endings to LF, nothing else) and the
  **exact-bytes hash** for `kind: binary` (see `CONTRACTS.md` §0.1). The kind is declared per role, never guessed.
- Roles recorded for a package: `facts`, `profile`, `resume_content`, `offer`, `tailoring_plan`, `cv_tex`, `cv_metadata`,
  `cv_validation_report`, and for the package itself `cv_pdf` (binary) when present.
- It does not carry the repository state as a substitute for provenance: `source_commit` is the commit claim, the snapshot
  names the bytes.

Resolution of the metadata of a package (deterministic, never by job id, company or folder name):
1. the package's own `provenance/source-snapshot.json` names exactly one `cv_metadata` and one `tailoring_plan`;
2. the metadata path must stay inside the applications tree and match its recorded hash;
3. the plan beside the metadata must name the package's `tailored_cv_id`.

Any failure fails closed (section 6). A secondary index never promotes a package.

## 6. States and reasons

`READY_TO_SEND` is **computed**, never declared. A package's own `routing.workflow_state`, an index or an old file are inputs,
not verdicts; `apply` can only downgrade.

| Reason | State | Meaning |
|---|---|---|
| `PACKAGE_JSON_INVALID`, `STALENESS_REGISTRY_UNREADABLE`, `PACKAGE_STALE` | BLOCKED | The package cannot be trusted. |
| `CV_METADATA_MISSING`, `_UNREADABLE`, `_AMBIGUOUS`, `_OUT_OF_SCOPE`, `CV_REFERENCE_MISMATCH`, `CV_METADATA_INVALID` | BLOCKED | The CV the package references cannot be established. |
| `CV_METADATA_CHANGED_SINCE_PACKAGING` | NEEDS_REVIEW | The metadata no longer equals the file the package was built from. |
| `SOURCE_COMMIT_PLACEHOLDER_LEGACY` | NEEDS_REVIEW | All-zero value: archivable, not sendable until a controlled regeneration. |
| `SOURCE_COMMIT_UNVERIFIABLE` | NEEDS_REVIEW | Well-formed SHA that Git cannot verify (unknown, not in history, files absent at it). |
| `DECLARED_<state>` and any failed recorded gate | NEEDS_REVIEW | The package itself says it is not ready. |
| `HUMAN_REVIEW_REQUIRED` | NEEDS_REVIEW | No approved `CVQualityReview-v1` names this exact `tailored_cv_id`. |
| `FACT_VALIDATION_REQUIRED` | NEEDS_REVIEW | A `DERIVED` fact or a fact gap needs a human decision. |

Reasons added by M3 on top of the table above (stable machine codes; `details` carries a finer `code` and a message):

| Reason | State | Meaning |
|---|---|---|
| `SNAPSHOT_MISSING` | BLOCKED | No `provenance/source-snapshot.json` in the package folder (or no workspace was given to verify against). |
| `SNAPSHOT_INVALID` | BLOCKED | Unreadable, wrong schema, bad fingerprint, unknown role, unsafe path, wrong kind, missing required role. |
| `SNAPSHOT_CONTRADICTORY` | BLOCKED | The same path twice with another hash or role; a single-use role (for example the plan) listed twice. |
| `CV_METADATA_AMBIGUOUS` | BLOCKED | Two `cv_metadata` entries. |
| `SOURCE_COMMIT_MISMATCH` | BLOCKED | A source of the snapshot is not what the recorded commit holds at that path: the commit claim is false. |
| `SOURCE_CHANGED_SINCE_PACKAGING`, `SOURCE_MISSING` | NEEDS_REVIEW | A workspace source no longer equals (or no longer exists as) the file in the snapshot. |
| `ARTIFACT_CHANGED_SINCE_PACKAGING`, `ARTIFACT_MISSING` | NEEDS_REVIEW | Same, for the plan, the CV document or another artefact. |
| `HUMAN_REVIEW_MISMATCH` | NEEDS_REVIEW | An approval exists but names another `tailored_cv_id` or another document hash. |
| `HUMAN_REVIEW_INVALID` | NEEDS_REVIEW | `cv-quality-review.json` is unreadable or malformed. |
| `HUMAN_REVIEW_REJECTED` | BLOCKED | The reviewer recorded `REJECTED`. |

`CV_METADATA_INVALID` covers a missing or malformed `source_commit` (`details.code`: `SOURCE_COMMIT_MISSING`,
`SOURCE_COMMIT_MALFORMED`) as well as every schema problem of a v1/v2 document. `SOURCE_COMMIT_UNVERIFIABLE` carries the Git
status in `details.code` (`SOURCE_COMMIT_UNKNOWN`, `SOURCE_COMMIT_NOT_IN_HISTORY`, `SOURCE_NOT_AT_COMMIT`, `GIT_UNAVAILABLE`,
`GIT_REPOSITORY_UNAVAILABLE`, `WORKSPACE_NOT_REPOSITORY_ROOT`). Warnings (never objections): `LEGACY_METADATA_SCHEMA_VERSION_1`
and `_2`.

Any objection prevents `READY_TO_SEND`; a BLOCKED reason wins over NEEDS_REVIEW. A single package of an audit cannot hide another:
`audit_directory` reports each package and every contradiction between the index (or the declared state) and the computed status.

## 7. Human validation conditions

A generated CV is never ready on its own. It carries `HUMAN_REVIEW_REQUIRED` until a person records `CVQualityReview-v1`
(`decision: APPROVED`, the exact `tailored_cv_id`, an optional note, written beside the CV, never editing it). A new CV identity
needs a new review. `DERIVED` facts and fact gaps listed in `human_validations_required` must be settled by editing the fact
base, which changes its fingerprint and therefore the identity of every dependent CV.

## 8. Known defect and mandatory correction (closed in `0.2.0`)

`0.1.0` readiness is **fail-open** on the points of section 1 (observed: `READY_TO_SEND` with absent metadata, an all-zero
`source_commit`, or an unknown SHA). The correction is **mandatory in milestone M3** and ships as `0.2.0`, a breaking
fail-closed change with its own tests. Until then, nothing generated by this engine may be treated as ready on the strength of
`modularcv.readiness`. M2 deliberately leaves `readiness` untouched; this document changes no behaviour.

## 9. `0.2.0`: what changed, and what is incompatible

Implemented in milestone M3. Evidence layout of a package, all workspace-relative:

```
packages/<folder>/package.json
packages/<folder>/provenance/source-snapshot.json   SourceSnapshot-v1: exactly one facts, tailoring_plan, cv_tex, cv_metadata
applications/<job>/cv/metadata.json                 CV metadata, schema_version "1" or "2"
applications/<job>/cv/tailoring-plan.json           names the package's tailored_cv_id
applications/<job>/cv/cv-quality-review.json        CVQualityReview-v1, written by a person
```

`CVQualityReview-v1` = `{schema, decision: APPROVED|REJECTED, tailored_cv_id, document_sha256, note?, reviewer?}`. Extension of the
M1.1 text: besides the identity, the approval names `document_sha256` (the snapshot hash of the `cv_tex`), so editing the document
under an unchanged identity voids the approval. Unknown fields are refused. The contract name `SourceSnapshot-v1` (section 5)
is the one implemented; the private `ImmutableSourceSnapshot-v1` is not.

Hash kinds in snapshots follow `CONTRACTS.md` 0.1; the kind is fixed by the role (`cv_pdf` is `binary`, every other role `text`).

**Breaking changes (readiness, `0.1.0` to `0.2.0`)**

| Before (`0.1.0`) | Now (`0.2.0`) |
|---|---|
| `assess(package, None, registry)` could be READY | Never READY without `root` and `package_dir`; `CV_METADATA_MISSING` (BLOCKED) |
| `assess(package, {"source_commit": <any 40 hex>}, registry)` was READY | Never READY: the commit is verified in the workspace Git repository |
| All-zero `source_commit` was a warning | Reason `SOURCE_COMMIT_PLACEHOLDER_LEGACY`, NEEDS_REVIEW |
| Unknown SHA accepted | `SOURCE_COMMIT_UNVERIFIABLE`, NEEDS_REVIEW |
| `assess` returned `status`, `reasons`, `warnings` | Adds `details` (`reason`, `code`, `message`) |
| `audit_directory(dir, registry)` passed no metadata | `audit_directory(dir, registry, root)` resolves everything from each package's snapshot |
| `check-packages` on a folder without package: empty report, exit 0 | `AuditError` (`PACKAGES_DIR_MISSING`, `NO_PACKAGES`), exit 2 |
| `check-packages` ignored configuration errors | `ConfigError`, exit 2 |
| Provenance compared text after replacing `CRLF` only | BOM, `CRLF` and lone `CR` are normalised (same rule as `canonical.sha256_text`) |
| `modularcv.json` accepted unsafe paths | Absolute, `..`, backslash, drive-letter and `:` paths are refused; new optional key `applications_dir` |
| The workspace could be a folder inside another repository | It must be the top level of its own repository (`WORKSPACE_NOT_REPOSITORY_ROOT`) |

Historical metadata: v1 and v2 stay readable and are never repaired, but get no automatic READY: without a snapshot they are
BLOCKED, without an approval NEEDS_REVIEW. Version 3 is refused until M7 defines it. Old packages are never written or migrated.

CLI exit codes: `check-packages` 0 = no contradiction, 1 = a contradiction between declared or indexed state and the computed
status, 2 = incomplete audit or unusable configuration. `snapshot verify FILE`: 0 consistent, 1 problems, 2 unreadable file.
`provenance --verify SHA [--recorded]`: 0 and the SHA on stdout, 2 and a JSON error on stderr.
