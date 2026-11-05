# Quick start and troubleshooting

Français : [QUICKSTART.fr.md](QUICKSTART.fr.md)

ModularCV builds a CV **only from facts you have confirmed**, and decides whether the result may be sent by **re-deriving the
evidence every time**. It never writes a sentence, never sends anything and never approves a CV in your place. This page takes
you from nothing to a package you can review, using the fictional example shipped in this repository.

## What you need

| Need | Detail |
|---|---|
| Python | **3.12, 3.13 or 3.14** (`Requires-Python: >=3.12,<3.15`; pip refuses other versions). Standard library only: no dependency to install. The whole test suite was run on 3.12 and 3.14 (Windows) and on 3.13 (Linux container); other combinations of version and platform were not tested. 3.9 and 3.10 were only regression environments of the source tree: no support is announced for them. |
| Git | Your workspace is a Git repository: a CV can only be built from sources committed in it. Git must know your name and e-mail (`git config user.name`, `user.email`) so you can commit. |
| `pdflatex` | **Optional.** MiKTeX (Windows) or TeX Live. Without it you still get the `.tex`; you cannot get a PDF, so a package stays `NEEDS_REVIEW` (never ready). `python -m modularcv latex check` tells you. MiKTeX on Windows is the only distribution exercised so far; **TeX Live and compilation on Linux are untested**. The template uses `fontenc`, `inputenc`, `lmodern`, `geometry` and `enumitem`; on Debian/Ubuntu these should come from `texlive-latex-base`, `texlive-latex-recommended`, `texlive-latex-extra` and `texlive-fonts-recommended` (expected, not verified: run `latex check`, then compile the example). |
| A private workspace | A separate private Git repository for your facts, CVs and packages. **Never put your data in this repository.** See [WORKSPACE.md](WORKSPACE.md). |

## Install

From a clone of this repository:

```bash
python -m pip install -e ".[dev]"      # pip downloads setuptools >= 77 into an isolated build environment: it needs a network (or use --no-build-isolation with setuptools >= 77 installed)
python -m modularcv --help
```

There is no `modularcv` command: always run `python -m modularcv ...`. Without installing, point Python at the clone instead:
`PYTHONPATH=/path/to/ModularCV python -m modularcv ...` (PowerShell: `$env:PYTHONPATH = "C:\path\to\ModularCV"`).

> Verified (Windows): `python -m build` produces a wheel and a source archive; each installs in a fresh virtual environment (Python 3.12
> and 3.14) and the commands above run from outside the clone. The source archive carries the tests, examples and documentation. Not
> verified: macOS, installation on Linux from a source archive, and PyPI (nothing is published).

## Try the fictional example (about five minutes)

```bash
cp -r examples/workspace ~/cv-demo && cd ~/cv-demo        # Windows: Copy-Item -Recurse examples\workspace $HOME\cv-demo
git init && git add -A && git commit -m "example sources"   # your sources must be committed
python -m modularcv provenance                              # prints the commit your CV will be tied to
python -m modularcv facts check facts.md                    # 1. the facts (status OK)
python -m modularcv profile check                           # 2. identity, families, availability
python -m modularcv content check                           # 3. the text of your CV, tied to the facts
python -m modularcv offer check offers/backend-intern.json  # 4. an offer (what it asks for)
python -m modularcv matrix --offer offers/backend-intern.json     # 5. DIRECT / ADJACENT / ABSENT / FORBIDDEN_TO_CLAIM per requirement
mkdir plans out
python -m modularcv plan --offer offers/backend-intern.json --out plans/job.json            # 6. which of your lines answer the offer
python -m modularcv render --plan plans/job.json --offer offers/backend-intern.json \
                           --out out/job.tex --pdf out/job.pdf                                # 7. LaTeX and, with pdflatex, the PDF
python -m modularcv package create --name job --plan plans/job.json --offer offers/backend-intern.json \
                           --tex out/job.tex --compile                                        # 8. the package (never an approval)
python -m modularcv package review --name job                                                # 9. what you must examine
```

Step 7 exits with `4` if `pdflatex` is absent: the `.tex` is still written (and the package of step 8 cannot be made). Step 8 compiles for
you: `--compile` runs `pdflatex` on the very bytes it has just verified and packages that output, so no file travels between the compilation
and the package. This is the only way to a package that can become `READY_TO_SEND`: a PDF handed over with `--pdf` is recorded as
`SUPPLIED_PROVENANCE_NOT_VERIFIED` and its package stays `NEEDS_REVIEW` (`PDF_ORIGIN_NOT_VERIFIED`) whatever you approve. Use `--paper letterpaper` on `render` for a US/Canadian
Letter page (the default is A4); `package create` recognises the paper by itself.

Then **open `applications/job/cv/resume.pdf` and read all of it**, and decide for yourself:

```bash
python -m modularcv package approve --name job --reviewer "Your Name"    # a person, in a real terminal: type the 12-character hash prefix
python -m modularcv package status --name job                            # exit 0 only when READY_TO_SEND
```

`approve` refuses to run from a script or a pipe (`APPROVAL_REQUIRES_A_PERSON`). Do not approve the fictional example in a real
workspace: it is a demonstration.

## What `READY_TO_SEND` means, and what it does not

It means the **process is consistent**: every source is committed and unchanged, the facts used are still `CONFIRMED`, the plan, the
assembly, the `.tex`, the PDF and the metadata agree, and an approval **you** recorded names that exact PDF. It does **not** mean you
meet the job's requirements (unsatisfied required requirements stay listed in `package status` and in the approval), that the PDF was
compiled from the `.tex` (that is not machine-verified: your reading of the PDF is what binds them), that an ATS will read it
well, or that the approval was made by you (it is an unsigned JSON file). Details: [PACKAGE.md](PACKAGE.md).

## Writing your own sources

| File | Rule of thumb |
|---|---|
| `facts.md` | One line per fact: `- [id] STATUS: text {technologies: ...; capabilities: ...; confirmed_on: ...}`. Only `CONFIRMED` facts can appear on a CV. Never invent a date or a number. Template: `examples/facts.v1.example.md`. |
| `profile.json` | Identity fields each marked `public` or `private` (only public ones are printed), your **families** (a family is a kind of CV with its own page target), policy, availability. Example: `examples/workspace/profile.json`. |
| `content/resume.json` | Your sentences, FR and/or EN. Every bullet, skill **and block heading** names the facts that back it (`supports`). A block with no bullet (for example your degree) is dropped from the CV unless it has `"protected": true`. `capabilities` and `technologies` must be identifiers of the taxonomy: see `examples/taxonomy.generic-v1.json` (identical to `builtin:generic-v1`). |
| `offers/*.json` | The posting as data. `requirements` are extracted from the description; add explicit ones if needed. |

With several families in your profile, name the one to use: `matrix --family software ...` and `plan --family software ...`.
Importing an old document: [IMPORT.md](IMPORT.md).

## Troubleshooting

| What you see | Meaning | What to do |
|---|---|---|
| `GIT_REPOSITORY_UNAVAILABLE` | The workspace is not a Git repository. | `git init`, add and commit your sources. |
| `SOURCE_NOT_AT_COMMIT` / `SOURCE_COMMIT_UNVERIFIABLE` | A source differs from the last commit, or the commit is unknown. | Commit your sources, then build the plan again. |
| `PLAN_FAMILY_REQUIRED` | Several families in the profile. | Add `--family NAME`. |
| `PLAN_CAPABILITY_UNKNOWN` | A fact or bullet uses a capability that is not in the taxonomy. | Use an identifier of the taxonomy (for example `data-analysis`, not `data`) or provide your own taxonomy. |
| A section (for example Education) is missing from the CV | Its block has no bullet and is not protected (`content check` warns `CONTENT_BLOCK_NEVER_PRINTED`). | Set `"protected": true` on the block. |
| `PDF_NO_PAGE` | The PDF given to `package create --pdf` has no page that can be read from its page tree. | Compile it again, or use `package create --compile`. |
| `METADATA_UNREADABLE` (`package review`, `package approve`) or `BLOCKED` with `CV_METADATA_INVALID` (`package status`) | The metadata file of the package was edited, emptied or damaged. | Packages are never edited: create a new one. |
| `PDF_ORIGIN_NOT_VERIFIED` | The PDF was handed over with `--pdf` (or the package predates the origin record): the tool cannot show it comes from this `.tex`. | Create the package again with `--compile`; an approval cannot replace this. |
| `ASSEMBLY_SOURCE_MISMATCH`, `ASSEMBLY_PLAN_FINGERPRINT` | A source changed after the plan, or the plan was edited. | Build a new plan (`plan --out` with a new file name). |
| `OUTPUT_EXISTS`, `PACKAGE_EXISTS` | Nothing is ever overwritten. | Choose a new file or package name. |
| `render` exits `4` | `pdflatex` not found. | Install MiKTeX or TeX Live, or continue without a PDF (the package will be `NEEDS_REVIEW` / `FINAL_DOCUMENT_MISSING`). |
| `render` exits `5` | The compilation failed. | Re-run with `--log out/cv.log` (the log can quote your CV: keep it private). |
| `APPROVAL_REQUIRES_A_PERSON` | `package approve` was run without an interactive terminal. | Run it yourself in a terminal. |
| `NEEDS_REVIEW` with `ARTIFACT_CHANGED_SINCE_PACKAGING`, `HUMAN_REVIEW_MISMATCH` | A file of the package or the PDF changed after packaging or approval. | Packages are never edited: create a new one and review it again. |
| `UNSATISFIED_REQUIRED` warning | A required requirement of the offer has no confirmed fact. | Nothing is hidden: decide whether to apply; never add a fact you cannot confirm. |
