# PROJECT_STATE.md

Source of truth for progress. Update it at the end of every session (see `AGENTS.md` §8).

## Repository

- Branch: `main`. M5 (`20979f9`) and M5-R1 are committed locally on top of `5585c42` (M4 final closure; see `git log`). Baseline of M4: `1114663` (M3, validated). M4 commits: `b38e1c8`, `4244cf9`. M4-R1 (`fe47a23`) and the M4 closure are committed locally on top. Earlier: `17bcf18` (M3 code), `ab35c91` (M2-R1), `d34af49`, `4865a27`,
  `0a553e1` (initial `0.1.0`). M4 is committed locally on top (see `git log`); nothing is pushed.
- Remote: `origin` (private). Nothing is published; no tag, no release.
- Version: `0.2.0` (proposed in M3, unpublished; M4 adds features without a version change); not tagged. Python: `>=3.12,<3.15` (M8-B).
- Tests: after M8-B, `py -3.9 -m pytest` gives 1408 passed and 1 skipped (1409 collected); after M8-A-R2, `py -3.9 -m pytest` gives 1311 passed and 1 skipped (1312 collected); after M8-A-R1 it gave 1304 passed and 1 skipped (1305 collected), as did Python 3.14; before that, after M8-A, `py -3.9 -m pytest` gave 1293 passed and 1 skipped (a symlink test needing privileges on Windows), 1294 collected (before M8-A: 1285 passed, 1 skipped, 1286 collected); on Linux (Python 3.10.12, WSL, no `pdflatex`) 1285 passed and 9 skipped; synthetic
  data only. (History: before M4: 376; after M4: 612; after M4-R1: 653; after the final closure: 671; after M5: 919 (248 new in `tests/test_content.py`); after M5-R1: 947 (276 in that file); after M6: 1112 (165 new); after M7-A: 1180 (68 new in `tests/test_render.py`, 2 of them skipped without `pdflatex`); after M7-B: 1286 (106 new in `tests/test_package.py`; two M3 tests moved from version "3" to "4" as the unknown version; after M8-A: 1294, 8 new). Before M8-A, Linux had only a stdlib smoke test.)
- Privacy scan: `python -m modularcv privacy --root .` and with an outside deny list and `--history`: 0 findings.
- Package: still `dependencies = []`; the engine imports no network module.

## Milestones

| ID | Title | Status |
|---|---|---|
| M1 | Audit of the private engine and architectural principles | PASS |
| M1.1 | Finalise the data and provenance contracts | PASS |
| M2 | Canonicalisation and FactBase-v1 | PASS (with M2-R1) |
| M3 | Provenance and readiness hardening (`0.2.0`) | PASS (validated) |
| M4 | Profile-v1 and legacy fact import | PASS (M4-R1 and final closure validated) |
| M5 | ResumeContent-v1 and reservoir | Rated PARTIAL; M5-R1 done, awaiting validation |
| M6 | JobOffer-v1, taxonomy, requirement matrix and plan | Done, awaiting validation |
| M7 | Rendering, optional PDF, metadata v3, package | M7-A validated; M7-B done, awaiting validation; M8 not authorised |
| M8 | Public release preparation | M8-A, M8-A-R1, M8-A-R2, M8-B validated; PUB-0 validated; PUB-1-R1 validated; `main` pushed to the private repository (G2, G3 verified); PUB-3-PRE, G2-bis (push), G4 (public) and SEC-1 (ruleset, secret scanning, push protection, private vulnerability reporting, Dependabot alerts) validated; DOC-1 (public documentation) done locally, awaiting validation; repository public, no tag, no release |

Details and acceptance criteria: `docs/design/MILESTONES.md`.

## Last work (G5-PRE, preparation of the first release `v0.2.0`; local commit, not pushed)

Nothing is tagged, released or pushed. `origin/main` was `2f8e466` at the start. The documents whose wording does not depend on the act of publication now say where
releases are listed (the GitHub Releases page) and that there is no package index, which stays true before and after a release (README EN/FR, SECURITY, CONTRIBUTING,
the Windows guides, `tests/test_doc_set.py`). The wording that does depend on it (the `CHANGELOG.md` introduction and heading, the changelog test) is kept for a
separate release patch applied at G5 with the real date. The release notes, the build strategy, the candidate archives and the exact G5 procedure are in the G5-PRE report.

## Earlier work (DOC-1-PACKAGE, packaging check of the documentation; local commit, not pushed)

Built from a clean export of `2734b33`: wheel (32 entries, engine and licence only, identical to the earlier wheel layout) and sdist (the three community
files, `docs/CLI.md`, both Windows guides, the new tests and `NOTICE.md` are inside; `MANIFEST.in` needed no further change). Both installed in fresh Python 3.14
environments outside the repository; the example ran end to end from each (`NEEDS_REVIEW`, nothing approved); the full suite ran from the unpacked sdist.
The one correction: the internal `0.1.0` state is no longer worded as "published" (`CHANGELOG.md`, `CONTRACTS.md`, `PROVENANCE_READINESS.md`). Nothing pushed,
no tag, no release, no GitHub setting changed. The archives are checks, not release artefacts: G5 builds its own from the public repository.

## Earlier work (DOC-1, public documentation and release preparation; local commit, not pushed)

Documentation, tests of the documentation and `MANIFEST.in` only; the engine, the contracts and the version (`0.2.0`) are unchanged. The repository is public;
`origin/main` was `0269f5d` when the work started. No tag, no release, no GitHub setting changed.

- New: `CONTRIBUTING.md`, `SECURITY.md` (private vulnerability reporting, no invented address, no promised delay), `CHANGELOG.md` (`0.2.0` as an unreleased
  candidate, known limits), `docs/INSTALL_WINDOWS.md` and `.fr.md` (commands run on Windows 11, PowerShell 5.1, Python 3.14, MiKTeX), `docs/CLI.md`
  (every command, argument and option).
- New tests: `tests/test_cli_reference.py` (CLI.md against `--help`, both directions) and `tests/test_doc_set.py` (release status, EN/FR parity, community files).
  `tests/test_docs_commands.py` also reads the new documents and the `$py` commands of the Windows guides.
- Corrected: the `README.fr.md` gaps (two table rows, the optional school summary), the leftover "letter" in the `ARCHITECTURE.md` diagram, the missing
  `WORKSPACE_NOT_REPOSITORY_ROOT` row of the troubleshooting tables, `MANIFEST.in` (the three community files go in the source archive).
- Open before G5: the release notes, the archives (the README is embedded in the wheel metadata, so they must be rebuilt), and the choice of the
  tag-protection ruleset and of immutable releases (see the SEC-PRE notes). Nothing was run on Python 3.12 or 3.13 for the Windows guide.

## Earlier work (PUB-3-PRE, documentation corrections before the visibility change; nothing pushed)

Documentation and metadata wording only; no code behaviour changed. Remote tip still `7f12d1c`, repository still private, no tag, no release.

- README clone URL: the `<your-user>` placeholder is replaced by the repository address (also added to the French Quick start).
- Scope: both READMEs now say ModularCV generates CVs, not cover letters; the `cv-panel` skill may review a cover letter the user wrote and never writes one.
  The same inaccurate claim was removed from `docs/ARCHITECTURE.md` (Package row), the `pyproject.toml` description and the `modularcv/__init__.py` docstring.
- Status: the source code is public in the repository; `0.2.0` is a release candidate and no versioned release (tag, GitHub release, archive, package index) exists
  until gate G5 is authorised. `AGENTS.md` section 3 excepts the repository's own address from the "handle" prohibition.
- Expected scan result: the privacy scan with the maintainer's private deny list reports the handle on the clone URL line of each README (two lines); it reports 0 without
  the handle-derived terms. This is the only place the handle appears in tracked files.

## Earlier work (PUB-1-R1, final local cleanup before synchronisation; nothing pushed)

Local corrections only: no push, no GitHub change, remote still private at `0a553e1`. Backups of PUB-1 (bundles, mirror, checksums) are kept outside the repository.

- **D1 done**: the four unpublished PUB-0 commits (`cfd16f3`, `10be3e0`, `4051f44`, `93429ce`) were squashed into one (`79cb876`); the 25 earlier commits keep
  their hashes; the tree differs from `93429ce` only by two wording lines that removed an unnecessary mention of the maintainer's private repository.
  Rollback: `93429ce` is in the reflog (`ORIG_HEAD`) and in the PUB-1 bundle. No remote ref touched.
- **D5 done**: a repository-local Git identity (the no-reply address); the global configuration is unchanged; a commit made without any `GIT_*` variable uses it.
- **D2 done**: the school summary `skills/cv-panel/normes-ets.md` stays in the repository and its history (maintainer's decision). Statements were made
  consistent: in the repository and in the source archive (no more `exclude` in `MANIFEST.in`), not in the wheel (engine only), optional, never used by
  the engine; `README.md`, `SKILL.md` and the tests say so; no legal claim is made. `PUBLIC_EXCLUDE.txt` no longer lists it.
- **Next**: the push itself (gate G2) needs an explicit authorisation; then verification of the private remote, then a separate decision for visibility.

## Earlier work (PUB-0, publication protocol; nothing executed)

Details: `docs/design/PUBLICATION_PROTOCOL.md` (facts, GitHub documentation, strategies A/B/C, gates G0 to G6) and `docs/design/PUBLIC_INVENTORY.sha256`.
Read-only GitHub audit and local simulations only: no push, rename, creation, deletion, tag, release or visibility change; the maintainer's private personal repository was not opened.

- **Remote**: `<owner>/ModularCV` (id 1441249060), private, one commit `0a553e1` (30 files, with `normes-ets.md`), `main` only, no PR, fork, tag,
  release, workflow, Pages; never public; no branch protection available (free plan, private).
- **Finding**: a force-push moves a ref but does not delete objects (shown locally); GitHub documents that old commits stay reachable by SHA in cached views
  until Support purges them, and that Support removes only sensitive data that cannot be mitigated by rotating credentials: strategy A gives no guarantee.
- **Recommendation**: strategy B (rename the old repository to a private archive, create a new empty private `ModularCV`, push the one-commit snapshot,
  verify a fresh mirror clone, then ask for a separate go before any visibility change). Snapshot tree to publish: `11f9c27a5026605e5f1fa52be6af9fbab17875ce`.
- **Open decisions added**: 25 strategy and rename authorisation; 26 public commit identity; 27 who may push the local commits (to the archive only).

## Earlier work (M8-B, release candidate and final audit)

Details: `docs/design/PREPUBLICATION_AUDIT.md` section 18. Nothing pushed, tagged, released or published; no remote; version `0.2.0`.

- **Python policy applied**: `requires-python = ">=3.12,<3.15"`, classifiers 3.12 to 3.14, documents aligned; 3.9/3.10 = regression only. Tests guard consistency.
- **Public inventory**: `PUBLIC_EXCLUDE.txt` lists the files left out of the public snapshot (itself, this file, the audit, the snapshot procedure,
  `normes-ets.md`); links and `SKILL.md`/README wording fixed so that exclusion breaks nothing (`tests/test_public_tree.py`).
- **Defect fixed**: `package status` crash (exit 1) on metadata of the wrong shape; now `BLOCKED` (3) / `METADATA_UNREADABLE`.
  `tests/test_docs_commands.py` checks every documented command and option.
- **Snapshot, archives, installs, journeys**: snapshot of the candidate HEAD (93 files, one commit, no remote, privacy 0 finding, excluded file and
  internal documents absent); wheel and sdist installed on 3.12 and 3.14 (pip refuses 3.9); 49/49 journey checks on 4 installations (FR/EN, A4/Letter,
  READY/NEEDS_REVIEW/BLOCKED, supplied PDF refused, substitution).
- **Matrix**: snapshot suite 3.12 and 3.14 (Windows) 1406 passed / 3 skipped, 3.13 (Linux container) and 3.10 (WSL) 1398 / 11, 3.9 1406 / 3; identical
  identity digest everywhere. TeX Live on Linux: not tested (no environment, nothing installed).
- **Open decisions added**: 23 acceptance of `PUBLIC_EXCLUDE.txt` and the public documents; 24 first public version number.

## Earlier work (M8-A-R2, final pre-publication checks)

Details: `docs/design/PREPUBLICATION_AUDIT.md` section 17 and `docs/design/PUBLIC_SNAPSHOT.md`. Nothing pushed, tagged, released or published; no remote.

- **PDF origin recorded**: optional additive field `pdf_origin` of metadata version 3 (`COMPILED_FROM_VERIFIED_TEX` / `SUPPLIED_PROVENANCE_NOT_VERIFIED`).
  Only a PDF made by `package create --compile` can make a package `READY_TO_SEND`; a supplied or unrecorded origin stays `NEEDS_REVIEW`
  (`PDF_ORIGIN_NOT_VERIFIED`) whatever a review says; `package approve` refuses it. Not a signature. 7 tests, 5 mutations caught.
- **Public snapshot** simulated in a temporary folder (single commit, no remote, `normes-ets.md` excluded): 93 files, no trace of the file or its content,
  no broken link, 0 privacy finding, builds, tests and quick start pass. `SKILL.md` no longer depends on the file. Private history untouched.
- **Python (suite, install, identities identical)**: 3.12.14 (Windows, uv), 3.13.18 (Linux, offline container), 3.14.7 (Windows); regression 3.9.13 and
  3.10.12. 3.15 absent. `Requires-Python` unchanged (`>=3.9`): governance decision.
- **Linux/TeX Live**: no TeX in any available environment; nothing installed; not tested; procedure documented.
- **Tests**: 1312 collected; private repository 3.9: 1311 passed, 1 skipped.
- **Open decisions added**: 19 route for the public repository (snapshot, rewritten history, or authorisation); 20 which working-tree documents are public;
  21 public identity, name, visibility; 22 whether to keep accepting `--pdf` at all.

## Earlier work (M8-A-R1, stabilisation and verification of the blockers)

Details and evidence: `docs/design/PREPUBLICATION_AUDIT.md` section 16. Nothing pushed, tagged, released or published; version `0.2.0`.

- **Distribution verified (Windows, online, temporary virtual environments only)**: wheel and sdist build with `python -m build` (setuptools 84.2.1
  in the isolated build environment); the wheel installs on Python 3.14, the sdist on 3.9, editable on 3.14; the commands run from outside the
  clone with the identities of the source tree. Fixed: deprecated `license = {text}` (now SPDX `license = "MIT"`, `setuptools>=77`), and a source
  archive whose tests could not run (`MANIFEST.in`; its tests pass unpacked: 1304 passed, 1 skipped on 3.9).
- **PDF supplied from outside**: `package create` refuses a PDF with no readable page (`PDF_NO_PAGE`, and `package status` blocks one with
  `CHAIN_PDF_NO_PAGE`); the create output declares `pdf_origin` (`COMPILED_FROM_VERIFIED_TEX` with `--compile`, `SUPPLIED_PROVENANCE_NOT_VERIFIED`
  with `--pdf`); the review limits say so. A supplied PDF of another CV or language is still accepted (documented, not provable). `--compile` is the
  recommended path. Approval (`CVQualityReview-v2`, unsigned) unchanged.
- **Python**: full suite on 3.9 (Windows), 3.14 (Windows) and 3.10 (Linux); identical fingerprints and `.tex` hashes. 3.14 exposed a crash on deeply
  nested JSON (fixed: `canonical.loads`, one limit on every interpreter). 3.12, 3.13, 3.15 were not available: **not claimed**; metadata unchanged.
- **Linux compilation**: not tested (no TeX distribution; none installed). Prerequisites and commands documented.
- **`normes-ets.md`**: no licence or permission recorded; tracked since the initial commit, hence in the whole history including `origin/main`;
  not needed by the engine; not in the wheel; excluded from the sdist. Blocking for publication; no file or history touched.
- **Ergonomics**: `content check` warns `CONTENT_BLOCK_NEVER_PRINTED` (block with no bullet and no `protected`); Letter paper verified and documented;
  A4 stays the default; no `generic-v2`.
- **Tests**: 1305 collected (1294 + 11): Windows 3.9 and 3.14: 1304 passed, 1 skipped.
- **Open decisions added**: 15 strategy for `normes-ets.md` and the history (authorisation, cleaned history, or a clean-source publication);
  16 supported Python range and permission to install interpreters or a CI for 3.12, 3.13, 3.15; 17 whether to store the PDF origin in the package
  (contract change); 18 permission to install TeX Live (WSL or container) to test Linux compilation.

## Earlier work (M8-A, pre-publication audit)

- **Audit** written in `docs/design/PREPUBLICATION_AUDIT.md`: capabilities (implemented / documented / validated), installation, journey,
  trust boundaries, PDF/LaTeX gap, approval options, compiler limits, portability, readability and ATS, documentation, privacy and licence,
  blocking risks, proposed M8-A-R1, decisions. M8-B and any publication are not authorised.
- **Installation from a clean source: NOT validated.** The tracked tree exports to 90 files, but no setuptools >= 61 and no `wheel` exist on
  the machine and there is no network, so `pip install` could not be exercised (nothing was installed to get around it). A stand-in
  `build_py` and runs from the build folder are not an installation test.
- **Linux**: the full suite ran on Python 3.10.12 (WSL, pytest borrowed read-only from the Windows site-packages): 1285 passed, 9 skipped
  (7 need `pdflatex`). It found a real defect (below). Windows py3.9: **1293 passed, 1 skipped**, 1294 collected (1286 + 8).
  Identities (`plan_sha256`, assembly, `.tex`, `tailored_cv_id`) are identical on a Windows CRLF checkout and a Linux LF clone.
- **Defect fixed**: on POSIX `Path.resolve()` follows a dangling symbolic link, so `facts import --out`, `plan|matrix|assemble|render --out`
  and `package create` could write a new file through a link pointing inside the workspace; the path as written is checked too and a package
  folder may not pass through a link (3 new tests, 4 failing before the fix on Linux, including the M4 test that was skipped on Windows).
- **Added** `package create --compile` (compile the verified `.tex` and package that output; exclusive with `--pdf`): closes the file travel
  between `render --pdf` and `package create`. It does not prove the PDF is the compilation of the `.tex` once the files sit in the workspace.
- **Docs**: `docs/QUICKSTART.md` and `.fr.md` (every command executed), README and README.fr, ARCHITECTURE, GOVERNANCE, CONTENT (`protected`),
  PACKAGE and RENDER (PDF provenance, compiler limits), CONTRACTS 4.2.
- **Not done**: online build and install, TeX Live, any Linux compilation, Python versions other than 3.9 and 3.10, any ATS, the proposals
  of M8-A-R1 (PDF reproduction check, `generic-v2`, environment allow-list, signed approvals, French guides).
- **Open decisions added**: 10 default paper (A4 or Letter); 11 supported Python versions (3.9 is past its end of life); 12 approval
  authenticity (see audit section 7); 13 whether `skills/cv-panel/normes-ets.md` may be redistributed; 14 whether a published repository
  may carry the current history and the maintainer's account name in its address.

## Last work (M7-B)

- **Chain of evidence** (`modularcv/chain.py`): `tailored_cv_id`, metadata v3 derivation, `verify` re-deriving sources -> plan -> assembly ->
  `.tex` -> PDF -> metadata from the workspace files. Documented hash graph without cycle (PACKAGE.md).
- **Package** (`modularcv/package.py`): `create` (only from a verified plan, a `.tex` equal to the rendering, an optional PDF, a Git-verified
  workspace; writes only new files; removes everything on failure; self-checks), `status`, `review_summary`, `record_review`. A package never
  carries a verdict (`UNEVALUATED`).
- **Review** (`review.py`): `CVQualityReview-v2` approves the exact PDF bytes and records what the reviewer was shown; `package approve` needs an
  interactive terminal and a typed 12-character hash prefix. No signature.
- **Readiness** (`readiness.py`): version 3 branch (package/snapshot fingerprints, chain, identity, `FINAL_DOCUMENT_MISSING`, review v2). A package
  without a PDF is never ready. M3 behaviour for v1/v2 metadata is unchanged (two tests that pinned version "3" as unknown now pin "4").
- **Metadata v3** (`metadata.py`), **snapshot roles** `taxonomy`/`assembly`, **`pdf.count_pages`** (stdlib page-tree reader).
- **Tests**: `tests/test_package.py` (106): creation and refusals, every substitution scenario with and without approval, forged but
  consistent packages, review variants, CLI with a stand-in terminal, metadata v3 validation, real MiKTeX compilation. All approvals are
  fictional fixtures in temporary workspaces. Mutations (throw-away harness) of the review judgement, the snapshot comparison, the package
  and snapshot fingerprints, the chain comparisons and the readiness branches all fail the tests.
- **Not verified**: TeX Live / Linux compilation; ATS; the PDF-to-`.tex` derivation; real-user approval (none was made).
- **Open decisions**: 8, print the public headline (still not printed); 9, whether a signed or authenticated approval is wanted (decision 5
  stays open and now also concerns `CVQualityReview-v2`).

## Last work (M7-A)

- **Assembly** (`modularcv/assemble.py`): five verification layers on the plan (shape, fingerprint, sources, reproduction by the
  engine, independent re-validation), then `AssembledResume-v1` (public header only, headline not printed, verbatim text, `soften`
  left pending, `ready_to_send` false).
- **LaTeX** (`modularcv/latex.py`): template `generic-v1`, one escaping table, ligature guards, closed safe character set (nine
  Latin Extended-A letters excluded after a real-compiler probe), only bold/italic markup, deterministic bytes and `tex_sha256`.
- **PDF** (`modularcv/pdf.py`): optional `pdflatex`, fixed command line, no shell escape, temporary directory, timeout, scrubbed
  environment, MiKTeX installer disabled, result verified, value-free diagnostics (log only with `--log`).
- **CLI**: `assemble`, `render` (`--out --pdf --log --paper --timeout`), `latex check`; exit 4 (`pdflatex` absent) and 5
  (compilation failed) leave the `.tex` written. Docs: `docs/RENDER.md`, `CONTRACTS.md` 5.2.
- **Tests**: 68 new in `tests/test_render.py`, including real compilation (MiKTeX 26.5 on Windows: 1-page PDF in en and fr),
  a real failing document, a hostile-document check and random worlds. Mutations (throw-away harness) of every verification layer,
  the escaping table, the character set, ligature guard, assembly fingerprint, public-view filter and the compiler wrapper
  (`-no-shell-escape`, timeout, environment, output checks) all fail the tests.
- **Not verified**: ATS behaviour; TeX Live / Linux compilation; byte-reproducibility of PDFs (not expected).
- **Open decision 8**: print the public headline? It is left out because no fact backs it.

## Last work (M6)

- **Offers.** `modularcv/joboffer.py`: JobOffer-v1 (strict, value-free `OFFER_*` errors, `description_sha256` verified,
  `offer_sha256`, optional explicit `requirements`, deterministic en/fr language detector with a recorded method). No LLM, no network.
- **Taxonomy.** `modularcv/taxonomy.py`: Taxonomy-v1 (terms, aliases per language, zones, directed single-hop adjacencies),
  `builtin:generic-v1` plus `examples/taxonomy.generic-v1.json`; ambiguous aliases, duplicate ids and bad adjacencies refused.
  Resolves decision 12: declared capabilities and technologies are checked against it.
- **Matrix and plan.** `modularcv/matrix.py`, `modularcv/plan.py`: four states (`FORBIDDEN_TO_CLAIM` > `DIRECT` > `ADJACENT` >
  `ABSENT`), corroboration by a `CONFIRMED` fact, pool limited to proven content, greedy deterministic ranking, `TailoringPlan-v1`
  with `plan_sha256` (`PLAN_ONLY`, not reviewed, no `tailored_cv_id`). Unsatisfied required requirements stay explicit; adjacent is
  never shown as satisfied.
- **CLI.** `offer check|fingerprint`, `taxonomy check|fingerprint`, `matrix`, `plan` (stage-named refusals; `--out` creates a new file
  inside the workspace and never overwrites an input). Examples: `examples/workspace/offers/`; `resume.json` gained a `pytest` skill.
- **Docs.** `docs/PLAN.md`, `CONTRACTS.md` §3.3, §4.1, §5.1.
- **Tests.** 165 new (`test_taxonomy.py` 41, `test_offer.py` 66, `test_plan.py` 58), including a seeded random campaign of provenance
  invariants. Mutation checks (throw-away harness, not committed): removing corroboration, the profile prohibition, the fact
  prohibition, the forbidden-over-direct order, the proof in `selectable`/`selectable_skills`/`plan._proven`, the heading proof or
  `never_publish` each make the tests fail; promoting `ADJACENT` to `DIRECT` also fails. One mutant survives by construction:
  letting a `DERIVED` fact corroborate is unreachable, because every pool item already has only `CONFIRMED` supports (defence in depth).
- Fix found while testing: the CLI printed fact-base errors with a missing attribute (`FactError` has `line`, not `path`); fixed.
- Not run: pytest on Linux (not installed in WSL); stdlib smoke only. Not done: rendering, `tailored_cv_id`, page-target enforcement,
  `soften` guidance (reported as `GUIDANCE_SOFTEN_PENDING`).

## Last work (M4)

- `modularcv/profile.py`: Profile-v1. Identity fields carry a required `visibility`; `public_view()` returns only public fields,
  `internal_preferences()` the generation preferences, `confirmed_availability(factbase)` only availabilities backed by a
  `CONFIRMED` fact. Unknown fields refused, `x-` fields kept. Error messages and reports never repeat a value.
- `modularcv/legacy.py`: `LegacyFactMap-v1` and the importer. Line-by-line decisions (`ACCEPTED`, `DUPLICATE`, `IGNORED`,
  `TECHNOLOGY`, `UNCLASSIFIED`, `AMBIGUOUS`, `REJECTED`); nothing unknown is imported; `CONFIRMED` needs `allow_confirmed` plus a rule
  status; a line rule can only lower a status; dates only from declared patterns; the proposal is parsed back by the FactBase-v1
  parser before it is written.
- `modularcv/docvalidate.py`: shared JSON reader (duplicate keys, NaN, unknown fields, value-free messages).
- `modularcv/canonical.py`: `fold()` for casefolded, accent-free matching. `modularcv/config.py`: new key `profile`.
- CLI: `profile check|fingerprint`, `facts import` (`--dry-run`, `--allow-partial`), `facts check|fingerprint --use-profile`.
- Examples: `examples/workspace/` (fictional facts, profile, mapping, legacy notes). Docs: `docs/IMPORT.md`, `CONTRACTS.md` §1.5.1
  and §2.1, `WORKSPACE.md`, `README`.
- Tests: `tests/test_profile.py`, `tests/test_legacy.py` (237 new). M2 and M3 tests unchanged and green.

## Last work (M4-R1)

- `profile check --no-facts` returned exit 0 and status `OK` while availability references stayed `UNVERIFIED`. It now exits `3`
  with status `UNVERIFIED` and a warning on stderr whenever a fact reference was not verified; with no reference to verify it
  still exits 0. `0` now means valid **and** verified (8 net new tests; the old test that expected 0 was replaced on purpose). Documented in `CONTRACTS.md` §2.1, `WORKSPACE.md` and the CLI docstring.
- Importer `CONFIRMED` policy audited: no violation found, no code change. Added 32 tests (flag types, full heading/rule status
  matrix, ambiguity, inherit, dates, traceability to the authorising rule, random documents and mappings) and checked that a
  removed promotion guard makes them fail. `IMPORT.md` and `CONTRACTS.md` §1.5.1 now separate the mapping's authorisation from
  the user's fact-by-fact verification.
- Foreign file investigated read-only (below). Nothing moved, ignored or committed.

## Last work (M5-R1)

- **Heading provenance (decision 9).** A block now carries `supports` (fact ids) that back its factual heading: job title,
  employer, period, place, institution, degree. It is required and non-empty (`CONTENT_UNSUPPORTED_HEADING`); with a fact base
  each fact must exist and be `CONFIRMED` (`CONTENT_FACT_UNKNOWN`, `CONTENT_FACT_NOT_CONFIRMED`, `CONTENT_FACT_DATE_REQUIRED`);
  without one the heading is `UNVERIFIED` and `content check` exits `3`. Organisational fields (section and skill-category titles,
  ids, order, kind, protected, baselines) need no proof. Same mechanism as bullets and skills: one `supports` list per entity, no
  second provenance architecture. `ResumeContent.selectable()` returns a bullet only when its own support **and** its block's
  heading support are `CONFIRMED`; `selectable_skills()` does the same for skills. Report and `--outline` show a heading state.
- **Skills (decision 10).** `supports` stays required on skill items; behaviour and tests unchanged.
- **Parity (decision 11).** The obligation is the contract's pair: an entity declaring both `en` and `fr` needs both everywhere
  (heading, section title, bullets, skill items). No obligation for any other language. Kept for all languages as general structure:
  a text may only use a declared language, a one-language entity needs that language, every text exists in at least one language.
- **Capabilities (decision 12).** Vocabulary and taxonomy deferred to M6; M5 keeps valid, stable identifiers.
- Examples updated (`supports` on every block) plus two invalid ones: `unproven-heading.json` (the regression: a confirmed bullet
  under a withdrawn title) and `missing-heading-support.json`.
- Limits recorded: no semantic comparison of any text against its facts, none between languages; every backslash is refused
  (also a Windows path), to be revisited with the renderer (M7).
- Not run: pytest on Linux. `legacy_import.py` stays in `_quarantine`, untouched.

## Last work (M5)

- `modularcv/content.py`: ResumeContent-v1 (sections, blocks, bullets, skills, baselines; FR, EN or bilingual). Validation by the
  shared reader: strict fields and types, `x-` extensions kept, value-free errors with stable `CONTENT_*` codes. Each publishable
  bullet and each skill must name its supporting facts; with a fact base every one must exist and be `CONFIRMED`
  (`CONTENT_FACT_UNKNOWN`, `CONTENT_FACT_NOT_CONFIRMED`, `CONTENT_UNSUPPORTED_BULLET`, `CONTENT_UNSUPPORTED_SKILL`); without one the
  references are `UNVERIFIED` and `content check` exits `3`. FR/EN parity is by entity id (bullet, heading, section title, skill),
  never by position and never imposed on a one-language block. Raw LaTeX (a backslash) is refused; `%`, `&`, `$`, `#`, `_`, `{`,
  `}` stay ordinary. `ResumeContent.selectable(factbase, language)` is the reservoir filter (confirmed support, language, not
  `never_publish`); there is no selection algorithm.
- Fingerprints `content_source_sha256` (normalised source) and `content_sha256` (canonical model; blocks in print order, sets
  sorted, defaults filled). CLI: `content check [--facts F | --no-facts] [--profile F] [--outline]`, `content fingerprint`.
- Examples (fictional): `examples/workspace/content/` (`resume.json` bilingual, `resume.fr.json`, `resume.en.json`, `invalid/`).
  Docs: `docs/CONTENT.md`, `CONTRACTS.md` section 3.2, `WORKSPACE.md`, READMEs.
- Fix in earlier modules: `facts.valid_id`, the language and extension checks of `docvalidate` accepted a trailing newline
  (`$` matches before `\n`); they now use `fullmatch`. No valid identifier changed, historical fingerprints are pinned by a test.
- Not run: pytest on Linux (not installed in WSL). A stdlib smoke test of `content check` and `content fingerprint` passed on
  Python 3.10.12 with the same fingerprints as on Windows.

## Last work (M4 final closure)

- The foreign file `modularcv/legacy_import.py` was moved, unchanged, to `D:\Projets\ModularCV\_quarantine\legacy_import.py`
  (outside the repository, so no local build can include it). SHA-256 checked before and after:
  `5c73e936d25ce534dc13b8ef77005630f1643f96092140a3b690b190a2504106`. Nothing deleted, nothing committed.
  **Restore:** move it back to `modularcv/legacy_import.py` (never overwrite a file there) and compare the SHA-256.
- `facts import` now refuses, with the stable code `IMPORT_OUTPUT_IS_FACT_BASE` (exit 2, no path in the message), any `--out` or
  `--report` that designates the configured fact base: existing or not, by an equivalent or absolute path, a different letter
  case, a symbolic link (also a dangling one) or a linked folder. `--dry-run` still writes nothing; existing files are still
  never overwritten (a dangling symbolic link now counts as existing, which closed a path where the import wrote through it);
  a separate proposal file works as before. Classification and the `CONFIRMED` policy are untouched. Decision 8 is settled.

## Known defects and anomalies

- Residual points of M3 stand: the human approval is a file, not a signature.
- Foreign file (now isolated in `_quarantine`, see above; origin still unknown), **not written by the M4 work**: 714 lines, 35,017 bytes, SHA-256
  `5c73e936d25ce534dc13b8ef77005630f1643f96092140a3b690b190a2504106`, created 2026-11-02 15:03:50 and last written 15:04:01
  (-0500). It is a parallel implementation of the same importer (`LegacyFactMap-v1`), it imports `profile.fold`, which does not
  exist (`fold` lives in `canonical`), so importing it raises `ImportError`; nothing in the tracked code, the tests or the docs
  references it; it holds no network, `exec` or `eval` call. Setuptools lists the whole `modularcv` package, so a build made from
  this working tree would ship it; a build from a clean checkout would not. Origin: **not established**. One indication only:
  the transcript search finds a write-result message naming this path in another local session (working directory outside
  ModularCV, last active 15:11 the same day); that is evidence, not proof. It was left unchanged and moved out of the
  package folder; `.gitignore` would not have been enough, it hides a file from Git but not from a build.

## Open decisions (maintainer)

1. Cover letters deferred beyond M8.
2. `pdflatex` optional or required for the first release.
3. One generic taxonomy, or several domain taxonomies.
4. Whether `###` sub-headings should be allowed later (M2 refuses them).
5. Whether a signed or otherwise authenticated approval is wanted instead of the plain `cv-quality-review.json`.
6. Whether the first release tags `0.2.0` or `0.3.0` now that `Profile-v1` and the import are in (M4 changed no version).
7. Final fate of the quarantined `legacy_import.py` (keep outside the repository, delete, or restore); isolated, not deleted.
23. (M8-B) Acceptance of `PUBLIC_EXCLUDE.txt` (what the public tree leaves out) and of the documents it keeps, among them `AGENTS.md` and `MILESTONES.md`.
24. (M8-B) The number of the first public version (`0.2.0` as it stands, or another) and the scope announced for it.
25. (PUB-0) Publication strategy (recommended B) and the rename of the old repository; 26. the public commit identity; 27. who may push the local
    commits of the development repository (to the private archive only, never to the public repository).
Settled: Python 3.12 to 3.14 (M8-B, governance); strict `facts.md` grammar with optional `confirmed_on` (M2); M3 is a breaking `0.2.0` correction of `readiness`; the
import never confirms by itself (M4); decision 9, factual headings are tied to the fact base through `supports` (M5-R1);
decision 10, `supports` is required on skills; decision 11, parity binds the `en`/`fr` pair only, other languages carry no
obligation; decision 12, the capability vocabulary and taxonomy belong to M6 (done: Taxonomy-v1, `vocabulary_problems`).

## Blockers

None.

## Next action

Wait for the maintainer's validation of DOC-1, the authorisation to push it, and then the authorisation of the release (gate G5). Do not push, tag or release without an explicit go for that exact action. Do not push, tag, release or
change a visibility without an explicit go for that exact action.
