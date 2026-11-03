# PROJECT_STATE.md

Source of truth for progress. Update it at the end of every session (see `AGENTS.md` §8).

## Repository

- Branch: `main`. Baseline of M4: `1114663` (M3, validated). M4 commits: `b38e1c8`, `4244cf9`. M4-R1 is committed locally on top. Earlier: `17bcf18` (M3 code), `ab35c91` (M2-R1), `d34af49`, `4865a27`,
  `0a553e1` (initial `0.1.0`). M4 is committed locally on top (see `git log`); nothing is pushed.
- Remote: `origin` (private). Nothing is published; no tag, no release.
- Version: `0.2.0` (proposed in M3, unpublished; M4 adds features without a version change); not tagged.
- Tests: `py -3.9 -m pytest` gives 652 passed and 1 skipped (a symlink test that only runs off Windows), 653 collected; synthetic
  data only. Before M4: 376; after M4: 612. Linux: no pytest run (not installed in WSL); a stdlib smoke test of the CLI passed on
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
| M4 | Profile-v1 and legacy fact import | Rated PARTIAL; M4-R1 closure done, awaiting validation |
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

## Last work (M4-R1)

- `profile check --no-facts` returned exit 0 and status `OK` while availability references stayed `UNVERIFIED`. It now exits `3`
  with status `UNVERIFIED` and a warning on stderr whenever a fact reference was not verified; with no reference to verify it
  still exits 0. `0` now means valid **and** verified (8 net new tests; the old test that expected 0 was replaced on purpose). Documented in `CONTRACTS.md` §2.1, `WORKSPACE.md` and the CLI docstring.
- Importer `CONFIRMED` policy audited: no violation found, no code change. Added 32 tests (flag types, full heading/rule status
  matrix, ambiguity, inherit, dates, traceability to the authorising rule, random documents and mappings) and checked that a
  removed promotion guard makes them fail. `IMPORT.md` and `CONTRACTS.md` §1.5.1 now separate the mapping's authorisation from
  the user's fact-by-fact verification.
- Foreign file investigated read-only (below). Nothing moved, ignored or committed.

## Known defects and anomalies

- Residual points of M3 stand: the human approval is a file, not a signature.
- Untracked file `modularcv/legacy_import.py`, **not written by the M4 work**: 714 lines, 35,017 bytes, SHA-256
  `5c73e936d25ce534dc13b8ef77005630f1643f96092140a3b690b190a2504106`, created 2026-11-02 15:03:50 and last written 15:04:01
  (-0500). It is a parallel implementation of the same importer (`LegacyFactMap-v1`), it imports `profile.fold`, which does not
  exist (`fold` lives in `canonical`), so importing it raises `ImportError`; nothing in the tracked code, the tests or the docs
  references it; it holds no network, `exec` or `eval` call. Setuptools lists the whole `modularcv` package, so a build made from
  this working tree would ship it; a build from a clean checkout would not. Origin: **not established**. One indication only:
  the transcript search finds a write-result message naming this path in another local session (working directory outside
  ModularCV, last active 15:11 the same day); that is evidence, not proof. It is left exactly as found.
  Proposed reversible isolation (needs the maintainer's authorisation): move it, unchanged, to a folder outside the repository
  (for example `D:\Projets\ModularCV\_quarantine\`), keep the SHA-256 above to check it later, and move it back to restore.
  Do not rely on `.gitignore` or `.git/info/exclude`: they would hide it from Git but not from a build.

## Open decisions (maintainer)

1. Cover letters deferred beyond M8.
2. `pdflatex` optional or required for the first release.
3. One generic taxonomy, or several domain taxonomies.
4. Whether `###` sub-headings should be allowed later (M2 refuses them).
5. Whether a signed or otherwise authenticated approval is wanted instead of the plain `cv-quality-review.json`.
6. Whether the first release tags `0.2.0` or `0.3.0` now that `Profile-v1` and the import are in (M4 changed no version).
7. What to do with the foreign `modularcv/legacy_import.py` (isolate, delete or keep), see above.
8. Whether `facts import` should refuse `--out` pointing at the configured fact base, so that a proposal can never become the
   source of truth without the review step (today only documented; an existing file is never overwritten).

Settled: strict `facts.md` grammar with optional `confirmed_on` (M2); M3 is a breaking `0.2.0` correction of `readiness`; the
import never confirms by itself (M4).

## Blockers

None.

## Next action

Wait for the maintainer's validation of M4 / M4-R1 and the decisions 7 and 8 above. Do not start M5 or any later milestone
before.
