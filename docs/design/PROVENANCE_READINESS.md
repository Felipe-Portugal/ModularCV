# Provenance and readiness contract (M1.1 design)

Status: **design, not implemented**. Section 1 records what `0.1.0` does today (observed by running it); sections 2 to 6
define the contract the engine will implement. Changing `0.1.0` behaviour is a separate, explicit decision (section 7).

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

Consequence: the engine must not rely on `0.1.0` readiness for anything it generates until the gaps marked **missing** are closed.

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

Any objection prevents `READY_TO_SEND`; a BLOCKED reason wins over NEEDS_REVIEW. A single package of an audit cannot hide another:
`audit_directory` reports each package and every contradiction between the index (or the declared state) and the computed status.

## 7. Human validation conditions

A generated CV is never ready on its own. It carries `HUMAN_REVIEW_REQUIRED` until a person records `CVQualityReview-v1`
(`decision: APPROVED`, the exact `tailored_cv_id`, an optional note, written beside the CV, never editing it). A new CV identity
needs a new review. `DERIVED` facts and fact gaps listed in `human_validations_required` must be settled by editing the fact
base, which changes its fingerprint and therefore the identity of every dependent CV.

## 8. Known defect and mandatory correction

`0.1.0` readiness is **fail-open** on the points of section 1 (observed: `READY_TO_SEND` with absent metadata, an all-zero
`source_commit`, or an unknown SHA). The correction is **mandatory in milestone M3** and ships as `0.2.0`, a breaking
fail-closed change with its own tests. Until then, nothing generated by this engine may be treated as ready on the strength of
`modularcv.readiness`. M2 deliberately leaves `readiness` untouched; this document changes no behaviour.
