# Generation architecture (M1.1 design)

Status: **design**; sections 2.2 and 2.3 (matrix and ranking) are implemented by M6 as `modularcv/matrix.py` and `modularcv/plan.py`,
see `CONTRACTS.md` §5.1 and `docs/PLAN.md`; the rest is not implemented yet. This document fixes the boundaries and says how each part of the generation chain is
adapted from the private engine it is ported from. The private code is not copied: each component is re-implemented against the
contracts of `CONTRACTS.md` and `PROVENANCE_READINESS.md`, and no personal fact, wording or identifier crosses over.

## 1. Boundaries

```
 ┌────────────── workspace (user's private Git repository) ──────────────┐
 │ facts.md  profile.json  content/  offers/  applications/  packages/   │
 │ optional overrides: taxonomy/, templates/        modularcv.json       │
 └───────────────────────────────┬───────────────────────────────────────┘
                                 │ explicit paths only (config / MODULARCV_ROOT)
 ┌───────────────────────────────▼───────────────────────────────────────┐
 │ CORE (this repository, stdlib only, no network, no model)             │
 │ canonical · facts · profile · content · offer · matrix · select ·     │
 │ render · package · provenance · readiness · staleness · privacy       │
 ├───────────────────────────────────────────────────────────────────────┤
 │ TEMPLATES shipped with the engine: LaTeX templates, taxonomy generic-v1 │
 └───────────────────────────────▲───────────────────────────────────────┘
                                 │ JobOffer-v1 (JSON)
 ┌───────────────────────────────┴───────────────────────────────────────┐
 │ ADAPTERS (optional, outside the core): job-scraper export → JobOffer-v1 │
 └───────────────────────────────────────────────────────────────────────┘
```

Rules, each enforced by a test:

1. **Core never imports an adapter**, and never imports from a workspace. Dependencies point inward only.
2. **The core reads only paths it is given** (config or argument). No default path to a machine-specific location; a missing
   input is a diagnostic, never an empty result.
3. **Stdlib only.** `pdflatex` is an optional external program; its absence skips PDF tests with a reason and never fails `.tex` generation.
4. **No model, no network** in generation. Anything non-deterministic is out of the core.
5. **No workspace content in this repository**, no engine content in the workspace (except explicit overrides).
6. **No adapter is mandatory.** A user can write a `JobOffer-v1` by hand. A scraper integration (for example the one the private
   project uses) stays a separate, optional adapter and is never a dependency.

## 2. Components and how they are adapted

### 2.1 Content reservoir
- Private: parses LaTeX masters with regular expressions, pairs FR and EN blocks by position, matches fact lines by shared words, and
  hard-codes block ids, section titles, capability and technology lists.
- Generic: the reservoir is built from `ResumeContent-v1` (structured, no LaTeX parsing). Items get ids `block.bullet`,
  per-language text, **explicit** fact support, technologies and capabilities from the taxonomy. `never_publish` comes from the
  profile policy. Parity is checked by id and only where both languages exist.
- Result: no regular expression over LaTeX, no position-based pairing, no hard-coded personal block list.

### 2.2 Requirement matrix
- Private: a 34-concept table with patterns, technologies, clusters and rules; posting zones (requirements, responsibilities,
  nice-to-have, context) with weights; "not confirmed" detection by scanning phrases in the fact file.
- Generic: the table, the zone patterns (per language) and the zone weights move to a **taxonomy file** (`generic-v1` ships
  with the engine; a workspace may extend or replace it). Classification keeps its four classes: `DIRECT`, `ADJACENT`,
  `ABSENT`, `FORBIDDEN_TO_CLAIM`. "Not confirmed" comes from `NOT_CONFIRMED` and `WITHDRAWN` facts, not from phrase scanning.
- The matrix is canonical JSON with a fingerprint.

### 2.3 Block ranking
- Private: greedy selection by marginal coverage, `gain = Σ weight(r) / (1 + already selected for r)`, with a baseline prior,
  an off-target penalty, saturating requirements, mutual exclusion between a condensed bullet and the bullets it condenses, a
  minimum gain, a precedence rule between two named roles, and tie-breaks by block then bullet order.
- Generic: the algorithm is kept as is. Constants become `profile.selection` with documented defaults; family exclusions, core
  skills and clusters come from `profile.families`; the person-specific precedence rule becomes optional declarative
  `precedence_rules` (default: none). Output: ordered selection, a trace with the gain of each item, and `omitted` with a reason each.

### 2.4 Deterministic LaTeX rendering
- Private: composes the document from validated pieces, writes no new sentence, preamble and header from a baseline file.
- Generic: shipped LaTeX templates with named placeholders; a small deterministic substitution engine; **all content is escaped**
  (raw LaTeX in content is refused). Sections keep their validated order; the page target is a plan input.
- Same inputs give the same `.tex` bytes (LF, no timestamp). That `.tex` hash is what identities and packages refer to.

### 2.5 Optional PDF compilation
- `pdflatex -interaction=nonstopmode -halt-on-error` in a temporary directory, bounded timeout, log kept on failure.
- A PDF is an artefact, not an identity: LaTeX embeds dates, so PDFs are not compared byte for byte. Checks use the extracted
  text and the `.tex` hash. Absent `pdflatex`: `PDF_UNAVAILABLE`, clear and non-fatal for `.tex` generation.

### 2.6 Fact audit
A generated document is audited against the fact base: anything it prints must be a `CONFIRMED` fact or a bullet whose `supports`
are all `CONFIRMED`; forbidden words (profile policy) and `NOT_CONFIRMED` terms fail the audit. Fail-closed, never silently rewritten.

### 2.7 Package and readiness
Packages bind CV, metadata, snapshot and gates; `readiness` computes the state (see `PROVENANCE_READINESS.md`).

## 3. Layout of a workspace (informative)

```
facts.md   profile.json   modularcv.json
content/resume.json
offers/<job_key>.json
applications/<company>/<job_key>/{tailoring-plan.json, resume.tex, resume.pdf?, metadata.json, validation-report.json}
packages/<package>/{package.json, provenance/source-snapshot.json}   packages/package-staleness.json
```

## 4. Cover letters

Out of scope until after the first public engine release: the private letter generator embeds a library of person-specific
paragraphs. A generic letter would need its own content contract. This is a decision for the maintainer.

## 5. Non-goals

No scraping, no model calls, no automatic sending, no editing of a user's fact base, no import of another repository's history.
