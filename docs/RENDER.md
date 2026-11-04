# Assembly and LaTeX rendering (M7-A)

From a tailoring plan (see [PLAN.md](PLAN.md)) the engine builds a structured CV, then a generic LaTeX file, and, if `pdflatex`
is installed, a PDF. It writes no sentence: every printed line is a line of your `content/resume.json`, chosen by the plan. The
result is an intermediate artefact: **not reviewed, never `READY_TO_SEND`**. Packaging, metadata v3 and the human review gate
belong to M7-B.

```bash
python -m modularcv plan --offer offers/job.json --out plans/job.json            # M6
python -m modularcv assemble --plan plans/job.json --offer offers/job.json --outline   # ids and counts, no text
python -m modularcv render   --plan plans/job.json --offer offers/job.json --out out/cv.tex
python -m modularcv render   --plan plans/job.json --offer offers/job.json --out out/cv.tex --pdf out/cv.pdf [--log out/cv.log]
python -m modularcv latex check                                                  # is pdflatex available?
```

Without `--out`, `assemble` prints the assembly and `render` prints the `.tex`; nothing is written. `--out`, `--pdf` and `--log`
create **new** files inside the workspace (extensions `.tex`/`.json`, `.pdf`, `.log`); an existing file, an input (facts, profile,
content, offer, plan), a path outside the workspace, `.git` or a symbolic link leading outside is refused (exit 2).

Exit codes of `render`: `0` done; `1` an input or the plan is refused (the stage is named: `facts`, `profile`, `taxonomy`,
`content`, `offer`, `plan`, `assemble`, `render`); `2` unreadable input, bad configuration or refused output path; `4` the `.tex`
was written but `pdflatex` is absent (`PDF_UNAVAILABLE`); `5` the `.tex` was written but the compilation failed.

## Input contract: the plan is verified, not trusted

The plan is an input, not an authorisation. Before anything is assembled the sources are loaded and validated again, then five
layers run, in this order; the first failing layer stops the run (`ASSEMBLY_*` codes, fixed messages, JSON paths, no value):

| Layer | Refuses | Codes |
|---|---|---|
| shape | not a `TailoringPlan-v1`, not `PLAN_ONLY`, reviewed, or carrying a `tailored_cv_id` | `PLAN_NOT_OBJECT`, `PLAN_SCHEMA`, `PLAN_STATUS`, `PLAN_FIELD` |
| fingerprint | `plan_sha256` does not match the body (edited plan) | `PLAN_FINGERPRINT` |
| sources | a recorded fingerprint (offer, profile, facts source, fact base, content, taxonomy) differs from the source loaded now: the plan is obsolete, build it again | `SOURCE_MISMATCH` (path `inputs.<name>`) |
| reproducible | the engine, run again on the same sources with the plan's family and language, does not give the very same plan: catches an edit whose hash was recomputed. The rebuilt plan is only compared, never used | `PLAN_NOT_REPRODUCIBLE`, `PLAN_REFUSED` |
| publishable | independent of the planner: every selected block, bullet and skill exists, is listed under its own block, is written in the plan language, is not `never_publish`, has `CONFIRMED` support for itself **and** its heading, passes the profile policy, and is selected once | `ITEM_UNKNOWN`, `DUPLICATE_SELECTION`, `LANGUAGE_UNAVAILABLE`, `FACT_NOT_CONFIRMED`, `HEADING_UNPROVEN`, `ITEM_NOT_PUBLISHABLE`, `PLAN_REFERENCE` |

Other refusals: `ORDER` (the plan lists blocks or bullets in another order than the content defines), `HEADER_NAME_PRIVATE`
(the display name is not public), `LABEL_UNAVAILABLE` (skills are printed in a language without a fixed interface label), `MARKUP`.
Nothing absent from the plan is ever added, to improve the layout or for any other reason.

## The assembled CV: `AssembledResume-v1`

Independent of LaTeX. `status` is `ASSEMBLED_NOT_REVIEWED`, `ready_to_send` is `false`.

- `language`, `family`, `job_key`, `source` (the plan and source fingerprints).
- `header`: the **public** identity only (`Profile.public_view()`): display name, location, email, phone, links. A private field is
  never printed. The headline is **not** printed (a self-description no fact backs; warning `HEADLINE_NOT_PRINTED`; open decision).
- `sections`: content sections in their defined order, only those with a selected block; each block has its `heading`
  (`title`, `subtitle`, `place`, `period`), `heading_supports`, `reason` (`SELECTED` or `PROTECTED`, a protected block keeps its
  proven heading even with no bullet) and its bullets (`id`, verbatim `text`, `spans`, `supports`).
- `skills`: the selected skills by category, titled with a fixed label (`Skills`, `Compétences`).
- `fact_ids`, `pending_directives`, `unsatisfied_required` (kept for the reviewer, never printed), `warnings`, `layout`, `limits`
  and `assembly_sha256`.

The text is the content's, verbatim: no rewriting, shortening, enriching or translation. A `soften` directive needs a text nobody
approved, so it stays in `pending_directives` and is **not** applied. `follows`, `condenses`, exclusions and protection are those
the plan already applied; the assembly does not recompute them.

## The generic LaTeX model: template `generic-v1`

A sober one-column article, 10 pt, `T1` fonts with `lmodern`, `geometry`, `enumitem`, `glyphtounicode` for text extraction, no
colour, no icon, no table, no hyperlink. Order: centred header, content sections (heading line, details line, bullet list), skills.
Titles, details and bullets are **plain lines** (no right-aligned date: text extraction reads it out of order). Paper `a4paper`
(default) or `letterpaper` (`--paper`). The file starts with comments carrying the plan and assembly fingerprints and the language;
no date. Packages are the standard ones of any TeX distribution; the template needs no network.

## Escaping rules (one place: `latex.escape`)

Every data text is untrusted and passes through `escape`; it is never read as LaTeX, and the template never contains data.

- Fixed replacements: `\ { } $ & # _ % ~ ^` and `[ ]` (an optional argument after `\item`); a no-break space becomes `~`.
- Ligatures are broken with `{}` (`--`, `''`, ``` `` ```, `<<`, `>>`, `,,`, `!` and `?` before a backquote) so the printed characters
  are the written ones.
- Printable ASCII and a closed list of Latin letters and punctuation pass (`SAFE_RANGES`: Latin-1 and Latin Extended-A letters,
  `« » – — ‘ ’ “ ” • … € ° · © ¡ ¿`); each was checked with a real compilation. Nine Latin Extended-A letters that `T1` + `utf8`
  cannot print are excluded.
- **Anything else is refused** (`RENDER_UNSUPPORTED_CHARACTER`, with the identifier of the item, never the character): control
  characters, an arrow, an emoji, a combining mark. Nothing is replaced or dropped silently.
- Markup: only `**bold**` and `_italic_` as ResumeContent-v1 defines them (`assemble.inline_spans`, the same rules as
  `content.inline_markup_problem`), rendered as `\textbf{}` and `\textit{}` by the module. `snake_case` is plain text.
- The output uses only the commands of the fixed template and of the escaping table; a test checks the command set whatever the data says.

## Determinism

The same canonical inputs give the same `.tex` **bytes**: UTF-8, LF, no BOM, no date, no random value, nothing dependent on the
system. `tex.sha256` (printed by `render`) is the fingerprint of the exact bytes. Two PDFs are **not** expected to be identical
(`byte_reproducible: false`); a PDF is an artefact, never an identity.

## Optional compilation (`pdflatex`)

`pdflatex` is an optional system dependency, never installed by `modularcv`. `latex check` reports it (exit 0 found, 1 absent).
Absent: the `.tex` is written, `pdf.status` is `UNAVAILABLE`, `pdf_compilation_validated` is `false`, exit 4.

The compiler is started with a fixed command line (`-interaction=nonstopmode -halt-on-error -no-shell-escape -jobname=resume`, plus
`--disable-installer` for MiKTeX so that nothing is downloaded), in a fresh temporary directory holding only the generated file,
no standard input, a time limit (`--timeout`, 1 to 300 s, default 60), `TEX*` environment variables removed, `shell_escape=f`,
`openout_any=p`. No user value reaches the command line. The module cannot sandbox the network: with the installer disabled and no
shell escape, a document built from the fixed template has no way to reach it.

The result is checked: exit status, no TeX error in the log, the PDF exists, starts with `%PDF-`, ends with `%%EOF`, and the page
count is read from the compiler's own log. Diagnostics carry the code, the return code, and the **kind** and **line** of the first
TeX error (kind from a closed list); the log can quote the CV and is written only with `--log` (a new `.log` file, flagged
`may_contain_resume_text`).

Environment and isolation, stated plainly: `-no-shell-escape` and `openout_any=p` stop a document from running a command or writing
outside the temporary directory; they are **not a sandbox**. The compiler inherits the rest of your environment (only `TEX*` variables
are removed), `openin_any` is left at the distribution's default (a document could read files if it could write a backslash), and the
network and the system are not otherwise restricted. What keeps the compilation safe is the input, not the compiler: the template is
fixed, every data text is escaped and restricted to a closed character set, and no backslash from your data reaches the file. The time
limit stops the compiler, but on Windows a helper process started by MiKTeX is not guaranteed to be stopped with it (not verified).

`package create --compile` (see [PACKAGE.md](PACKAGE.md)) runs the same compilation on a `.tex` already verified against the assembly of the
plan, and packages the result directly.

## `page_target`

Three different things are kept apart: the **target** the family asks for (`layout.page_target`), the **selection rules** the plan
applied (it does not enforce the target: `PAGE_TARGET_NOT_ENFORCED`), and the **real page count**, known only after compilation
(`layout.pages`, from the compiler log; `page_verdict` is `NO_TARGET`, `NOT_COMPILED`, `TARGET_MET` or `TARGET_EXCEEDED`). When the
target is exceeded nothing is shortened or removed: a different selection belongs to the deterministic planner (change the
profile's selection constants and build the plan again).

## Limits and not verified

- ATS compatibility is **not verified**: the plain-text extraction order, accents, bullets and spacing were checked on synthetic French and
  English examples with poppler's `pdftotext` (correct, fonts embedded with a Unicode map), not against any applicant tracking system.
  A second, simpler extractor (`pypdf`) merged words around bold text and separators (`accèsRESTen`) because `pdfTeX` encodes the space as
  a position, not a character; `\pdfinterwordspaceon` repaired it in a test (not adopted: it would change `generic-v1`, see the audit).
  The default paper is A4; for Canada use `--paper letterpaper`. French labels such as `Outils:` carry no space before the colon.
- A reference check proves that facts exist and are `CONFIRMED`, not that a text means what they say; French and English texts are
  not checked for equivalence.
- Only French and English have interface labels; other languages render if they have no skills section.
- The generic template is one design; fonts are Latin Modern. No Unicode engine (XeTeX, LuaTeX) is supported yet.
- Real compilation was exercised with MiKTeX on Windows. TeX Live and Linux were **not** tested.

## Deferred to M7-B

Package builder, `tailored_cv_id`, metadata v3, readiness integration, the human review gate and approval, a decision on printing
the headline, other templates, and the Linux/TeX Live compilation check.
