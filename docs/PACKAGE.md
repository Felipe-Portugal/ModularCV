# CV packages, human approval and readiness (M7-B)

A **package** ties together, inside your private workspace, everything that produced one CV for one job: the plan, the assembled
CV, the `.tex`, the PDF, the CV metadata, a snapshot of the sources and a small `package.json`. A person then reviews the exact PDF
and approves it. `READY_TO_SEND` is **computed** from that evidence every time you ask; it is never stored and never typed.
Nothing here sends anything: ModularCV has no distribution or sending mechanism.

> **Privacy.** The `.tex`, the PDF, the compilation log (`--log`), the assembly and the review file can hold your personal data
> and your professional history. They belong in your private workspace, never in a public repository. Diagnostics of these
> commands name identifiers, hashes and reason codes, never a line of your CV, your name or your contact details.

## The procedure

```bash
# 1. prepare your sources (facts.md, profile.json, content/resume.json, offers/job.json) and commit them in the workspace repository
python -m modularcv plan   --offer offers/job.json --out plans/job.json                 # 2. the plan (M6)
python -m modularcv render --plan plans/job.json --offer offers/job.json \
                           --out out/job.tex --pdf out/job.pdf                          # 3. assemble, render, compile (M7-A)
python -m modularcv package create --name job --plan plans/job.json --offer offers/job.json \
                           --tex out/job.tex --compile                                  # 4. the package (never an approval)
#    --compile packages the compiler's own output for the verified .tex. A PDF handed over with --pdf instead is recorded as
#    SUPPLIED_PROVENANCE_NOT_VERIFIED and the package can never be READY_TO_SEND (see "PDF origin" below)
python -m modularcv package review --name job                                          # 5. what to examine, and the exact PDF hash
#    open applications/job/cv/resume.pdf and read it, all of it
python -m modularcv package approve --name job --reviewer "Your Name"                  # 6. YOU, in a terminal: type the hash prefix
python -m modularcv package status --name job                                          # 7. exit 0 only if READY_TO_SEND
```

Run `package status` again before every use: it re-derives the whole chain. Any change to a source, a file of the package or the PDF
after the approval takes `READY_TO_SEND` away (see "When something changes").

## Files of a package (all new, never overwritten)

```
applications/<name>/cv/tailoring-plan.json   the plan, byte for byte as you passed it
applications/<name>/cv/assembly.json         the assembled CV (AssembledResume-v1)
applications/<name>/cv/resume.tex            the .tex, byte for byte
applications/<name>/cv/resume.pdf            the PDF (optional but required for READY_TO_SEND)
applications/<name>/cv/metadata.json         CV metadata, schema_version "3"
applications/<name>/cv/cv-quality-review.json  written last, by a person (CVQualityReview-v2)
packages/<name>/package.json                 ApplicationPackage-v2
packages/<name>/provenance/source-snapshot.json   SourceSnapshot-v1
```

`<name>` is lowercase letters, digits, `.` and `-`. A package is never edited: to change anything, create a new one.

## The dependency graph of the fingerprints (no cycle)

```
facts, profile, content, taxonomy, offer      workspace sources, committed in the workspace Git repository
   └─> plan             plan_sha256, with the canonical fingerprint of every source in `inputs`
        └─> assembly    assembly_sha256
             └─> .tex   tex_sha256 (exact bytes; also depends on the paper size)
                  └─> .pdf   pdf_sha256 (exact bytes; compiled from the .tex, not reproducible)
                       └─> metadata v3   names all of the above and the workspace commit
                            └─> snapshot   path, role, hash and size of the files above
                                 └─> package.json   names the snapshot fingerprint; carries no verdict
                                      └─> review (written by a person, outside the snapshot)
tailored_cv_id = sha256 of the plan's fingerprints, the language, the template and the engine version
```

Order of creation: artefacts → metadata → snapshot → `package.json`; the review comes last. No document contains the hash of a
document that contains its own hash. Two kinds of hash are kept apart: **canonical fingerprints** of structured sources (key order and
whitespace do not matter) and **exact-byte hashes** of artefacts (the `.tex`, the PDF); text files in the snapshot use the
normalised-source hash (BOM and line endings), binary ones the exact bytes.

## Contracts

**`tailored_cv_id`** (`TailoredCvIdentity-v1`): the canonical fingerprint of `{engine_version, template_id, language, plan_sha256,
facts_source_sha256, factbase_sha256, content_sha256, profile_sha256, taxonomy_sha256, offer_sha256}`. No path, no name, no clock;
it can be recomputed from the plan file and the engine version recorded in the metadata.

**CV metadata, `schema_version: "3"`** (`metadata.py`): exactly the fields `tailored_cv_id, job_key, language, family,
source_commit, facts_source, taxonomy, company, title, job_sha256, plan_sha256, assembly_sha256, tex_sha256, pdf_sha256, pdf_pages,
page_target, paper, template_id, engine_version, inputs{six fingerprints}, decision{selected_content, excluded_content,
human_validations_required}, unsatisfied_required, pending_directives, warnings`. No `generated_at`, no `master_resume`. Versions 1 and 2
stay readable, are never repaired and **never become `READY_TO_SEND` on their own**: they keep the M3 rules (snapshot and a review of the
`.tex` required); an unknown version (4, ...) is refused.

**`ApplicationPackage-v2`**: `application.job_id`, `artifacts.cv` (identity, language, family, `document_role: cv_pdf`, the five paths),
`routing.workflow_state` = `UNEVALUATED`, `validation.gates`, `snapshot_fingerprint`, `package_fingerprint`. A v2 package that declares a
verdict (for example `READY_TO_SEND`) is `BLOCKED`.

**`SourceSnapshot-v1`** (M3, extended): two roles added, `taxonomy` (a workspace taxonomy file, when the profile names one) and
`assembly`. A version 3 package snapshots `facts, profile, resume_content, offer, tailoring_plan, assembly, cv_tex, cv_metadata`,
plus `taxonomy` and `cv_pdf` when they exist. Guarantees: each listed file is the one packaged (a missing, changed, substituted,
duplicated or unsafe-path entry is reported) and each source equals its content at the recorded commit. Not guaranteed: that the
snapshot is genuine (a person who can edit the workspace can rebuild it; Git history and your own backups are the defence) and
that files it does not list are unchanged. A built-in taxonomy is not a file: it is identified by `taxonomy_sha256`.

**`CVQualityReview-v2`**: `schema, decision (APPROVED|REJECTED), tailored_cv_id, document_role (cv_pdf), document_sha256 (exact
bytes of the PDF), reviewed{plan_sha256, assembly_sha256, tex_sha256}, acknowledged{unsatisfied_required, pending_directives, warnings,
page_verdict}, reviewer, note?`. The approval binds a decision to **the exact PDF** and records what the reviewer was shown: if the
PDF, the plan, the warnings or the pagination change, it no longer applies. The approval of a `.tex` never covers a PDF, and the PDF
hash is read from the file **now**, not from the snapshot.

## The human step

`package review` prints what to examine and writes nothing: the document and its hash, language, family, page count against the
family's target (`TARGET_MET`, `TARGET_EXCEEDED`, `NOT_COMPILED`, `NO_TARGET`), the **unsatisfied required requirements**, the
unresolved `soften` directives, the warnings, the limits below. `package approve` is a person's act: it refuses to run without an
interactive terminal, prints the same summary, and asks you to type the first 12 characters of the PDF's sha256 after you have opened
and read the PDF. An agent or a script cannot approve in your place; a script that fakes a terminal can write the file by hand, which is
the limit of an unsigned JSON file. Tests use clearly fictional approvals in temporary workspaces; they are never real approvals.

`REJECTED` is recorded the same way and makes the package `BLOCKED`. A review is never overwritten: move it aside to review again.

## States

`READY_TO_SEND`, `NEEDS_REVIEW` and `BLOCKED` keep the M3 meaning (`PROVENANCE_READINESS.md` §6): `BLOCKED` when the package or its chain
cannot be trusted (invalid or contradictory snapshot or package, metadata that does not match the chain, a plan, assembly or `.tex` that no
longer verifies, a rejected review, a stale package); `NEEDS_REVIEW` when the evidence is intact but incomplete or moved on (no review, no
PDF, a source or artefact changed since packaging, a commit Git cannot verify). Exit codes of `package status`: 0 / 1 / 3 for the three
states, 2 when the package cannot be read.

**`READY_TO_SEND` needs all of these, re-derived on every call:** the sources present, valid and equal to the snapshot and to the commit; a
workspace Git repository with the recorded commit in history; the facts used still `CONFIRMED` (the plan re-verifies against the current
sources); the plan, the assembly, the `.tex` and the metadata consistent with each other and with the identity; the snapshot and
`package.json` intact; **a PDF**, whose hash is the one in the metadata and the snapshot; an approving `CVQualityReview-v2` that names this
identity and this exact PDF, with the same plan, assembly and `.tex` hashes and the same warnings as now; and no failing gate or
stale registry entry. Unresolved `soften` directives and unsatisfied required requirements do not block, but they must have been shown to the
reviewer and recorded in the approval.

**A `.tex` alone is never ready.** The conservative policy: the document that can be approved and sent is the PDF. A package without one is
`NEEDS_REVIEW` (`FINAL_DOCUMENT_MISSING`) and `package approve` refuses.

**`READY_TO_SEND` proves the process, not the candidate.** It does not say that you meet the job's requirements: the unsatisfied required
requirements stay listed in the metadata, in `package status` and in the review. Nor does an approval replace a provenance check: a
package whose chain is broken cannot be approved and loses readiness whatever a review says.

## When something changes

| After packaging (and after the approval) | Result |
|---|---|
| a source: fact, profile, content, taxonomy file, offer | `NEEDS_REVIEW` (`SOURCE_CHANGED_SINCE_PACKAGING` / `ARTIFACT_CHANGED_SINCE_PACKAGING`); build a new plan and package |
| the plan, the assembly, the `.tex` or the PDF replaced | `NEEDS_REVIEW` (changed since packaging); if the snapshot is rebuilt to agree, `BLOCKED` (chain) or `NEEDS_REVIEW` (the approval names other bytes) |
| the metadata edited, even to a valid document | `NEEDS_REVIEW`; with a rebuilt snapshot, `BLOCKED` (`METADATA_DIFFERS_FROM_CHAIN`) |
| the snapshot deleted or altered | `BLOCKED` |
| the review deleted, malformed, for another CV or another document | `NEEDS_REVIEW` (or `BLOCKED` if rejected) |
| the workspace Git repository missing, or the commit unknown | `NEEDS_REVIEW` (`SOURCE_COMMIT_UNVERIFIABLE`) |

## Limits that are not hidden

- **No signature.** An approval is a JSON file. Whoever can write to your workspace can write one. It records a decision against exact bytes;
  it does not authenticate the person. Keep the workspace private and under Git.
- **Semantics.** A reference check proves that facts exist and are `CONFIRMED`, not that a sentence means what they say; FR and EN texts are
  paired by identifier and their equivalence is not checked. The headline of the profile is **not printed**: no fact backs it (open decision).
- **ATS.** Compatibility with applicant tracking systems is not verified; only text order and accents were checked on the example.
- **PDF origin (M8-A-R2).** The metadata record how the PDF came to be, in the optional field `pdf_origin`:
  `COMPILED_FROM_VERIFIED_TEX` (made by `package create --compile`) or `SUPPLIED_PROVENANCE_NOT_VERIFIED` (`--pdf`). **Only the first
  can reach `READY_TO_SEND`.** A package whose origin is supplied, or not recorded (a package made before this field existed), stays
  `NEEDS_REVIEW` with the reason `PDF_ORIGIN_NOT_VERIFIED` whatever an approval says; `package approve` refuses it (`PACKAGE_NOT_REVIEWABLE`),
  and an approval file written by hand for it does not change the verdict: a person's approval binds a decision to exact bytes, it cannot
  make the origin of those bytes known. The field is **not a signature**: it is a statement in a file covered by the snapshot like the rest of
  the metadata (editing it without rebuilding the snapshot is detected), and whoever can write the workspace can rebuild the snapshot and
  claim `COMPILED_FROM_VERIFIED_TEX` for a PDF of their choice. Schema change: `pdf_origin` is an optional, additive field of metadata
  version 3 (version 3 was never published; no migration, no version bump); historical metadata (versions 1 and 2) are unchanged. To get a
  ready package from a PDF you made elsewhere, compile it the controlled way: `package create --compile`.
- **PDF provenance.** `package create --compile` is the recommended way to build a package: it runs `pdflatex` itself on the `.tex` it
  has just verified against the assembly and packages that output, so the normal workflow has no gap between compilation and package
  (`pdf_origin: COMPILED_FROM_VERIFIED_TEX` in the command's output). With `--pdf`, the PDF is a file the tool did not make and its
  origin is **not verified** (`pdf_origin: SUPPLIED_PROVENANCE_NOT_VERIFIED`, and a note): `package create` checks that it looks like a
  complete PDF (starts with `%PDF-`, ends with `%%EOF`) and that **at least one page can be read from its own page tree**
  (`PDF_NO_PAGE` otherwise; `package status` also blocks such a file with `CHAIN_PDF_NO_PAGE`). It does not check that the file comes from
  the `.tex`: the PDF of another CV, of another language, or the right PDF with bytes appended is accepted, and it can be reviewed
  but never reaches `READY_TO_SEND` (see "PDF origin"). The guarantees of the integrated compilation are not attributed to a supplied PDF. The page count is read from the page tree written in the file by a small reader
  that does not render anything: a counted page is not necessarily legible, and a PDF built differently from what the reader expects is
  refused (use `--compile`, or report it). Neither
  proves, once the files sit in the workspace, that the PDF is the compilation of the `.tex`: PDFs are not guaranteed reproducible (on one
  machine with one engine, two compilations were identical, which is evidence but not a contract), and whoever can write to the workspace can
  replace the PDF and rebuild every hash. The human review of the PDF is what binds the two.
- **TeX.** `pdflatex` is not a sandbox. The compiler is run with no shell escape, a fixed command line and a time limit, but its isolation is
  not proven. MiKTeX on Windows was exercised; TeX Live and Linux were **not** (no TeX distribution was available on the Linux test
  machine, and none was installed for the purpose).
- **Page count** is read from the PDF's own page tree (standard library); when it cannot be established it is recorded as unknown.
