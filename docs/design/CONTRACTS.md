# Data contracts of the generic engine (M1.1 design)

Status: sections 0 and 1 are implemented (M2), the legacy import of section 1.5 and section 2 are implemented (M4, see 1.5.1
and 2.1), section 3 is implemented (M5, see 3.2); sections 4 to 6 are still **design, not implemented**. Every contract is persona-independent: no personal rule, wording, date or identifier belongs to the engine. Examples use the
fictional identity of `examples/facts.example.md`.

## 0. Conventions shared by every contract

| Topic | Rule |
|---|---|
| Encoding | UTF-8, no BOM. A BOM is stripped on read. |
| Line endings | Normalised to LF **before** any hash or comparison (`\r\n` and lone `\r` become `\n`). A Windows checkout with `core.autocrlf=true` must never change a fingerprint. |
| Unicode | Strings are NFC-normalised before canonicalisation. |
| Canonical JSON | Keys sorted, separators `,` and `:`, `ensure_ascii=False`, UTF-8, no trailing newline, no `NaN`/`Infinity`. |
| Hashes | Three kinds, never mixed. See section 0.1. |
| Versioning | Every document carries `"schema": "<Name>-v<N>"`. An unknown schema or major version is refused, never guessed. |
| Identifiers | `^[a-z0-9]+(?:[.-][a-z0-9]+)*$`, 1 to 80 characters, unique inside their namespace. Stable: never reused for another fact. |
| Dates | `YYYY-MM-DD`, `YYYY-MM` or `YYYY` (calendar-valid). No time zone. A missing date is `null`: **the engine never invents or back-fills a date**. |
| Timestamps | Operational only (`generated_at`, `captured_at`): UTC, `YYYY-MM-DDTHH:MM:SSZ`. They never take part in a fingerprint or an identity. |
| Languages | Lowercase ISO 639-1 codes. The engine ships rules for `fr` and `en`; a workspace may declare others without parity obligations. |
| Unknown fields | Refused in `FactBase`, `Profile`, `ResumeContent` and `JobOffer` (a typo must not become silence). `x-` prefixed fields are kept (in FactBase: in the model and the fingerprint) and ignored by the engine's logic. |
| Errors | Stable machine codes (`FACT_DUPLICATE_ID`, ...), a human message, and the file and line when known. Never an empty result. |

### 0.1 Three kinds of hash

| Kind | Computed on | Invariant under | Name | Used for |
|---|---|---|---|---|
| **Canonical fingerprint** | the canonical JSON of a *model* (a parsed document), after NFC and LF normalisation of every string | key order, line endings, spacing the parser discards, BOM | `<model>_sha256` (for example `factbase_sha256`) | semantic identity: plans, `tailored_cv_id`, "has the meaning changed?" |
| **Normalised-source hash** | the bytes of a *text file*: BOM removed, `\r\n` and lone `\r` turned into `\n`; **no NFC, no other change** | checkout line endings and BOM only | `<role>_source_sha256` (for example `facts_source_sha256`) | provenance and snapshots: "is this the file the commit holds?" Any other edit, including whitespace, changes it. |
| **Exact-bytes hash** | the raw bytes of a *binary file* (PDF, image); no normalisation ever | nothing | `<role>_bytes_sha256` | integrity of artefacts that are not text |

Rules: the text normalisation is **never** applied to a binary file; a file's kind is declared (`text` or `binary`), never guessed.
Two files with equal canonical fingerprints may have different source hashes, and that is expected (reformatting). Provenance and
snapshots use the normalised-source hash for text and the exact-bytes hash for binaries; identities use canonical fingerprints.

## 1. FactBase-v1

The only source of professional facts. The authoritative file is **human-edited Markdown** (`facts.md`); the engine
parses it into a canonical JSON model. Nothing is written in a document that is not a published fact here.

### 1.1 Markdown grammar (strict)

```
<!-- modularcv: FactBase-v1 -->            first non-blank line; required
# Free title                               ignored
## Section title {#section-id}             a section; the id is optional (slug of the title otherwise)
- [fact.id] STATUS: text of the fact {attr: value; attr: value}
    continuation lines are indented by 4 spaces and belong to the same fact
```

Anything that is neither blank, a heading, a comment, a fact line nor a continuation line is **not a fact**. It is
reported as `FACT_UNPARSED_LINE` and makes `facts check` fail; it is never silently treated as prose that the engine
may use. Free prose is allowed only inside HTML comments.

### 1.2 Fact record

| Field | Req. | Type | Notes |
|---|---|---|---|
| `id` | yes | identifier | Unique in the file. |
| `status` | yes | enum | `CONFIRMED`, `DERIVED`, `NOT_CONFIRMED`, `WITHDRAWN` (below). |
| `text` | yes | string | Non-empty after trimming. Language given by `lang`, else the profile's default language. |
| `section` | derived | identifier | From the enclosing heading. |
| `lang` | no | `fr`/`en`/... | Language of `text`. |
| `confirmed_on` | no | date | **Optional.** A fact without a date is valid and carries `null`. |
| `technologies` | no | list of strings | Display names; normalised for matching by `fold()` (casefold, accents removed). |
| `capabilities` | no | list of identifiers | Drawn from the taxonomy in use (`generic-v1` by default). |
| `source` | no | string | Free reference (document, course, confirmation channel). Never a path outside the workspace. |
| `supersedes` | no | identifier | Id of an earlier fact it replaces; the replaced fact must be `WITHDRAWN`. |
| `note` | no | string | Reviewer note, never published. |

Attributes use `{technologies: Python, pytest; capabilities: testing; confirmed_on: 2026-01-10; lang: en}`.

### 1.3 Confirmation policy

| Status | May appear in a generated document | Effect |
|---|---|---|
| `CONFIRMED` | yes | Publishable. No date is required (`profile.policy.require_confirmation_date`, default `false`, can make it so for a workspace that wants it). |
| `DERIVED` | **no** | A wording derived from confirmed facts. Reported under `human_validations_required`; becomes publishable only when a human edits it to `CONFIRMED`. The engine never promotes a status. |
| `NOT_CONFIRMED` | no | A claim that must not be made. Feeds the requirement matrix as `FORBIDDEN_TO_CLAIM` evidence. |
| `WITHDRAWN` | no | Was claimed once and retracted. Any package built on it is stale (staleness registry). |

Validation errors (all fatal): duplicate id, unknown status, empty text, invalid date, unknown `supersedes`,
`supersedes` target not `WITHDRAWN`, `CONFIRMED` fact whose `capabilities` are outside the taxonomy, missing marker line.

### 1.4 Canonical model and fingerprints

```json
{"schema":"FactBase-v1","facts":[{"id":"...","status":"CONFIRMED","text":"...","section":"...",
  "lang":null,"confirmed_on":null,"technologies":[],"capabilities":[],"source":null,"supersedes":null,"note":null}]}
```

Facts are ordered by file order; `line` is **not** part of the canonical model (moving a fact must not change the
semantic identity).

- `facts_source_sha256`: normalised-source hash of `facts.md` (section 0.1). Used by provenance. Changes when the file changes in any way except BOM and line endings.
- `factbase_sha256`: canonical fingerprint of the model above. Used for plan identity. Unchanged by blank lines, spacing and comments; changed by any change of order, text, status or attribute.
- A fact's `text` is canonicalised by collapsing every run of whitespace (including the line breaks of continuation lines) into one space and trimming.

### 1.4.1 Implementation status and choices (M2)

Section 1 is **implemented** by `modularcv/facts.py` and `modularcv/canonical.py` (the rest of this document is still design).
Choices the contract left open, made in M2:

- A fact must sit under a `## section` heading (`FACT_OUTSIDE_SECTION`); only `#` and `##` headings exist (`###` is `FACT_UNPARSED_LINE`).
- A blank line ends a fact; a continuation line after a blank line is `FACT_UNPARSED_LINE`.
- The attribute block is the last `{...}` of the fact when the text ends with `}`. Attribute values cannot contain `;`; lists are
  comma-separated. `x-` attributes (name `x-` then a lowercase identifier) are accepted, **kept** in the canonical model as an
  `extensions` object `{name: value}` and therefore part of `factbase_sha256`. The object is omitted when a fact has none, so a
  file without extensions keeps the fingerprint it had before. Values are whitespace-collapsed and NFC like other attributes;
  attribute order does not matter (keys are sorted); duplicates, empty values and malformed names are errors; unprefixed
  unknown attributes stay `FACT_UNKNOWN_ATTRIBUTE`. An extension has no effect on status or publication.
- An empty or whitespace-only file is `FACT_EMPTY_FILE`; a file with only the marker is valid with the warning `FACT_NO_FACTS`.
- `capabilities` must be lowercase identifiers; their vocabulary is not checked before M6 (no taxonomy yet).
- `require_confirmation_date` is a parameter of the parser (`--require-confirmation-date` on the CLI); the profile that will
  carry it arrives in M4.
- Error messages never repeat the text of a fact.

Error codes: `FACT_FILE_UNREADABLE`, `FACT_NOT_UTF8`, `FACT_EMPTY_FILE`, `FACT_MARKER_MISSING`, `FACT_UNKNOWN_SCHEMA`,
`FACT_UNPARSED_LINE`, `FACT_CONTROL_CHARACTER`, `FACT_UNTERMINATED_COMMENT`, `FACT_BAD_SECTION_ID`, `FACT_DUPLICATE_SECTION`,
`FACT_OUTSIDE_SECTION`, `FACT_INVALID_ID`, `FACT_DUPLICATE_ID`, `FACT_UNKNOWN_STATUS`, `FACT_EMPTY_TEXT`, `FACT_BAD_ATTRIBUTES`,
`FACT_UNKNOWN_ATTRIBUTE`, `FACT_DUPLICATE_ATTRIBUTE`, `FACT_EMPTY_ATTRIBUTE`, `FACT_INVALID_LANG`, `FACT_INVALID_DATE`,
`FACT_INVALID_CAPABILITY`, `FACT_BAD_SUPERSEDES`, `FACT_DATE_REQUIRED`; warning `FACT_NO_FACTS`.
CLI exit codes of `facts check|fingerprint`: 0 valid, 1 invalid content, 2 unreadable file or bad configuration.

### 1.5 Importing historical Markdown facts

The engine contains **no** rule for any particular person's file. Import is driven by a mapping that lives in the
user's workspace:

```
python -m modularcv facts import --mapping import-map.json --in legacy.md --out facts.md --report import-report.json
```

`import-map.json` (`LegacyFactMap-v1`) holds: heading regular expressions with a section id and a default status;
line regular expressions that set a status (for example "not confirmed" markers); an optional technology list
section; the id rule. The built-in neutral rule set only knows "every bullet under a heading is a `CONFIRMED` fact
only if the mapping says so".

- Default id: `<section-slug>.<first 10 hex of sha256(line)>` (stable and content-derived).
- `confirmed_on` stays `null` unless the legacy text states a valid date in a pattern the mapping declares.
- Fail-closed: a line the mapping cannot classify becomes `FACT_UNMAPPED` in the report and is **not** written as a fact.
- The report lists every legacy line with its decision, so the import can be audited line by line. It lives in the
  workspace, never in the engine repository.

### 1.5.1 Implementation status and choices (M4)

Section 1.5 is **implemented** by `modularcv/legacy.py` (`facts import`); the user guide is `docs/IMPORT.md`. Choices the
contract left open, made in M4:

- **Nothing becomes `CONFIRMED` implicitly.** A heading rule must state its `status`. `CONFIRMED` is refused unless the mapping
  also carries `"allow_confirmed": true` (`LEGACY_MAP_CONFIRMED_NOT_ALLOWED`): a mapping that says it twice is the only way to
  create a publishable fact. A line rule (`status_rules`) can only **lower** the status its heading gave; a rule that would
  raise it rejects the line (`LEGACY_PROMOTION_REFUSED`). A `status_rules` entry can never name `CONFIRMED`.
- **Decisions.** Every non-blank line of the document appears in the report with one decision: `ACCEPTED` (written as a fact),
  `DUPLICATE` (same text and status as an earlier line, not written twice), `IGNORED` (an explicit `ignore` heading or
  `ignore_patterns`), `TECHNOLOGY` (an entry of the technology list), `UNCLASSIFIED` (`FACT_UNMAPPED`: no rule applies),
  `AMBIGUOUS` (two rules disagree: two headings, two status rules, two dates, one text under two statuses) and `REJECTED`
  (classified but unusable: invalid date, text ending in `}`, control character, empty or over-long text, id collision,
  promotion). `UNCLASSIFIED`, `AMBIGUOUS` and `REJECTED` are *problems*: the import is then incomplete.
- **Document grammar.** Headings are `#` to `######`. A bullet is `-`, `*`, `+`, `1.` or `1)`, with its text on the same line;
  following lines indented by two spaces or a tab continue it. Everything else (prose, tables, rules, front matter) is
  `UNCLASSIFIED` unless an `ignore_patterns` entry matches the whole line. A heading no rule matches closes the previous section:
  its bullets are `UNCLASSIFIED`; an `inherit` rule keeps the parent context instead.
- **Rules.** A heading rule has `pattern` (matched against the whole heading text), an `action` (`map` by default, `ignore`,
  `inherit`, `technologies`) and, for `map`, `section`, `status`, optional `title`, `lang`. `level` (1 to 6) restricts a rule to
  one heading level. Patterns are Python regular expressions of at most 300 characters. A `date_patterns` entry needs exactly one
  capturing group; its match must be a valid date, and a date is applied only to a `CONFIRMED` fact.
- **Technology list.** Entries under a `technologies` heading are a vocabulary, never facts. A term is attached to an accepted
  fact, as `technologies`, only when it appears there as a whole word (casefolded, accents removed).
- **Ids.** `<section>.<ten hex digits of the sha256 of the NFC, whitespace-collapsed text>`: stable when a line moves or is respaced.
- **Origin.** Each fact carries `source: legacy-import:<first 12 hex of the legacy document's source hash>:L<line>`.
- **Mapping authorisation is not human verification.** `allow_confirmed` plus a `CONFIRMED` heading rule is the *user's
  authorisation of a class of lines* ("everything under this heading was checked"). It is stated once, in the mapping, and the
  engine checks that it is present; it cannot check that each fact was individually verified. That verification stays a human
  act: the output is a **proposal** (`facts.proposed.md`), the engine never edits `facts.md`, and a fact becomes part of the
  fact base only when the user copies it there. Every `CONFIRMED` line of a proposal can be traced in the report to the heading
  rule (`rule`) that authorised it. Ambiguity never confirms: two rules that disagree leave the line `AMBIGUOUS` and unwritten.
- **Partial results.** Exit `0` only when every line is classified and at least one fact is accepted. Otherwise exit `1`, the
  report is written, and the facts file is written only with `--allow-partial` (the exit code stays `1`).
- **Boundaries.** The mapping, `--out` and `--report` must be inside the workspace; the legacy document may be anywhere and is only
  read. An output that already exists (a dangling symbolic link included) is never overwritten. Neither `--out` nor `--report` may
  designate the workspace's configured fact base, existing or not, by any equivalent path, resolved path or symbolic link: the
  refusal `IMPORT_OUTPUT_IS_FACT_BASE` repeats no path, and a proposal reaches the fact base only when the user copies it there
  after review. `--dry-run` classifies and prints the report and writes nothing.
- **Privacy.** The report holds line numbers, decisions, rule indexes and a hash per line, never the text of a line.

Error codes of the mapping (exit `2`): `LEGACY_MAP_FILE_UNREADABLE`, `LEGACY_MAP_NOT_UTF8`, `LEGACY_MAP_NOT_JSON`,
`LEGACY_MAP_DUPLICATE_KEY`, `LEGACY_MAP_UNKNOWN_SCHEMA`, `LEGACY_MAP_UNKNOWN_FIELD`, `LEGACY_MAP_MISSING_FIELD`,
`LEGACY_MAP_BAD_TYPE`, `LEGACY_MAP_BAD_PATTERN`, `LEGACY_MAP_BAD_EXTENSION`, `LEGACY_MAP_INVALID_ID`, `LEGACY_MAP_INVALID_VALUE`,
`LEGACY_MAP_INVALID_LANGUAGE`, `LEGACY_MAP_INVALID_RULE`, `LEGACY_MAP_OUT_OF_RANGE`, `LEGACY_MAP_EMPTY_VALUE`,
`LEGACY_MAP_CONTROL_CHARACTER`, `LEGACY_MAP_CONFIRMED_NOT_ALLOWED`. Codes of the report (per line): `FACT_UNMAPPED`,
`LEGACY_AMBIGUOUS_HEADING`, `LEGACY_CONFLICTING_STATUS_RULES`, `LEGACY_CONFLICTING_DATES`, `LEGACY_CONFLICTING_DUPLICATES`,
`LEGACY_DUPLICATE_TEXT`, `LEGACY_IGNORED_BY_RULE`, `LEGACY_IGNORED_BY_PATTERN`, `LEGACY_PROMOTION_REFUSED`, `LEGACY_INVALID_DATE`,
`LEGACY_TEXT_UNSAFE`, `LEGACY_TECHNOLOGY_UNSAFE`, `LEGACY_CONTROL_CHARACTER`, `LEGACY_EMPTY_TEXT`, `LEGACY_LINE_TOO_LONG`,
`LEGACY_ID_COLLISION`. Refusals of the command (exit `2`): `CONFIG_ERROR`, `MAPPING_INVALID`, `LEGACY_FILE_UNREADABLE`,
`LEGACY_NOT_UTF8`, `LEGACY_OUTPUT_INVALID`, `IMPORT_OUTPUT_REQUIRED`, `IMPORT_MAPPING_OUTSIDE_WORKSPACE`,
`IMPORT_OUTPUT_OUTSIDE_WORKSPACE`, `IMPORT_OUTPUT_IS_FACT_BASE`, `IMPORT_OUTPUT_EXISTS`, `IMPORT_PATH_CONFLICT`, `IMPORT_WRITE_FAILED`.

## 2. Profile-v1

The candidate's configuration, as JSON (`profile.json`). Persona data lives here and in the fact base, never in code.

| Field | Req. | Notes |
|---|---|---|
| `schema` | yes | `"Profile-v1"`. |
| `languages` | yes | Non-empty list; `default_language` must belong to it. |
| `identity` | yes | `display_name` (req.), `headline`, `location`, `email`, `phone`, `links[]` (all optional strings). Each field has `visibility`: `public` or `private`; a public render omits private fields. |
| `families` | yes | Map `family_id` to `{label, languages, core_skills[], excluded_blocks{block_id: reason}, clusters[], page_target}`. At least one family. |
| `policy` | no | `never_publish_terms[]`, `omit_by_default_terms[]`, `forbidden_words{lang: []}`, `require_confirmation_date` (bool). |
| `availability` | no | List of `{id, fact_id, applies_to[]}`: availability statements are **fact ids**, never wording copied into code. `applies_to` uses employment kinds. |
| `taxonomy` | no | `"builtin:generic-v1"` (default) or a workspace-relative path. |
| `selection` | no | Overrides of the ranking constants (section 5.3); defaults are the documented ones. |
| `precedence_rules` | no | Declarative: `{when_direct: requirement_id, keep: block_id, over: block_id}`. Default: none. |
| `guidance` | no | Per `job_key` presentation rules: `{job_key, rules: [{fact_id, action: "omit"|"soften", text}]}`. |

Relation with the published `modularcv.json`: that file keeps its role (paths and registry); its existing keys are
unchanged. M4 adds optional keys `profile`, `content` and `offers_dir`. Unknown keys stay refused, as today.

### 2.1 Implementation status and choices (M4)

Section 2 is **implemented** by `modularcv/profile.py` (with the shared reader `modularcv/docvalidate.py`); the commands are
`profile check` and `profile fingerprint`. Of the three configuration keys announced above, M4 adds `profile` (default
`profile.json`); `content` and `offers_dir` arrive with the milestones that read those files (M5, M6). Choices made in M4:

- **Three kinds of content, never mixed.** *Private*: identity fields marked `private` and every `x-` field. *Public*: identity
  fields marked `public`; `Profile.public_view()` returns only these, and a renderer must use nothing else. *Generation
  preferences*: families, policy, availability, taxonomy, selection, precedence, guidance (`internal_preferences()`); they steer
  the engine and are never printed in a document. Nothing is public by default.
- **Identity.** Each of `display_name`, `headline`, `location`, `email`, `phone` is `{"value": ..., "visibility": "public"|"private"}`;
  `visibility` is required, so a field is never public by omission. `links` is a list of `{"label"?, "value", "visibility"}`.
  Values are single-line strings (NFC, whitespace collapsed, no control character). The engine checks no e-mail or phone format.
  A private `display_name` is a warning (`PROFILE_DISPLAY_NAME_PRIVATE`).
- **Languages.** `languages` is a non-empty set of two-letter codes. `default_language` is required when there are several and
  implied when there is one; it must belong to `languages`. A family's `languages` and the keys of `policy.forbidden_words`
  must belong to the profile languages.
- **Families.** `label` and `languages` are required. `core_skills` are display names, unique once folded, and none may equal a
  `never_publish_terms` entry (`PROFILE_SKILL_FORBIDDEN`). `excluded_blocks` maps block ids to a non-empty reason. `clusters` is a
  list of identifiers whose vocabulary is defined by the taxonomy (M6). `page_target` is an integer from 1 to 5, or absent.
- **Policy.** Terms are unique once folded and stored sorted; a term in both `never_publish_terms` and `omit_by_default_terms`
  is `PROFILE_POLICY_CONFLICT`. Technologies are forbidden the same way: through `never_publish_terms` and `omit_by_default_terms`.
  `require_confirmation_date` is read by `facts check --use-profile`.
- **Availability and proof.** An entry is `{id, fact_id, applies_to}` with `applies_to` drawn from `INTERNSHIP`, `PERMANENT`,
  `FIXED_TERM`, `PART_TIME`, `UNSPECIFIED`. With a fact base, the fact must exist (`PROFILE_FACT_UNKNOWN`) and be `CONFIRMED`
  (`PROFILE_FACT_NOT_CONFIRMED`), and dated when the policy requires it (`PROFILE_FACT_DATE_REQUIRED`). Without a fact base the
  entry is reported `UNVERIFIED` with the warning `PROFILE_FACTS_NOT_CHECKED`. `Profile.confirmed_availability(factbase)` is the
  only way to get availabilities a document may state; the declaration alone proves nothing.
- **Selection.** Keys `baseline_prior` (0.25), `minimum_gain` (1.0), `off_target_penalty` (0.1), `off_target_penalty_cap` (0.6),
  `named_bonus` (0.5), `inferred_factor` (0.5). Numbers from 0 to 1,000,000, `inferred_factor` at most 1, the cap at least the
  penalty. The canonical model always holds the effective values, as floats, so an explicit default and an omitted one give the
  same fingerprint.
- **Precedence and guidance.** A precedence rule needs three identifiers and `keep` different from `over`; rules of one requirement
  that form a cycle are `PROFILE_PRECEDENCE_CONFLICT`. A guidance rule `omit` takes no text and may name any existing fact; `soften`
  needs a replacement `text` and a `CONFIRMED` fact; one fact appears once per job.
- **Taxonomy.** `builtin:generic-v1` or a safe workspace-relative path ending in `.json`; the file is not resolved before M6.
- **Fingerprints.** `profile_source_sha256` is the normalised-source hash of the file; `profile_sha256` is the canonical
  fingerprint of the model (defaults filled in; `languages`, terms, `applies_to`, family `languages` sorted; `core_skills`,
  `clusters`, links, availability, precedence and guidance keep their order). `x-` fields are kept in the model and the
  fingerprint and ignored by the engine.
- **Errors never repeat a value.** An error is a code, a fixed message and a path of field names (`families.software.languages[1]`).
  A key the user chose (a family id) appears only when it is a valid identifier; any other key is shown as `<key>`.

Error codes (`PROFILE_` prefix): `FILE_UNREADABLE`, `NOT_UTF8`, `NOT_JSON`, `DUPLICATE_KEY`, `UNKNOWN_SCHEMA`, `UNKNOWN_FIELD`,
`MISSING_FIELD`, `BAD_TYPE`, `BAD_EXTENSION`, `EMPTY_VALUE`, `CONTROL_CHARACTER`, `OUT_OF_RANGE`, `INVALID_ID`, `INVALID_VALUE`,
`INVALID_LANGUAGE`, `UNKNOWN_LANGUAGE`, `DEFAULT_LANGUAGE`, `DUPLICATE_VALUE`, `NO_FAMILY`, `POLICY_CONFLICT`, `SKILL_FORBIDDEN`,
`INVALID_TAXONOMY`, `PRECEDENCE_INVALID`, `PRECEDENCE_CONFLICT`, `GUIDANCE_INVALID`, `FACT_UNKNOWN`, `FACT_NOT_CONFIRMED`,
`FACT_DATE_REQUIRED`, `FACTS_INVALID`; warnings `FACTS_NOT_CHECKED`, `DISPLAY_NAME_PRIVATE`. CLI exit codes of `profile check`:
`0` valid **and** every fact reference verified (or none to verify), `1` invalid (or fact references that cannot be verified
because the fact base is invalid), `2` unreadable profile, unreadable fact base or bad configuration, `3` (M4-R1) structurally
valid but fact references left `UNVERIFIED`, which is what `--no-facts` yields whenever the profile has availability or guidance
references. `--no-facts` is a structure-only check: its status is `UNVERIFIED`, never `OK`, so a script cannot read it as a
complete validation. `profile fingerprint` is structural by nature and says nothing about fact references.

## 3. ResumeContent-v1

The structured, validated resume text: the replacement for parsing LaTeX masters. The engine writes **no new sentence**:
every printed bullet is a bullet of this file.

```json
{"schema":"ResumeContent-v1",
 "sections":[{"id":"experience","kind":"experience","title":{"en":"Experience","fr":"Expérience"}}],
 "blocks":[{"id":"acme-2025","section":"experience","order":1,"languages":["en","fr"],"supports":["fact.id"],
   "heading":{"en":{"title":"...","subtitle":"...","period":"...","place":"..."}},
   "protected":false,
   "bullets":[{"id":"acme-2025.01","text":{"en":"...","fr":"..."},
               "supports":["fact.id"],"technologies":["Python"],"capabilities":["testing"],
               "follows":null,"condenses":[],"never_publish":false}]}],
 "skills":[{"id":"languages","title":{"en":"Languages"},"items":[{"id":"python","text":{"en":"Python"},"supports":["fact.id"],"technologies":["Python"]}]}],
 "baselines":[{"family":"software","language":"en","items":["acme-2025.01"],"skills":["python"],"focus":"..."}]}
```

Rules:

- Text is plain Unicode with a minimal inline subset (`**bold**`, `_italic_`). **Raw LaTeX is refused**; the renderer escapes.
- A block's `supports` backs its **factual heading** (job title, employer, period, place, institution, degree) the same way a
  bullet's `supports` backs the bullet (M5-R1, see 3.2). Section and skill-category titles are organisational and need none.
- `supports` lists fact ids. Each must exist and be `CONFIRMED`; otherwise the content is invalid (`CONTENT_UNSUPPORTED_BULLET`).
  Support is **explicit**, never inferred by shared words.
- `technologies` and `capabilities` are declared, or derived deterministically from the taxonomy; a declared value must be in it.
- `baselines` select items by id for one family and language (no text matching).
- A bullet that `condenses` other bullets and those bullets are mutually exclusive in a selection.
- `follows` names a bullet that must be printed first ("the same system...").

### 3.1 FR/EN parity: only where both versions exist

Parity is checked **per entity**, by id (not by position):

| Entity | Check |
|---|---|
| Block | If it declares both languages, its bullet id sets must be equal, and each bullet must have both texts. |
| Bullet | A bullet with one language only is valid and is selectable only for that language; it appears in the plan as `LANGUAGE_UNAVAILABLE` for the other. |
| Skill category | Same rule as a block. |
| Block order | Compared by `order` between languages for blocks present in both. |

A workspace with a single language has no parity rule. Drift between two declared versions is an error
(`CONTENT_PARITY_*`), never repaired by guessing.

### 3.2 Implementation status and choices (M5)

Section 3 is **implemented** by `modularcv/content.py` (the shared reader is `modularcv/docvalidate.py`); the commands are
`content check` and `content fingerprint`, the user guide is `docs/CONTENT.md`, the examples are in
`examples/workspace/content/`. The default file is the `content` key of `modularcv.json` (`content/resume.json`). Choices the
contract left open, made in M5, always the smallest compatible one:

- **Two levels of validation, never confused.** *Structure* is always checked. *References to the fact base* are checked only
  when a fact base is given; they prove the **existence and status** of each fact (it exists and is `CONFIRMED`), and nothing
  more. The check is **not semantic**: the engine does not read a bullet against its facts, and does not compare the French and the
  English text of an entity. Support is explicit and made by a human. Without a fact base the result is the warning
  `CONTENT_FACTS_NOT_CHECKED`, every reference is reported `UNVERIFIED`, and `content check` exits `3`, never `0`.
- **Nothing is confirmed by the content.** The file has no status field (an unknown field is refused). A bullet may be printed only
  because every fact in its `supports` is `CONFIRMED` in the fact base (`ResumeContent.selectable`); `DERIVED`, `NOT_CONFIRMED`
  and `WITHDRAWN` facts never allow it. A `never_publish` bullet is a reminder: it needs no support, may cite a fact of any status,
  but a fact id it names must still exist.
- **Factual and organisational fields (M5-R1, decision 9).** *Factual* fields assert something about the person and may be
  printed in a CV: a block's heading (`title`, `subtitle`, `period`, `place`: job title, employer, dates, location, institution,
  degree), a bullet, a skill item. *Organisational* fields assert nothing: a section `title`, a skill category `title`, ids,
  `order`, `kind`, `protected`, baselines and `focus`. Only factual fields need proof.
- **Support is required for every factual field.** One list of fact ids per entity: `supports` on the block (it backs the whole
  heading, not field by field), on each bullet and on each skill item. A publishable bullet, a heading or a skill with an empty or
  missing `supports` is `CONTENT_UNSUPPORTED_BULLET`, `CONTENT_UNSUPPORTED_HEADING` or `CONTENT_UNSUPPORTED_SKILL` (decision 10:
  `supports` is required on skills, which the first draft of this section did not have). A reference that fails adds
  `CONTENT_FACT_UNKNOWN`, `CONTENT_FACT_NOT_CONFIRMED` or, when a profile requires a date, `CONTENT_FACT_DATE_REQUIRED` at the
  reference itself. The same fact may back several entities. Nothing is inferred from the text of a heading: no date, employer,
  title or responsibility is read from it.
- **Printable means proven, for the whole chain.** `ResumeContent.selectable(factbase, language)` returns a bullet only if its
  own `supports` **and** its block's heading `supports` exist and are `CONFIRMED`; `selectable_skills` does the same for skill
  items. Without a fact base nothing is verified and nothing is selectable. A bullet proven under an unproven heading is not
  printable, and a content file with an unproven heading is invalid when checked against a fact base.
- **Technologies and capabilities are declared, never derived (decision 12).** The taxonomy and its controlled vocabulary are
  deferred to M6, so in M5 `capabilities` are valid, stable identifiers whose vocabulary is not checked, and `technologies` are
  display names. When a fact base is given, a declared technology that no
  supporting fact lists is the warning `CONTENT_TECHNOLOGY_NOT_IN_SUPPORT` (compared with `fold`, not by words of the text).
- **Section kinds** are `experience`, `project`, `education` and `other`. A section title and a block heading are plain text in
  every language the blocks declare.
- **Identifiers.** Sections, blocks, bullets, skill categories and skill items each have a namespace; bullets are unique across
  all blocks and skill items across all categories, because baselines and links name them by id alone. No `block.bullet` prefix is
  enforced.
- **Order.** `order` is an integer from 1 to 9999, unique within a section (`CONTENT_DUPLICATE_ORDER`). The canonical model lists
  blocks in print order (section position, then `order`), so moving a block in the file changes nothing; sections, bullets,
  `technologies`, baseline `items` and baseline `skills` keep the order written. `supports`, `capabilities` and `condenses` are
  sets, stored sorted. The block order is single (one `order` for all languages), so "compared between languages" holds by construction.
- **Parity (by id, structure only; decision 11).** A block declares `languages`. Two rules, kept distinct:
  *the contractual pair*: when an entity declares **both `en` and `fr`**, its heading, its section's title and every bullet must
  exist in both (`CONTENT_PARITY_HEADING`, `CONTENT_PARITY_TITLE`, `CONTENT_PARITY_BULLET`), and likewise for a skill category,
  which declares its languages through its `title` (`CONTENT_PARITY_ITEM`). *Any other language* carries no obligation: a
  third language such as `de` may be missing from a bullet, a heading or a title. What stays for every language is general
  structure, not parity: a text may use only languages its entity declares, an entity declaring one language must have that
  language, and every text exists in at least one language. A bullet that exists in one language only is selectable for that
  language only (`selectable` leaves it out for the other). Drift between `en` and `fr` is an error, never repaired.
- **Links.** `follows` and `condenses` name other bullets of the **same block** (`CONTENT_UNKNOWN_BULLET`,
  `CONTENT_INVALID_REFERENCE` for itself, `CONTENT_REFERENCE_CYCLE` for a loop). `protected` (default `false`) is metadata for the
  future selection engine and has no effect today.
- **Baselines.** `family` and `language` are unique together (`CONTENT_DUPLICATE_BASELINE`); `items` are bullets and `skills` are
  skill items, each existing and written in the baseline language (`CONTENT_UNKNOWN_BULLET`, `CONTENT_UNKNOWN_SKILL`,
  `CONTENT_BASELINE_LANGUAGE`), never a `never_publish` bullet (`CONTENT_BASELINE_NEVER_PUBLISH`), never a bullet together with a
  bullet it condenses (`CONTENT_BASELINE_EXCLUSIVE`), and a bullet that `follows` another needs it earlier in the list
  (`CONTENT_BASELINE_FOLLOWS`). With a profile (`--profile`), the family must exist and use the language
  (`CONTENT_BASELINE_FAMILY_UNKNOWN`, `CONTENT_BASELINE_FAMILY_LANGUAGE`) and `policy.require_confirmation_date` applies to
  supporting facts. `focus` is an optional note and is never printed.
- **Text.** A text is one line, NFC, whitespace collapsed, 1 to 1000 characters (headings and titles up to 200). A **backslash**
  is TeX's escape and is refused everywhere (`CONTENT_RAW_LATEX`): raw LaTeX is not a content format and the renderer escapes.
  This is a deliberately blunt, current restriction: it also refuses a legitimate backslash such as a Windows path (write `/`).
  It will be revisited with the renderer (M7), not before. The
  other characters that LaTeX treats specially (`%`, `&`, `$`, `#`, `_`, `{`, `}`, `~`, `^`) are ordinary text here. In a bullet or
  a skill item, `**bold**` and `_italic_` must be balanced, not empty and not crossed (`CONTENT_INLINE_MARKUP`); an underscore
  inside a word (`snake_case`) is ordinary, one that opens a word is read as italics.
- **Extensions.** `x-` fields are accepted at every level, kept in the canonical model and therefore in `content_sha256`, and
  ignored by the engine.
- **Fingerprints.** `content_source_sha256` is the normalised-source hash of the file; `content_sha256` is the canonical
  fingerprint of the model (defaults filled in). Neither changes with line endings or a BOM; the logical one also ignores key
  order, layout, the Unicode form and whitespace inside a text, and an explicit default. They are the `content_sha256` of section 5.
- **Errors never repeat a value.** A problem is a code, a fixed message and a path of field names and positions
  (`blocks[0].bullets[2].supports[1]`); a fact id, an identifier or a text is never echoed.

Error codes (`CONTENT_` prefix): `FILE_UNREADABLE`, `NOT_UTF8`, `NOT_JSON`, `DUPLICATE_KEY`, `UNKNOWN_SCHEMA`, `UNKNOWN_FIELD`,
`MISSING_FIELD`, `BAD_TYPE`, `BAD_EXTENSION`, `EMPTY_VALUE`, `CONTROL_CHARACTER`, `TOO_LONG`, `OUT_OF_RANGE`, `INVALID_ID`,
`INVALID_VALUE`, `INVALID_LANGUAGE`, `DUPLICATE_ID`, `DUPLICATE_VALUE`, `DUPLICATE_ORDER`, `DUPLICATE_BASELINE`, `UNKNOWN_SECTION`,
`UNKNOWN_BULLET`, `UNKNOWN_SKILL`, `INVALID_REFERENCE`, `REFERENCE_CYCLE`, `RAW_LATEX`, `INLINE_MARKUP`, `PARITY_HEADING`,
`PARITY_TITLE`, `PARITY_BULLET`, `PARITY_ITEM`, `UNSUPPORTED_BULLET`, `UNSUPPORTED_HEADING`, `UNSUPPORTED_SKILL`, `FACT_UNKNOWN`, `FACT_NOT_CONFIRMED`,
`FACT_DATE_REQUIRED`, `FACTS_INVALID`, `BASELINE_NEVER_PUBLISH`, `BASELINE_LANGUAGE`, `BASELINE_EXCLUSIVE`, `BASELINE_FOLLOWS`,
`BASELINE_FAMILY_UNKNOWN`, `BASELINE_FAMILY_LANGUAGE`; warnings `FACTS_NOT_CHECKED`, `TECHNOLOGY_NOT_IN_SUPPORT`. CLI exit codes of
`content check`: `0` valid **and** every reference verified (or none to verify), `1` invalid (or a fact base that is invalid), `2`
unreadable content, unreadable fact base, bad profile or bad configuration, `3` structurally valid but references left
`UNVERIFIED` (what `--no-facts` yields whenever there is a reference to verify). `content fingerprint` is structural and says nothing
about fact references. M5 also made identifier, language and extension patterns reject a trailing newline (`fullmatch`), a
defect of M2 that Profile-v1 shared; no valid identifier changed, so no earlier fingerprint moved.

### 3.3 Taxonomy-v1 (M6)

A small JSON document, candidate-independent, named by the profile (`"taxonomy": "builtin:generic-v1"` or a safe relative
`.json` path). It resolves M5 decision 12: capabilities and technologies a content item or a fact declares are checked against it.

| Field | Notes |
|---|---|
| `schema` | `"Taxonomy-v1"`. |
| `id` | Identifier of the taxonomy. |
| `terms` | `[{id, kind: capability\|technology, name, aliases}]`; `name` and each alias are a string (language `any`) or a map language → string(s). |
| `zones` | `[{id, priority: REQUIRED\|PREFERRED, weight, headings}]`: where in a posting a term is found. `default_zone` names one. |
| `priority_weights` | weight per priority. |
| `adjacencies` | `[{from, to}]`: directed, single hop. `docker → kubernetes` does not give the reverse. |

Matching folds case and accents and requires a whole word. Fingerprint `taxonomy_sha256` is the canonical fingerprint of the
model (the built-in one has no source hash). Error codes (`TAXONOMY_` + ): the shared codes of `docvalidate` and `ALIAS_AMBIGUOUS`
(one spelling, two terms, same language), `DUPLICATE_ID`, `ADJACENCY_INVALID`, `HEADING_AMBIGUOUS`, `FILE_UNREADABLE`.
`vocabulary_problems(taxonomy, content, factbase)` reports content or fact declarations outside the vocabulary.

## 4. JobOffer-v1

The engine's only input about an offer. It is deliberately small and source-agnostic.

| Field | Req. | Notes |
|---|---|---|
| `schema` | yes | `"JobOffer-v1"`. |
| `job_key` | yes | Identifier unique in the workspace. |
| `title`, `company` | yes | Non-empty. |
| `description` | yes | Non-empty text (LF-normalised). |
| `language` | no | `fr`, `en`, `auto` (default). `auto` is decided by the deterministic detector and the decision is recorded. |
| `employment_type` | no | `INTERNSHIP`, `PERMANENT`, `FIXED_TERM`, `PART_TIME`, `UNSPECIFIED` (default). |
| `location`, `workplace_type`, `source_url`, `source_system`, `posted_on`, `captured_at` | no | Informational. |
| `source_ref` | no | Opaque string for the adapter that produced it. |
| `description_sha256` | computed | Source hash of `description`; a supplied value that differs is refused. |

`offer_sha256` = canonical fingerprint of `{job_key, title, company, location, description, language, employment_type}`.
It feeds the metadata field `job_sha256`.

**Adapters** turn an external document into a `JobOffer-v1`. They live outside the core, are named explicitly
(`--adapter`), and are optional. An adapter for a job-scraper export may exist; **no adapter is required to use the engine**,
and the core never imports one.

### 4.1 Implementation status and choices (M6)

`modularcv/joboffer.py`. The contract above had no structured requirements; M6 adds, minimally:

- optional `requirements: [{id, term, priority: REQUIRED|PREFERRED}]` (explicit entries), and detection of every taxonomy spelling
  found as a whole word in `description`, with its priority taken from the taxonomy zone of the surrounding heading.
  `offer_sha256` includes `requirements` only when the list is non-empty, so offers without it keep the fingerprint defined above.
- `language: auto` is decided by a deterministic French/English function-word count; the result and its method (`declared`,
  `detected`, `default`) are recorded; a tie falls back to the profile's default language (`LANGUAGE_UNDECIDED` otherwise).
- No LLM extraction, no network, no adapter. The description is untrusted data: it is never executed or interpreted as an instruction.
- Error codes (`OFFER_` + ): the shared `docvalidate` codes, `DESCRIPTION_HASH_MISMATCH`, `REQUIREMENT_CONFLICT`,
  `REQUIREMENT_DUPLICATE_TERM`, `REQUIREMENT_ID_COLLISION`, `FILE_UNREADABLE`. Messages are fixed and carry a JSON path, never a value.
- CLI: `offer check|fingerprint` (exit 0 valid, 1 invalid or `LANGUAGE_UNDECIDED`, 2 unreadable).

### 4.2 Package, metadata version 3 and human review (M7-B)

`modularcv/chain.py`, `package.py`, and the extensions of `metadata.py`, `review.py`, `snapshot.py`, `readiness.py`; user guide:
[PACKAGE.md](../PACKAGE.md).

- **Identity.** `tailored_cv_id` = canonical fingerprint of `{schema: TailoredCvIdentity-v1, engine_version, template_id, language,
  plan_sha256, facts_source_sha256, factbase_sha256, content_sha256, profile_sha256, taxonomy_sha256, offer_sha256}`. It is a function of the
  plan file and the engine version only (recomputable), so it contains no personal value, path or clock. `assembly_sha256` and the artefact
  hashes are not part of it; they are bound by the metadata and the review.
- **Metadata `schema_version` "3".** Exactly the fields listed in PACKAGE.md; strictly validated (`metadata.problems`); no `generated_at`.
  Versions 1 and 2 remain readable and are never repaired; unknown versions are refused. Compatibility rule: a document of version 1 or 2 is
  judged by the M3 rules and a v2 package may not carry version 3 metadata (and the reverse).
- **`ApplicationPackage-v2`.** Carries no verdict: `routing.workflow_state` is `UNEVALUATED`; declaring any other state is `PACKAGE_JSON_INVALID`
  (BLOCKED). The legacy package format keeps its M3 behaviour (a declared state other than `READY_TO_SEND` still yields `DECLARED_*`).
- **Snapshot.** Roles `taxonomy` (source role, checked against the commit) and `assembly` (artefact role) added; no other change.
- **`CVQualityReview-v2`.** `document_role` is always `cv_pdf`; the approved hash is that of the exact PDF bytes read at verification time.
  `reviewed` and `acknowledged` must equal the values derived from the verified metadata, so a changed warning list, plan, assembly, `.tex`
  or pagination voids the approval. `CVQualityReview-v1` (approval of a `.tex`) is accepted only for version 1 and 2 metadata.
- **Readiness for version 3.** `readiness.assess` runs the M3 checks, then `chain.verify` re-derives the chain from the workspace files (plan
  integrity, sources reload and validate, the plan re-verifies by the five layers of `assemble.verify_plan`, the stored assembly equals the fresh
  assembly, the `.tex` equals the rendering of the assembly, the PDF is a complete PDF, the metadata equals what the chain implies) and the
  identity, final-document and review checks. New reasons: `CHAIN_INVALID` (BLOCKED), `FINAL_DOCUMENT_MISSING` (NEEDS_REVIEW); existing
  reasons are reused otherwise (`CV_REFERENCE_MISMATCH`, `SNAPSHOT_CONTRADICTORY`, `PACKAGE_JSON_INVALID`, `HUMAN_REVIEW_*`). The chain is only
  re-derived when the snapshot files are unchanged (a changed file is reported on its own, `NEEDS_REVIEW`, without cascading).
- **CLI.** `package create|status|review|approve`; exit codes of `status`: 0 `READY_TO_SEND`, 1 `NEEDS_REVIEW`, 3 `BLOCKED`, 2 unusable.
  `approve` requires an interactive terminal and a typed confirmation; it writes a new file only.
- **Deliberate limits.** No signature; the PDF-to-`.tex` derivation is not machine-verified; ATS and semantics are not verified;
  the profile headline is not printed.

## 5. Plan and identity (outputs, for reference)

- `RequirementMatrix-v1` and `TailoringPlan-v1` keep the semantics of the private engine's matrix and plan
  (DIRECT, ADJACENT, ABSENT, FORBIDDEN_TO_CLAIM; greedy ranking by marginal coverage), with fingerprints over canonical JSON.
- `tailored_cv_id` = sha256 of canonical `{versions, facts_source_sha256, factbase_sha256, content_sha256, profile_sha256,
  taxonomy_sha256, offer_sha256, plan_sha256, template_version, language}`. No timestamp participates.
- Selection constants (defaults): baseline prior `0.25`, minimum gain `1.0`, off-target penalty `0.1` capped at `0.6`,
  named bonus `0.5`, inferred factor `0.5`; overridable in `profile.selection`.

### 5.1 Implementation status and choices (M6)

`modularcv/matrix.py`, `modularcv/plan.py`; user guide: [PLAN.md](../PLAN.md).

- **States** are evaluated `FORBIDDEN_TO_CLAIM` > `DIRECT` > `ADJACENT` > `ABSENT`. Forbidden: a profile `never_publish_terms`
  spelling, or any `NOT_CONFIRMED`/`WITHDRAWN` fact declaring the term. Direct: a pool item declares the term **and** a `CONFIRMED`
  fact backing that item declares it (corroboration; a content declaration alone is not proof). Adjacent: one directed hop from
  a `DIRECT`, non-forbidden term. Absent reasons: `UNKNOWN_TERM`, `UNCORROBORATED`, `NO_PUBLISHABLE_CONTENT`, `NO_EVIDENCE`.
- **Pool**: only content proven by `ResumeContent.selectable()`/`selectable_skills()` (bullet, skill and block heading all
  `CONFIRMED`), in the plan language, not `never_publish`, passing the family exclusions, forbidden words and terms, per-job
  guidance and `omit_by_default_terms` (a baseline can rescue the latter only).
- **Ranking**: greedy, marginal gain `weight × factor / (1 + n)` (`factor` 1 for direct, `inferred_factor` for adjacent), plus
  `named_bonus`, plus `baseline_prior`, minus `min(off_target_penalty × k, cap)`; selection needs gain ≥ `minimum_gain`; ties
  by print position then id; gains rounded to 9 decimals.
- **Plan**: `plan_status` `PLAN_ONLY`, `review` `NOT_REVIEWED`, `tailored_cv_id` `null`, `plan_sha256` over the canonical plan
  (including every input fingerprint and the matrix fingerprint). No timestamp participates.
- Error codes (`PLAN_` + ): `FACTBASE_REQUIRED`, `FAMILY_REQUIRED`, `FAMILY_UNKNOWN`, `LANGUAGE_UNDECIDED`, `LANGUAGE_UNAVAILABLE`,
  `CAPABILITY_UNKNOWN`, `CLUSTER_UNKNOWN`. Warnings are listed in PLAN.md.
- CLI: `matrix` and `plan` (`--offer` required; `--family`, `--language`, `--out`); exit 0 produced, 1 refused (the failing stage is
  named), 2 unreadable input, bad configuration or refused output path.
- Limits (also recorded in every plan): requirements are explicit entries plus exact taxonomy spellings; a reference check
  proves existence and status of facts, never that a text means what they say (nor FR/EN equivalence); `ADJACENT` is declared
  neighbourhood, not a level; the page target is recorded, not enforced.
- Deferred to M7: any rendering, `tailored_cv_id`, the review gate.

### 5.2 Assembly and rendering (M7-A)

`modularcv/assemble.py`, `modularcv/latex.py`, `modularcv/pdf.py`; user guide: [RENDER.md](../RENDER.md).

- **Input contract.** The renderer consumes a verified plan, never a trusted one: shape, `plan_sha256`, source fingerprints,
  reproduction by the engine from the current sources, and an independent re-validation of everything selected (fact status for
  the item and its heading, language, `never_publish`, profile policy). Errors are `ASSEMBLY_*`, `RENDER_*` and `PDF_*`, with fixed
  messages and paths, never a value of a document.
- **`AssembledResume-v1`** is the LaTeX-independent CV: public header, sections and blocks in content order, verbatim bullets with
  their `supports`, skills, `pending_directives` (unapplied `soften`), `layout`, `assembly_sha256`; `ready_to_send` is always `false`.
- **LaTeX.** Template `generic-v1`; one escaping function; unsupported characters are refused, never replaced; the `.tex` is
  byte-deterministic and fingerprinted (`tex_sha256`). PDFs are artefacts, not identities.
- **`pdflatex`** is optional and never installed; no shell escape, fixed command line, time limit, scrubbed environment.
- Deferred to M7-B: package, `tailored_cv_id`, metadata v3, readiness, human review gate.

## 6. Compatibility with the published metadata schema

`schemas/application_metadata.schema.json` (published with `0.1.0`) accepts `schema_version` in `["1","2"]`, requires
`master_resume` (ending in `.tex`) and the common fields below, allows `base_resume` (`.tex` or `null`), and has
`additionalProperties: true`. The published template is v2. The schema does not distinguish v1 from v2 beyond the value of
`schema_version`; that stays true.

**Compatibility matrix.** `schema_version` selects the rule set. Nothing in v1 or v2 changes.

| | v1 | v2 | v3 (new) |
|---|---|---|---|
| Common fields: `job_key`, `generated_at`, `language`, `family`, `source_commit`, `facts_source`, `company`, `title`, `job_sha256`, `decision` | required | required | required, identical rules |
| `source_commit` | real SHA, never all zeros | same | same |
| `master_resume` (`.tex`) | required | required | **not required**; if present it is validated as before |
| `base_resume` (`.tex` or `null`) | optional | optional | optional, as before |
| `resume_content` (path ending `.json`) | not defined | not defined | **required** |
| `profile` (path ending `.json`) | not defined | not defined | **required** |
| `engine` = `{name, version, template_version}` | not defined | not defined | **required** |
| `fingerprints` (hashes of section 5, 64 hex digits each) | not defined | not defined | **required** |
| Optional fields of v2 (`recommended_length_pages`, `strategy_source`, `location`, `job_id`, `source_url`) | as published | as published | as published |
| Extra unknown fields | allowed | allowed | allowed |

Rules:

1. Every document that validates against the published schema validates unchanged against the revised one. A test validates the
   published v2 template and a v1 sample against the revised schema.
2. A v3 document that lacks a v3-required field is invalid; a v1 or v2 document is never required to carry one.
3. A reader checks `schema_version` first and refuses an unknown value (`"4"`, `""`) instead of guessing.
4. Fields present in a v1 or v2 document that the v3 rule set also knows (`facts_source`, `source_commit`, ...) keep one meaning
   across versions. A v3 field name is never reused with another meaning in an older version.
5. Readiness treats the three versions alike for its own checks; only the CV-source fields differ.
6. Publication happens in milestone M7 as a revised schema file; this section is the specification it is tested against.

Mapping: `facts_source` = path of `facts.md`; `job_sha256` = `offer_sha256`; `decision.selected_content` =
selected bullet ids; `decision.excluded_content` = omitted ids with reasons; `decision.human_validations_required`
= `DERIVED` facts used as requirements, fact gaps, and the human CV review gate.
