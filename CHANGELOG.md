# Changelog

All notable changes to ModularCV are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/).

**ModularCV 0.2.0 is the first release.** It is listed on the Releases page of the GitHub repository, with its archives (a wheel and a
source archive) and their SHA-256 checksums. ModularCV is not on PyPI or any other package index. The first commit of the repository
describes an earlier internal state called `0.1.0`. It is **not a public release**: the repository was private until its publication
and had no tag or release before `v0.2.0`. The differences with that internal state are listed under "Changed since the internal
`0.1.0` state".

## [0.2.0] - 2026-11-07

### Added

- **Fact base (`FactBase-v1`).** A strict parser and validator for the Markdown fact base, canonical JSON and SHA-256 fingerprints
  independent of line endings and key order, and the commands `facts check` and `facts fingerprint`. A fact with status `CONFIRMED` is the
  only thing that can be printed on a CV; a missing fact is never guessed.
- **Controlled legacy import.** `facts import` classifies a historical Markdown document with a mapping you write (`LegacyFactMap-v1`)
  into a *proposed* fact base and a line-by-line report. Unknown lines are never imported and nothing becomes `CONFIRMED` unless the
  mapping says so.
- **Profile (`Profile-v1`).** Identity fields each marked `public` or `private` (only public ones are printed), languages, CV families,
  policy and availability. An availability counts only if a `CONFIRMED` fact backs it. Commands `profile check` and `profile fingerprint`.
- **Resume content (`ResumeContent-v1`).** The text of a CV as validated data (sections, blocks, bullets, skills, baselines) in French,
  English or both. Each bullet, skill and block heading names the facts that back it and is printable only if they are all `CONFIRMED`. Raw
  LaTeX is refused. Commands `content check` and `content fingerprint`.
- **Job offers, taxonomy, matrix and plan.** `JobOffer-v1` files, a small configurable taxonomy (`builtin:generic-v1` or your own),
  the requirement matrix (`DIRECT`, `ADJACENT`, `ABSENT`, `FORBIDDEN_TO_CLAIM`) and a deterministic tailoring plan (`TailoringPlan-v1`).
  Only confirmed facts count, a prohibition beats relevance and an unmet requirement stays explicit. Commands `offer check`,
  `offer fingerprint`, `taxonomy check`, `taxonomy fingerprint`, `matrix` and `plan`.
- **Assembly and LaTeX/PDF export.** `assemble` turns a verified plan into a structured CV (`AssembledResume-v1`); `render` writes a
  generic, escaped, byte-deterministic `.tex` and, if `pdflatex` is installed, compiles it (A4 by default, `--paper letterpaper` for Letter).
  `latex check` reports whether `pdflatex` is available. `pdflatex` is optional and never installed by the tool.
- **Packages and human approval.** `package create`, `package review`, `package approve` and `package status` build a package (plan,
  assembled CV, `.tex`, PDF, metadata, source snapshot) in your private workspace and record **your** approval of the exact PDF. Nothing is
  sent and nothing is approved automatically; `package approve` refuses to run without a person at a terminal.
- **Provenance and readiness.** A generated document must name a real Git commit that holds the exact sources it was built from.
  `READY_TO_SEND` is computed from the evidence on every call (sources, `SourceSnapshot-v1`, plan-to-PDF chain, metadata, staleness registry
  and the human approval) and is never stored. Commands `provenance`, `snapshot verify` and `check-packages`.
- **PDF origin.** A package records how its PDF came to be. Only a PDF compiled by `package create --compile` from the verified `.tex`
  can reach `READY_TO_SEND`; a PDF supplied with `--pdf` is recorded as `SUPPLIED_PROVENANCE_NOT_VERIFIED` and stays `NEEDS_REVIEW`.
- **Privacy protection.** `privacy` scans a tree, and optionally commit author e-mails, for e-mails, phone numbers, social insurance
  numbers, absolute user paths, profile URLs, credentials and your own private terms (kept in a file outside the repository).
- **`cv-panel` skill.** A Claude Code skill in which seven independent readers review a CV (and a cover letter you wrote). It reviews
  only: it never rewrites and never adds a fact. It is adapted from `hiring-panel-skill` by Alex Chen (MIT); see
  `skills/cv-panel/NOTICE.md`.
- **Documentation.** READMEs in English and French, a quick start in both languages with troubleshooting, guides for the workspace, plan,
  content, import, rendering and packages, design contracts in `docs/design/`, a Windows installation guide, a command reference
  ([docs/CLI.md](docs/CLI.md)) checked by the tests against `--help`, [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
- **Tests.** A synthetic test suite (no real data), documentation tests that check every link and every documented command and option, and
  a test that the Python support statements agree everywhere.

### Changed since the internal `0.1.0` state

Readiness became fail-closed. The full table is in [docs/design/PROVENANCE_READINESS.md](docs/design/PROVENANCE_READINESS.md) (section 9);
the main points are:

- A package is never `READY_TO_SEND` without the workspace root, its snapshot, its metadata and a human approval; a commit that cannot
  be verified in the workspace Git repository, or an all-zero placeholder, is refused.
- `check-packages` on a folder without packages is an error (exit code 2), not an empty successful report.
- Unsafe paths in `modularcv.json` are refused, and the workspace must be the top level of its own Git repository.
- Text is normalised (BOM, `CRLF`, lone `CR`) before it is compared or hashed.

### Supported platforms and Python

- **Python 3.12, 3.13 and 3.14** (`requires-python = ">=3.12,<3.15"`); the engine uses the standard library only. The suite was run on
  3.12 and 3.14 (Windows) and 3.13 (Linux container); not every combination of version and platform was tried. Python 3.9 and 3.10 were
  regression environments only: no support is announced.
- **PDF output** was exercised with MiKTeX on Windows only.

### Known limits

These are documented in the README and in [docs/PACKAGE.md](docs/PACKAGE.md) ("Limits that are not hidden"); they are not guarantees:

- The checks prove that facts exist and are `CONFIRMED`, not that a sentence means what they say; the equivalence of French and English
  texts is not checked.
- An approval is an unsigned JSON file that binds a decision to the exact bytes of a PDF; the reviewer is **not authenticated**. The
  recorded origin of a PDF is a statement in a file, not a cryptographic proof, and whoever can write your workspace can forge it.
- `READY_TO_SEND` means the process is consistent, not that you meet the job's requirements.
- `pdflatex` is not a sandbox. **TeX Live and compilation on Linux are not tested; macOS is not tested.** Without `pdflatex` you get the
  `.tex` and no PDF.
- **Compatibility with applicant tracking systems is not verified and nothing is certified.** Only the order and the accents of the
  extracted text were looked at on the example.
- The privacy scan is best-effort pattern matching.
- ModularCV generates CVs only. It does not generate or rewrite cover letters; the optional skill can review one you wrote.
- The CV generation engine of the original private project is not included, because it still embeds one person's content; porting it
  behind a configurable fact base is future work.
- The optional summary of the school's co-op guidance (`skills/cv-panel/normes-ets.md`) is in the Git repository and the source archive,
  not in the wheel; the engine does not use it, and it may be out of date.
