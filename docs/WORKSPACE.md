# Your private workspace

This repository is public. **Your data must never be in it.** Keep a separate, private Git repository (the
*workspace*) and point ModularCV at it.

```
my-cv-workspace/            private repository
├─ facts.md                 your fact base (the single source of truth)
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
  "packages_dir": "packages"
}
```

Run commands from the workspace, or set `MODULARCV_ROOT`:

```bash
python -m modularcv provenance            # verified source commit, or a clear refusal
python -m modularcv check-packages packages
```

## Before you publish anything

Run the scanner on whatever you intend to make public. Keep your private terms (name, employers,
school, handles) in a file **outside** the repository:

```bash
python -m modularcv privacy --root . --deny-file ~/private-terms.txt --history
```

It flags e-mails, phone numbers, social insurance numbers, absolute user paths, profile URLs,
credentials, your own terms, and (with `--history`) personal commit e-mails. Use a no-reply
address for public commits: `<id>+<user>@users.noreply.github.com`.
