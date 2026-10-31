# Governance

The method that keeps a CV pipeline honest when several people or agents (human, Claude, ChatGPT)
touch it.

## 1. Milestones with human validation
Work advances in numbered milestones. A milestone is `PASS` only when the owner validates it;
an agent may report *done, awaiting validation*, never *validated*. A blocked milestone stays
blocked until an explicit instruction. Decisions are recorded in a dated registry.

## 2. Facts first
- One fact base. A claim is either confirmed there, a *derived wording* (flagged for validation),
  or unconfirmed (never published).
- A correction from the owner overrides older wording everywhere and is propagated, with a record.
- No invented number, metric, technology or role. Missing information becomes a question.

## 3. Provenance
Every generated document records `source_commit`: a real commit in the workspace history whose
fact base, master and baselines equal the files used. Git missing, unknown SHA, modified source or
all-zero value means **no generation**. Old metadata is inventoried, never silently rewritten.

## 4. Fail-closed promotion
A package may be sent only if the declared state, every recorded gate, the staleness registry and the CV
metadata all agree. Any objection downgrades it: stale or invalid means *blocked*, unreviewed means
*needs review*. A secondary index can never promote a package. A registry that cannot be read blocks.

## 5. Portability of tests
- Tests run on committed **synthetic** fixtures, with no dependency on a private path.
- External inputs are configured by environment variable; a missing one is a clear diagnostic.
- Tests that need real private data are explicitly marked and *skipped with a reason*, never
  counted as passed.

## 6. Reorganising a messy workspace
1. Commit what exists, by theme, before moving anything.
2. Move documents and generated data first; leave paths read by other tools alone until their
   readers are updated.
3. Update the code that reads moved paths, regenerate derived manifests, run the full tests.
4. Only then commit the reorganisation, separately.

## 7. Agents
Agents work on a dedicated branch or worktree, never on a quarantined commit, and do not merge,
rebase, reset, push or delete without being asked. Nothing is sent to an employer automatically.
