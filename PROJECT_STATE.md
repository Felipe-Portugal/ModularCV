# PROJECT_STATE.md

Source of truth for progress. Update it at the end of every session (see `AGENTS.md` §8).

## Repository

- Branch: `main`. Baseline of M4: `1114663` (M3, validated). Earlier: `17bcf18` (M3 code), `ab35c91` (M2-R1), `d34af49`, `4865a27`,
  `0a553e1` (initial `0.1.0`). M4 is committed locally on top (see `git log`); nothing is pushed.
- Remote: `origin` (private). Nothing is published; no tag, no release.
- Version: `0.2.0` (proposed in M3, unpublished; M4 adds features without a version change); not tagged.
- Tests: `py -3.9 -m pytest` gives 612 passed and 1 skipped (a symlink test that only runs off Windows), 613 collected; synthetic
  data only. Baseline before M4: 376 passed.
- Privacy scan: `python -m modularcv privacy --root .` and with an outside deny list and `--history`: 0 findings.
- Package: still `dependencies = []`; the engine imports no network module.

## Milestones

| ID | Title | Status |
|---|---|---|
| M1 | Audit of the private engine and architectural principles | PASS |
| M1.1 | Finalise the data and provenance contracts | PASS |
| M2 | Canonicalisation and FactBase-v1 | PASS (with M2-R1) |
| M3 | Provenance and readiness hardening (`0.2.0`) | PASS (validated) |
| M4 | Profile-v1 and legacy fact import | Done, awaiting validation |
| M5 | ResumeContent-v1 and reservoir | Planned, **not authorised** |
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

## Known defects and anomalies

- Residual points of M3 stand: the human approval is a file, not a signature.
- An untracked file `modularcv/legacy_import.py` (about 700 lines, written at 15:04 on 2026-11-02, imports a `profile.fold` that does
  not exist) appeared in the working tree during M4 and was **not** written by this work. It is not referenced, not tested and not
  committed. The maintainer should decide whether to delete it.

## Open decisions (maintainer)

1. Cover letters deferred beyond M8.
2. `pdflatex` optional or required for the first release.
3. One generic taxonomy, or several domain taxonomies.
4. Whether `###` sub-headings should be allowed later (M2 refuses them).
5. Whether a signed or otherwise authenticated approval is wanted instead of the plain `cv-quality-review.json`.
6. Whether the first release tags `0.2.0` or `0.3.0` now that `Profile-v1` and the import are in (M4 changed no version).

Settled: strict `facts.md` grammar with optional `confirmed_on` (M2); M3 is a breaking `0.2.0` correction of `readiness`; the
import never confirms by itself (M4).

## Blockers

None.

## Next action

Wait for the maintainer's validation of M4 and the decision on the stray `legacy_import.py`. Do not start M5 or any later milestone
before.
