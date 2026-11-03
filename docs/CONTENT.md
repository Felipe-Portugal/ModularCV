# Your resume content (ResumeContent-v1)

`content/resume.json` is the reservoir of text your future CVs are built from: experiences, projects, education, skills,
bullets, and the baselines that pick bullets by id. It holds **your words**, in your workspace, never in this repository. The
engine writes no new sentence: every line a CV will print is a line of this file.

The point of the file is traceability. Each bullet, each skill **and each block heading** names, in `supports`, the facts of your
`facts.md` that back it. A line may be printed only if all of those facts are `CONFIRMED`. The content file itself can never
confirm anything.

What needs proof and what does not:

| Needs `supports` (it states something about you) | Needs none (it only organises) |
|---|---|
| a block's heading: job title, employer, period, place, institution, degree | section titles, skill-category titles |
| each bullet (unless `never_publish`) | ids, `order`, `kind`, `protected` |
| each skill item | baselines and their `focus` |

A heading is checked as a whole by the block's `supports`; you cannot print a proven bullet under a title nobody confirmed.

## What `content check` does, and what it never checks

```bash
python -m modularcv content check                      # exit 0 valid and every reference verified
python -m modularcv content check --no-facts           # structure only: references stay UNVERIFIED, exit 3 (never 0)
python -m modularcv content check --profile profile.json   # also check baseline families and the date policy
python -m modularcv content check --outline            # add identifiers and states (never a text)
python -m modularcv content fingerprint --only content
```

| It checks | It never checks |
|---|---|
| The shape, the types, unknown fields, duplicate keys, `NaN` | That a bullet **means** what its supporting facts say |
| Identifiers, unique where they must be; the order of blocks | That the French and the English text of a bullet say the same thing (no equivalence check, no translation) |
| That each `supports` fact exists and is `CONFIRMED` (when a fact base is used), for headings, bullets and skills | Whether the fact really says what the heading, bullet or skill says |
| French/English parity **by identifier**: when an entity declares both `en` and `fr`, everything in it exists in both | Spelling, style or length of a line |
| No raw LaTeX; balanced `**bold**` and `_italic_` | Anything about an offer (that is a later milestone) |

Two ideas to keep in mind:

- **Structure is not verification.** Without a fact base, `content check` says `UNVERIFIED` and exits `3`. Only a run against your
  `facts.md` (the default) proves that the facts exist and are confirmed. Even then it proves existence and status, not meaning:
  choosing the right facts for a sentence stays a human decision, and so does checking a translation.
- **Nothing is inferred.** No date, technology, responsibility or achievement is deduced. A technology you list on a bullet is
  compared, as a name, with the technologies of its facts, and a mismatch is only a warning (`CONTENT_TECHNOLOGY_NOT_IN_SUPPORT`).

## The file

```json
{
  "schema": "ResumeContent-v1",
  "sections": [{"id": "experience", "kind": "experience", "title": {"en": "Experience", "fr": "Expérience"}}],
  "blocks": [{
    "id": "acme", "section": "experience", "order": 1, "languages": ["en", "fr"], "supports": ["exp.api"],
    "heading": {"en": {"title": "Developer", "period": "2025"}, "fr": {"title": "Développeur", "period": "2025"}},
    "bullets": [
      {"id": "acme.01", "text": {"en": "Built **REST** endpoints.", "fr": "Développement de points d'accès **REST**."},
       "supports": ["exp.api"], "technologies": ["Python"]}
    ]
  }],
  "skills": [{"id": "tools", "title": {"en": "Tools", "fr": "Outils"},
              "items": [{"id": "python", "text": {"en": "Python", "fr": "Python"}, "supports": ["skill.python"]}]}],
  "baselines": [{"family": "software", "language": "en", "items": ["acme.01"], "skills": ["python"]}]
}
```

Complete examples with a fictional fact base: `examples/workspace/content/` (`resume.json` is bilingual, `resume.fr.json` and
`resume.en.json` are single-language, `invalid/` holds files that must be refused).

- **Languages.** Write French only, English only, or both. A block lists the languages it is written in. If it lists both `en`
  and `fr`, its heading, its section title and each of its bullets must exist in both. Any other language (a third one, or a block
  that has no `en`/`fr` pair) carries no such obligation, but a text may only use a language its block lists. A French-only
  entry is a French-only block; it is simply not offered for an English CV. The engine never translates and never requires a
  second language, and it does not check that two versions say the same thing.
- **Identifiers.** Lowercase letters, digits, `.` and `-` (`acme.01`). They are the stable names baselines, links and the future
  selection use, so do not reuse one for something else. Bullet ids are unique across the whole file.
- **Order.** `order` places a block inside its section (unique there). The order of sections, of bullets inside a block, and of
  a baseline's `items` is the order written. The order of blocks in the file does not matter.
- **Links.** `follows` names a bullet of the same block that must be printed first; `condenses` lists bullets of the same block that
  it replaces (never selected together). `never_publish: true` keeps a bullet as a reminder; it needs no support but is never printed.
- **Text.** One line, up to 1000 characters. Write plain text: **every backslash is refused** (it is how LaTeX starts a command),
  while `%`, `&`, `$`, `#`, `_`, `{` and `}` are ordinary characters that the renderer will escape. This is blunt on purpose and
  also refuses a Windows path such as `C:\dir`: write `C:/dir` instead. It will be revisited with the renderer. `**bold**` and
  `_italic_` are the only markup.
- **Capabilities.** `capabilities` are lowercase identifiers with no controlled vocabulary yet: the taxonomy arrives with M6.
  Choose stable names; they are not checked against a list today.
- **Extensions.** Fields starting with `x-` are kept and ignored by the engine.

## Fingerprints

`content fingerprint` prints two hashes. `content_source_sha256` follows the file (line endings and a BOM never change it).
`content_sha256` follows the meaning: it ignores key order, layout, the Unicode form of a letter, spaces inside a text and an
explicit default value, and it changes with any real edit, including the order of bullets. See `CONTRACTS.md` section 3.2 for
every choice and error code.
