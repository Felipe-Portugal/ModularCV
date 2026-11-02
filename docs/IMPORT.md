# Importing a historical document into your fact base

You may already have notes about your experience in some Markdown file: an old CV source, a list of achievements, a Q&A.
`facts import` turns such a document into a **proposed** `FactBase-v1` file, under rules that *you* write, and gives you a report
that accounts for every line. The engine knows nothing about your document: all the knowledge is in a mapping file that lives in
your private workspace. The contract is in `docs/design/CONTRACTS.md` section 1.5.1.

What the import never does:

- it never imports a line that no rule classifies, and never silently;
- it never makes a fact `CONFIRMED` on its own: that needs your mapping to say so twice;
- it never invents a date;
- it never modifies your document, and never overwrites an existing file;
- it never writes outside your workspace, and uses no network or model.

## Workflow

1. Write `import-map.json` in your workspace (see the example below and `examples/workspace/`).
2. Try it without writing anything:

   ```bash
   python -m modularcv facts import --mapping import-map.json --in legacy-notes.md --dry-run
   ```

   The report is printed. Fix the mapping until nothing is `UNCLASSIFIED`, `AMBIGUOUS` or `REJECTED`.
3. Run it for real; it creates two new files:

   ```bash
   python -m modularcv facts import --mapping import-map.json --in legacy-notes.md \
       --out facts.proposed.md --report import-report.json
   ```

4. Read `facts.proposed.md` and the report. **Review every fact**, then copy the ones you want into your `facts.md` yourself
   and check it with `python -m modularcv facts check`. The engine never edits your fact base.

Relative paths are resolved against the workspace (`--root`, `MODULARCV_ROOT` or the current directory). The mapping, `--out`
and `--report` must be inside the workspace and `--out`/`--report` must not exist yet. The legacy document may be anywhere.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Every line was classified and at least one fact was accepted. Files written (or `--dry-run` finished). |
| `1` | Incomplete: some lines are `UNCLASSIFIED`, `AMBIGUOUS` or `REJECTED`, or nothing was accepted. The report is written; the proposed facts are written **only** with `--allow-partial`. |
| `2` | Refused before doing anything: invalid mapping or workspace configuration, unreadable or non-UTF-8 input, a path outside the workspace, an output that exists, two paths that are the same file, a write error. |

## The mapping file (`LegacyFactMap-v1`)

```json
{
  "schema": "LegacyFactMap-v1",
  "allow_confirmed": true,
  "headings": [
    {"pattern": "Notes of .*", "action": "ignore", "level": 1},
    {"pattern": "Experience \\(checked\\)", "section": "experience", "title": "Experience", "status": "CONFIRMED", "lang": "en"},
    {"pattern": "Experience \\(to check\\)", "section": "experience-to-check", "status": "DERIVED"},
    {"pattern": "Tools", "action": "technologies"}
  ],
  "status_rules": [{"pattern": "\\[not confirmed\\]", "status": "NOT_CONFIRMED"}],
  "date_patterns": ["\\(confirmed (\\d{4}-\\d{2}-\\d{2})\\)"],
  "ignore_patterns": ["-{3,}"]
}
```

| Key | Meaning |
|---|---|
| `headings` | Required, ordered rules. `pattern` must match the **whole** heading text. `action`: `map` (default: needs `section` and `status`; optional `title`, `lang`), `ignore` (skip the bullets under it), `inherit` (keep the section of the parent heading), `technologies` (the bullets under it are a vocabulary of technology names). `level` restricts the rule to one heading level. Two rules that match one heading with different effects make it `AMBIGUOUS`. |
| `allow_confirmed` | Default `false`. Without `true`, a rule with `"status": "CONFIRMED"` makes the mapping invalid. |
| `status_rules` | Regexes searched in the bullet text. They can only **lower** a status (to `DERIVED`, `NOT_CONFIRMED` or `WITHDRAWN`); a rule that would raise the status rejects the line. |
| `date_patterns` | Regexes with exactly one group holding `YYYY`, `YYYY-MM` or `YYYY-MM-DD`. The date is set on `CONFIRMED` facts only; an invalid date rejects the line; two different dates make it ambiguous. |
| `ignore_patterns` | Regexes that must match a whole non-bullet line (a rule, front matter) to ignore it on purpose. |

Patterns are Python regular expressions (put `(?i)` at the start for case-insensitive matching).

## What the document may contain

Headings (`#` to `######`) and bullets (`-`, `*`, `+`, `1.`, `1)`); lines indented by two spaces or a tab continue the bullet above.
Prose, tables and anything else are `UNCLASSIFIED` unless you ignore them explicitly. A heading that no rule matches ends the
previous section: its bullets are `UNCLASSIFIED` until a heading rule applies.

## The report (`LegacyImportReport-v1`)

Deterministic JSON (no timestamp). It holds the hashes of the mapping and of the legacy document, the counts, the facts per status,
the fingerprints of the proposed fact base, and one entry per non-blank line:

```json
{"line": 7, "end_line": 7, "kind": "BULLET", "decision": "ACCEPTED", "code": null, "rule": 1,
 "section": "experience", "status": "CONFIRMED", "fact_id": "experience.5be87343e5", "dated": true, "unit_sha256": "..."}
```

| Decision | Meaning |
|---|---|
| `ACCEPTED` | Written as a fact. |
| `DUPLICATE` | Same text (and status) as an earlier line, listed under `duplicate_of`; not written twice. |
| `IGNORED` | Skipped by one of your rules. |
| `TECHNOLOGY` | An entry of your technology vocabulary. |
| `UNCLASSIFIED` | `FACT_UNMAPPED`: no rule applies. Not imported. |
| `AMBIGUOUS` | Two rules disagree. Not imported. |
| `REJECTED` | Classified but unusable (invalid date, text ending in `}`, control character, over-long line, promotion refused). Not imported. |

The report never contains the text of your lines, only their line numbers and a hash (`unit_sha256`) so that you can check which
line a decision belongs to. Keep it in your private workspace anyway.

## The proposed fact base

Each fact reads `- [section.<hash>] STATUS: text {lang?; confirmed_on?; technologies?; source: legacy-import:<document hash>:L<line>}`.
The `source` attribute points back to the line of the original document. The file is parsed by the real `FactBase-v1` parser before
it is written; if that fails nothing is written.
