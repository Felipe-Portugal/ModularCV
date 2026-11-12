# ModularCV

A modular, traceable and **fact-first** workflow for building CVs, with guard
rails that stop an automated pipeline from inventing facts, shipping stale documents, or leaking
personal data. Built for students and early-career developers applying in Canada and Québec
(French and English documents, ÉTS co-op conventions), but nothing in the code is tied to one person.

Français : [README.fr.md](README.fr.md)

**Scope.** ModularCV generates **CVs** (French or English). It does not generate or rewrite cover letters (see
[docs/design/ENGINE.md](docs/design/ENGINE.md), section 4). The optional `cv-panel` skill can *review* a cover letter that you wrote and list
its problems; it never writes one.

## What it gives you

| Piece | What it does |
|---|---|
| `modularcv.provenance` | A generated document must name a **real Git commit** that holds the exact sources it was built from. Placeholders (all zeros), a missing Git, an unknown SHA or a modified source all refuse the generation. |
| `modularcv.readiness` | **Fail-closed** promotion: a package is "ready to send" only if its evidence (sources, snapshot, plan-to-PDF chain, gates, staleness registry, CV metadata and a human approval of the exact PDF) all agree, re-derived on every call. A secondary index can never promote it. |
| `modularcv.profile` | **Profile-v1**: your identity (each field `public` or `private`), languages, CV families, policy and availability, kept in your workspace. An availability counts only if a `CONFIRMED` fact backs it. |
| `modularcv.content` | **ResumeContent-v1**: your resume text as validated data (sections, blocks, bullets, skills, baselines), in French, English or both. Each bullet, skill and block heading names the facts that back it; it can be printed only if they are all `CONFIRMED`. Raw LaTeX is refused, and the check proves existence and status of the facts, never the meaning of a text. See [docs/CONTENT.md](docs/CONTENT.md). |
| `modularcv.joboffer`, `taxonomy`, `matrix`, `plan` | **JobOffer-v1**, a small configurable **taxonomy**, the **requirement matrix** (`DIRECT`, `ADJACENT`, `ABSENT`, `FORBIDDEN_TO_CLAIM`) and a deterministic **tailoring plan**: which of your proven lines would answer an offer. Only confirmed facts count, a prohibition beats relevance, an unmet requirement stays explicit. The plan is not a CV and nothing is written by a model. See [docs/PLAN.md](docs/PLAN.md). |
| `modularcv.assemble`, `latex`, `pdf` | Turns a **verified** tailoring plan into a structured CV and a generic, escaped, byte-deterministic LaTeX file, and compiles it with `pdflatex` if you have it (optional). Nothing is written by a model, nothing is marked ready to send. See [docs/RENDER.md](docs/RENDER.md). |
| `modularcv.package`, `chain` | Builds a **package** (plan, assembled CV, `.tex`, PDF, metadata, snapshot) in your private workspace, records a **human approval of the exact PDF**, and computes `READY_TO_SEND` from the evidence every time. Nothing is sent, nothing is approved automatically. See [docs/PACKAGE.md](docs/PACKAGE.md). |
| `modularcv.legacy` | `facts import`: turns a historical Markdown document into a *proposed* fact base under a mapping you write. Unknown lines are never imported, nothing becomes `CONFIRMED` by itself. See [docs/IMPORT.md](docs/IMPORT.md). |
| `modularcv.privacy` | Scans a tree (and optionally commit history) for e-mails, phones, SINs, user paths, profile URLs, credentials and your own private terms, **before** you publish. |
| `modularcv.config`, `external` | A workspace configuration and clear diagnostics when an external input directory is missing. |
| `skills/cv-panel` | A Claude Code skill: seven independent readers (ATS, recruiter, technical manager, ÉTS co-op advisor, rival candidate, teammate, fact checker) review a CV and, if you give one, a cover letter you wrote. **Review only: it never rewrites and never adds a fact.** |
| `schemas/`, `templates/` | The traceability record and the analysis templates. |

**New here? Start with [docs/QUICKSTART.md](docs/QUICKSTART.md)** (a five-minute fictional example, what `READY_TO_SEND` means, troubleshooting;
[français](docs/QUICKSTART.fr.md)). On Windows, see [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md) first. Every command and option is
listed in [docs/CLI.md](docs/CLI.md). Then see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/GOVERNANCE.md](docs/GOVERNANCE.md) and
[docs/WORKSPACE.md](docs/WORKSPACE.md).

## Your data stays private

This repository holds **no personal data**. You keep a separate private workspace (your fact base,
CVs and applications) and run ModularCV against it. `facts.md`, `applications/`, `packages/` and
similar folders are ignored by Git here on purpose. See [docs/WORKSPACE.md](docs/WORKSPACE.md).

## Quick start

```bash
git clone https://github.com/Felipe-Portugal/ModularCV && cd ModularCV
python -m pip install -e ".[dev]"        # Python 3.12 to 3.14, pip >= 21.3 (see docs/QUICKSTART.md; no `modularcv` command: use `python -m modularcv`)
python -m pytest                         # all tests use synthetic data

cd /path/to/your/private/workspace       # a Git repository with facts.md
python -m modularcv provenance           # verified source commit, or a clear refusal
python -m modularcv check-packages packages
python -m modularcv facts check facts.md        # strict FactBase-v1 validation (see examples/facts.v1.example.md)
python -m modularcv facts fingerprint facts.md  # source and canonical fingerprints of a valid fact base
python -m modularcv profile check                # Profile-v1 and its fact references (see examples/workspace/)
python -m modularcv content check                # ResumeContent-v1 and its fact references (see examples/workspace/content/)
python -m modularcv offer check offer.json       # JobOffer-v1 (see examples/workspace/offers/)
python -m modularcv matrix --offer offers/backend-intern.json   # requirement states, from confirmed facts only
python -m modularcv plan --offer offers/backend-intern.json     # deterministic tailoring plan (PLAN_ONLY)
python -m modularcv render --plan plans/p.json --offer offers/backend-intern.json --out out/cv.tex   # add --pdf out/cv.pdf if pdflatex is installed
python -m modularcv facts import --mapping import-map.json --in legacy.md --dry-run   # classify, write nothing
python -m modularcv package create --name job --plan plans/job.json --offer offers/job.json --tex out/job.tex --compile   # then: package review, package approve (by you), package status; a PDF given with --pdf can never be READY_TO_SEND
python -m modularcv privacy --root . --deny-file ~/private-terms.txt --history
```

To use the skill, copy `skills/cv-panel/` into `~/.claude/skills/` and run
`/cv-panel resume.pdf cover-letter.pdf <job posting>` in Claude Code.

## Status, supported platforms and limits

The source code is public in this repository: install from a clone (above). Versioned releases, if there are any, are listed on the Releases page of the
GitHub repository and described in [CHANGELOG.md](CHANGELOG.md). ModularCV is **not on PyPI** or any other package index. The engine and the command line are installed from a clone; a separate, optional
Windows application, **ModularCV Desktop** (beta, see [desktop/README.md](desktop/README.md)), has its own installer and its own version. `0.2.0` is the version of the engine in this source tree: the persona-independent chain from fact base to a human-approved PDF (provenance, readiness,
`Profile-v1`, controlled legacy import, `ResumeContent-v1`, offers, plan, assembly, generic LaTeX, packages). Nothing is sent anywhere and
nothing is approved automatically. The CV generation engine from the original private project is not included here because it still embeds
one person's content; porting it behind a configurable fact base is future work.

| Subject | Status |
|---|---|
| Python | **3.12, 3.13, 3.14** (`Requires-Python: >=3.12,<3.15`). Full test suite run on 3.12 and 3.14 (Windows) and 3.13 (Linux container); not every combination of version and platform. 3.9 and 3.10 were regression environments only: no support. 3.15 untested. |
| The engine and the `.tex` | Standard library only. The same synthetic example gives the same plan and the same `.tex` on the interpreters above. |
| PDF with MiKTeX (Windows) | Exercised. |
| PDF with TeX Live (Linux) | **Not tested.** Without a TeX distribution you get the `.tex` and no PDF. |
| macOS | Not tested. |
| Applicant tracking systems | **Not verified, nothing is certified.** Only the order and the accents of the extracted text were looked at on the example. |

**Guarantees.** Everything printed comes from a `CONFIRMED` fact; a generated document names the real Git commit of its sources; the chain
plan, assembly, `.tex` and PDF is re-derived on every call; `READY_TO_SEND` is computed, never stored, and is lost as soon as a source, a
file of the package or the PDF changes.

**Limits.** The checks prove that facts exist and are confirmed, not that a sentence means what they say. An approval is an unsigned JSON
file that binds a decision to the exact bytes of a PDF: the reviewer is **not authenticated**. Only a PDF compiled by
`package create --compile` can become `READY_TO_SEND`; the recorded origin of the PDF is a statement in a file, **not a cryptographic proof**,
and whoever can write your workspace can forge it, as they can forge an approval. `READY_TO_SEND` means the process is consistent, not that
you meet the job's requirements. `pdflatex` is not a sandbox. The privacy scan is best-effort pattern matching. Details:
[docs/PACKAGE.md](docs/PACKAGE.md) ("Limits that are not hidden").

## Contributing, security and changelog

[CONTRIBUTING.md](CONTRIBUTING.md) explains how to propose a change; report a suspected vulnerability privately as described in
[SECURITY.md](SECURITY.md), not in a public issue; [CHANGELOG.md](CHANGELOG.md) lists what `0.2.0` contains, its status and its known limits.

## Credits and license

MIT. `skills/cv-panel` is adapted from
[hiring-panel-skill](https://github.com/alexyc9381/hiring-panel-skill) by Alex Chen (MIT); see
`skills/cv-panel/NOTICE.md`. The skill's co-op advisor can read `skills/cv-panel/normes-ets.md`, an optional summary of the school's co-op guidance: it is in this Git
repository and in the source archive, it is not in the wheel, and the engine does not use it. It is a convenience, may be out of date and does not
replace the school's own documents, which are not included here; replace it with your own norms if yours differ.
