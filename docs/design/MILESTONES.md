# Milestones M2 to M8 (M1.1 design)

A milestone is `PASS` only when the maintainer validates it with evidence (command and output). An agent reports
*done, awaiting validation*, never *validated*. Every milestone keeps the existing tests green, adds synthetic tests only,
passes the privacy scan, and ends without a push, tag or release unless explicitly authorised.

| ID | Title | Scope | PASS when |
|---|---|---|---|
| M2 | Canonicalisation and FactBase-v1 | `canonical.py`, `facts.py`, `facts check` / `facts fingerprint` commands, strict example | acceptance criteria below |
| M3 | Provenance and readiness hardening (`0.2.0`), implemented, awaiting validation | `verify_recorded_commit`, snapshot, metadata resolution, new reasons, `--check`; closes the fail-open behaviour | every reason of `PROVENANCE_READINESS.md` §6 has a test; old fail-open cases now refuse |
| M4 | Profile-v1 and legacy fact import, implemented, awaiting validation | `profile.py`, `legacy.py`, `docvalidate.py`, `profile check\|fingerprint`, `facts import` with audit report, config key `profile` | import of a synthetic legacy file is line-by-line auditable; unmapped lines never become facts |
| M5 | ResumeContent-v1 and reservoir, implemented, awaiting validation | content parser, per-entity FR/EN parity, explicit support, baselines, reservoir | parity only where both versions exist; unsupported bullet refused |
| M6 | JobOffer-v1, taxonomy, matrix and plan, implemented, awaiting validation | offer parser, `generic-v1` taxonomy, requirement matrix, greedy ranking, plan fingerprints | same inputs give same plan fingerprint; unconfirmed claim never selected |
| M7 | Rendering, optional PDF, metadata v3, package (M7-A validated; M7-B packaging, review and readiness implemented, awaiting validation) | templates, escaped deterministic `.tex`, `pdflatex` wrapper, schema `3`, package builder, human review gate | end-to-end synthetic run to a package; readiness gives the expected state |
| M8 | Public release preparation (M8-A pre-publication audit done, awaiting validation: [PREPUBLICATION_AUDIT.md](PREPUBLICATION_AUDIT.md); M8-B not authorised) | CLI polish, docs FR/EN, full privacy audit with history, decision on letters, version and tag proposal | independent clone passes tests and scan; maintainer decides publication |

## M2 in detail (the first increment, deliberately small)

Scope: canonical JSON and hashing helpers, the FactBase-v1 parser and validator, two CLI commands. Nothing else: no profile, no
content, no rendering, no readiness change.

New files: `modularcv/canonical.py`, `modularcv/facts.py`, `tests/test_canonical.py`, `tests/test_facts.py`,
`examples/facts.v1.example.md` (fictional identity), CLI wiring in `__main__.py` (additive).

Acceptance criteria (each is a test, and the 78 existing tests stay green):

1. `normalise_text` turns CRLF and lone CR into LF, strips a BOM, applies NFC.
2. `canonical_bytes` is independent of key order and of line endings in strings; it refuses NaN and infinity.
3. `sha256_text` of a file is identical for LF and CRLF copies of it.
4. The example file parses; the parsed model equals the expected canonical JSON; two parses give the same `factbase_sha256`.
5. Adding blank lines or changing spacing changes `facts_source_sha256` but keeps `factbase_sha256`; reordering facts, or
   changing a fact's text or status, changes `factbase_sha256`.
6. A fact without `confirmed_on` parses with `null` and is valid; no date is ever inserted.
7. An invalid date (`2026-02-30`) is `FACT_INVALID_DATE` with the line number.
8. Duplicate id → `FACT_DUPLICATE_ID`; unknown status → `FACT_UNKNOWN_STATUS`; empty text → `FACT_EMPTY_TEXT`.
9. A line that is neither a fact, a heading, a comment nor a continuation → `FACT_UNPARSED_LINE`; `facts check` exits 1.
10. Missing marker line → `FACT_MARKER_MISSING`.
11. `supersedes` must name an existing `WITHDRAWN` fact (`FACT_BAD_SUPERSEDES`).
12. `DERIVED`, `NOT_CONFIRMED` and `WITHDRAWN` facts are excluded from `publishable()`; only `CONFIRMED` is returned.
13. `python -m modularcv facts check <file>` exits 0 and prints the fingerprints on a valid file, 1 with codes and lines otherwise.
14. `python -m modularcv privacy --root .` reports nothing on the repository, and no private term of a deny list is present.
15. The package still has no dependency (`dependencies = []`), and importing `modularcv.facts` imports no adapter.

Status: implemented, awaiting validation. Choices and error codes: `CONTRACTS.md` §1.4.1. Tests:
`tests/test_canonical.py`, `tests/test_facts.py`, `tests/test_facts_cli.py`. `modularcv.readiness` is untouched: its
fail-open defect stays open until M3, where its correction is **mandatory**.

Out of M2 (decisions taken later): the strict format keywords beyond those above, the taxonomy vocabulary for `capabilities`
(M2 accepts any identifier; M6 checks the vocabulary against the taxonomy, see `CONTRACTS.md` §3.3).

## Decisions the maintainer must take

1. Strict `facts.md` grammar as specified in `CONTRACTS.md` §1 (including the optional `confirmed_on`).
2. M3 as a breaking `0.2.0` correction of the fail-open readiness.
3. Cover letters deferred beyond M8 (`ENGINE.md` §4).
4. Optional or required `pdflatex` for the first public release.
5. Taxonomy `generic-v1`: a software-oriented default, or several domain taxonomies.
