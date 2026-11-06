# Command reference

Français : les noms de commandes et d'options sont les mêmes ; cette référence n'est disponible qu'en anglais. Pour un parcours guidé,
voir [QUICKSTART.fr.md](QUICKSTART.fr.md).

Every command is run as `python -m modularcv <command> ...` (there is no `modularcv` executable). This page lists **every command, its
arguments and its options**. It does not repeat the explanations of the guides; it links to them.

**This page is checked by the test suite** (`tests/test_cli_reference.py`): the tests run `python -m modularcv ... --help` for every
command and fail if a command, an argument or an option appears here without existing, or exists without appearing here. The
descriptions are written by hand and the tests do not check them: for the exact wording and defaults, the output of `--help` is the
authority (for example `python -m modularcv facts check --help`).

Common to all commands that take it: `--root DIR` is the workspace, which is `MODULARCV_ROOT` or the current directory when omitted
([WORKSPACE.md](WORKSPACE.md)). Commands that write a file never overwrite an existing one. Nothing in this tool sends anything.

| Group | Commands | Guide |
|---|---|---|
| Provenance and audit | `provenance`, `check-packages`, `snapshot verify` | [WORKSPACE.md](WORKSPACE.md), [PACKAGE.md](PACKAGE.md) |
| Fact base | `facts check`, `facts fingerprint`, `facts import` | [IMPORT.md](IMPORT.md) |
| Profile, content, offer, taxonomy | `profile …`, `content …`, `offer …`, `taxonomy …` | [WORKSPACE.md](WORKSPACE.md), [CONTENT.md](CONTENT.md) |
| Matrix, plan, assembly | `matrix`, `plan`, `assemble` | [PLAN.md](PLAN.md) |
| LaTeX and PDF | `render`, `latex check` | [RENDER.md](RENDER.md) |
| Package and approval | `package create`, `package review`, `package approve`, `package status` | [PACKAGE.md](PACKAGE.md) |
| Privacy | `privacy` | [WORKSPACE.md](WORKSPACE.md) |

## Provenance and audit

### `python -m modularcv provenance`

Prints the Git commit that the workspace sources are tied to, or refuses with a clear code (no Git, unknown commit, modified source).

Options:
- `--root` the workspace.
- `--verify` verify this commit SHA instead of resolving `HEAD`.
- `--recorded` with `--verify`: the document already exists, so the working tree is not compared.

### `python -m modularcv check-packages`

Audits the effective status of the packages in a folder, recomputed from the evidence. Exit code `0` clean, `1` contradiction, `2` incomplete audit
([WORKSPACE.md](WORKSPACE.md)).

Argument: `directory` the folder that holds the packages (for example `packages`).

Options:
- `--registry` the staleness registry file.
- `--root` the workspace.

### `python -m modularcv snapshot verify`

Checks a source snapshot (`provenance/source-snapshot.json` of a package) against the sources it names.

Argument: `file` the snapshot file.

Options:
- `--root` the workspace.

## Fact base

### `python -m modularcv facts check`

Validates a `FactBase-v1` file strictly. See `examples/facts.v1.example.md`.

Argument: `file` optional; the `facts` file of the workspace by default.

Options:
- `--root` the workspace.
- `--require-confirmation-date` make `confirmed_on` mandatory on `CONFIRMED` facts.
- `--use-profile` also apply `policy.require_confirmation_date` of the workspace profile.

### `python -m modularcv facts fingerprint`

Prints the source and canonical fingerprints (SHA-256) of a valid fact base.

Argument: `file` optional; the `facts` file of the workspace by default.

Options:
- `--root` the workspace.
- `--require-confirmation-date` make `confirmed_on` mandatory on `CONFIRMED` facts.
- `--use-profile` also apply `policy.require_confirmation_date` of the workspace profile.
- `--only` print only one hash (`source` or `factbase`), alone on a line.

### `python -m modularcv facts import`

Turns a historical Markdown document into a **proposed** fact base, with a mapping you write. Unknown lines are never imported and nothing
becomes `CONFIRMED` unless the mapping says so. Guide: [IMPORT.md](IMPORT.md).

Options:
- `--mapping` the `LegacyFactMap-v1` file, inside the workspace (required).
- `--in` the historical document, which is only read (required).
- `--out` the proposed fact base to create (never overwritten).
- `--report` the line-by-line audit report to create (never overwritten).
- `--dry-run` classify and print the report, write nothing.
- `--allow-partial` write the accepted facts even if some lines are unclassified, ambiguous or rejected.
- `--root` the workspace.

## Profile, content, offer, taxonomy

### `python -m modularcv profile check`

Validates a `Profile-v1` file and verifies its fact references. Exit code `0` valid and verified, `1` invalid, `2` unreadable, `3` when
references were not verified (`--no-facts`). Prints field names, never values.

Argument: `file` optional; the `profile` file of the workspace by default.

Options:
- `--root` the workspace.
- `--facts` the fact base used to verify references (the workspace one by default).
- `--no-facts` structure only: references stay `UNVERIFIED` and the exit code is `3`.

### `python -m modularcv profile fingerprint`

Prints the fingerprints of a valid profile.

Argument: `file` optional; the `profile` file of the workspace by default.

Options:
- `--root` the workspace.
- `--only` print only one hash (`source` or `profile`).

### `python -m modularcv content check`

Validates a `ResumeContent-v1` file and verifies that each line is backed by `CONFIRMED` facts. Exit codes as for `profile check`.
Guide: [CONTENT.md](CONTENT.md).

Argument: `file` optional; the `content` file of the workspace by default.

Options:
- `--root` the workspace.
- `--facts` the fact base used to verify references (the workspace one by default).
- `--no-facts` structure only: references stay `UNVERIFIED` and the exit code is `3`.
- `--profile` also check the baseline families and the confirmation-date policy against this profile.
- `--outline` add the structure (identifiers and states, no text).

### `python -m modularcv content fingerprint`

Prints the fingerprints of a valid resume content file.

Argument: `file` optional; the `content` file of the workspace by default.

Options:
- `--root` the workspace.
- `--only` print only one hash (`source` or `content`).

### `python -m modularcv offer check`

Validates a `JobOffer-v1` file and finds its requirements.

Argument: `file` the offer.

Options:
- `--root` the workspace.
- `--taxonomy` the taxonomy used to find requirements (the built-in one by default).

### `python -m modularcv offer fingerprint`

Prints the fingerprints of a valid offer.

Argument: `file` the offer.

Options:
- `--root` the workspace.
- `--only` print only one hash (`source` or `offer`).

### `python -m modularcv taxonomy check`

Validates a taxonomy: `builtin:generic-v1` or a `.json` file.

Argument: `spec` optional; `builtin:generic-v1` or a `.json` file.

Options:
- `--root` the workspace.

### `python -m modularcv taxonomy fingerprint`

Prints the fingerprint of a valid taxonomy.

Argument: `spec` optional; `builtin:generic-v1` or a `.json` file.

Options:
- `--root` the workspace.
- `--only` print the hash alone.

## Matrix, plan, assembly

### `python -m modularcv matrix`

Builds the requirement matrix of an offer: one of `DIRECT`, `ADJACENT`, `ABSENT`, `FORBIDDEN_TO_CLAIM` per requirement, from confirmed facts
only. Writes nothing unless `--out` is given. Guide: [PLAN.md](PLAN.md).

Options:
- `--offer` the `JobOffer-v1` file (required).
- `--family` the profile family (required when the profile has several).
- `--language` override the language of the offer (`fr` or `en`).
- `--out` write the result to a new file inside the workspace (never overwritten).
- `--root` the workspace.

### `python -m modularcv plan`

Builds the deterministic tailoring plan of an offer. The plan says what would be shown and why; it is not a CV. Writes nothing unless `--out`
is given. Guide: [PLAN.md](PLAN.md).

Options:
- `--offer` the `JobOffer-v1` file (required).
- `--family` the profile family (required when the profile has several).
- `--language` override the language of the offer (`fr` or `en`).
- `--out` write the plan to a new file inside the workspace (never overwritten).
- `--root` the workspace.

### `python -m modularcv assemble`

Assembles the structured CV that a verified plan describes (no LaTeX). The plan is checked against the current sources first.

Options:
- `--plan` the `TailoringPlan-v1` file written by `plan --out` (required).
- `--offer` the `JobOffer-v1` file the plan was built for (required).
- `--out` write to a new file inside the workspace (never overwritten).
- `--outline` identifiers and counts only, no text.
- `--root` the workspace.

## LaTeX and PDF

### `python -m modularcv render`

Verifies a plan against the current sources, writes a generic, escaped, deterministic `.tex`, and optionally compiles it with `pdflatex`.
Exit code `4` when `pdflatex` is not found (the `.tex` is still written) and `5` when the compilation fails. The output is an artefact: not
reviewed, never ready to send. Guide: [RENDER.md](RENDER.md).

Options:
- `--plan` the `TailoringPlan-v1` file written by `plan --out` (required).
- `--offer` the `JobOffer-v1` file the plan was built for (required).
- `--out` the new `.tex` file inside the workspace (never overwritten).
- `--pdf` also compile the `.tex` to this new `.pdf` (needs `pdflatex`).
- `--log` keep the compiler log in this new `.log` file; it can quote the CV, so keep it private.
- `--paper` the page size: `a4paper` (default) or `letterpaper`.
- `--timeout` the compiler time limit, in seconds.
- `--root` the workspace.

### `python -m modularcv latex check`

Reports whether the optional `pdflatex` dependency is available (`FOUND` or `ABSENT`) and which distribution it is. ModularCV never installs it.

## Package and approval

### `python -m modularcv package create`

Builds a package (plan, assembled CV, `.tex`, PDF, metadata, snapshot) from a verified plan. Creating a package is never an approval.
Guide: [PACKAGE.md](PACKAGE.md).

Options:
- `--name` the package name (lowercase letters, digits, `.` and `-`) (required).
- `--plan` the `TailoringPlan-v1` file (required).
- `--offer` the `JobOffer-v1` file, inside the workspace (required).
- `--tex` the `.tex` written by `render` (required).
- `--compile` compile the verified `.tex` now with `pdflatex` and package that very output. This is the only way to a package that can become `READY_TO_SEND`.
- `--pdf` a PDF made elsewhere, instead of `--compile`: its origin is recorded as not verified and the package can never be `READY_TO_SEND`.
- `--timeout` the compiler time limit in seconds, with `--compile`.
- `--root` the workspace.

### `python -m modularcv package review`

Shows what you must examine before approving: the exact PDF, the unmet requirements and the warnings.

Options:
- `--name` the package name (required).
- `--root` the workspace.

### `python -m modularcv package approve`

Records **your** decision about the exact PDF. It must be run by a person in an interactive terminal and refuses to run from a script
(`APPROVAL_REQUIRES_A_PERSON`). The approval is an unsigned file and the reviewer is not authenticated ([PACKAGE.md](PACKAGE.md)).

Options:
- `--name` the package name (required).
- `--reviewer` who reviewed the PDF (required).
- `--decision` `APPROVED` or `REJECTED`.
- `--note` a free note kept in the approval.
- `--root` the workspace.

### `python -m modularcv package status`

Computes the state of a package from the evidence, every time. The exit code is `0` only for `READY_TO_SEND`.

Options:
- `--name` the package name (required).
- `--root` the workspace.

## Privacy

### `python -m modularcv privacy`

Scans a tree (and, with `--history`, the commit author e-mails) for e-mails, phone numbers, social insurance numbers, absolute user paths,
profile URLs, credentials and your own private terms, before you publish. It is best-effort pattern matching, not a guarantee.

Options:
- `--root` the folder to scan.
- `--deny-file` a text file with one private term per line (keep it outside the repository).
- `--deny` a private term (repeatable).
- `--history` also check commit author e-mails.
