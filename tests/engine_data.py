"""Synthetic inputs for the offer, taxonomy, matrix and plan tests (M6). Fictional data only."""
import copy
import json

from modularcv import content, facts, joboffer, profile, taxonomy

FACTS = (
    "<!-- modularcv: FactBase-v1 -->\n## S {#s}\n"
    "- [f.job] CONFIRMED: A confirmed job fact. {confirmed_on: 2026-01}\n"
    "- [f.job2] CONFIRMED: Another confirmed job fact.\n"
    "- [f.py] CONFIRMED: Python work. {technologies: Python; capabilities: backend}\n"
    "- [f.test] CONFIRMED: Testing work. {technologies: pytest; capabilities: testing}\n"
    "- [f.docker] CONFIRMED: Docker usage. {technologies: Docker}\n"
    "- [f.team] CONFIRMED: Teamwork. {capabilities: collaboration}\n"
    "- [f.js] CONFIRMED: JavaScript work. {technologies: JavaScript}\n"
    "- [f.git] CONFIRMED: Git usage. {technologies: Git}\n"
    "- [f.plain] CONFIRMED: A fact that declares nothing.\n"
    "- [f.k8s] NOT_CONFIRMED: A Kubernetes claim. {technologies: Kubernetes}\n"
    "- [f.lead] WITHDRAWN: Led a team. {capabilities: project-management}\n"
    "- [f.java] DERIVED: Derived Java wording. {technologies: Java}\n"
)


def factbase(text=FACTS):
    return facts.parse_text(text)


def profile_doc(**changes):
    document = {
        "schema": "Profile-v1", "languages": ["en", "fr"], "default_language": "en",
        "identity": {"display_name": {"value": "Alex Sample", "visibility": "public"}},
        "families": {"software": {"label": "Software", "languages": ["en", "fr"], "clusters": ["backend", "testing"]}},
    }
    document.update(changes)
    return document


def make_profile(**changes):
    result = profile.check_data(profile_doc(**changes))
    assert not result.errors, [e.as_dict() for e in result.errors]
    return result.profile


def bullet(bullet_id, en, fr, supports, technologies=(), capabilities=(), **extra):
    record = {"id": bullet_id, "text": {"en": en, "fr": fr}, "supports": list(supports),
              "technologies": list(technologies), "capabilities": list(capabilities)}
    record.update(extra)
    return record


def content_doc():
    return {
        "schema": "ResumeContent-v1",
        "sections": [{"id": "experience", "kind": "experience", "title": {"en": "Experience", "fr": "Expérience"}}],
        "blocks": [{
            "id": "job", "section": "experience", "order": 1, "languages": ["en", "fr"], "supports": ["f.job"],
            "heading": {"en": {"title": "Developer"}, "fr": {"title": "Développeur"}},
            "bullets": [
                bullet("job.py", "Built services in Python.", "Services en Python.", ["f.py"], ["Python"], ["backend"]),
                bullet("job.test", "Wrote tests with pytest.", "Tests avec pytest.", ["f.test"], ["pytest"], ["testing"]),
                bullet("job.docker", "Packaged apps with Docker.", "Conteneurs Docker.", ["f.docker"], ["Docker"]),
                bullet("job.team", "Worked in a team.", "Travail en équipe.", ["f.team"], [], ["collaboration"]),
            ],
        }],
        "skills": [{"id": "tools", "title": {"en": "Tools", "fr": "Outils"}, "items": [
            {"id": "python", "text": {"en": "Python", "fr": "Python"}, "supports": ["f.py"], "technologies": ["Python"]},
            {"id": "git", "text": {"en": "Git", "fr": "Git"}, "supports": ["f.git"], "technologies": ["Git"]}]}],
    }


def make_content(document=None, base=None):
    result = content.check_data(document or content_doc())  # structure only: the engine re-checks the proof itself
    assert not result.errors, [e.as_dict() for e in result.errors]
    return result.content


def offer_doc(description="Requirements:\n- Python\n- pytest\n", **changes):
    document = {"schema": "JobOffer-v1", "job_key": "job-1", "title": "Developer", "company": "Example Co (fictional)",
                "language": "en", "description": description}
    document.update(changes)
    return document


def make_offer(description="Requirements:\n- Python\n- pytest\n", **changes):
    result = joboffer.check_data(offer_doc(description, **changes))
    assert not result.errors, [e.as_dict() for e in result.errors]
    return result.offer


def encode(document):
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


def tax():
    return taxonomy.builtin()


def mutable(document):
    return copy.deepcopy(document)
