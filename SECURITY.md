# Security policy

## Reporting a vulnerability

Please report a suspected vulnerability **privately**, using GitHub's private vulnerability reporting:

1. Open the repository page on GitHub.
2. Go to the **Security** tab.
3. Choose **Report a vulnerability** and fill in the form.

Only you and the maintainer can see the report. **No e-mail address is offered for security reports.** If the button is not available
(for example if the repository has moved), open a public issue that says only that you need a private channel for a security report,
**with no technical detail**, and wait for a reply.

### Do not post sensitive evidence publicly

Do **not** put any of the following in a public issue, pull request, discussion or commit:

- the details or a working proof of an unfixed vulnerability;
- personal data: a real CV, fact base, profile, job posting, package, approval file or compiler log (`render --log` can quote a CV);
- credentials, tokens or keys, and absolute paths from your machine.

In a report, give the **smallest synthetic reproduction** you can: the fictional data of `examples/` or a few made-up lines, the exact
command, the output, and your versions (`python --version`, operating system, whether `pdflatex` is installed and which distribution). If
you accidentally included real personal data, say so, so that it can be handled.

## What is relevant

ModularCV is a local command-line tool that reads and writes files in a workspace you choose. It has no server, no account, no
network access of its own and no telemetry; it sends nothing. Reports that are relevant include:

- a way to write, overwrite or read **outside the workspace**, or to **overwrite an existing file** that the tool promises never to
  overwrite;
- **command or LaTeX injection**: content (a fact, a CV line, an offer, a name) that makes `pdflatex` or another process do something that
  was not intended, or that gets through the escaping of the generated `.tex`;
- a way to make a package **`READY_TO_SEND` without the conditions the documentation states** (for example without a human approval of
  the exact PDF, or with a PDF whose origin is not `COMPILED_FROM_VERIFIED_TEX`), or to run `package approve` without a person;
- **disclosure of private data** that the documentation says is not printed or not written (for example private profile fields, or values
  in a validation report);
- a crash or hang on hostile input that makes the tool report success, or stops it from failing closed;
- a secret or personal data that ended up in this repository or its history (please report it privately so it can be handled).

Please report a problem you are not sure about: the maintainer will decide whether it is a vulnerability.

## What is not a vulnerability

The trust model has limits that are **documented, not hidden**, in [docs/PACKAGE.md](docs/PACKAGE.md) ("Limits that are not hidden") and in
the README. They are not security guarantees, and a report that only restates them is not a vulnerability. In particular:

- An approval is an **unsigned JSON file** that binds a decision to the exact bytes of a PDF. The reviewer is **not authenticated**. Whoever
  can write to your workspace can forge an approval, a snapshot or the recorded origin of a PDF. Keep your workspace private and under Git.
- `READY_TO_SEND` means the process is consistent. It does not mean that you meet the job's requirements, that a sentence means what its
  facts say, or that an applicant tracking system will read the document.
- `pdflatex` is **not a sandbox**. ModularCV runs it without shell escape, with a fixed command line and a time limit, but its isolation is
  not proven.
- The privacy scan is **best-effort pattern matching**. A string it does not recognise is not a vulnerability (but a pattern that should
  be recognised is a welcome bug report, as long as you use synthetic data).
- Vulnerabilities in Python, Git, MiKTeX, TeX Live, `pip`, `setuptools`, GitHub or your operating system belong to their own projects.

If you can show that the tool **claims more than the documentation says it does**, that is welcome: report it.

## Supported versions

Security fixes are made on the `main` branch. The only version that exists is `0.2.0`, the version of the source tree; whether it has been
published as a release is shown on the Releases page of the GitHub repository. There are no older versions. Python 3.12, 3.13 and 3.14 are the supported interpreters (see [README.md](README.md)); no support is announced
for older ones.

## How reports are handled

This is a small project maintained by one person, so this policy describes intentions, not guarantees:

- Reports are read and assessed as time allows. **No response time, fix time or outcome is promised.**
- The maintainer may ask you for more information, and will say if a report is judged out of scope, with the reason.
- A confirmed vulnerability is fixed on `main` as soon as practical. A security advisory may be published after the fix, naming the
  affected commits. You are credited if you wish; say so in your report.
- Please allow reasonable time for a fix before you disclose the problem publicly, and tell the maintainer if you intend to.
- This project offers **no bug bounty**.

## Related documents

[CONTRIBUTING.md](CONTRIBUTING.md) (privacy rules for contributors), [docs/PACKAGE.md](docs/PACKAGE.md) (limits of the trust model),
[docs/WORKSPACE.md](docs/WORKSPACE.md) (keeping your data private).
