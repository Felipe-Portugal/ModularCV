# Publishing from a clean snapshot (procedure, M8-A-R2)

Status: **a procedure, a local simulation (M8-A-R2) and a release-candidate snapshot (M8-B, `PREPUBLICATION_AUDIT.md` section 18). Nothing was published**, no GitHub repository was created, no remote was configured and nothing
was pushed. Whether, when and how to publish is a human decision (see "Decisions" below).

## Why a snapshot

The private repository's history contains `skills/cv-panel/normes-ets.md` from the initial commit (`0a553e1`), and the right to redistribute
that file is not established (`PREPUBLICATION_AUDIT.md` section 16.5). Rewriting the private history and deleting the file are **not** done and
not needed: a public repository can start from a **single new commit** made from the tracked files that may be distributed. The private
repository stays as it is.

## Procedure (reproducible, local, no remote)

Run from a clean checkout of the private repository at the commit to publish (`git status` empty). `<private>` is that checkout, `<out>` a new
empty temporary folder, `<deny>` a file **outside** both, holding your private terms (one per line).

```bash
git -C <private> archive HEAD | tar -x -C <out>          # tracked files only: no .git, no untracked file, no cache, no quarantine
grep -vE '^(#|$)' <out>/PUBLIC_EXCLUDE.txt | while read -r f; do rm -f "<out>/$f"; done   # the exclusions of the candidate, one path per line
cd <out>
git init -b main                                          # a new history; no remote is ever configured here
git add -A
git -c user.name=ModularCV -c user.email=<id>+<user>@users.noreply.github.com commit -m "ModularCV 0.2.0: initial public snapshot"
```

Then verify, in `<out>`:

| Check | Command | Expected |
|---|---|---|
| one commit, no remote | `git rev-list --count HEAD; git remote` | `1`, empty |
| excluded file absent from tree and history | `git ls-files \| grep normes-ets; git rev-list --objects --all \| grep normes-ets` | no output |
| its content absent | `git grep -n -e "<distinctive phrase>" $(git rev-list --all)` | no output (outside documentation that merely names the file) |
| no private or generated artefact | `git ls-files \| grep -iE "legacy_import\|_quarantine\|\.pdf$\|\.log$\|\.pyc$"` | no output |
| no broken relative link | a link check over `*.md` | none |
| privacy | `python -m modularcv privacy --root . --deny-file <deny> --history` | `0 finding(s)` |
| build | `python -m build` (in a virtual environment) | wheel + sdist, no excluded file inside |
| tests | `python -m pytest` | all pass; the one test that reads the excluded file is skipped |
| quick start | `docs/QUICKSTART.md` with the installed wheel, from outside the folder | as in the private repository |

**M8-B inventory.** `PUBLIC_EXCLUDE.txt` (at the root of the private tree, itself excluded) lists what is left out: itself, `PROJECT_STATE.md`
(working log), `docs/design/PREPUBLICATION_AUDIT.md` (audit journal), this document (maintainer procedure) and `skills/cv-panel/normes-ets.md`
(rights not established). `tests/test_public_tree.py` checks that no distributed Markdown file links to a missing or excluded file and that
the Python policy, the classifiers and the documents agree; it runs unchanged in the snapshot. `AGENTS.md`, the contracts, the architecture
documents, the guides, the examples and the skills are distributed.

`SKILL.md` was changed (M8-A-R2) so that the skill no longer depends on the excluded file: without it the skill must not quote any norm from
memory. `MANIFEST.in` already excludes the file from source archives. A few documents (`PREPUBLICATION_AUDIT.md`, `PROJECT_STATE.md`, the quick
starts, `MANIFEST.in`, `tests/test_skill.py`) **name** the file to explain the exclusion; they reproduce nothing of its content. Whether to keep
`PROJECT_STATE.md`, `AGENTS.md` and the audit in a public tree is a maintainer decision (M8-B proposes the list above).

## What the snapshot does not change

- The private history is untouched and still contains the file; nobody should push it to a public remote.
- The snapshot loses the fine-grained history. If a public history is wanted, it must be rebuilt by a separate, explicit decision (for
  instance by replaying the commits after removing the file, which rewrites hashes), not as a by-product of this procedure.
- The GitHub account name appears in the no-reply address used for the commit; choose the public identity before the commit.

## Decisions the maintainer must take (none was taken)

1. Which route to publish: (a) this single-commit snapshot without the file, (b) a rewritten history without the file, (c) keep the file after
   obtaining the school's written authorisation. Each is a separate decision; (b) rewrites history and needs its own approval.
2. Which documents of the working tree are public (`PROJECT_STATE.md`, `AGENTS.md`, the audit).
3. The public identity of the commit, the repository name and visibility, and the licence line (MIT is in `LICENSE`).
4. The version to tag, and the supported Python range (audit section 17).
