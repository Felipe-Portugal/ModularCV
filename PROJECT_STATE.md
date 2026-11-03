# PROJECT_STATE.md

Source of truth for progress. Update it at the end of every session (see `AGENTS.md` §8).

## Repository

- Branch: `main`. M5 is committed locally on top of `5585c42` (M4 final closure; see `git log`). Baseline of M4: `1114663` (M3, validated). M4 commits: `b38e1c8`, `4244cf9`. M4-R1 (`fe47a23`) and the M4 closure are committed locally on top. Earlier: `17bcf18` (M3 code), `ab35c91` (M2-R1), `d34af49`, `4865a27`,
  `0a553e1` (initial `0.1.0`). M4 is committed locally on top (see `git log`); nothing is pushed.
- Remote: `origin` (private). Nothing is published; no tag, no release.
- Version: `0.2.0` (proposed in M3, unpublished; M4 adds features without a version change); not tagged.
- Tests: `py -3.9 -m pytest` gives 918 passed and 1 skipped (a symlink test that only runs off Windows), 919 collected; synthetic
  data only. Before M4: 376; after M4: 612; after M4-R1: 653; after the final closure: 671; after M5: 919 (248 new in `tests/test_content.py`). Linux: no pytest run (not installed in WSL); a stdlib smoke test of the CLI passed on
  Python 3.10 (see the M4-R1 report).
- Privacy scan: `python -m modularcv privacy --root .` and with an outside deny list and `--history`: 0 findings.
- Package: still `dependencies = []`; the engine imports no network module.

## Milestones

| ID | Title | Status |
|---|---|---|
| M1 | Audit of the private engine and architectural principles | PASS |
| M1.1 | Finalise the data and provenance contracts | PASS |
| M2 | Canonicalisation and FactBase-v1 | PASS (with M2-R1) |
| M3 | Provenance and readiness hardening (`0.2.0`) | PASS (validated) |
| M4 | Profile-v1 and legacy fact import | PASS (M4-R1 and final closure validated) |
| M5 | ResumeContent-v1 and reservoir | Implemented, awaiting validation |
| M6 | JobOffer-v1, taxonomy, requirement matrix and plan | Planned, not authorised |
| M7 | Rendering, optional PDF, metadata v3, package | Planned, not authorised |
| M8 | Public release preparation | Planned, not authorised |

Details and acceptance criteria: `docs/design/MILESTONES.md`.

## Last work (M4)

- `modularcv/profile.py`: Profile-v1. Identity fields carry a required `visibility`; `public_view()` returns only public fields,
  `internal_preferences()` the generation preferences, `confirmed_availability(factbase)` only availabilities backed by a
  `CONFIRMED` fact. Unknown fields refused, `x-` fields kept. Error messages and reports never repeat a value.
- `modularcv/legacy.py`: `LegacyFactMap-v1` and the importer. Line-by-line decisions (`ACCEPTED`, `DUPLICATE`, `IGNORED`,
  `TECHNOLOGY`, `UNCLASSIFIED`, `AMBIGUOUS`, `REJECTED`); nothing unknown is imported; `CONFIRMED` needs `allow_confirmed` plus a rule
  status; a line rule can only lower a status; dates only from declared patterns; the proposal is parsed back by the FactBase-v1
  parser before it is written.
- `modularcv/docvalidate.py`: shared JSON reader (duplicate keys, NaN, unknown fields, value-free messages).
- `modularcv/canonical.py`: `fold()` for casefolded, accent-free matching. `modularcv/config.py`: new key `profile`.
- CLI: `profile check|fingerprint`, `facts import` (`--dry-run`, `--allow-partial`), `facts check|fingerprint --use-profile`.
- Examples: `examples/workspace/` (fictional facts, profile, mapping, legacy notes). Docs: `docs/IMPORT.md`, `CONTRACTS.md` §1.5.1
  and §2.1, `WORKSPACE.md`, `README`.
- Tests: `tests/test_profile.py`, `tests/test_legacy.py` (237 new). M2 and M3 tests unchanged and green.

## Last work (M4-R1)

- `profile check --no-facts` returned exit 0 and status `OK` while availability references stayed `UNVERIFIED`. It now exits `3`
  with status `UNVERIFIED` and a warning on stderr whenever a fact reference was not verified; with no reference to verify it
  still exits 0. `0` now means valid **and** verified (8 net new tests; the old test that expected 0 was replaced on purpose). Documented in `CONTRACTS.md` §2.1, `WORKSPACE.md` and the CLI docstring.
- Importer `CONFIRMED` policy audited: no violation found, no code change. Added 32 tests (flag types, full heading/rule status
  matrix, ambiguity, inherit, dates, traceability to the authorising rule, random documents and mappings) and checked that a
  removed promotion guard makes them fail. `IMPORT.md` and `CONTRACTS.md` §1.5.1 now separate the mapping's authorisation from
  the user's fact-by-fact verification.
- Foreign file investigated read-only (below). Nothing moved, ignored or committed.

## Last work (M5)

- `modularcv/content.py`: ResumeContent-v1 (sections, blocks, bullets, skills, baselines; FR, EN or bilingual). Validation by the
  shared reader: strict fields and types, `x-` extensions kept, value-free errors with stable `CONTENT_*` codes. Each publishable
  bullet and each skill must name its supporting facts; with a fact base every one must exist and be `CONFIRMED`
  (`CONTENT_FACT_UNKNOWN`, `CONTENT_FACT_NOT_CONFIRMED`, `CONTENT_UNSUPPORTED_BULLET`, `CONTENT_UNSUPPORTED_SKILL`); without one the
  references are `UNVERIFIED` and `content check` exits `3`. FR/EN parity is by entity id (bullet, heading, section title, skill),
  never by position and never imposed on a one-language block. Raw LaTeX (a backslash) is refused; `%`, `&`, `$`, `#`, `_`, `{`,
  `}` stay ordinary. `ResumeContent.selectable(factbase, language)` is the reservoir filter (confirmed support, language, not
  `never_publish`); there is no selection algorithm.
- Fingerprints `content_source_sha256` (normalised source) and `content_sha256` (canonical model; blocks in print order, sets
  sorted, defaults filled). CLI: `content check [--facts F | --no-facts] [--profile F] [--outline]`, `content fingerprint`.
- Examples (fictional): `examples/workspace/content/` (`resume.json` bilingual, `resume.fr.json`, `resume.en.json`, `invalid/`).
  Docs: `docs/CONTENT.md`, `CONTRACTS.md` section 3.2, `WORKSPACE.md`, READMEs.
- Fix in earlier modules: `facts.valid_id`, the language and extension checks of `docvalidate` accepted a trailing newline
  (`$` matches before `\n`); they now use `fullmatch`. No valid identifier changed, historical fingerprints are pinned by a test.
- Not run: pytest on Linux (not installed in WSL). A stdlib smoke test of `content check` and `content fingerprint` passed on
  Python 3.10.12 with the same fingerprints as on Windows.

## Last work (M4 final closure)

- The foreign file `modularcv/legacy_import.py` was moved, unchanged, to `D:\Projets\ModularCV\_quarantine\legacy_import.py`
  (outside the repository, so no local build can include it). SHA-256 checked before and after:
  `5c73e936d25ce534dc13b8ef77005630f1643f96092140a3b690b190a2504106`. Nothing deleted, nothing committed.
  **Restore:** move it back to `modularcv/legacy_import.py` (never overwrite a file there) and compare the SHA-256.
- `facts import` now refuses, with the stable code `IMPORT_OUTPUT_IS_FACT_BASE` (exit 2, no path in the message), any `--out` or
  `--report` that designates the configured fact base: existing or not, by an equivalent or absolute path, a different letter
  case, a symbolic link (also a dangling one) or a linked folder. `--dry-run` still writes nothing; existing files are still
  never overwritten (a dangling symbolic link now counts as existing, which closed a path where the import wrote through it);
  a separate proposal file works as before. Classification and the `CONFIRMED` policy are untouched. Decision 8 is settled.

## Known defects and anomalies

- Residual points of M3 stand: the human approval is a file, not a signature.
- Foreign file (now isolated in `_quarantine`, see above; origin still unknown), **not written by the M4 work**: 714 lines, 35,017 bytes, SHA-256
  `5c73e936d25ce534dc13b8ef77005630f1643f96092140a3b690b190a2504106`, created 2026-11-02 15:03:50 and last written 15:04:01
  (-0500). It is a parallel implementation of the same importer (`LegacyFactMap-v1`), it imports `profile.fold`, which does not
  exist (`fold` lives in `canonical`), so importing it raises `ImportError`; nothing in the tracked code, the tests or the docs
  references it; it holds no network, `exec` or `eval` call. Setuptools lists the whole `modularcv` package, so a build made from
  this working tree would ship it; a build from a clean checkout would not. Origin: **not established**. One indication only:
  the transcript search finds a write-result message naming this path in another local session (working directory outside
  ModularCV, last active 15:11 the same day); that is evidence, not proof. It was left unchanged and moved out of the
  package folder; `.gitignore` would not have been enough, it hides a file from Git but not from a build.

## Open decisions (maintainer)

1. Cover letters deferred beyond M8.
2. `pdflatex` optional or required for the first release.
3. One generic taxonomy, or several domain taxonomies.
4. Whether `###` sub-headings should be allowed later (M2 refuses them).
5. Whether a signed or otherwise authenticated approval is wanted instead of the plain `cv-quality-review.json`.
6. Whether the first release tags `0.2.0` or `0.3.0` now that `Profile-v1` and the import are in (M4 changed no version).
7. Final fate of the quarantined `legacy_import.py` (keep outside the repository, delete, or restore); isolated, not deleted.
9. Headings (`title`, `subtitle`, `period`, `place`) carry no fact link in the contract, so employers, dates and places are not
   verified. Add an optional `supports` on blocks, or keep them as free text?
10. M5 made `supports` required on skill items (the contract had none). Confirm, or relax to optional.
11. Parity applies to any declared language code, not only `fr` and `en` (the contract said others have no parity obligation).
    Confirm, or restrict it to the two shipped languages.
12. `capabilities` are identifiers without a vocabulary until the taxonomy (M6); `technologies` are display names compared with the
    technologies of the supporting facts (warning only).

Settled: strict `facts.md` grammar with optional `confirmed_on` (M2); M3 is a breaking `0.2.0` correction of `readiness`; the
import never confirms by itself (M4).

## Blockers

None.

## Next action

Wait for the maintainer's validation of M5 and decisions 7 and 9 to 12 above. Do not start M6 (JobOffer-v1, taxonomy, matrix,
plan) before. Do not start M5 or any later milestone
before.
