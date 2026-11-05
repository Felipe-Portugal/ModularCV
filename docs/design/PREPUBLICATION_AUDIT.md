# Pre-publication audit (M8-A)

Audit of product, security, installation, documentation and portability, made before any publication decision. Nothing was pushed,
tagged, released or published; the repository visibility was not changed (it was read: private). Following `AGENTS.md` section 4,
each statement is **Observed** (a command or test was run), **Hypothesis** (deduced, not verified) or **Planned** (not done).

Baseline: `main` at `88756b9` (M7-B), version `0.2.0`, `origin/main` at `0a553e1`, 15 commits, one author identity (a no-reply
address), `legacy_import.py` outside the repository with SHA-256 `5c73e936...2504106` unchanged.

## 1. Environments actually used

| Environment | Used for |
|---|---|
| Windows 11, Python 3.9.13, MiKTeX 26.5 (pdfTeX 1.40.29) | the reference suite, real compilation, the end-to-end journey |
| WSL Ubuntu 22.04, Python 3.10.12, ext4, **no `pdflatex`** | the full suite (pytest 8.4.2 was imported read-only from the Windows `site-packages`: pure Python, nothing installed), parity of identities |
| Python 3.14 | only `pypdf`, already installed, as a second text extractor |
| MiKTeX's own `pdftotext`, `pdftoppm` (poppler) | text extraction and visual inspection of PDFs |

Not available, therefore **not tested**: TeX Live, macOS, any Python other than 3.9, 3.10 (and 3.14 for `pypdf` only), a build backend able to
read `pyproject.toml` (see section 3), a network.

## 2. Capabilities: implemented, documented, validated

All components are standard library only; Git is required for provenance, snapshots and packages; `pdflatex` is optional. "Tests" are
files of the 1294 tests collected after M8-A.

| Component | Commands that work today | Tests | Main limits |
|---|---|---|---|
| FactBase-v1 | `facts check`, `facts fingerprint` | `test_facts` 101, `test_facts_cli` 14, `test_canonical` 19 | The truth of the facts is the user's; nothing is inferred |
| Profile-v1 | `profile check`, `profile fingerprint` | `test_profile` 142 | Public headline is validated but never printed (no fact backs it) |
| Legacy import | `facts import` (`--dry-run`, mapping file) | `test_legacy` 153 | Proposes only; a mapping you write; `CONFIRMED` only if your mapping says so |
| ResumeContent-v1 | `content check`, `content fingerprint` | `test_content` 276 | Existence and status of facts, never meaning; FR/EN parity by id only |
| JobOffer-v1 | `offer check`, `offer fingerprint` | `test_offer` 66 | Keyword extraction via the taxonomy, no semantics |
| Taxonomy-v1 | `taxonomy check`, `taxonomy fingerprint` | `test_taxonomy` 41 | One generic software taxonomy (13 capabilities, 12 technologies) |
| Requirement matrix | `matrix` | in `test_plan` | `DIRECT`/`ADJACENT`/`ABSENT`/`FORBIDDEN_TO_CLAIM`; quality depends on the tags you give |
| Deterministic plan | `plan` | `test_plan` 58 | Greedy ranking, `PAGE_TARGET_NOT_ENFORCED` |
| Assembly | `assemble` | `test_render` 69 | `soften` directives are never applied; headline not printed |
| LaTeX and PDF | `render`, `latex check`, `--paper` | `test_render` | One template `generic-v1`; optional `pdflatex`; MiKTeX only verified |
| Package | `package create` (`--pdf` or `--compile`), `status`, `review` | `test_package` 114 | See sections 5 to 7 |
| Human review | `package approve` (interactive terminal only) | `test_package` | Unsigned JSON file |
| Readiness | `package status`, `check-packages`, `snapshot verify`, `provenance` | `test_readiness` 106, `test_snapshot` 93, `test_provenance` 22 | Proves the process, not the candidate |
| Privacy scan | `privacy --root . [--deny-file F] [--history]` | `test_privacy` 8 | Patterns and your own terms; cannot find what it is not told |
| Skill `cv-panel` | a Claude Code skill (no command) | `test_skill` 5 (structure only) | Review only; depends on a model, not exercised here |

Observed: every command above ran during the audit on synthetic data, except `facts import` (covered by its tests only) and the skill
(structure tests only). Not announced because not implemented: cover letters, other templates, a web or graphical interface, a
`modularcv` console script, a `.docx` output, any sending mechanism, a signature.

## 3. Installation from a clean source

Observed. `git archive HEAD` gave a tree of 90 tracked files, no untracked file, no quarantined file. `python -m pip install` of that
tree **could not be validated**:

- In a fresh Python 3.9 venv (pip 22.0.4, setuptools 58.1.0, no `wheel`): with build isolation the build requirement `setuptools>=61`
  could not be fetched (no network); without isolation, `setuptools` 58 does not read the `[project]` table (the project is named
  `UNKNOWN`) and fails on `bdist_wheel`. Python 3.14 has neither `setuptools` nor `wheel`; Python 3.8 and WSL have setuptools 56 and 59.6.
  No setuptools >= 61 and no `wheel` exist on this machine, and nothing was installed to get around that.
- What could be checked, and is **not equivalent to an installation**: `build_py` with a stand-in `setup()` lists exactly the 27 files
  of `modularcv/*.py` (no `_quarantine`, no test, no example); the code reads no data file from the package (no `__file__`, no
  `importlib.resources`; the generic taxonomy is built in), so the package needs no resource; the CLI ran from that build folder, from an
  unrelated directory, with the right exit codes (`latex check`, `taxonomy check`, `provenance` outside Git exits 2).
- Hypothesis, to verify online in M8-B: `pip install .` and `python -m build` with a current setuptools. Two points to check there:
  `license = {text = "MIT"}` (a TOML table, deprecated in recent setuptools in favour of an SPDX string) and `requires = ["setuptools>=61"]`
  (an editable install needs >= 64).
- Observed: without `pdflatex` on `PATH`, `latex check` exits 1, `render --pdf` exits 4 with the `.tex` written, `package create` without a PDF
  gives `NEEDS_REVIEW` (`FINAL_DOCUMENT_MISSING`) and `package approve` refuses. With MiKTeX: 1-page PDFs, real compilation.

## 4. End-to-end journey (new user, fictional data)

Observed, on a workspace written from scratch from the documentation (a new fictional person, two families, English and French content,
accents, `& % #`, two offers) and on the shipped `examples/workspace`: Git workspace, facts, profile, content, offer, matrix, plan,
assembly, `.tex`, PDF, package, inspection of the warnings and of the unsatisfied required requirements, `package review`, a **synthetic**
approval (library call, reviewer named "SYNTHETIC TEST ONLY", temporary workspace; no real approval was ever recorded), `READY_TO_SEND`,
then one appended byte in the PDF: `NEEDS_REVIEW` (`ARTIFACT_CHANGED_SINCE_PACKAGING`, `HUMAN_REVIEW_MISMATCH`), restored: `READY_TO_SEND`.
A 40-bullet file with a zero minimum gain gave a 2-page PDF recorded as `TARGET_EXCEEDED`. A source not committed was refused
(`SOURCE_NOT_AT_COMMIT`).

Difficulties met by a new user, and what was done:

| Difficulty | Action |
|---|---|
| No install, prerequisite or troubleshooting page | `docs/QUICKSTART.md` and `QUICKSTART.fr.md` added; every command in them was executed |
| A multi-family profile needs `--family`; the README never says so | documented (QUICKSTART, troubleshooting) |
| `PLAN_CAPABILITY_UNKNOWN` does not list the valid identifiers | documented where they are (`examples/taxonomy.generic-v1.json` is `builtin:generic-v1`, same fingerprint) |
| A block with no bullet (typically the degree) silently vanishes from the CV unless `protected: true`; never explained for a beginner | `CONTENT.md`, QUICKSTART |
| Default paper A4 in a product aimed at Canada | documented (`--paper letterpaper`); the default itself is a maintainer decision |
| `provenance` prints an absolute path in its error (local output) | noted, not changed |
| The matrix tagged "REST APIs" as `ABSENT` although a bullet says REST: tags are what the matrix reads | documented as how the matrix works; the unsatisfied requirement stays visible |
| `package approve` prints the whole summary before the prompt | acceptable, left |

## 5. Trust boundaries

| Boundary | Controlled by the software | Not controlled (relies on the person) |
|---|---|---|
| Source -> FactBase | strict grammar, status per fact; an import only proposes | that a fact is true |
| FactBase -> content | each bullet, skill and heading names facts that must exist and be `CONFIRMED` | that a sentence means what its facts say; FR/EN equivalence |
| Content + offer -> plan | deterministic; pool limited to proven lines; a prohibition beats relevance; unsatisfied required stays explicit | the quality of the capability tags |
| Plan -> assembly | five layers re-derive the plan from the current sources: an edited plan with a recomputed hash is refused (`PLAN_NOT_REPRODUCIBLE`) | - |
| Assembly -> LaTeX | one escaping table, closed character set, and `package create` and `chain.verify` require the `.tex` to equal the rendering of the assembly | - |
| **LaTeX -> PDF** | with `--pdf`: only that the file looks like a PDF. With `--compile`: the compiler's own output for the verified bytes | that a PDF supplied by hand comes from that `.tex` |
| PDF -> package | exact-byte hash in the snapshot and the metadata; page count read from the PDF | - |
| Package -> review | the review names the exact PDF hash and what the reviewer was shown (plan, assembly, `.tex`, warnings, page verdict) | who wrote the review; that the text is faithful |
| Review -> READY | recomputed on every call; any later change loses it | - |

## 6. The PDF / LaTeX gap

The risk: a PDF unrelated to the verified `.tex` enters before the review, with every hash and metadata recomputed.

Observed, on the pre-audit code:

- `package create --pdf` accepted a PDF compiled from **another** CV (the French one for the English `.tex`) and a 3-line file
  `%PDF-1.4 ... %%EOF` with no page (`pdf_pages: null`, `page_verdict: NOT_COMPILED`). Both gave a valid `NEEDS_REVIEW` package.
- Between `render --pdf` and `package create --pdf` a file travels: nothing links the compilation to the package.
- Any change to the PDF **after** packaging is detected (snapshot, metadata hash, approval mismatch), as is a substituted plan,
  assembly or `.tex` even with recomputed hashes (the chain is re-derived from the sources). A PDF changed after the approval loses
  `READY_TO_SEND`.
- A person who can write to the workspace can create a package with their own PDF through the tool itself (`package create --pdf`) or
  rebuild the snapshot, metadata and `package.json` by hand, and write the review file. Only hashes are involved, no secret.
  The one step bound to a person is the approval, and a file is not authenticated (section 7).
- On this machine, with `SOURCE_DATE_EPOCH=0` as set by the compiler wrapper, three compilations and the `render` output were
  **byte-identical**, and the French PDF differed from the English recompilation. Observed once, on one engine: evidence, not a contract.

Corrected (minimal, testable, additive): `package create --compile` (`package.create(..., compile_timeout=)`) compiles **after** the `.tex`
is verified against the assembly of the plan and **before** anything is written, then packages that output; it is exclusive with `--pdf`,
leaves nothing on failure, exits 4 or 5 like `render`. Tests: real MiKTeX compilation (skipped without `pdflatex`), compiler absent,
compilation failing, an unverified `.tex` never reaching the compiler, both sources refused.

What this does not give: once the files sit in the workspace, nothing proves the PDF is the compilation of the `.tex`. No
cryptographic equivalence is claimed. What rests only on a person's reading: that the PDF read is the PDF packaged (the typed hash
prefix), that its content is what the `.tex` says, and that it is faithful to the facts.

Not done, proposed for M8-A-R1 (**Planned**): (a) an advisory reproduction check in `package review`: recompile when `pdflatex` is present;
identical bytes is positive evidence, different bytes is "inconclusive", never a failure; (b) require a readable page tree
(`pdf_pages` not null) before an approval can be recorded (changes a documented contract: decision needed; fail-closed but
unverified on TeX Live); (c) extracting text from the PDF and comparing it with the assembly (rejected for now: fragile with a
stdlib-only parser and defeated by invisible text).

## 7. The human approval

The file is unsigned JSON. Distinguish:

| Property | Today |
|---|---|
| Integrity of the document | none: no checksum or signature inside it |
| Binding to a review | strong: it names `tailored_cv_id`, the exact PDF hash, and the plan, assembly, `.tex`, warnings and page verdict shown; any change voids it |
| Authenticity of the reviewer | none: `reviewer` is free text |
| Resistance to an attacker who can write to the workspace | none: they can write the file; the typed prefix only stops an honest script |

Options and trade-offs: **(0)** keep it, documented (current). **(1)** a checksum or HMAC inside the file: stops accidents only, the key
would sit beside the data. **(2)** have the review committed in the workspace Git repository and report, as information, whether that
commit is signed with the user's own Git signing key (`git verify-commit`): no new dependency, real authenticity if the user already
signs, history as audit trail; readiness would not depend on it. **(3)** a detached signature (`ssh-keygen -Y`, minisign, GPG) verified
against a public key in the profile: strongest, but key management and an external tool, disproportionate for one person's local tool.

Recommendation: keep (0) for `0.2.0` and say so (done in `PACKAGE.md`, `review`), plan (2) as an optional, informational line, and
revisit (3) only if several people share a workspace. No signature system was added.

## 8. The compiler

Observed in `pdf.py`: fixed command line, `-no-shell-escape`, `-halt-on-error`, `--disable-installer` on MiKTeX, fresh temporary directory
(no leftover after the runs), no standard input, a time limit, `TEX*` variables removed, `shell_escape=f`, `openout_any=p`,
`SOURCE_DATE_EPOCH=0`, the log kept out of diagnostics (it can quote the CV; `--log` writes it).
Not a sandbox, and not claimed to be: the process inherits the rest of the environment; `openin_any` is the default; the network and the
system are not restricted; output is read fully into memory before being truncated (bounded by the time limit); the stopping of a helper
process on timeout under MiKTeX was **not verified**. What keeps the compilation safe is the input (fixed template, escaping, closed
character set), tested with a hostile-document test. Planned for R1: an allow-list environment, `openin_any=p`, an output size bound.

## 9. Portability

Observed: **the full suite on Linux (Python 3.10.12, ext4): 1285 passed, 9 skipped, 0 failed** (the 9: 7 need `pdflatex`, 2 are
Windows-only or case-insensitive-filesystem cases); on Windows (Python 3.9.13, MiKTeX): **1293 passed, 1 skipped** (a symbolic-link test
that needs privileges). The 1294 collected tests are the 1286 of M7-B plus 8 added here. Identities were
compared on a Windows CRLF checkout and a Linux LF clone, with accents and French text: plan, assembly, `.tex` hashes and `tailored_cv_id`
**identical**. Text is normalised before hashing; PDFs are hashed as bytes.

The Linux run found a **real defect**, never seen on Windows because its test was skipped there: `Path.resolve()` follows a dangling
symbolic link on POSIX, so `facts import --out alias.md`, `plan|matrix|assemble|render --out`, and `package create` could write a new file
through a dangling link pointing inside the workspace (never over an existing file, never outside the workspace). Corrected: the path as
written is checked too, and a package folder may not be or pass through a link; 4 tests fail on the old code and pass on the new, on Linux.

Not tested: TeX Live, any Linux compilation, macOS, Python 3.11 to 3.14 for the suite, case-insensitive macOS file systems beyond the
existing tests, a non-ASCII user name in the workspace path, paths with spaces in the end-to-end journey.

## 10. Readability and ATS

Observed with poppler: one column, correct reading order, accents, bullets, spacing, section titles, fonts embedded with a Unicode map,
English and French, one and two pages, `& % #` printed correctly; the two-page CV is recorded as `TARGET_EXCEEDED`; page images
were inspected (clean, plain, legible; a short CV leaves most of the page empty). With `pypdf`, words around bold text and separators
were merged (`accèsRESTen`): a property of that extractor (pdfTeX stores the space as a position); `\pdfinterwordspaceon` fixed it in a
test with MiKTeX. Not adopted: it would change `generic-v1` bytes, hence every hash; a guarded `\ifdefined` form or a `generic-v2` is an R1
decision. Other limits of `generic-v1`: A4 default, French labels without the space before a colon, no hyperlink, no right-aligned dates,
Latin Modern fonts, pdfLaTeX only. No ATS was tested: nothing is claimed about any ATS.

## 11. Documentation

Audited: README and README.fr, WORKSPACE, CONTENT, PLAN, RENDER, PACKAGE, IMPORT, ARCHITECTURE, GOVERNANCE. Fixed: stale "declared state"
wording (README, README.fr, GOVERNANCE), an ARCHITECTURE that predated everything after M3, a README status claiming the generation engine
was absent, README.fr without the package commands, no install/quick start/troubleshooting (new), `protected` unexplained, `--family`
unexplained, `--compile` and the compiler limits. Remaining: the guides in `docs/` other than the quick start exist in English only (the
design documents' French translation is planned before publication, `AGENTS.md` section 7).

## 12. Privacy, licence, distribution

Observed: the scanner reports 0 finding on the tree and on the history (with an outside deny list); all 15 commits carry one no-reply
identity; no tracked PDF, log, archive or binary; `.gitignore` excludes workspace folders and generated documents; the licence is MIT
("ModularCV contributors"); `cv-panel` carries the attribution and the MIT notice of its upstream author. Inspected by hand beyond the
scanner: `LICENSE`, `NOTICE.md`, `SKILL.md`, `normes-ets.md`, the examples (fictional, `example.com`/`example.org`), the templates, the
schema. Points for a human decision: `normes-ets.md` summarises two documents of a school's co-op service (the notice says examples are not
reproduced; the right to redistribute a summary is not established); the maintainer's account name appears in the remote URL of the local
Git configuration only (not tracked), and a published repository would carry it in its address. The Git history is small (110 KiB packed)
and was scanned; a published history would expose the commit messages and the 15 commits' content.

## 13. Defects found and corrected in this audit

1. Dangling symbolic link written through on POSIX (above). Corrected, 4 tests that fail before and pass after on Linux.
2. A PDF of any origin accepted without a link to the `.tex`: gap documented, `--compile` added (5 tests), rest proposed. (Tests that
   fail before and pass after: the dangling-link ones, on Linux. The `--compile` tests cover new behaviour.)
3. Documentation gaps and stale statements (section 11).

Tests added: 8 (`test_package.py`: 2 dangling-link cases and 5 for `--compile`; `test_render.py`: 1 dangling-link case).

## 14. Risks that block a public release (to settle before M8-B)

Status after M8-A-R1: see section 16 (risk 1 verified on Windows; risks 2 to 5 remain, risk 3 characterised).

1. Installation from a distribution is **unverified** (section 3): build and install must be tried online, with a current setuptools.
2. TeX Live and Linux compilation are **unverified**: the supported-platform statement must say so or this must be tested.
3. The right to distribute `normes-ets.md` is not established.
4. Python 3.9 reached its end of life: decide the supported versions (`requires-python`), and test the newer ones.
5. The unsigned approval and the PDF/LaTeX gap are documented limits, not defects; a publication must keep saying so.

## 15. Proposed M8-A-R1 and decisions for the maintainer

Proposals: advisory PDF reproduction check; `generic-v2` (guarded `\pdfinterwordspaceon`, French colon, paper default); compiler
environment allow-list and `openin_any=p`; optional informational Git-signature line for approvals; online build and install check
(wheel, sdist, `pip install`, console script decision); Python version matrix; French translation of the user guides; an `examples`
walkthrough script.

Decisions: default paper (A4 or Letter); whether to require a readable page count for approval; approval authenticity (section 7);
supported Python versions; whether `normes-ets.md` stays; whether the published repository may carry the current history and
the account name in its address; the fate of the quarantined file (open decision 7).

## 16. M8-A-R1: stabilisation and verification of the blockers

M8-A-R1 resolves or characterises the blockers of section 14 without a new major feature. Nothing was pushed, tagged, released or published;
the version stays `0.2.0`. Baseline: `main` at `72543a8`, `origin/main` at `0a553e1`. Same convention: Observed / Hypothesis / Planned.

### 16.1 Installation from a distribution (blocker 1 of section 14)

Observed, Windows 11, with network access, PyPI as the only source, **only in temporary virtual environments** (the global Python was not
modified): `python -m build` 1.6.1 (with `pyproject_hooks` 1.3.3, `packaging` 26.3, `colorama` 0.4.6, pip 26.2.1) in a Python 3.14.7
environment; the isolated build environment of `build` fetched `setuptools` 84.2.1 (the wheel records `Generator: setuptools (84.2.1)`).
The runtime has no dependency and none was added.

- The wheel and the sdist build from the files tracked by Git (`git archive`).
- **Wheel**: 27 modules of `modularcv/`, `LICENSE`, `METADATA`, `WHEEL`, `RECORD`, `top_level.txt`; nothing else (no test, example, template,
  schema, skill, PDF, log, quarantine file). The engine reads no data file of the package (templates and taxonomy are in the code).
  There is no console script: `python -m modularcv` is the only entry point (documented since M8-A).
- **Metadata**: `Name: modularcv`, `Version: 0.2.0`, `Requires-Python: >=3.9`, no `Requires-Dist` outside the `dev` extra (`pytest>=7`).
- Wheel installed in a fresh Python 3.14.7 environment, source archive installed in a fresh Python 3.9.13 environment (pip 22.0.4, whose
  isolated build downloaded a setuptools compatible with 3.9); editable installation (`pip install -e .`) also works on 3.14. In each, from a
  folder outside the clone and with `python -I`, `import modularcv` resolves to `site-packages`, and the whole quick-start sequence
  (provenance, facts, profile, content, offer, matrix, plan, render with a real PDF, package create with `--pdf` and with `--compile`,
  review, status, an A4 and a Letter package) gave the exit codes and identities of the source tree.
- Python 3.8 is refused by pip (`requires a different Python: 3.8.10 not in '>=3.9'`).

Defects found and fixed (packaging only):

1. `license = {text = "MIT"}` is deprecated: setuptools warned that the build would break after 2027-02-18. Now `license = "MIT"` and
   `license-files = ["LICENSE"]` with `setuptools>=77` (the metadata become `License-Expression: MIT`; the warning is gone).
2. The source archive carried `tests/` but none of the files the tests read (`examples/`, `schemas/`, `templates/`, `skills/`, `docs/`):
   10 test modules failed at collection. A `MANIFEST.in` now adds those folders, so the suite runs from the unpacked source archive
   (1304 passed there on Python 3.9, see 16.3), **except** `skills/cv-panel/normes-ets.md`, excluded on purpose (16.5); the one test that reads it
   is skipped when the file is absent.

Not verified: installation on Linux or macOS, any index other than PyPI, a build without network (`--no-build-isolation` with setuptools >= 77).

### 16.2 PDF supplied from outside, `--compile` and the approval (P0)

Scenarios run on the shipped synthetic workspace, with and without a **synthetic** approval (a library call in a temporary folder, reviewer
"SYNTHETIC TEST ONLY"; no real approval was simulated):

| Scenario | Before R1 | After R1 |
|---|---|---|
| `--pdf` with the PDF of another CV | accepted; `READY_TO_SEND` after approval | **unchanged**: accepted, declared `SUPPLIED_PROVENANCE_NOT_VERIFIED` |
| `--pdf` with a PDF of another language | same | **unchanged**, same declaration |
| `--pdf` with only the PDF markers (`%PDF-` ... `%%EOF`), no page | accepted, `pages: null`, `READY_TO_SEND` after approval | **refused** `PDF_NO_PAGE`, nothing written; a hand-forged package with consistent hashes is `BLOCKED` (`CHAIN_PDF_NO_PAGE`) |
| `--pdf` with the right PDF modified (bytes appended) before packaging | accepted | **unchanged** (it is a different, supplied document) |
| PDF modified after the approval | `NEEDS_REVIEW` (`ARTIFACT_CHANGED_SINCE_PACKAGING`, `HUMAN_REVIEW_MISMATCH`); restoring the bytes restores `READY_TO_SEND` | unchanged |
| `--compile` | PDF made by the tool from the verified `.tex`; same readiness path | same, declared `COMPILED_FROM_VERIFIED_TEX` |

Decisions applied: `package create --compile` is the recommended path; a supplied PDF is never given the guarantees of the integrated
compilation (the output says so, the review's limits say so, `PACKAGE.md` says so); a file without a recognised page cannot be packaged or
approved; the approval mechanism (`CVQualityReview-v2`, unsigned) is unchanged. The origin is **not** stored in the package (it would change the
metadata or package contract): it is reported when the package is created and in the permanent limits of every review. Limits of the page reader
(`pdf.count_pages`): it reads the page tree written in the file with the standard library; a counted page is not necessarily legible, and a PDF
whose page tree it cannot read is refused (workaround: `--compile`). Tests: 6 added in `test_package.py` (refusal and no residue, forged
consistent package, origin declaration in the output and in the review limits, compiled output without a readable page, stand-in compiler); a
mutation run (page checks disabled) is caught by 4 of them.

### 16.3 Python versions (P1)

Proposed public support: 3.12, 3.13, 3.14, 3.15. **Available and tested**: 3.9.13 (Windows), 3.10.12 (Linux, WSL), 3.14.7 (Windows); 3.8.10 only
to check that pip refuses it. **Not available**: 3.12, 3.13, 3.15; no interpreter was installed (not authorised).

| Python | Platform | Full suite | Wheel / sdist | Identities |
|---|---|---|---|---|
| 3.9.13 | Windows | 1304 passed, 1 skipped | sdist install, sdist tests: 1304 passed, 1 skipped | reference |
| 3.10.12 | Linux (WSL), no `pdflatex` | see `PROJECT_STATE.md` (7 tests need `pdflatex`) | not built there | identical |
| 3.14.7 | Windows | 1304 passed, 1 skipped | wheel and editable install | identical |

Identities compared (value-free, from the shipped example, EN and FR): fact base, profile and content fingerprints, `plan_sha256`, SHA-256 of the
`.tex`: identical on 3.9, 3.10 (Linux) and 3.14.

Defect found by 3.14 and fixed: `json` goes much deeper than on 3.9 before failing, so a deeply nested value inside an `x-` field made
`canonical_json` overflow the stack and the command crash with a traceback (3.9 refused it earlier, by luck of the limit). All JSON readers now go
through `canonical.loads`, which refuses more than 100 nested levels with the same error on every interpreter (a document is a few levels
deep). Two tests of M8-A (a 5000-level array) also failed on 3.14 for this reason and now pass. Tests added: 4.

**Recommendation** (not applied; metadata unchanged): do not declare 3.12, 3.13 and 3.15 supported until they are run; the evidence supports
"3.9 to 3.14 as tested, the newest tested being 3.14". A restricted public statement could be `>=3.9` (as declared) with 3.14 and the oldest
declared version tested, or `>=3.12` once 3.12 and 3.13 are tested. The choice, and the end-of-life policy for 3.9, is the maintainer's.

### 16.4 Compilation on Linux (P1)

Observed: the Linux test machine (WSL Ubuntu 22.04) has no `pdflatex` and no TeX Live package; none was installed. Therefore **no PDF compilation,
page count, text extraction or `package create --compile` was tested on Linux**, and PDF compatibility on Linux is not claimed. Reproducible
commands for whoever has a Linux machine with TeX Live (expected packages on Debian/Ubuntu, not verified): `sudo apt install
texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended`, then `python -m modularcv latex check`, then the quick
start of `docs/QUICKSTART.md` with `package create --compile`, then `pdftotext -layout` on the result. Hypothesis: the page reader may need
attention with TeX Live's default object-stream compression (it reads Flate-compressed object streams, but this was only exercised with MiKTeX's output).

### 16.5 `skills/cv-panel/normes-ets.md` (P0 for publication)

Observed, without extrapolation:

- **Provenance**: a French summary (4.7 KB) of two documents of the co-operative education service of a school ("PRE811 - CV, Gabarit et modeles"
  and "Redaction d'une lettre de presentation"), written for the `cv-panel` skill. The file says it summarises them; it names no author, licence or permission.
- **Licence / authorisation references**: none in the repository. `skills/cv-panel/NOTICE.md` covers only the upstream `hiring-panel-skill` (MIT,
  an unrelated source).
- **Tracked by Git**: yes, `skills/cv-panel/normes-ets.md`.
- **History**: added by the initial commit `0a553e1` and never modified since; present in every commit of the history, **including `origin/main`** (the
  private remote). Any publication that keeps that history publishes the file.
- **Distributions**: not in the wheel (only the package). The first R1 `MANIFEST.in` would have put it in the source archive; it is now excluded
  (`exclude skills/cv-panel/normes-ets.md`) and checked absent from the built archive.
- **Needed to run the engine**: no. No module of `modularcv/` reads it; only `SKILL.md` (the review skill, a separate prompt) refers to it and one test reads it
  (skipped when absent).

Nothing was deleted, moved or rewritten, and the history is untouched. **Blocking for publication until a decision is taken.** Options, each
needing a separate human decision: (a) obtain the school's authorisation to redistribute the summary (or its written statement that the summary is
free to share) and keep the file; (b) exclude the file and publish a **cleaned** history (rewriting history, to be decided and executed separately);
(c) publish from a clean source **without the private history** (a new repository from a single clean commit, the file left out or replaced by a
neutral checklist written from the user's own knowledge). In all cases `SKILL.md` must stop depending on the file or say that the user supplies it.

### 16.6 Ergonomics

- The block without a bullet and without `protected` (the degree) used to vanish silently. `content check` now warns `CONTENT_BLOCK_NEVER_PRINTED`
  (path of the block); the selection algorithm, the plan and the fingerprints are unchanged. A block whose bullets are all `never_publish` is a
  deliberate reminder and is not flagged. 1 test; documented in `CONTENT.md`, `CONTRACTS.md` 3.2 and the quick starts.
- A4 stays the default. Letter checked with a real compilation: PDF page box 612 x 792 pt (A4: 595.3 x 841.9 pt); `package create` recognises
  the paper from the `.tex` and records it in the metadata; documented in `RENDER.md`.
- `generic-v2` was **not** created. The unprinted `headline` is unchanged.

### 16.7 Remaining blockers and decisions

Blockers for a publication: (1) the right to distribute `normes-ets.md`, and the fact that it is in the history (16.5); (2) the supported-Python statement
(only 3.9, 3.10 and 3.14 were run; 3.12, 3.13 and 3.15 were not available); (3) compilation on Linux and TeX Live are unverified; (4) installation was verified
on Windows only and never through an index; (5) the documented limits (unsigned approval, a supplied PDF is not proven to come from the `.tex`).
Decisions for the maintainer, in addition to section 15: the strategy for `normes-ets.md` and the history (16.5); the supported Python range
and whether to authorise installing interpreters (or a CI) to test 3.12, 3.13 and 3.15; whether to store the PDF origin in the package (a contract change);
whether to authorise a TeX Live installation (WSL or a container) for the Linux compilation test.

## 17. M8-A-R2: final pre-publication checks

Nothing was pushed, merged, tagged, released or published; no remote or GitHub repository was created; the version stays `0.2.0`. Baseline:
`main` at `6af7675`, `origin/main` at `0a553e1`, 1304 passed / 1 skipped on Python 3.9 as expected.

### 17.1 Origin of the PDF: policy and tests (P0)

Rule now enforced: **only a PDF made by `package create --compile` from the verified `.tex` can make a package `READY_TO_SEND`.**

- The metadata of version 3 gain one **optional, additive** field, `pdf_origin`: `COMPILED_FROM_VERIFIED_TEX` or `SUPPLIED_PROVENANCE_NOT_VERIFIED`
  (only with a PDF). Absent means "not recorded". It is covered by the snapshot like the rest of the metadata.
- Readiness: a version 3 package with a PDF whose origin is not the compiled one is `NEEDS_REVIEW` with the reason `PDF_ORIGIN_NOT_VERIFIED`
  (codes `PDF_ORIGIN_SUPPLIED`, `PDF_ORIGIN_NOT_RECORDED`), **whatever the review file says**. `package approve` refuses such a package
  (`PACKAGE_NOT_REVIEWABLE`), and a review file written by hand for it leaves the verdict unchanged: an approval binds a decision to exact bytes, it
  cannot make the origin of those bytes known.
- Pages: no PDF without a readable page can be packaged (`PDF_NO_PAGE`) or be ready (`CHAIN_PDF_NO_PAGE`), unchanged from R1. A PDF modified after
  approval voids it (`HUMAN_REVIEW_MISMATCH`), unchanged and re-tested on the compiled path.
- Historical formats: metadata versions 1 and 2 and their rules are untouched. A version 3 package made before this field (R1 and earlier, never
  published) has no origin and is therefore conservatively `NEEDS_REVIEW`.
- **Schema evaluation**: an additive optional field in version 3, no version bump (version 3 was never published), no migration; the existing
  validator refused unknown fields, so the field is declared in `metadata.V3_OPTIONAL`. Documented in `CONTRACTS.md` 4.2 and `PACKAGE.md`.
- **Not a signature.** The field is a recorded statement. Whoever can write the workspace can rewrite it and rebuild the snapshot, and then
  claim a compiled origin for any PDF. Editing it without rebuilding the snapshot is detected (tested). This limit is documented.
- Tests added (7, plus fixtures moved to the compiled path): origin recorded and compiled package ready; supplied package never ready, approval
  refused; hand-written approval does not help; unrecorded origin conservative; edited origin detected, invalid value blocked; origin without a PDF
  invalid; modification after approval on the compiled path. **Mutations** (throw-away harness, scratch copies): disabling the readiness check,
  recording a supplied PDF as compiled, never recording the origin, not validating the value, allowing approval of an unknown origin: each is caught
  (3, 3, 32, 1 and 1 failing tests).

### 17.2 Public snapshot (P0)

Procedure and decisions: [PUBLIC_SNAPSHOT.md](PUBLIC_SNAPSHOT.md). Simulation, in a temporary folder, from the tracked files of `fa4142b`:

- The file `normes-ets.md` removed; a new repository with **one** commit, **no remote**; 93 tracked files (94 minus the excluded one).
- Observed: the file is absent from the tree and from every object of the new history; its distinctive content is absent; no quarantine file,
  PDF, log, cache or backup; one identity (the no-reply address); no broken relative link in any Markdown file; `LICENSE` and the attribution of
  `cv-panel` (`NOTICE.md`) kept.
- `SKILL.md` no longer depends on the file (without it the skill must not quote school norms from memory); `MANIFEST.in` excludes it; the one
  test that reads it is skipped when it is absent.
- Privacy scan of the snapshot tree and history with the outside deny list: 0 finding; the built archives: 0 finding each.
- From the snapshot: wheel and sdist build (27 modules in the wheel; the sdist holds tests, examples, docs, templates, schemas and skills but not the
  excluded file); the wheel installs on Python 3.14, 3.12 and (offline, Linux) 3.13; the sdist on 3.9 and 3.12; the quick start runs from outside the
  folder with the installed package, with `--compile` (origin `COMPILED_FROM_VERIFIED_TEX` in both the A4 and the Letter package).
- Not done, by instruction: rewriting the private history, deleting the file from the private repository, creating a repository, configuring a remote.
  Some documents still *name* the file to explain the exclusion (they reproduce none of its content).

### 17.3 Python matrix actually run

Interpreters found already installed (no interpreter was installed): 3.8.10, 3.9.13, 3.10.21 and 3.12.14 (Windows; the last two managed by `uv`),
3.14.7 (Windows), 3.10.12 (WSL Ubuntu 22.04) and 3.13.18 (the local `python:3.13` Docker image, run **offline**, `--network none`). **3.15 is not
available** and not tested; 3.11 is not available.

| Python | Platform | Full suite (snapshot) | Installation | Identities |
|---|---|---|---|---|
| 3.9.13 (regression) | Windows | 1310 passed, 2 skipped (private repository: 1311 / 1) | sdist | reference |
| 3.10.12 (regression) | Linux, WSL | 1302 passed, 10 skipped (private: 1303 / 9) | n/a | identical |
| 3.12.14 | Windows | 1310 passed, 2 skipped | wheel and sdist; quick start | identical |
| 3.13.18 | Linux, container, offline | 1302 passed, 10 skipped | wheel (offline) | identical |
| 3.14.7 | Windows | 1310 passed, 2 skipped | wheel; quick start | identical |

"Identities": fact base, profile and content fingerprints, `plan_sha256` and `.tex` SHA-256 of the shipped example in French and English, compared
across all interpreters (one digest of the lines: identical everywhere). Skips: the symbolic-link test on Windows, the excluded-file test, and on Linux
the tests that need `pdflatex` (see 17.4).

The proposed range **3.12, 3.13, 3.14** is therefore *supported by tests* on those three versions (full suite, installation, identities), with the
limits that 3.13 was exercised on Linux only and 3.12 and 3.14 on Windows only, and no compilation was run on Linux. `Requires-Python` was **not
changed** (it still says `>=3.9`): changing it, and the end-of-life policy for 3.9 to 3.11, needs a governance decision.

### 17.4 Linux and TeX Live

Environments checked: WSL Ubuntu 22.04, the Docker Desktop distribution and the local images (`ubuntu:22.04`, `ubuntu:24.04`, `debian`, `python:*`):
none has `pdflatex` or a TeX Live package. **Not installed (no authorisation).** Result: **not tested** (no compilation, page count, extraction,
`--compile`, or substitution test with a real PDF on Linux). A stand-in PDF was not used in place of a compilation. Reproducible procedure, to run
once the installation of TeX Live in a throw-away container is authorised (network needed; paths are examples):

```bash
docker run --rm -v <snapshot>:/src:ro ubuntu:24.04 bash -c '
  apt-get update && apt-get install -y --no-install-recommends git python3 python3-venv poppler-utils \
      texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended &&
  cp -r /src /work && cd /work && git config --global --add safe.directory "*" &&
  python3 -m venv /v && /v/bin/pip install . pytest &&
  /v/bin/python -m modularcv latex check && /v/bin/python -m pytest -q -rs'
# then the quick start of docs/QUICKSTART.md with `package create --compile`, `pdftotext -layout` on both PDFs (FR and EN), and a one-byte change of the
# PDF to see READY_TO_SEND lost; compare plan_sha256 and the .tex SHA-256 with the Windows values.
```

### 17.5 Remaining blockers and exact decisions

Technical blockers (need work or means, not a decision): compilation on Linux/TeX Live not run (needs the installation in 17.4); Python 3.15 absent.
Missing authorisations: installing TeX Live in a container (network); installing Python 3.11/3.15; any publication step.
Human decisions: (1) route for the public repository: single-commit snapshot (17.2), rewritten history, or authorisation for the school summary;
(2) which working-tree documents are public; (3) public identity, repository name, visibility; (4) supported Python range and `Requires-Python`
(and what to do with 3.9 to 3.11); (5) whether to keep the weaker `--pdf` path at all or to reject it (today it is accepted and never ready);
(6) the earlier open decisions (default paper, approval authenticity, quarantined file).

## 18. M8-B: release candidate and final audit before publication

Nothing was pushed, merged, tagged, released or published; no remote or GitHub repository was created; the version stays `0.2.0`. Baseline: `main` at
`f5435e7`, `origin/main` at `0a553e1`, clean tree, no tag, quarantine intact; 3.9 reference suite 1311 passed / 1 skipped as expected.

### 18.1 Python policy (governance decision applied)

Target: Python 3.12 to 3.14 inclusive. `pyproject.toml`: `requires-python = ">=3.12,<3.15"` and classifiers 3.12, 3.13, 3.14 (no licence classifier:
SPDX `license = "MIT"`). `README`, `README.fr`, both quick starts and `AGENTS.md` announce the same range; 3.9 and 3.10 are described as regression
environments of the source tree with no announced support; 3.11 and 3.15 are not tested. `tests/test_public_tree.py` fails if the metadata, the
classifiers and the four user documents disagree. Observed: both archives carry `Requires-Python: <3.15,>=3.12`; `pip` on 3.9.13 refuses both with
"requires a different Python"; the specifier excludes 3.9 to 3.11 and 3.15.0. Not claimed: every combination of version and platform. What ran:
3.12.14 and 3.14.7 on Windows, 3.13.18 on Linux (offline container), regression 3.9.13 (Windows) and 3.10.12 (Linux, WSL).

### 18.2 Content of the public tree

`PUBLIC_EXCLUDE.txt` (root, itself excluded) is the exact list of what the public snapshot leaves out: itself, `PROJECT_STATE.md`
(working log), `docs/design/PREPUBLICATION_AUDIT.md` (this journal), `docs/design/PUBLIC_SNAPSHOT.md` (maintainer procedure) and
`skills/cv-panel/normes-ets.md` (rights not established). Distributed: `AGENTS.md` (contributor rules, now independent of `PROJECT_STATE.md`),
the user guides (FR/EN), the contracts and architecture documents, `MILESTONES.md`, examples, templates, schemas, the engine, the tests, the
skill `cv-panel` and its attribution (`NOTICE.md`), `LICENSE`. Corrections made so that exclusion breaks nothing: links from `README`,
`ARCHITECTURE`, `MILESTONES`, `ENGINE` to excluded documents removed; `SKILL.md` no longer tells the agent to read the school file and its
description no longer cites a school template code; `README` no longer claims that school conventions are summarised in the distribution;
`MANIFEST.in` no longer ships `PROJECT_STATE.md`. No absolute user path, private name, remote or collaborator name was found in the tracked tree
(`git grep` and the outside deny list: 0 finding). Licences: MIT (`LICENSE`, copy in the wheel as `License-File`); the attribution to
`hiring-panel-skill` (MIT, Alex Chen) is in `skills/cv-panel/NOTICE.md` and is shipped in the sdist and the snapshot; the wheel contains no
skill. The wheel does not contain the examples, so the quick start needs a clone or the sdist.

### 18.3 Defects found and corrected

| Defect | Found by | Fix | Test |
|---|---|---|---|
| `package status` printed a traceback and exited `1` (the code of `NEEDS_REVIEW`) when `metadata.json` was readable JSON of the wrong shape (`{}`, `[]`, ...); `package review|approve` crashed the same way | replaying the journeys on the built archives, then a malformed-file sweep (216 runs: 10 crashes before, 0 after) | `review_summary` raises `METADATA_UNREADABLE`; `status` reports `BLOCKED` (exit 3) | `test_metadata_that_is_not_a_cv_metadata_is_blocked_cleanly_by_every_command` (4 cases, fail without the fix) |
| `package create --help` said a package with a `--pdf` could become ready | reading `--help` against the policy of M8-A-R2 | help text corrected | `tests/test_docs_commands.py` reads every documented command |
| Skill description cited a school template code; skill told the agent to read the excluded file; README attributed summaries to the school | inventory of the public tree | reworded | `test_public_tree.py` |

A second sweep over the source files (facts, profile, content FR and EN, offer, import map, legacy notes replaced by 10 malformed contents, 9 commands:
630 runs): 0 crash.

### 18.4 Public snapshot (from the candidate HEAD)

Built in a temporary folder by `git archive` of the committed HEAD, removal of the paths of `PUBLIC_EXCLUDE.txt`, `git init`, one commit (no remote,
no tag, identity: the no-reply address). 93 tracked files. Observed: no excluded path in the tree or in any object of the history; the blob of
`normes-ets.md` is absent from the object store; its distinctive text is absent from every file of every commit; no PDF, log, cache, quarantine
file; privacy scan of the tree and of the history: 0 finding; the same on the built wheel and sdist. The tested snapshot tree is
`11f9c27a5026605e5f1fa52be6af9fbab17875ce`; the snapshot built from the final HEAD must have the same tree (see the report).

### 18.5 Distributions and journeys (built from the snapshot)

Wheel (27 modules + `dist-info`, 32 entries) and sdist (113 entries: engine, tests, docs, examples, schemas, templates, skills, licence; no excluded or
generated-private file) build without warning. Each installs in a clean virtual environment on 3.12.14 and on 3.14.7; `python -I -m modularcv` runs
from outside the source tree; name, version `0.2.0` and `Requires-Python` are read back from the installed metadata. From each of the four installations,
a script runs the synthetic example (French and English, A4 and Letter) through plan, render, `package create --compile`, status, a refused script
approval, a **synthetic** approval (reviewer `SYNTHETIC TEST ONLY`, written by the engine's API in a throw-away workspace; no real approval exists
anywhere), substitution of the PDF (READY lost, restored: READY again), a source edited after packaging, a PDF supplied with `--pdf`
(`SUPPLIED_PROVENANCE_NOT_VERIFIED`, `PDF_ORIGIN_NOT_VERIFIED`, approval refused with `PACKAGE_NOT_REVIEWABLE`), a package without PDF, a page-less
PDF (`PDF_NO_PAGE`), a recorded rejection (`BLOCKED`) and emptied metadata (`BLOCKED`): 49 checks each, 49/49 on all four installations.
`READY_TO_SEND`, `NEEDS_REVIEW` and `BLOCKED` were all observed. The A4 page box is 595.276 x 841.89 pt and the Letter one 612 x 792 pt.

### 18.6 Test matrix (snapshot, tests run from the unpacked sdist unless stated)

| Python | Platform | Result | Identity digest |
|---|---|---|---|
| 3.12.14 | Windows (MiKTeX) | 1406 passed, 3 skipped | `c84146783d031172` |
| 3.14.7 | Windows (MiKTeX) | 1406 passed, 3 skipped | identical |
| 3.13.18 | Linux, offline container (no TeX) | 1398 passed, 11 skipped | identical |
| 3.9.13 (regression) | Windows | 1406 passed, 3 skipped | identical |
| 3.10.12 (regression) | Linux, WSL (no TeX) | 1398 passed, 11 skipped | identical |
| 3.9.13, private tree | Windows | 1408 passed, 1 skipped (1409 collected) | n/a |

Skips: a symbolic-link test on Windows, the two tests that need files absent from the snapshot (`PUBLIC_EXCLUDE.txt`, `normes-ets.md`), and on Linux
the tests that need `pdflatex`. Nothing failed.

### 18.7 Portability and limits

Engine and `.tex` generation: identical on 3.9, 3.10, 3.12, 3.13, 3.14. PDF compilation: **MiKTeX on Windows only**. **TeX Live on Linux: not tested**:
the environments available (WSL Ubuntu 22.04, the local images `ubuntu`, `debian`, `python`) were probed again and none has `pdflatex`; nothing was
installed. A Linux 3.12 container was tried and abandoned (the image has no git). The reproducible procedure of section 17.4 is unchanged. Not
claimed: ATS compatibility, authentication of the PDF origin or of the reviewer (both are statements in unsigned files), support for 3.11, 3.15, macOS.

### 18.8 Remaining blockers and decisions

No technical blocker for a first release restricted to what was verified. Human decisions: route of the public repository (single-commit snapshot,
rewritten history, or authorisation for the school summary); acceptance of the list of `PUBLIC_EXCLUDE.txt`; public identity, repository name,
visibility; version number; whether TeX Live may be tested in a throw-away container; whether to keep accepting `--pdf`; the earlier open decisions
(default paper, authenticity of approvals, quarantined file).
