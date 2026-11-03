# Your private workspace

This repository is public. **Your data must never be in it.** Keep a separate, private Git repository (the
*workspace*) and point ModularCV at it.

```
my-cv-workspace/            private repository
├─ facts.md                 your fact base (the single source of truth)
├─ profile.json             your Profile-v1: identity, languages, CV families, policy, availability
├─ content/resume.json      your ResumeContent-v1: the text of your CVs, each line tied to confirmed facts
├─ modularcv.json           optional configuration
├─ master/ baselines/       validated documents
├─ applications/            one folder per offer
├─ packages/                generated packages and package-staleness.json
└─ reviews/                 /cv-panel reports
```

`modularcv.json` (every key optional):

```json
{
  "facts": "facts.md",
  "provenance_files": ["master/resume.tex", "baselines/software.tex"],
  "staleness_registry": "packages/package-staleness.json",
  "packages_dir": "packages",
  "applications_dir": "applications",
  "profile": "profile.json",
  "content": "content/resume.json"
}
```

Run commands from the workspace, or set `MODULARCV_ROOT`:

```bash
python -m modularcv provenance            # verified source commit, or a clear refusal
python -m modularcv check-packages packages   # exit 0 clean, 1 contradiction, 2 incomplete audit
python -m modularcv snapshot verify packages/<folder>/provenance/source-snapshot.json
```

### Your profile

`profile.json` (`Profile-v1`, example: `examples/workspace/profile.json`) holds who you are and how your CVs are
configured. It keeps three kinds of content apart: **private** identity fields, fields **allowed to appear in a CV**, and
**internal preferences** (families, policy, selection) that are never printed. Every identity field states its `visibility`;
nothing is public by default. An availability names a fact id and counts only if that fact is `CONFIRMED` in your `facts.md`.

```bash
python -m modularcv profile check          # exit 0 valid and verified, 1 invalid, 2 unreadable; prints field names, never values
python -m modularcv profile check --no-facts   # structure only: references stay UNVERIFIED, exit 3 (never 0)
python -m modularcv profile fingerprint --only profile
```

### Your resume content

`content/resume.json` (`ResumeContent-v1`, example: `examples/workspace/content/`, guide: [CONTENT.md](CONTENT.md)) holds the text
your CVs will be built from. Each bullet and skill lists the fact ids that support it, and counts as printable only if every one
of those facts is `CONFIRMED` in your `facts.md`. French-only, English-only and bilingual content are all valid.

```bash
python -m modularcv content check            # exit 0 valid and references verified, 1 invalid, 2 unreadable
python -m modularcv content check --no-facts # structure only: references stay UNVERIFIED, exit 3 (never 0)
python -m modularcv content fingerprint --only content
```

The check proves that each referenced fact exists and is confirmed. It does not prove that a sentence says what its facts say,
nor that a French line and its English line are equivalent: those stay human decisions.

### Importing an old document

`python -m modularcv facts import --mapping import-map.json --in old-notes.md --dry-run` classifies a historical Markdown
document with rules you write and reports every line. Nothing unknown is imported and nothing becomes `CONFIRMED` unless
your mapping says so. Full guide: [IMPORT.md](IMPORT.md).

A package is `READY_TO_SEND` only with evidence in the workspace: its `provenance/source-snapshot.json`, the CV metadata and
plan it names under `applications/`, a `source_commit` that is a commit of this repository, and a `cv-quality-review.json`
written by you that approves the exact CV. See `docs/design/PROVENANCE_READINESS.md` section 9.

## Before you publish anything

Run the scanner on whatever you intend to make public. Keep your private terms (name, employers,
school, handles) in a file **outside** the repository:

```bash
python -m modularcv privacy --root . --deny-file ~/private-terms.txt --history
```

It flags e-mails, phone numbers, social insurance numbers, absolute user paths, profile URLs,
credentials, your own terms, and (with `--history`) personal commit e-mails. Use a no-reply
address for public commits: `<id>+<user>@users.noreply.github.com`.
