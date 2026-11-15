# AGENTS.md — Rules for every agent (Claude Code, Codex, others)

This file is authoritative. Tool-specific files (for example `CLAUDE.md`) only add to it.

## 1. Before a session

1. Read `PROJECT_STATE.md` when the maintainers keep one (a working log that is not part of the public distribution): active
   milestone, last work, blockers, next action.
2. Check the real state: `git status`, `git log -1 --oneline`, current branch. Report any gap with `PROJECT_STATE.md` (if any) before acting.
3. Read the contracts of the active milestone in `docs/design/`.
4. Work only on the active milestone. Never start the next one without the maintainer's explicit validation.

## 2. Scope

This repository is the generic, persona-independent engine. Work here concerns only this repository. A request about another
project (a private workspace, a scraper, an infrastructure repository) is out of scope: do nothing there, say so, and propose a
dedicated session.

## 3. Absolute prohibitions

- Putting personal data in this repository: a name, e-mail, phone, address, employer, school, handle, profile URL, real CV text,
  real job posting, real fact, absolute user path, or any identifier taken from a private project.
  The one exception is the repository's own public address (the clone URL in the READMEs), which is how the project is found.
  A second, narrow exception covers third-party legal notices: official licence texts and copyright notices of redistributed components may
  keep the public contact details of their rights holders (for example the address in a copyright line), because altering a notice would
  alter the licence. Such a file may carry the `privacy-scan: ignore-file` marker only if a test restricts its addresses to an explicit list
  (by exact value), rejects any other finding (token, key, user path, other address), and fixes the exact set of exempt files. This never
  extends to data about the maintainer, a contributor or any other person who is not a rights holder named in the notice.
- Copying code, fixtures, documents or history from a private repository. Interfaces and algorithms may be studied read-only and
  re-implemented against the contracts in `docs/design/`.
- Pushing, creating a remote, tagging, releasing or publishing without the maintainer's explicit authorisation for that exact action.
- Rewriting Git history (`rebase`, `reset --hard`, `push --force`) without agreement.
- Inventing a metric, a result, a test outcome or a validation.
- Changing the behaviour of a validated module without an explicit decision (see the milestone plan).
- Disabling TLS verification or adding an option to do so.
- Sending anything to an employer. Nothing in this project sends anything.

## 4. Reports

Every report separates **Observed** (a command, test or cited source), **Hypothesis** (unverified deduction) and **Planned**
(not implemented). A milestone is `PASS` only with proof for every criterion (command and output); otherwise `PARTIAL` with
what is missing, or `BLOCKED` with the cause. A test that was not run is never described as passed.

## 5. Code conventions

- Python 3.12 to 3.14 (`requires-python = ">=3.12,<3.15"`), standard library only (`dependencies = []`); a new dependency needs an ADR and
  the maintainer's approval. Python 3.9 and 3.10 were only regression environments of the source tree: no support is announced for them.
- Deterministic by construction: no timestamp, random value or environment-dependent path in an identity or fingerprint.
- Text is LF-normalised before hashing; a Windows checkout must not change a fingerprint.
- Fail closed: an unreadable, missing or ambiguous input is an error with a stable machine code, never an empty result.
- No global mutable state, no side-effecting import, no hidden default path to a machine-specific location.
- Tests use synthetic data created in temporary directories (including temporary Git repositories). Tests that need real private
  data do not belong here.
- Core modules never import adapters; adapters are optional.
- Before every commit: the full test suite and `python -m modularcv privacy --root .` pass.

## 6. Git

- Default branch `main`. Work on `mN/<topic>` if the maintainer asks, otherwise commit locally on `main` only when asked.
- Commit messages: Conventional Commits in English (`feat:`, `fix:`, `docs:`, `test:`, `chore:`). No attribution line about a tool
  or an assistant in a commit message or a pull request description.
- Use a no-reply address for public commits (`<id>+<user>@users.noreply.github.com`); never a personal e-mail.
- Small, coherent commits; never commit a state whose tests fail.
- Commit only on request or as the milestone says.

## 7. Documentation language

English for code, identifiers, commit messages and the documents in `docs/`; `README.fr.md` mirrors the README in French. A French
translation of the design documents is prepared before any publication (milestone M8).

## 8. End of a session

Update `PROJECT_STATE.md` (if the maintainers keep one) before stopping, even when interrupted: branch and last commit, active milestone and status, work done,
tests run **with their real result**, blockers and open decisions, and the next precise action, so another agent can resume
without reading the conversation.
