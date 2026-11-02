# PROJECT_STATE.md

Source of truth for progress. Update it at the end of every session (see `AGENTS.md` §8).

## Repository

- Branch: `main`. Baseline of M3: `ab35c91` (M2-R1). Earlier: `0a553e1` (initial `0.1.0`), `d34af49`, `4865a27`. M3 is committed
  locally on top (see `git log`); nothing is pushed.
- Remote: `origin` (private). Nothing is published; no tag, no release.
- Version: `0.2.0` (proposed in M3, in `pyproject.toml` and `modularcv/__init__.py`); not tagged.
- Tests: see the M3 report (`python -m pytest`, Python 3.9.13, synthetic data only).
- Privacy scan: `python -m modularcv privacy --root .` and with an outside deny list and `--history`: see the M3 report.
- Package: still `dependencies = []`; the engine imports no network module.

## Milestones

| ID | Title | Status |
|---|---|---|
| M1 | Audit of the private engine and architectural principles | PASS |
| M1.1 | Finalise the data and provenance contracts | PASS |
| M2 | Canonicalisation and FactBase-v1 | PASS (with M2-R1) |
| M3 | Provenance and readiness hardening (`0.2.0`) | Done, awaiting validation |
| M4 | Profile-v1 and legacy fact import | Planned, **not authorised** |
| M5 | ResumeContent-v1 and reservoir | Planned, not authorised |
| M6 | JobOffer-v1, taxonomy, requirement matrix and plan | Planned, not authorised |
| M7 | Rendering, optional PDF, metadata v3, package | Planned, not authorised |
| M8 | Public release preparation | Planned, not authorised |

Details and acceptance criteria: `docs/design/MILESTONES.md`.

## Last work (M3)

- `modularcv/readiness.py` rewritten fail-closed: READY is computed from a package's own evidence (snapshot, workspace Git commit,
  metadata, plan, human approval). Without the evidence nothing is READY. Stable reasons with `details`.
- `modularcv/snapshot.py` (SourceSnapshot-v1: build, structure check, read-only file verification), `modularcv/metadata.py`
  (v1/v2 validation, v3 refused until M7), `modularcv/review.py` (CVQualityReview-v1), `modularcv/paths.py` (portable safe paths).
- `modularcv/provenance.py`: `verify_recorded_commit`, `hash_at_commit`, reasons for missing/untracked/modified sources, workspace
  must be the root of its own Git repository, unified text normalisation (BOM, CRLF, lone CR).
- CLI: `check-packages DIR --root` (exit 0/1/2), `snapshot verify FILE`, `provenance --verify SHA [--recorded]`.
- Config: new optional key `applications_dir`; unsafe paths and non-object config are refused.
- Tests: `tests/synthetic.py` (temporary Git workspace), rewritten `tests/test_readiness.py`, new `tests/test_snapshot.py`.
  Existing tests that asserted the 0.1.0 fail-open behaviour were rewritten on purpose (listed in the M3 report); no test was
  weakened to hide a security regression.
- Docs: `PROVENANCE_READINESS.md` §6 (new reasons) and §9 (breaking changes, evidence layout, exit codes).

## Known defect

The `0.1.0` fail-open readiness defect is closed by M3 (pending validation). Residual points: see the M3 report (human approval
is a file, not a signature; the engine cannot know a file was written by a person).

## Open decisions (maintainer)

1. Cover letters deferred beyond M8.
2. `pdflatex` optional or required for the first release.
3. One generic taxonomy, or several domain taxonomies.
4. Whether `###` sub-headings should be allowed later (M2 refuses them).
5. Whether a signed or otherwise authenticated approval is wanted instead of the plain `cv-quality-review.json`.

Settled: strict `facts.md` grammar with optional `confirmed_on` (M2); M3 is a breaking `0.2.0` correction of `readiness`.

## Blockers

None.

## Next action

Wait for the maintainer's validation of M3 and the decision on tagging `0.2.0`. Do not start M4 or any later milestone before.
