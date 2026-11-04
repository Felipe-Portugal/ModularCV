# Architecture

ModularCV treats a CV as the end of a chain in which every step is traceable and every claim
comes from one place.

```
facts.md ──► master CV ──► family baselines ──► tailored CV ──► application package ──► readiness check
 (truth)      (full)        (software, ...)       (per offer)     (CV + letter + proof)     (fail-closed)
```

| Layer | Role | Rule |
|---|---|---|
| **Fact base** | The only source of professional facts: roles, dates, technologies, confirmed wording, forbidden claims. | Nothing is written that is not here. A missing fact is a question, never a guess. |
| **Master CV** | The most complete, validated document. | Reviewed by a human; changes are milestones. |
| **Baselines** | One short CV per family and language, derived from the master. | Validated once, then frozen. |
| **Tailored CV** | A baseline reordered and trimmed for one offer. | Deterministic, never adds a fact; carries a metadata record. |
| **Package** | CV + cover letter + provenance for one application. | Every gate passes, or it is not ready. |
| **Readiness** | Decides if a package may be sent. | Fail-closed (see `GOVERNANCE.md`). |

## The chain as implemented (M2 to M7)

The diagram above is the original idea. What the code does today, one module per step, every arrow a verification:

```
facts.md (FactBase-v1)  ─►  content/resume.json (ResumeContent-v1, each line tied to CONFIRMED facts)
        │                           │
        └──── profile.json (Profile-v1) ──┐
offers/*.json (JobOffer-v1) + taxonomy ─► requirement matrix ─► TailoringPlan-v1 (deterministic, not a CV)
                                                                   │
        assembly (AssembledResume-v1, five verification layers) ◄──┘
                │
            .tex (generic-v1, escaped, byte-deterministic) ─► PDF (optional pdflatex)
                │                                                │
                └──────── package (metadata v3, snapshot, package.json) ─► your review of the exact PDF ─► READY_TO_SEND (computed)
```

Modules: `facts`, `profile`, `content`, `joboffer`, `taxonomy`, `matrix`, `plan`, `assemble`, `latex`, `pdf`, `chain`, `package`, `review`,
`snapshot`, `metadata`, `provenance`, `readiness`, `staleness`, `privacy`, `legacy`. Start with [QUICKSTART.md](QUICKSTART.md). The
pre-publication audit (trust boundaries, limits, open decisions) is [design/PREPUBLICATION_AUDIT.md](design/PREPUBLICATION_AUDIT.md).

## What this repository contains

The persona-independent parts, with tests:

- `modularcv/provenance.py`: a generated document must name a **real** Git commit that contains
  the exact sources it was built from. All-zero placeholders are refused.
- `modularcv/readiness.py` and `modularcv/staleness.py`: a stale, invalid or unreviewed package is
  never "ready", whatever a secondary index says.
- `modularcv/config.py`, `modularcv/external.py`: a workspace configuration and a diagnostic
  (never a silent empty result) when an external input directory is missing.
- `modularcv/privacy.py`: scans a tree and its history for personal data before publishing.
- `schemas/` and `templates/`: the metadata record and the analysis templates.
- `skills/cv-panel/`: a Claude Code skill that reviews a CV with seven independent readers,
  adapted to Canada/Québec and to ÉTS student conventions. It reviews; it never rewrites.

## What stays in your private workspace

Your facts, CVs, applications and generated packages. See `WORKSPACE.md`.
