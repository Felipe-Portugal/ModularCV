# Contributing to ModularCV

Thank you for your interest. ModularCV is a small, careful project: its value is that it **never invents a fact, never ships a stale
document and never leaks personal data**. Contributions are welcome when they keep those properties.

This page is in English only, like the other documents in `docs/` (see [AGENTS.md](AGENTS.md), section 7). French speakers are welcome
to open issues and pull requests in French.

There is no formal governance yet: one maintainer reviews contributions when time allows. **No response time is promised.** This page
describes how to make a change that is easy to review; it is not an approval process you must follow to the letter.

## What is welcome

- **Bug reports** with a minimal, synthetic reproduction.
- **Fixes** with a test that fails before and passes after.
- **Documentation**: corrections, clearer wording, missing steps, translations of the user guides.
- **Tests**, in particular edge cases of the validators.
- **Small, focused improvements** to the existing commands.

Please **open an issue first** for anything larger (a new command, a new file format, a change to a contract in
[docs/design/CONTRACTS.md](docs/design/CONTRACTS.md), a new dependency): a short discussion avoids work that cannot be merged. The project has a
fixed scope (below); a change outside it will be declined however well it is made.

## Scope: what ModularCV is, and is not

ModularCV builds **CVs** from facts you have confirmed. It does **not** generate or rewrite cover letters, does not write sentences with a
model, does not send anything to anyone and does not approve a CV in your place. The optional `skills/cv-panel` only *reviews*.
Compatibility with applicant tracking systems is not verified and nothing is certified. Please do not propose changes that claim
more than that.

## Set up a development environment

You need **Python 3.12, 3.13 or 3.14** (`requires-python = ">=3.12,<3.15"`) and Git. Python 3.9 and 3.10 were only regression
environments of the source tree: no support is announced for them, so please target the supported versions. The engine uses the Python
standard library only (`dependencies = []`); the one development dependency is `pytest`.

Clone your fork (the clone address of the project is in the Quick start of [README.md](README.md)), then, from the clone:

```bash
python -m venv ../modularcv-venv          # outside the clone, so it is never scanned or committed
../modularcv-venv/bin/python -m pip install -e ".[dev]"
```

Use the interpreter of that environment for the commands below (`../modularcv-venv/bin/python -m pytest`, and so on).

On Windows, with PowerShell, follow [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md). There is no `modularcv` command: run
`python -m modularcv ...`. Every command and option is listed in [docs/CLI.md](docs/CLI.md).

To produce a PDF you also need `pdflatex` (MiKTeX is the only distribution exercised so far; TeX Live and Linux are untested). It is
optional: the tests do not need it.

## Run the checks

```bash
python -m pytest                          # the full suite: synthetic data only, takes a few minutes
python -m modularcv privacy --root .      # must report 0 finding(s)
git diff --check                          # no whitespace errors
```

Run both before you open a pull request. A change that makes either fail will not be merged. Tests that need real private data do not
belong in this repository.

## Conventions

The rules of [AGENTS.md](AGENTS.md) apply to everyone, human or not. In short:

- **Standard library only.** A new dependency needs an architecture decision record and the maintainer's explicit approval.
- **Deterministic by construction.** No timestamp, random value or environment-dependent path may enter an identity or a fingerprint.
  Text is normalised to LF before hashing, so a Windows checkout must not change a fingerprint. The same inputs give the same plan and
  the same `.tex`.
- **Fail closed.** An unreadable, missing or ambiguous input is an error with a **stable machine code** (for example
  `SOURCE_NOT_AT_COMMIT`), never an empty result and never a silent fallback. Readiness is recomputed on every call, never stored.
- **No hidden state.** No global mutable state, no side effects on import, no default path to a machine-specific location.
- **Core modules never import adapters;** adapters are optional.
- **Behaviour changes need tests.** A new behaviour, a fixed bug or a new refusal code comes with a test. Tests build synthetic data in
  temporary directories (including temporary Git repositories). A change to a validated module needs an explicit decision first.
- **Documentation travels with the change.** If you add or change a command or an option, update [docs/CLI.md](docs/CLI.md): the test
  `tests/test_cli_reference.py` fails when it drifts from `--help`, and `tests/test_docs_commands.py` checks the commands shown in the guides.
  Keep the English and French guides in step.
- **Style.** Follow the style of the surrounding code. English for code, identifiers, commit messages and the documents in `docs/`.

## Three principles you must not weaken

1. **No invention of facts.** Everything printed on a CV comes from a fact with status `CONFIRMED`. A missing fact is a question, never a
   guess. Never add an invented date, number, metric, technology or role, in code, in a fixture or in an example. The checks prove that
   facts exist and are confirmed, not that a sentence means what they say, and that limit must stay documented.
2. **Everything must work without a remote AI service.** Generation and every validation run locally, offline, with the Python standard
   library (and `pdflatex` if you want a PDF). No command may call an AI service or any remote API, and no test may depend on one. Nothing in
   the project writes text with a model.
3. **Fail closed.** When in doubt, refuse and say why. A change that makes a package easier to mark `READY_TO_SEND`, or that weakens a
   refusal, needs a very good reason and a test.

## Privacy: no personal data, ever

This repository is public. **Do not commit, paste into an issue, or attach to a pull request** any personal data: a real name, e-mail,
phone number, address, employer, school, profile URL, real CV text, real job posting, real fact, absolute path on your machine, or any
credential. Use the fictional material in [examples/](examples/) and synthetic test data.

- Keep your own facts, CVs, applications and packages in a **separate private repository**, your *workspace* (see
  [docs/WORKSPACE.md](docs/WORKSPACE.md)). Its usual folders are ignored by Git here on purpose.
- Logs can quote a CV (`render --log`): read them before you share them.
- Use a GitHub *no-reply* address for your commits (`<id>+<user>@users.noreply.github.com`), not your personal e-mail.
- Do not copy code, fixtures or text from a private project. Do not add copyrighted text (for example the school's own documents).

`python -m modularcv privacy --root .` is a best-effort pattern check, not a guarantee: you remain responsible for what you submit.

## Open an issue

Describe: what you did (the exact command), what you expected, what happened (the refusal code or the output), and your versions:
`python --version`, your operating system, and whether `python -m modularcv latex check` finds `pdflatex`. Reduce the problem to
**synthetic** data. If the problem could be a **security vulnerability**, do not open a public issue: read [SECURITY.md](SECURITY.md).

## Open a pull request

1. Fork the repository and create a branch from `main` (the maintainer works on `main`; you can name your branch freely).
2. Keep the change small and about one topic. Explain *why* in the description.
3. Run the checks above and say which Python version and operating system you used. Do not claim a test passed if you did not run it.
4. Use [Conventional Commits](https://www.conventionalcommits.org/) in English: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
5. Do not mention a tool or an assistant in a commit message or a pull request description. If you use a coding agent, it must follow
   [AGENTS.md](AGENTS.md).

The project is released under the [MIT licence](LICENSE); contributions are accepted under that licence. There is no contributor
agreement to sign.

## Releases

No versioned release has been published yet: `0.2.0` is a release candidate (see [CHANGELOG.md](CHANGELOG.md)). Releases, tags and
publication are decided by the maintainer; please do not open pull requests that change the version number.
