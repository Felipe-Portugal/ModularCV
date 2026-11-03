# ModularCV

A modular, traceable and **fact-first** workflow for building CVs and cover letters, with guard
rails that stop an automated pipeline from inventing facts, shipping stale documents, or leaking
personal data. Built for students and early-career developers applying in Canada and Québec
(French and English documents, ÉTS co-op conventions), but nothing in the code is tied to one person.

Français : [README.fr.md](README.fr.md)

## What it gives you

| Piece | What it does |
|---|---|
| `modularcv.provenance` | A generated document must name a **real Git commit** that holds the exact sources it was built from. Placeholders (all zeros), a missing Git, an unknown SHA or a modified source all refuse the generation. |
| `modularcv.readiness` | **Fail-closed** promotion: a package is "ready to send" only if its declared state, gates, staleness registry and CV metadata all agree. A secondary index can never promote it. |
| `modularcv.profile` | **Profile-v1**: your identity (each field `public` or `private`), languages, CV families, policy and availability, kept in your workspace. An availability counts only if a `CONFIRMED` fact backs it. |
| `modularcv.content` | **ResumeContent-v1**: your resume text as validated data (sections, blocks, bullets, skills, baselines), in French, English or both. Each bullet, skill and block heading names the facts that back it; it can be printed only if they are all `CONFIRMED`. Raw LaTeX is refused, and the check proves existence and status of the facts, never the meaning of a text. See [docs/CONTENT.md](docs/CONTENT.md). |
| `modularcv.legacy` | `facts import`: turns a historical Markdown document into a *proposed* fact base under a mapping you write. Unknown lines are never imported, nothing becomes `CONFIRMED` by itself. See [docs/IMPORT.md](docs/IMPORT.md). |
| `modularcv.privacy` | Scans a tree (and optionally commit history) for e-mails, phones, SINs, user paths, profile URLs, credentials and your own private terms, **before** you publish. |
| `modularcv.config`, `external` | A workspace configuration and clear diagnostics when an external input directory is missing. |
| `skills/cv-panel` | A Claude Code skill: seven independent readers (ATS, recruiter, technical manager, ÉTS co-op advisor, rival candidate, teammate, fact checker) review a CV and its cover letter. **Review only: it never rewrites and never adds a fact.** |
| `schemas/`, `templates/` | The traceability record and the analysis templates. |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/GOVERNANCE.md](docs/GOVERNANCE.md) and
[docs/WORKSPACE.md](docs/WORKSPACE.md).

## Your data stays private

This repository holds **no personal data**. You keep a separate private workspace (your fact base,
CVs and applications) and run ModularCV against it. `facts.md`, `applications/`, `packages/` and
similar folders are ignored by Git here on purpose. See [docs/WORKSPACE.md](docs/WORKSPACE.md).

## Quick start

```bash
git clone https://github.com/<your-user>/ModularCV && cd ModularCV
python -m pip install -e ".[dev]"        # Python 3.9+
python -m pytest                         # all tests use synthetic data

cd /path/to/your/private/workspace       # a Git repository with facts.md
python -m modularcv provenance           # verified source commit, or a clear refusal
python -m modularcv check-packages packages
python -m modularcv facts check facts.md        # strict FactBase-v1 validation (see examples/facts.v1.example.md)
python -m modularcv facts fingerprint facts.md  # source and canonical fingerprints of a valid fact base
python -m modularcv profile check                # Profile-v1 and its fact references (see examples/workspace/)
python -m modularcv content check                # ResumeContent-v1 and its fact references (see examples/workspace/content/)
python -m modularcv facts import --mapping import-map.json --in legacy.md --dry-run   # classify, write nothing
python -m modularcv privacy --root . --deny-file ~/private-terms.txt --history
```

To use the skill, copy `skills/cv-panel/` into `~/.claude/skills/` and run
`/cv-panel resume.pdf cover-letter.pdf <job posting>` in Claude Code.

## Status

`0.2.0` (unpublished): the persona-independent core, with fail-closed provenance and readiness, `Profile-v1` and a controlled legacy import (incompatible changes since `0.1.0`: `docs/design/PROVENANCE_READINESS.md` section 9). The CV generation engine from the original private project is
not included here because it still embeds one person's content; porting it behind a configurable
fact base is future work.

## Credits and license

MIT. `skills/cv-panel` is adapted from
[hiring-panel-skill](https://github.com/alexyc9381/hiring-panel-skill) by Alex Chen (MIT); see
`skills/cv-panel/NOTICE.md`. The ÉTS conventions are summarised from the school's public guidance
for students; examples from that guidance are not reproduced.
