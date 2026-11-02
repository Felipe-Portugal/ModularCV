<!-- modularcv: FactBase-v1 -->
<!--
  Example fact base in the strict FactBase-v1 format. Everything below is invented (fictional person,
  fictional employer). Copy it to `facts.md` in your private workspace and replace it with your own facts.
  Free prose is allowed only inside HTML comments such as this one.

  A fact line reads:   - [fact-id] STATUS: text {attribute: value; attribute: value}
  Statuses: CONFIRMED (publishable), DERIVED, NOT_CONFIRMED, WITHDRAWN (never publishable).
  Attributes: lang, confirmed_on, technologies, capabilities, source, supersedes, note.
  A continuation line is indented by four spaces. `confirmed_on` is optional and is never invented.
-->

# Fact base of Jordan Example (fictional)

## Experience {#experience}

- [exp.junior-dev.api] CONFIRMED: Built REST endpoints in Python for an internal tool.
    Wrote automated tests with pytest. {technologies: Python, pytest; capabilities: backend, testing; confirmed_on: 2026-01-10; lang: en}
- [exp.junior-dev.review] CONFIRMED: Took part in code reviews and sprint ceremonies. {capabilities: collaboration}
- [exp.junior-dev.speed] NOT_CONFIRMED: Improved the response time of the endpoints. {note: no measurement exists, do not claim}
- [exp.junior-dev.lead] WITHDRAWN: Led a team of three developers. {note: retracted, the role was a contribution only}
- [exp.junior-dev.lead-v2] DERIVED: Coordinated work with two other developers on a shared feature. {supersedes: exp.junior-dev.lead; note: wording derived from confirmed facts, needs a human decision}

## Education {#education}

- [edu.beng] CONFIRMED: B.Eng. in software engineering at Example University, 2024 to expected 2028. {confirmed_on: 2026-01}

## Skills {#skills}

- [skill.python] CONFIRMED: Python for scripting and automated tests. {technologies: Python; capabilities: backend}
- [skill.git] CONFIRMED: Daily use of Git for branches and pull requests. {technologies: Git; source: team handbook, fictional}
