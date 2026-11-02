# PROJECT_STATE.md

Source of truth for progress. Update it at the end of every session (see `AGENTS.md` §8).

## Repository

- Branch: `main`. Baseline: `0a553e1` (initial release `0.1.0`). M1.1 design documents and M2 code are committed locally
  on top of it (see `git log`); nothing is pushed.
- Remote: `origin` (private). Nothing is published; no tag, no release.
- Tests: 197 passed (`python -m pytest`, Python 3.9.13, synthetic data only): 78 existing + 119 added by M2.
- Privacy scan: `python -m modularcv privacy --root .` reports 0 finding; also 0 with an outside deny list and `--history`.
- Package: still `dependencies = []`; `modularcv.facts` and `modularcv.canonical` import only the standard library.

## Milestones

| ID | Title | Status |
|---|---|---|
| M1 | Audit of the private engine and architectural principles | PASS (validated by the maintainer) |
| M1.1 | Finalise the data and provenance contracts | PASS (validated by the maintainer) |
| M2 | Canonicalisation and FactBase-v1 | Done, awaiting validation |
| M3 | Provenance and readiness hardening (`0.2.0`) | Planned, **not authorised** |
| M4 | Profile-v1 and legacy fact import | Planned, not authorised |
| M5 | ResumeContent-v1 and reservoir | Planned, not authorised |
| M6 | JobOffer-v1, taxonomy, requirement matrix and plan | Planned, not authorised |
| M7 | Rendering, optional PDF, metadata v3, package | Planned, not authorised |
| M8 | Public release preparation | Planned, not authorised |

Details and acceptance criteria: `docs/design/MILESTONES.md`.

## Last work (M2)

- `modularcv/canonical.py`: text normalisation (BOM, LF, NFC), canonical JSON, the three hash kinds
  (canonical fingerprint, normalised-source hash, exact-bytes hash).
- `modularcv/facts.py`: strict FactBase-v1 parser and model, stable error codes with line numbers, `publishable()` returning
  only `CONFIRMED` facts. No function changes a status.
- CLI (additive): `python -m modularcv facts check [FILE]` and `facts fingerprint [FILE]`.
- `examples/facts.v1.example.md` (fictional person), tests `tests/test_canonical.py`, `tests/test_facts.py`, `tests/test_facts_cli.py`.
- Documentation reserves fixed: hash kinds (`CONTRACTS.md` §0.1, `PROVENANCE_READINESS.md` §5) and the v1/v2/v3 metadata
  compatibility matrix (`CONTRACTS.md` §6). Implementation choices: `CONTRACTS.md` §1.4.1.

## Known defect (open, mandatory in M3)

`modularcv.readiness` 0.1.0 is **fail-open**: it returns `READY_TO_SEND` when CV metadata is absent, when `source_commit` is
all zeros (warning only) and when it is a well-formed but unknown SHA. Its correction is mandatory in M3 (`0.2.0`, breaking,
fail-closed). M2 did not touch it. Until M3 is done, do not rely on `modularcv.readiness` to mark anything as ready.
Details: `docs/design/PROVENANCE_READINESS.md` §1 and §8.

## Open decisions (maintainer)

1. Cover letters deferred beyond M8.
2. `pdflatex` optional or required for the first release.
3. One generic taxonomy, or several domain taxonomies.
4. Whether `###` sub-headings and `x-` attributes in the model should be allowed later (M2 refuses `###` and drops `x-`).

Settled: strict `facts.md` grammar with optional `confirmed_on` (M2); M3 is a breaking `0.2.0` correction of `readiness`.

## Blockers

None.

## Next action

Wait for the maintainer's validation of M2. Only then start M3 (provenance and readiness hardening, `0.2.0`) on the
authorisation of that milestone. Do not start M3 or any later milestone before.
