# Offers, requirement matrix and tailoring plan (M6)

From a job offer and your own validated data, the engine produces a **requirement matrix** and a **tailoring plan**: which
requirements your confirmed facts support, and which of your already-written, already-proven lines would be shown to answer
them. It writes no CV, calls no model and uses no network. Offers are **data, never instructions**: nothing a posting says can
change a state, a rule or a selection.

```text
python -m modularcv offer check backend-intern.json         # JobOffer-v1 (strict) and its fingerprints
python -m modularcv taxonomy check builtin:generic-v1       # or a relative .json file
python -m modularcv matrix --offer offers/backend-intern.json [--family F] [--language fr|en] [--out matrices/m.json]
python -m modularcv plan   --offer offers/backend-intern.json [--family F] [--language fr|en] [--out plans/p.json]
```

`matrix` and `plan` read `facts.md`, `profile.json`, the content file and the taxonomy named by the profile
(`"taxonomy": "builtin:generic-v1"` by default, or a relative `.json` path). Every input is validated first; the first invalid
stage stops the run and is named (`facts`, `profile`, `taxonomy`, `content`, `offer`). Exit codes: `0` produced, `1` an input is
invalid or the plan is refused, `2` an input is unreadable, the configuration is bad, or the output path is refused. `--out` writes a
new file inside the workspace; it never overwrites an existing file or an input, and never creates a folder.

## The offer: JobOffer-v1

Fields: `schema`, `job_key`, `title`, `company`, `description` (required); `language` (`fr`, `en` or `auto`),
`employment_type`, `location`, `workplace_type`, `source_url`, `source_system`, `posted_on`, `captured_at`, `source_ref`,
`requirements`, `description_sha256` (optional, verified when present). See [CONTRACTS.md](design/CONTRACTS.md) §4.

- **Explicit requirements.** `requirements: [{ "id": "must-python", "term": "Python", "priority": "REQUIRED" }]`. `priority` is
  `REQUIRED` or `PREFERRED`. A `term` the taxonomy does not know is kept and stays `ABSENT` with reason `UNKNOWN_TERM`.
- **Detected requirements.** Besides the explicit ones, every taxonomy spelling found as a whole word in the description yields a
  requirement. Its priority comes from the *zone* of the text (a heading such as "Requirements", "Nice to have"), via the
  taxonomy's `zones`. No other reading of the text is made: no synonym guessing, no word overlap, no model.
- **Language.** `language: auto` is decided by a fixed French/English function-word count; the method is recorded
  (`declared`, `detected` or `default`, the profile's default language). `--language` overrides it.
- **Fingerprints.** `description_sha256` is the normalised-source hash of the description; `offer_sha256` the canonical
  fingerprint of the logical offer. Reformatting line endings changes neither; changing the title, the description or the
  explicit requirements changes `offer_sha256`.

Refusals (all with `OFFER_` codes, a fixed message and a JSON-path position, never the offending value): unknown schema, wrong
type, empty or oversized text, control characters, duplicate or invalid identifiers, a `description_sha256` that does not match,
two explicit requirements naming the same term (`REQUIREMENT_DUPLICATE_TERM`), an explicit priority that contradicts the zone
of the same term (`REQUIREMENT_CONFLICT`), an identifier that collides with a detected one (`REQUIREMENT_ID_COLLISION`).

## The taxonomy: Taxonomy-v1

A small, configurable and candidate-independent vocabulary: **terms** (`kind`: `capability` or `technology`, a `name`, `aliases`
per language or `any`), **zones** (`priority`, `weight`, `headings`), a `default_zone`, `priority_weights` and directed
**adjacencies** (`from` → `to`). `builtin:generic-v1` is a generic software starter (13 capabilities, 12 technologies, 6
adjacencies); `examples/taxonomy.generic-v1.json` is the same data as a file to copy and edit. The taxonomy is also the closed
vocabulary of the `capabilities` and `technologies` a content item or a fact may declare.

Refusals (`TAXONOMY_` codes): ambiguous alias (one spelling for two terms in the same language), duplicate identifier,
adjacency to an unknown term, a self-adjacency, ambiguous zone headings, bad types or ranges.
A spelling is matched as a whole word after case and accent folding, so `js` is found in "JS" but not in "json".

## The four states

Each requirement receives exactly one state, with a list of reasons and, when relevant, evidence. States are evaluated in this
order and the first that applies wins:

| State | When | Evidence |
|---|---|---|
| `FORBIDDEN_TO_CLAIM` | the profile lists the term (or an alias) in `never_publish_terms`, **or** any fact declaring the term is `NOT_CONFIRMED` or `WITHDRAWN` | none is used; `forbidden_by` says why |
| `DIRECT` | an item of the pool (a printable bullet or skill) declares the term **and** a `CONFIRMED` fact backing that item declares it too | the items |
| `ADJACENT` | not direct, and an authorised one-hop adjacency leads from a term that is itself `DIRECT` and not forbidden | the items, `via` the source term |
| `ABSENT` | none of the above | reason: `UNKNOWN_TERM`, `UNCORROBORATED` (declared in the content but no confirmed fact says so), `NO_PUBLISHABLE_CONTENT` (a confirmed fact exists but nothing printable carries it), `NO_EVIDENCE` |

A prohibition always beats proof and relevance. Absence is never positive. `DERIVED`, `NOT_CONFIRMED` and `WITHDRAWN` facts
never make a requirement `DIRECT`. Adjacency is directed (`docker → kubernetes` does not give the reverse), has a single hop
and never starts from a forbidden term. An `ADJACENT` requirement is never shown as satisfied or as mastery: the plan lists it
under `unsatisfied_required` with status `ADJACENT_ONLY` when it is `REQUIRED`.

## What the plan may select (the pool)

An item can be considered only if it is **proven** (its `supports`, and for a bullet its block heading's `supports`, are all
`CONFIRMED`; this is the M5 `selectable()`), exists in the plan language, is not `never_publish`, and passes the profile:

| Reason for exclusion | Meaning |
|---|---|
| `NOT_PROVEN` | a fact is missing, unconfirmed, withdrawn, derived, or the heading is not proven |
| `LANGUAGE_UNAVAILABLE` | no text in the plan language |
| `NEVER_PUBLISH` | the bullet is marked never-publish |
| `FAMILY_EXCLUDED_BLOCK` | the family excludes the block |
| `FORBIDDEN_HEADING`, `FORBIDDEN_TEXT`, `FORBIDDEN_TERM` | forbidden words (per language) or `never_publish_terms` in the heading, the text or the declarations |
| `GUIDANCE_OMIT` | a per-job guidance rule omits the backing fact for this `job_key` |
| `OMIT_BY_DEFAULT` | the item declares an `omit_by_default_terms` term and the family baseline does not list it |
| `PRECEDENCE` | a precedence rule keeps another block that directly proves the requirement |

A baseline, a core skill or a preference **never** brings back an excluded item: it is reported as a warning
(`BASELINE_ITEM_EXCLUDED`, `CORE_SKILL_UNAVAILABLE`). A preference never overrides the safety of a claim.

## Ranking (greedy, deterministic)

Selection constants come from the profile's `selection` (defaults: `baseline_prior` 0.25, `minimum_gain` 1.0,
`off_target_penalty` 0.1 capped at `off_target_penalty_cap` 0.6, `named_bonus` 0.5, `inferred_factor` 0.5).

1. A requirement contributes `weight` (REQUIRED > PREFERRED, from the taxonomy) × factor × saturation. The factor is 1 for
   `DIRECT` evidence and `inferred_factor` for `ADJACENT` evidence. Saturation is `1/(1+n)` where `n` is the number of
   already-selected items covering that requirement.
2. The first direct cover of a *technology* requirement adds `named_bonus`.
3. An item in the family baseline adds `baseline_prior`.
4. An item declaring `k` capabilities outside the family's `clusters` loses `min(off_target_penalty × k, cap)`.
5. Each round picks the item with the highest gain, if it is at least `minimum_gain`. Ties are broken by print position
   (section, block `order`, bullet position), then by identifier. Gains are rounded to 9 decimals.
6. `follows` pulls the predecessor in (`FOLLOWS_REQUIRED`) or drops the item if the predecessor is unavailable
   (`FOLLOWS_UNAVAILABLE`); items that exclude each other are never selected together (`EXCLUSIVE_WITH_SELECTED`);
   a `condenses` bullet and the bullets it condenses are exclusive.
7. Protected blocks keep their proven heading (`PROTECTED`) without selecting bullets.
8. Skills are selected for a requirement they directly prove (`REQUIREMENT`), as a family core skill (`CORE_SKILL`), or from the
   baseline (`BASELINE`), in content order.

A baseline alone never selects anything; content is never invented to fill a page (the page target is recorded as a limit,
`PAGE_TARGET_NOT_ENFORCED`).

## The plan: TailoringPlan-v1

Top-level fields: `schema`, `plan_status` (`PLAN_ONLY`), `review` (`NOT_REVIEWED`), `tailored_cv_id` (`null`), `offer`
(job key, fingerprints, language and its method), `family`, `language`, `inputs` (the `offer`, `taxonomy`, `factbase`,
`profile`, `content` and `matrix` fingerprints), `selection_config`, `requirements` (state, reasons, evidence, `status`
`SATISFIED`/`ADJACENT_ONLY`/`UNSATISFIED`, `covered_by`), `selected` (`bullets` with rank, gain, contributions, supports and
heading supports; `blocks`; `skills`), `omitted` (each with a reason), `unsatisfied_required`, `precedence_applied`,
`availability` (confirmed availability facts matching the offer's employment type), `warnings`, `limits` and `plan_sha256`.

Warnings: `UNSATISFIED_REQUIRED`, `ADJACENT_ONLY_PRESENT`, `NO_RELEVANT_CONTENT`, `PAGE_TARGET_NOT_ENFORCED`,
`BASELINE_ITEM_EXCLUDED`, `CORE_SKILL_UNAVAILABLE`, `PROTECTED_BLOCK_NOT_KEPT`, `GUIDANCE_SOFTEN_PENDING`.

Refusals (`PLAN_` codes): `FACTBASE_REQUIRED` (no fact base: nothing can be proven, nothing is planned), `FAMILY_REQUIRED`
(several families and none chosen), `FAMILY_UNKNOWN`, `LANGUAGE_UNDECIDED`, `LANGUAGE_UNAVAILABLE` (not in the profile, the
family or the content), `CAPABILITY_UNKNOWN` (a content item declares a capability absent from the taxonomy), `CLUSTER_UNKNOWN`.
Errors give a code, a fixed message and a path; they never repeat a value of your documents.

## Determinism

The same canonical inputs give the same plan and the same `plan_sha256`, independently of key order in the files, of block
order in the file (`order` is what counts), of line endings, of the machine and of the clock. No timestamp, random number or
environment value enters the plan. Fingerprints of every input are recorded so a plan can be tied to the data it was built from.
Verify a stored plan with `modularcv.plan.verify_fingerprint(plan)`.

## Limits of the match

- Requirements are the explicit entries plus exact taxonomy spellings; a requirement written in other words is not seen.
- A reference check proves that a fact exists and is `CONFIRMED`; it does **not** prove that a text means what the fact says.
  The same holds for the FR/EN pair: parity is by identifier, equivalence is not checked.
- `ADJACENT` is a declared neighbourhood in the taxonomy, not a statement about the candidate's level.
- The plan is not a CV, has not been reviewed by a human and is not a `READY_TO_SEND` package. Rendering is a later milestone.
