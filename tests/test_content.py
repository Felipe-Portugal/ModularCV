"""ResumeContent-v1: structure, fact references, FR/EN parity, fingerprints, CLI (M5). Synthetic data only."""
import ast
import copy
import json
import random
import re
import shutil
import unicodedata
from pathlib import Path

import pytest

from modularcv import __main__ as cli
from modularcv import canonical, content, facts, profile
from synthetic import tree_hash

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = REPO / "examples" / "workspace"
SECRET = "ZXQ private é 9931"

FACTS = (
    "<!-- modularcv: FactBase-v1 -->\n## S {#s}\n"
    "- [fact.one] CONFIRMED: A confirmed fact. {technologies: Python, pytest; confirmed_on: 2026-02}\n"
    "- [fact.two] CONFIRMED: Another confirmed fact. {technologies: Git}\n"
    "- [fact.derived] DERIVED: A derived wording.\n"
    "- [fact.unsure] NOT_CONFIRMED: A claim that must not be made.\n"
    "- [fact.gone] WITHDRAWN: A retracted claim.\n"
)


def minimal():
    return {
        "schema": "ResumeContent-v1",
        "sections": [{"id": "experience", "kind": "experience", "title": {"en": "Experience"}}],
        "blocks": [{
            "id": "job", "section": "experience", "order": 1, "languages": ["en"], "supports": ["fact.one"],
            "heading": {"en": {"title": "Developer"}},
            "bullets": [{"id": "job.01", "text": {"en": "Built a thing."}, "supports": ["fact.one"]}],
        }],
    }


def bilingual():
    document = minimal()
    document["sections"][0]["title"]["fr"] = "Expérience"
    block = document["blocks"][0]
    block["languages"] = ["en", "fr"]
    block["heading"]["fr"] = {"title": "Développeur"}
    block["bullets"][0]["text"]["fr"] = "A construit une chose."
    return document


def encode(document):
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


def factbase(text=FACTS):
    return facts.parse_text(text)


def check(document, with_facts=True, **kwargs):
    return content.check_bytes(encode(document), factbase() if with_facts else None, **kwargs)


def codes(result):
    return [error.code for error in result.errors]


def set_at(document, dotted, value):
    node = document
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return document


def drop_at(document, dotted):
    node = document
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    del node[parts[-1]]
    return document


def valid(document, **kwargs):
    result = check(document, **kwargs)
    assert not result.errors, [e.as_dict() for e in result.errors]
    return result


def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(str(EXAMPLE_DIR), str(root))
    return root


# --- valid documents --------------------------------------------------------------------------------------

def test_a_minimal_document_is_valid_and_its_defaults_are_filled_in():
    result = valid(minimal())
    model = result.content.to_model()
    block = model["blocks"][0]
    bullet = block["bullets"][0]
    assert block["supports"] == ["fact.one"]
    assert block["protected"] is False and block["heading"]["en"] == {
        "title": "Developer", "subtitle": None, "period": None, "place": None}
    assert bullet == {"id": "job.01", "text": {"en": "Built a thing."}, "supports": ["fact.one"], "technologies": [],
                      "capabilities": [], "follows": None, "condenses": [], "never_publish": False}
    assert model["skills"] == [] and model["baselines"] == []
    assert result.content.counts()["bullets"] == 1


def test_the_complete_example_is_valid_with_the_fact_base_and_the_profile():
    facts_result = facts.check_file(EXAMPLE_DIR / "facts.md")
    profile_result = profile.check_file(EXAMPLE_DIR / "profile.json")
    result = content.check_file(EXAMPLE_DIR / "content" / "resume.json", facts_result.factbase, profile_result.profile)
    assert not result.errors and not result.warnings
    counts = result.content.counts()
    assert counts["blocks"] == 3 and counts["bilingual_blocks"] == 3 and counts["baselines"] == 2
    assert counts["never_publish_bullets"] == 1 and counts["skill_items"] == 2
    states = {entity_id: state for _kind, entity_id, state in result.references}
    assert states["junior-dev.05"] == "NEVER_PUBLISH" and states["junior-dev.01"] == "VERIFIED"
    assert states["python"] == "VERIFIED"


@pytest.mark.parametrize("name,languages", [("resume.fr.json", ("fr",)), ("resume.en.json", ("en",)),
                                            ("resume.json", ("en", "fr"))])
def test_french_only_english_only_and_bilingual_content_are_all_valid(name, languages):
    facts_result = facts.check_file(EXAMPLE_DIR / "facts.md")
    result = content.check_file(EXAMPLE_DIR / "content" / name, facts_result.factbase)
    assert not result.errors and result.content.languages == languages


def test_no_second_language_is_ever_required():
    result = valid(minimal())
    assert result.content.languages == ("en",)
    other = minimal()
    other["sections"][0]["title"] = {"fr": "Expérience"}
    other["blocks"][0].update(languages=["fr"], heading={"fr": {"title": "Développeur"}})
    other["blocks"][0]["bullets"][0]["text"] = {"fr": "A construit une chose."}
    assert valid(other).content.languages == ("fr",)


def test_a_one_language_block_in_another_language_is_valid():
    document = minimal()
    document["sections"][0]["title"] = {"de": "Erfahrung"}
    document["blocks"][0].update(languages=["de"], heading={"de": {"title": "Entwickler"}})
    document["blocks"][0]["bullets"][0]["text"] = {"de": "Etwas gebaut."}
    assert valid(document).content.languages == ("de",)


def test_a_block_without_bullets_is_valid_for_a_heading_only_entry():
    document = minimal()
    document["blocks"][0]["bullets"] = []
    assert valid(document).content.counts()["bullets"] == 0
    drop_at(document, "blocks.0.bullets")
    assert valid(document).content.counts()["bullets"] == 0


# --- identifiers ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["Upper", "has space", "", "a" * 81, "trailing\n", "-lead", "dot..dot", "é", 5, None])
@pytest.mark.parametrize("where", ["sections.0.id", "blocks.0.id", "blocks.0.bullets.0.id"])
def test_an_invalid_identifier_is_refused(where, bad):
    result = check(set_at(minimal(), where, bad))
    assert "CONTENT_INVALID_ID" in codes(result) and result.content is None


def test_identifiers_are_unique_per_namespace_and_bullets_are_unique_across_blocks():
    document = minimal()
    document["blocks"].append(copy.deepcopy(document["blocks"][0]))
    document["blocks"][1]["id"] = "job-2"
    document["blocks"][1]["order"] = 2
    result = check(document)
    assert codes(result) == ["CONTENT_DUPLICATE_ID"]
    assert result.errors[0].path == "blocks[1].bullets[0].id"
    document["blocks"][1]["bullets"][0]["id"] = "job-2.01"
    valid(document)


def test_the_same_identifier_may_live_in_different_namespaces():
    document = minimal()
    document["blocks"][0]["id"] = "experience"          # same as the section
    document["blocks"][0]["bullets"][0]["id"] = "experience"  # and as the block
    valid(document)


def test_duplicate_sections_blocks_skills_and_categories_are_refused():
    document = minimal()
    document["sections"].append(copy.deepcopy(document["sections"][0]))
    assert "CONTENT_DUPLICATE_ID" in codes(check(document))
    document = minimal()
    document["blocks"].append(copy.deepcopy(document["blocks"][0]))
    assert "CONTENT_DUPLICATE_ID" in codes(check(document))
    document = minimal()
    skill = {"id": "py", "text": {"en": "Python"}, "supports": ["fact.one"]}
    document["skills"] = [{"id": "cat", "title": {"en": "Tools"}, "items": [skill, copy.deepcopy(skill)]}]
    assert "CONTENT_DUPLICATE_ID" in codes(check(document))
    document["skills"] = [{"id": "cat", "title": {"en": "A"}, "items": [skill]},
                          {"id": "cat", "title": {"en": "B"}, "items": [dict(skill, id="py2")]}]
    assert "CONTENT_DUPLICATE_ID" in codes(check(document))


# --- order --------------------------------------------------------------------------------------------------

def two_blocks():
    document = minimal()
    second = copy.deepcopy(document["blocks"][0])
    second.update(id="job-2", order=2)
    second["bullets"][0]["id"] = "job-2.01"
    document["blocks"].append(second)
    return document


def test_two_blocks_of_one_section_cannot_share_an_order():
    document = two_blocks()
    document["blocks"][1]["order"] = 1
    assert codes(check(document)) == ["CONTENT_DUPLICATE_ORDER"]
    document["sections"].append({"id": "projects", "kind": "project", "title": {"en": "Projects"}})
    document["blocks"][1]["section"] = "projects"
    valid(document)  # the same order in another section is fine


@pytest.mark.parametrize("bad,code", [(0, "CONTENT_OUT_OF_RANGE"), (10000, "CONTENT_OUT_OF_RANGE"),
                                      (True, "CONTENT_BAD_TYPE"), ("1", "CONTENT_BAD_TYPE"), (1.5, "CONTENT_BAD_TYPE"),
                                      (None, "CONTENT_BAD_TYPE")])
def test_the_order_must_be_a_small_positive_integer(bad, code):
    assert codes(check(set_at(minimal(), "blocks.0.order", bad))) == [code]


def test_blocks_are_stored_in_print_order_whatever_their_position_in_the_file():
    document = two_blocks()
    forward = valid(document).content
    document["blocks"].reverse()
    backward = valid(document).content
    assert [b["id"] for b in forward.to_model()["blocks"]] == ["job", "job-2"]
    assert forward.content_sha256 == backward.content_sha256


def test_changing_an_order_or_a_list_that_carries_meaning_changes_the_fingerprint():
    base = valid(two_blocks()).content.content_sha256
    swapped = two_blocks()
    swapped["blocks"][0]["order"], swapped["blocks"][1]["order"] = 2, 1
    assert valid(swapped).content.content_sha256 != base

    document = minimal()
    document["blocks"][0]["bullets"].append({"id": "job.02", "text": {"en": "Second."}, "supports": ["fact.two"]})
    first = valid(document).content.content_sha256
    document["blocks"][0]["bullets"].reverse()
    assert valid(document).content.content_sha256 != first  # bullets print in list order

    document = minimal()
    document["sections"].append({"id": "projects", "kind": "project", "title": {"en": "Projects"}})
    first = valid(document).content.content_sha256
    document["sections"].reverse()
    assert valid(document).content.content_sha256 != first  # sections print in list order

    document = minimal()
    document["blocks"][0]["bullets"][0]["technologies"] = ["Python", "pytest"]
    first = valid(document).content.content_sha256
    document["blocks"][0]["bullets"][0]["technologies"] = ["pytest", "Python"]
    assert valid(document).content.content_sha256 != first  # display order of technologies is kept


def test_sets_do_not_depend_on_the_order_they_were_written_in():
    document = minimal()
    document["blocks"][0]["bullets"][0]["supports"] = ["fact.two", "fact.one"]
    document["blocks"][0]["bullets"][0]["capabilities"] = ["testing", "backend"]
    result = valid(document).content
    assert result.to_model()["blocks"][0]["bullets"][0]["supports"] == ["fact.one", "fact.two"]
    document["blocks"][0]["bullets"][0]["supports"].reverse()
    document["blocks"][0]["bullets"][0]["capabilities"].reverse()
    assert valid(document).content.content_sha256 == result.content_sha256


# --- references to the fact base ----------------------------------------------------------------------------

def test_every_publishable_bullet_must_name_its_supporting_facts():
    document = minimal()
    for change in (lambda d: set_at(d, "blocks.0.bullets.0.supports", []),
                   lambda d: drop_at(d, "blocks.0.bullets.0.supports")):
        result = check(change(copy.deepcopy(document)), with_facts=False)
        assert codes(result) == ["CONTENT_UNSUPPORTED_BULLET"] and result.content is None


@pytest.mark.parametrize("fact_id,status", [("fact.derived", "DERIVED"), ("fact.unsure", "NOT_CONFIRMED"),
                                            ("fact.gone", "WITHDRAWN")])
def test_a_fact_that_is_not_confirmed_never_supports_a_publication(fact_id, status):
    result = check(set_at(minimal(), "blocks.0.bullets.0.supports", [fact_id]))
    assert result.content is None
    assert sorted(codes(result)) == ["CONTENT_FACT_NOT_CONFIRMED", "CONTENT_UNSUPPORTED_BULLET"]
    assert any(status in e.message for e in result.errors)


def test_an_unknown_fact_is_reported_and_the_bullet_is_unsupported():
    result = check(set_at(minimal(), "blocks.0.bullets.0.supports", ["fact.missing"]))
    assert sorted(codes(result)) == ["CONTENT_FACT_UNKNOWN", "CONTENT_UNSUPPORTED_BULLET"]
    assert {e.path for e in result.errors} == {"blocks[0].bullets[0]", "blocks[0].bullets[0].supports[0]"}


def test_one_unconfirmed_fact_among_confirmed_ones_is_enough_to_refuse():
    result = check(set_at(minimal(), "blocks.0.bullets.0.supports", ["fact.one", "fact.two", "fact.unsure"]))
    assert "CONTENT_UNSUPPORTED_BULLET" in codes(result) and result.content is None


def test_skills_need_confirmed_support_too():
    document = minimal()
    document["skills"] = [{"id": "cat", "title": {"en": "Tools"},
                           "items": [{"id": "py", "text": {"en": "Python"}, "supports": ["fact.derived"]}]}]
    result = check(document)
    assert sorted(codes(result)) == ["CONTENT_FACT_NOT_CONFIRMED", "CONTENT_UNSUPPORTED_SKILL"]
    set_at(document, "skills.0.items.0.supports", [])
    assert codes(check(document, with_facts=False)) == ["CONTENT_UNSUPPORTED_SKILL"]
    set_at(document, "skills.0.items.0.supports", ["fact.two"])
    valid(document)


def test_a_never_publish_bullet_needs_no_support_but_a_named_fact_must_exist():
    document = minimal()
    document["blocks"][0]["bullets"].append({"id": "job.02", "text": {"en": "Kept as a reminder."},
                                             "never_publish": True})
    valid(document, with_facts=False)
    set_at(document, "blocks.0.bullets.1.supports", ["fact.unsure"])  # not confirmed: allowed, it is never printed
    result = valid(document)
    assert dict((e, s) for _k, e, s in result.references)["job.02"] == "NEVER_PUBLISH"
    set_at(document, "blocks.0.bullets.1.supports", ["fact.missing"])
    assert codes(check(document)) == ["CONTENT_FACT_UNKNOWN"]


def test_without_a_fact_base_references_are_never_presented_as_verified():
    result = check(minimal(), with_facts=False)
    assert not result.errors and [w.code for w in result.warnings] == ["CONTENT_FACTS_NOT_CHECKED"]
    assert {state for _k, _e, state in result.references} == {"UNVERIFIED"}
    verified = check(minimal())
    assert not verified.warnings and {state for _k, _e, state in verified.references} == {"VERIFIED"}


def test_a_heading_reference_is_always_left_to_verify_even_when_no_bullet_is_publishable():
    document = minimal()
    document["blocks"][0]["bullets"] = [{"id": "job.01", "text": {"en": "Reminder."}, "never_publish": True}]
    result = check(document, with_facts=False)
    assert [w.code for w in result.warnings] == ["CONTENT_FACTS_NOT_CHECKED"]
    assert {(k, s) for k, _e, s in result.references} == {("heading", "UNVERIFIED"), ("bullet", "NEVER_PUBLISH")}


def test_the_confirmation_date_policy_of_a_profile_applies_to_supporting_facts():
    strict = profile.check_data({"schema": "Profile-v1", "languages": ["en"],
                                 "identity": {"display_name": {"value": "Alex Sample", "visibility": "public"}},
                                 "families": {"software": {"label": "Software", "languages": ["en"]}},
                                 "policy": {"require_confirmation_date": True}}).profile
    document = set_at(minimal(), "blocks.0.bullets.0.supports", ["fact.two"])  # confirmed, undated
    assert valid(document).content is not None
    result = check(document, profile=strict)
    assert sorted(codes(result)) == ["CONTENT_FACT_DATE_REQUIRED", "CONTENT_UNSUPPORTED_BULLET"]
    valid(minimal(), profile=strict)  # fact.one is dated


def test_a_technology_no_supporting_fact_lists_is_flagged_not_added_or_removed():
    document = minimal()
    document["blocks"][0]["bullets"][0]["technologies"] = ["python", "Rust"]  # case-insensitive match for the first
    result = valid(document)
    assert [(w.code, w.path) for w in result.warnings] == [
        ("CONTENT_TECHNOLOGY_NOT_IN_SUPPORT", "blocks[0].bullets[0].technologies[1]")]
    assert result.content.to_model()["blocks"][0]["bullets"][0]["technologies"] == ["python", "Rust"]


def test_content_has_no_way_to_carry_a_status_so_nothing_is_ever_confirmed_by_it():
    for field in ("status", "confirmed", "confirmed_on", "verified", "publishable"):
        document = minimal()
        document["blocks"][0]["bullets"][0][field] = "CONFIRMED"
        result = check(document)
        assert "CONTENT_UNKNOWN_FIELD" in codes(result), field


def test_selectable_follows_the_fact_base_and_the_content_cannot_override_it():
    document = minimal()
    document["blocks"][0]["bullets"] += [
        {"id": "job.02", "text": {"en": "Derived claim."}, "supports": ["fact.derived"]},
        {"id": "job.03", "text": {"en": "Reminder."}, "never_publish": True}]
    parsed = content.check_data(document).content  # structure only: nothing is verified yet
    assert parsed is not None
    assert [e.bullet_id for e in parsed.selectable(factbase(), "en")] == ["job.01"]
    promoted = FACTS.replace("DERIVED: A derived", "CONFIRMED: A derived")
    assert [e.bullet_id for e in parsed.selectable(factbase(promoted), "en")] == ["job.01", "job.02"]
    withdrawn = FACTS.replace("[fact.one] CONFIRMED", "[fact.one] WITHDRAWN")
    assert parsed.selectable(factbase(withdrawn), "en") == ()
    assert parsed.selectable(factbase(), "fr") == ()


def test_the_reservoir_lists_every_bullet_in_print_order_with_its_explicit_support():
    result = valid(two_blocks()).content
    entries = result.reservoir()
    assert [e.bullet_id for e in entries] == ["job.01", "job-2.01"]
    assert entries[0].supports == ("fact.one",) and entries[0].languages == ("en",) and entries[0].block_order == 1
    assert result.fact_ids() == ("fact.one",)


# --- languages and parity -----------------------------------------------------------------------------------

def test_a_bilingual_document_is_valid_and_parity_is_by_entity_id_not_by_position():
    document = bilingual()
    document["blocks"][0]["bullets"].append({"id": "job.02", "text": {"en": "Second.", "fr": "Deuxième."},
                                             "supports": ["fact.two"]})
    first = valid(document).content
    document["blocks"][0]["bullets"].reverse()
    second = valid(document).content
    for model in (first.to_model(), second.to_model()):
        by_id = {b["id"]: b["text"] for b in model["blocks"][0]["bullets"]}
        assert by_id["job.01"] == {"en": "Built a thing.", "fr": "A construit une chose."}
        assert by_id["job.02"] == {"en": "Second.", "fr": "Deuxième."}  # the two languages stay attached to the id


@pytest.mark.parametrize("change,code", [
    (lambda d: d["blocks"][0]["bullets"][0]["text"].pop("fr"), "CONTENT_PARITY_BULLET"),
    (lambda d: d["blocks"][0]["bullets"][0]["text"].update(de="Etwas."), "CONTENT_PARITY_BULLET"),
    (lambda d: d["blocks"][0]["heading"].pop("fr"), "CONTENT_PARITY_HEADING"),
    (lambda d: d["blocks"][0]["heading"].update(de={"title": "x"}), "CONTENT_PARITY_HEADING"),
    (lambda d: d["sections"][0]["title"].pop("fr"), "CONTENT_PARITY_TITLE"),
])
def test_drift_between_the_declared_languages_of_an_entity_is_an_error_never_repaired(change, code):
    document = bilingual()
    change(document)
    result = check(document)
    assert code in codes(result) and result.content is None


def test_parity_binds_only_where_an_entity_declares_both_languages():
    document = bilingual()
    document["blocks"].append({"id": "side", "section": "experience", "order": 2, "languages": ["fr"],
                               "supports": ["fact.two"], "heading": {"fr": {"title": "Seulement"}},
                               "bullets": [{"id": "side.01", "text": {"fr": "Français seulement."},
                                            "supports": ["fact.two"]}]})
    result = valid(document).content
    assert [e.bullet_id for e in result.selectable(factbase(), "en")] == ["job.01"]
    assert [e.bullet_id for e in result.selectable(factbase(), "fr")] == ["job.01", "side.01"]


def test_skill_categories_and_items_follow_the_same_parity_rule():
    document = bilingual()
    document["skills"] = [{"id": "cat", "title": {"en": "Tools", "fr": "Outils"},
                           "items": [{"id": "py", "text": {"en": "Python", "fr": "Python"}, "supports": ["fact.one"]}]}]
    valid(document)
    document["skills"][0]["items"][0]["text"].pop("fr")
    assert codes(check(document)) == ["CONTENT_PARITY_ITEM"]
    document["skills"][0]["items"][0]["text"]["fr"] = "Python"
    document["skills"][0]["title"].pop("fr")
    assert codes(check(document)) == ["CONTENT_PARITY_ITEM"]


def test_the_engine_makes_no_claim_about_the_equivalence_of_two_languages():
    document = bilingual()
    set_at(document, "blocks.0.bullets.0.text.fr", "Un texte qui ne dit pas du tout la même chose.")
    assert valid(document).content is not None  # undetectable by design: parity is structural, by id


def test_the_report_states_what_is_never_checked(workspace, capsys):
    code, out, _ = run(capsys, "content", "check", "--root", str(workspace))
    report = json.loads(out)
    assert code == 0 and report["semantic_equivalence_checked"] is False
    assert report["parity"] == "by entity id, structure only" and report["facts_checked"] is True


# --- links between bullets and baselines ----------------------------------------------------------------------

def linked():
    document = minimal()
    document["blocks"][0]["bullets"] += [
        {"id": "job.02", "text": {"en": "Second."}, "supports": ["fact.two"]},
        {"id": "job.03", "text": {"en": "Third, built on the first."}, "supports": ["fact.one"], "follows": "job.01"},
        {"id": "job.04", "text": {"en": "Condensed."}, "supports": ["fact.one"], "condenses": ["job.01", "job.02"]},
        {"id": "job.05", "text": {"en": "Reminder."}, "never_publish": True}]
    return document


def test_follows_and_condenses_name_other_bullets_of_the_same_block():
    valid(linked())
    for field, value in (("follows", "job.99"), ("condenses", ["job.99"])):
        document = linked()
        set_at(document, "blocks.0.bullets.2.%s" % field, value)
        assert codes(check(document)) == ["CONTENT_UNKNOWN_BULLET"]
    document = two_blocks()
    set_at(document, "blocks.1.bullets.0.follows", "job.01")  # a bullet of another block
    assert codes(check(document)) == ["CONTENT_UNKNOWN_BULLET"]


def test_a_bullet_cannot_follow_or_condense_itself_and_links_cannot_loop():
    document = linked()
    set_at(document, "blocks.0.bullets.2.follows", "job.03")
    assert codes(check(document)) == ["CONTENT_INVALID_REFERENCE"]
    document = linked()
    set_at(document, "blocks.0.bullets.3.condenses", ["job.04"])
    assert codes(check(document)) == ["CONTENT_INVALID_REFERENCE"]
    document = linked()
    set_at(document, "blocks.0.bullets.0.follows", "job.03")  # job.01 -> job.03 -> job.01
    assert codes(check(document)) == ["CONTENT_REFERENCE_CYCLE"]
    document = linked()
    set_at(document, "blocks.0.bullets.0.condenses", ["job.04"])  # job.04 condenses job.01 condenses job.04
    assert codes(check(document)) == ["CONTENT_REFERENCE_CYCLE"]


def with_baseline(**changes):
    document = linked()
    baseline = {"family": "software", "language": "en", "items": ["job.01", "job.03", "job.02"], "skills": [],
                "focus": "Backend"}
    baseline.update(changes)
    document["baselines"] = [baseline]
    return document


def test_a_baseline_selects_items_by_id_and_keeps_their_order():
    result = valid(with_baseline()).content
    assert result.baseline("software", "en")["items"] == ["job.01", "job.03", "job.02"]
    assert result.baseline("software", "fr") is None
    other = valid(with_baseline(items=["job.01", "job.02", "job.03"])).content
    assert other.content_sha256 != result.content_sha256


@pytest.mark.parametrize("changes,code", [
    ({"items": ["job.99"]}, "CONTENT_UNKNOWN_BULLET"),
    ({"items": ["job.05"]}, "CONTENT_BASELINE_NEVER_PUBLISH"),
    ({"language": "fr"}, "CONTENT_BASELINE_LANGUAGE"),
    ({"items": ["job.04", "job.01"]}, "CONTENT_BASELINE_EXCLUSIVE"),
    ({"items": ["job.03"]}, "CONTENT_BASELINE_FOLLOWS"),
    ({"items": ["job.03", "job.01"]}, "CONTENT_BASELINE_FOLLOWS"),
    ({"items": ["job.01", "job.01"]}, "CONTENT_DUPLICATE_VALUE"),
    ({"skills": ["nothing"]}, "CONTENT_UNKNOWN_SKILL"),
    ({"family": "Bad Family"}, "CONTENT_INVALID_ID"),
    ({"focus": "Needs \\textbf{LaTeX}"}, "CONTENT_RAW_LATEX"),
])
def test_baseline_rules(changes, code):
    result = check(with_baseline(**changes))
    assert code in codes(result) and result.content is None


def test_one_baseline_per_family_and_language_and_a_profile_checks_the_family():
    document = with_baseline()
    document["baselines"].append(copy.deepcopy(document["baselines"][0]))
    assert codes(check(document)) == ["CONTENT_DUPLICATE_BASELINE"]
    known = profile.check_data({"schema": "Profile-v1", "languages": ["en", "fr"], "default_language": "en",
                                "identity": {"display_name": {"value": "Alex Sample", "visibility": "public"}},
                                "families": {"software": {"label": "Software", "languages": ["en"]}}}).profile
    assert known is not None
    valid(with_baseline(), profile=known)
    assert codes(check(with_baseline(family="other"), profile=known)) == ["CONTENT_BASELINE_FAMILY_UNKNOWN"]
    document = bilingual()
    document["baselines"] = [{"family": "software", "language": "fr", "items": ["job.01"]}]
    assert codes(check(document, profile=known)) == ["CONTENT_BASELINE_FAMILY_LANGUAGE"]
    valid(with_baseline())  # without a profile the family is just an identifier


# --- text: plain Unicode, raw LaTeX refused, inline subset ---------------------------------------------------

ORDINARY = ["50% faster", "R&D team", "C# and F#", "Saved $5 per run", "Used {braces} and ~tilde ^caret", "Ticket #1",
            "snake_case_name and file_name_here", "100 % sure", "a * b", "Émile à l'œuvre – 日本語", "email@example.com"]


@pytest.mark.parametrize("text", ORDINARY)
def test_ordinary_characters_are_not_mistaken_for_typesetting_commands(text):
    assert valid(set_at(minimal(), "blocks.0.bullets.0.text.en", text)).content is not None


@pytest.mark.parametrize("text", ["\\textbf{x}", "a \\\\ b", "50\\% faster", "\\begin{itemize}", "path C:\\dir", "end\\"])
@pytest.mark.parametrize("where", ["blocks.0.bullets.0.text.en", "blocks.0.heading.en.title",
                                   "blocks.0.heading.en.subtitle", "sections.0.title.en"])
def test_raw_latex_is_refused_in_every_text(where, text):
    result = check(set_at(minimal(), where, text))
    assert codes(result) == ["CONTENT_RAW_LATEX"] and result.content is None


def test_raw_latex_is_refused_in_skills_technologies_and_extensions_are_not_text():
    document = minimal()
    document["skills"] = [{"id": "cat", "title": {"en": "Tools"},
                           "items": [{"id": "py", "text": {"en": "\\Python"}, "supports": ["fact.one"]}]}]
    assert codes(check(document)) == ["CONTENT_RAW_LATEX"]
    document = set_at(minimal(), "blocks.0.bullets.0.technologies", ["\\LaTeX"])
    assert codes(check(document)) == ["CONTENT_RAW_LATEX"]


@pytest.mark.parametrize("text", ["**bold** word", "_italic_ word", "**_both_**", "_**both**_", "a **b** and _c_ d",
                                  "snake_case and _x_"])
def test_balanced_inline_markers_are_accepted(text):
    assert valid(set_at(minimal(), "blocks.0.bullets.0.text.en", text)).content is not None


@pytest.mark.parametrize("text", ["**open", "close**", "_open", "****", "**a _b** c_", "x **y _z_ w", "**  **".replace("  ", "")])
def test_unbalanced_empty_or_crossed_markers_are_refused(text):
    result = check(set_at(minimal(), "blocks.0.bullets.0.text.en", text))
    assert codes(result) == ["CONTENT_INLINE_MARKUP"]


def test_texts_are_single_line_nfc_and_bounded():
    for bad in ("two\nlines", "tab\there", "nul\x00", "sep\u2028x"):
        assert codes(check(set_at(minimal(), "blocks.0.bullets.0.text.en", bad))) == ["CONTENT_CONTROL_CHARACTER"]
    assert codes(check(set_at(minimal(), "blocks.0.bullets.0.text.en", "x" * 1001))) == ["CONTENT_TOO_LONG"]
    assert codes(check(set_at(minimal(), "blocks.0.bullets.0.text.en", "   "))) == ["CONTENT_EMPTY_VALUE"]
    valid(set_at(minimal(), "blocks.0.bullets.0.text.en", "x" * 1000))
    cleaned = valid(set_at(minimal(), "blocks.0.bullets.0.text.en", "  spaced \u00a0  out  ")).content
    assert cleaned.to_model()["blocks"][0]["bullets"][0]["text"]["en"] == "spaced out"


# --- unknown fields, extensions, malformed data ------------------------------------------------------------

LEVELS = ["", "sections.0", "blocks.0", "blocks.0.heading.en", "blocks.0.bullets.0"]


@pytest.mark.parametrize("where", LEVELS)
def test_an_unknown_field_is_refused_at_every_level(where):
    document = minimal()
    target = document
    for part in [p for p in where.split(".") if p]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    target["surprise"] = 1
    result = check(document)
    assert codes(result) == ["CONTENT_UNKNOWN_FIELD"] and result.content is None


@pytest.mark.parametrize("where", LEVELS)
def test_extensions_are_kept_in_the_model_and_the_fingerprint_but_do_nothing(where):
    plain = valid(minimal()).content
    document = minimal()
    target = document
    for part in [p for p in where.split(".") if p]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    target["x-note"] = {"anything": [1, 2]}
    extended = valid(document).content
    assert extended.content_sha256 != plain.content_sha256
    assert "x-note" in json.dumps(extended.to_model())
    assert extended.counts() == plain.counts()


def test_extension_names_follow_the_shared_rule():
    for name in ("x-", "x-UPPER", "x- space", "x-a\n"):
        document = minimal()
        document[name] = 1
        assert "CONTENT_BAD_EXTENSION" in codes(check(document)) or "CONTENT_UNKNOWN_FIELD" in codes(check(document)), name


@pytest.mark.parametrize("where,value,code", [
    ("schema", "ResumeContent-v2", "CONTENT_UNKNOWN_SCHEMA"),
    ("sections", "x", "CONTENT_BAD_TYPE"), ("sections", [], "CONTENT_EMPTY_VALUE"),
    ("blocks", {}, "CONTENT_BAD_TYPE"), ("blocks", [], "CONTENT_EMPTY_VALUE"),
    ("sections.0", "x", "CONTENT_BAD_TYPE"), ("sections.0.kind", "novel", "CONTENT_INVALID_VALUE"),
    ("sections.0.title", {}, "CONTENT_EMPTY_VALUE"), ("sections.0.title", "x", "CONTENT_BAD_TYPE"),
    ("sections.0.title", {"english": "x"}, "CONTENT_INVALID_LANGUAGE"),
    ("blocks.0.section", "nowhere", "CONTENT_UNKNOWN_SECTION"),
    ("blocks.0.languages", [], "CONTENT_EMPTY_VALUE"), ("blocks.0.languages", "en", "CONTENT_BAD_TYPE"),
    ("blocks.0.languages", ["EN"], "CONTENT_INVALID_LANGUAGE"), ("blocks.0.languages", ["en", "en"], "CONTENT_DUPLICATE_VALUE"),
    ("blocks.0.heading", {}, "CONTENT_EMPTY_VALUE"), ("blocks.0.heading", {"en": {}}, "CONTENT_MISSING_FIELD"),
    ("blocks.0.heading", {"en": "x"}, "CONTENT_BAD_TYPE"), ("blocks.0.heading.en.title", 5, "CONTENT_BAD_TYPE"),
    ("blocks.0.heading.en.title", None, "CONTENT_BAD_TYPE"),
    ("blocks.0.protected", "no", "CONTENT_BAD_TYPE"),
    ("blocks.0.bullets", "x", "CONTENT_BAD_TYPE"), ("blocks.0.bullets.0", [], "CONTENT_BAD_TYPE"),
    ("blocks.0.bullets.0.text", {}, "CONTENT_EMPTY_VALUE"), ("blocks.0.bullets.0.text.en", 5, "CONTENT_BAD_TYPE"),
    ("blocks.0.bullets.0.text.en", "", "CONTENT_EMPTY_VALUE"),
    ("blocks.0.bullets.0.supports", "fact.one", "CONTENT_BAD_TYPE"), ("blocks.0.bullets.0.supports", [5], "CONTENT_INVALID_ID"),
    ("blocks.0.bullets.0.supports", ["fact.one", "fact.one"], "CONTENT_DUPLICATE_VALUE"),
    ("blocks.0.bullets.0.never_publish", "yes", "CONTENT_BAD_TYPE"),
    ("blocks.0.bullets.0.technologies", "Python", "CONTENT_BAD_TYPE"),
    ("blocks.0.bullets.0.technologies", ["Python", "python"], "CONTENT_DUPLICATE_VALUE"),
    ("blocks.0.bullets.0.capabilities", ["Bad Id"], "CONTENT_INVALID_ID"),
    ("blocks.0.bullets.0.follows", 5, "CONTENT_INVALID_ID"), ("blocks.0.bullets.0.condenses", "x", "CONTENT_BAD_TYPE"),
])
def test_malformed_data_is_refused_with_a_stable_code(where, value, code):
    result = check(set_at(minimal(), where, value), with_facts=False)
    assert code in codes(result), codes(result)
    assert result.content is None


@pytest.mark.parametrize("missing", ["schema", "sections", "blocks", "blocks.0.id", "blocks.0.section", "blocks.0.order",
                                     "blocks.0.languages", "blocks.0.heading", "blocks.0.bullets.0.id",
                                     "blocks.0.bullets.0.text", "sections.0.id", "sections.0.kind", "sections.0.title"])
def test_a_missing_required_field_is_reported(missing):
    result = check(drop_at(minimal(), missing), with_facts=False)
    assert "CONTENT_MISSING_FIELD" in codes(result) and result.content is None


@pytest.mark.parametrize("data,code", [
    (b"\xff\xfe nope", "CONTENT_NOT_UTF8"), (b"{not json", "CONTENT_NOT_JSON"), (b"", "CONTENT_NOT_JSON"),
    (b'{"a": 1, "a": 2}', "CONTENT_DUPLICATE_KEY"), (b'{"a": NaN}', "CONTENT_NOT_JSON"),
    (b'{"a": Infinity}', "CONTENT_NOT_JSON"), (b'{"a": -Infinity}', "CONTENT_NOT_JSON"),
    (b"[" * 5000 + b"]" * 5000, "CONTENT_NOT_JSON"), (b"[]", "CONTENT_BAD_TYPE"), (b"null", "CONTENT_BAD_TYPE"),
    (b'"text"', "CONTENT_BAD_TYPE"),
])
def test_unusable_files_are_refused_without_raising(data, code):
    result = content.check_bytes(data)
    assert result.content is None and code in codes(result)


def test_a_duplicate_key_is_refused_wherever_it_hides():
    text = json.dumps(minimal()).replace('"id": "job.01"', '"id": "job.01", "id": "job.02"')
    assert codes(content.check_bytes(text.encode("utf-8"))) == ["CONTENT_DUPLICATE_KEY"]


def test_an_unreadable_file_and_parse_file():
    result = content.check_file(Path("does-not-exist.json"))
    assert codes(result) == ["CONTENT_FILE_UNREADABLE"]
    with pytest.raises(content.ContentError) as raised:
        content.parse_file(Path("does-not-exist.json"))
    assert raised.value.code == "CONTENT_FILE_UNREADABLE"


# --- no leak of private values ---------------------------------------------------------------------------------

def test_no_error_repeats_a_value_of_the_document(workspace, capsys):
    document = minimal()
    document["blocks"][0]["bullets"][0]["text"]["en"] = SECRET + " \\cmd"
    document["blocks"][0]["heading"]["en"]["subtitle"] = SECRET + " \\cmd"
    document["blocks"][0]["bullets"][0]["supports"] = ["zxq-private-9931", SECRET]
    document["blocks"][0]["supports"] = ["zxq-private-9931", SECRET]
    document["blocks"][0]["heading"]["en"]["title"] = SECRET + " title"
    document["blocks"][0]["heading"]["en"]["period"] = SECRET + " period"
    document["blocks"][0]["bullets"][0]["technologies"] = [SECRET + "\\x"]
    document["blocks"][0]["bullets"][0][SECRET] = SECRET
    document["blocks"][0]["heading"][SECRET] = {"title": SECRET}
    document["blocks"][0]["bullets"][0]["text"][SECRET] = SECRET
    document["sections"][0]["id"] = SECRET
    document["blocks"][0]["section"] = SECRET
    document["blocks"][0]["id"] = SECRET
    document["baselines"] = [{"family": SECRET, "language": SECRET, "items": [SECRET], "skills": [SECRET], "focus": SECRET + "\\x"}]
    document["x-" + SECRET] = SECRET
    document[SECRET] = SECRET
    path = workspace / "content" / "leaky.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    parts = [part.lower() for part in ("ZXQ", "9931", "private")]

    result = content.check_bytes(path.read_bytes(), factbase())
    assert result.errors
    for error in result.errors:
        shown = ("%s %s %s" % (error.code, error.message, error.path)).lower()
        assert not any(part in shown for part in parts), shown

    code, out, err = run(capsys, "content", "check", str(path), "--root", str(workspace),
                         "--facts", str(workspace / "facts.md"), "--outline")
    assert code == 1
    assert not any(part in (out + err).lower() for part in parts)


def test_a_reported_path_never_shows_a_free_text_value_even_for_a_valid_looking_key():
    document = minimal()
    document["blocks"][0]["bullets"][0]["text"]["fr"] = "Texte"
    result = check(document)
    assert [e.path for e in result.errors] == ["blocks[0].bullets[0].text"]


def test_outline_and_report_never_contain_a_text(workspace, capsys):
    code, out, _ = run(capsys, "content", "check", "--root", str(workspace), "--outline")
    assert code == 0
    for needle in ("REST endpoints", "Developer", "Jordan", "Python for scripting", "Example Company"):
        assert needle not in out
    outline = json.loads(out)["outline"]
    assert outline["blocks"][0]["bullets"][0] == {"id": "junior-dev.01", "state": "VERIFIED"}


# --- fingerprints and normalisation --------------------------------------------------------------------------

def hashes(data, factbase_=None):
    result = content.check_bytes(data, factbase_)
    assert not result.errors, [e.as_dict() for e in result.errors]
    return result.content_source_sha256, result.content.content_sha256


def test_line_endings_and_the_bom_never_change_either_fingerprint():
    text = json.dumps(bilingual(), indent=2, ensure_ascii=False)
    reference = hashes(text.encode("utf-8"))
    for ending in ("\r\n", "\r"):
        assert hashes(text.replace("\n", ending).encode("utf-8")) == reference
    assert hashes(b"\xef\xbb\xbf" + text.encode("utf-8")) == reference
    assert hashes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")) == reference


def test_key_order_and_layout_keep_the_logical_fingerprint_but_not_the_source_hash():
    document = bilingual()
    compact = json.dumps(document, ensure_ascii=False).encode("utf-8")
    spread = json.dumps(document, indent=4, ensure_ascii=False).encode("utf-8")
    shuffled = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
    sources = {hashes(blob)[0] for blob in (compact, spread, shuffled)}
    logical = {hashes(blob)[1] for blob in (compact, spread, shuffled)}
    assert len(sources) == 3 and len(logical) == 1


def test_unicode_normalisation_gives_one_canonical_representation():
    composed = unicodedata.normalize("NFC", "Développement à Zürich")
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    one = set_at(bilingual(), "blocks.0.bullets.0.text.fr", composed)
    two = set_at(bilingual(), "blocks.0.bullets.0.text.fr", decomposed)
    (source_a, logical_a), (source_b, logical_b) = hashes(encode(one)), hashes(encode(two))
    assert logical_a == logical_b and source_a != source_b  # the source hash applies no NFC, by contract
    model_text = content.check_bytes(encode(two)).content.to_model()["blocks"][0]["bullets"][0]["text"]["fr"]
    assert model_text == composed


def test_whitespace_and_explicit_defaults_do_not_change_the_logical_fingerprint():
    base = hashes(encode(minimal()))[1]
    document = set_at(minimal(), "blocks.0.bullets.0.text.en", "  Built    a\u00a0thing.  ")
    explicit = copy.deepcopy(minimal())
    explicit["blocks"][0].update(protected=False)
    explicit["blocks"][0]["bullets"][0].update(never_publish=False, follows=None, condenses=[], technologies=[],
                                               capabilities=[])
    explicit["blocks"][0]["heading"]["en"].update(subtitle=None, period=None, place=None)
    assert hashes(encode(document))[1] == base and hashes(encode(explicit))[1] == base


@pytest.mark.parametrize("where,value", [
    ("blocks.0.bullets.0.text.en", "Built another thing."), ("blocks.0.bullets.0.supports", ["fact.two"]),
    ("blocks.0.bullets.0.technologies", ["Python"]), ("blocks.0.bullets.0.capabilities", ["backend"]),
    ("blocks.0.bullets.0.never_publish", True), ("blocks.0.heading.en.title", "Engineer"),
    ("blocks.0.heading.en.period", "2025"), ("blocks.0.protected", True), ("blocks.0.order", 2),
    ("blocks.0.supports", ["fact.two"]), ("sections.0.title.en", "Work"), ("sections.0.kind", "project"), ("blocks.0.languages", ["en", "fr"]),
    ("schema", "ResumeContent-v1"),
])
def test_every_real_change_moves_the_fingerprint_except_a_no_op(where, value):
    base = valid(minimal()).content.content_sha256
    document = set_at(minimal(), where, value)
    if where == "blocks.0.languages":
        document["blocks"][0]["heading"]["fr"] = {"title": "x"}
        document["blocks"][0]["bullets"][0]["text"]["fr"] = "x"
        document["sections"][0]["title"]["fr"] = "x"
    result = check(document)
    assert not result.errors, [e.as_dict() for e in result.errors]
    changed = result.content.content_sha256 != base
    assert changed == (where != "schema")


def test_fingerprints_are_stable_across_calls_and_independent_of_the_fact_base():
    document = encode(bilingual())
    assert hashes(document) == hashes(document) == hashes(document, factbase())


def test_historical_fingerprints_of_earlier_milestones_are_unchanged():
    base = facts.parse_file(EXAMPLE_DIR / "facts.md")
    assert base.facts_source_sha256 == "fea38cb3a3257f8837a2fe86c2ec283b9835ff6526a443e8423bade684a32d71"
    assert base.factbase_sha256 == "53ec19925778e29ee8069a12644e9bac607a6446f0b6c77ce49449746f6e2dcd"
    second = facts.parse_file(REPO / "examples" / "facts.v1.example.md")
    assert second.facts_source_sha256 == "fcdd74a771a47b8990c80c3293973837e8ad8a910a30ec4058f385ef6c8d39fb"
    assert second.factbase_sha256 == "ec0ea60ff47ff2227627b308eafc0fd6f389910373692880d17afb35a9a29474"
    loaded = profile.parse_file(EXAMPLE_DIR / "profile.json")
    assert loaded.profile_source_sha256 == "ad6803647208756f319c89812e4cf24c6e7143600070f53c8323a0b231785a83"
    assert loaded.profile_sha256 == "8918ff623543e88dfba365ea843d9f91a4cd42834c75a818b242278bc496c1ee"


def test_identifier_patterns_no_longer_accept_a_trailing_newline():
    assert not facts.valid_id("abc\n") and facts.valid_id("abc")
    document = {"schema": "Profile-v1", "languages": ["en\n"],
                "identity": {"display_name": {"value": "Alex Sample", "visibility": "public"}},
                "families": {"software\n": {"label": "Software", "languages": ["en"]}}}
    assert profile.check_data(document).errors


# --- command line ------------------------------------------------------------------------------------------------

def test_content_check_exit_codes(workspace, capsys):
    code, out, err = run(capsys, "content", "check", "--root", str(workspace))
    assert code == 0 and json.loads(out)["status"] == "OK" and err == ""

    code, out, err = run(capsys, "content", "check", "--root", str(workspace), "--no-facts")
    report = json.loads(out)
    assert code == 3 and report["status"] == "UNVERIFIED" and report["facts_checked"] is False
    assert "CONTENT_FACTS_NOT_CHECKED" in err

    code, out, err = run(capsys, "content", "check", str(workspace / "content/invalid/unconfirmed-support.json"), "--root", str(workspace))
    assert code == 1 and json.loads(out)["status"] == "INVALID" and "CONTENT_FACT_NOT_CONFIRMED" in err
    assert "CONTENT_FACT_UNKNOWN" in err

    code, out, err = run(capsys, "content", "check", str(workspace / "content/invalid/parity-drift.json"), "--root", str(workspace))
    assert code == 1 and "CONTENT_PARITY_BULLET" in err
    code, out, err = run(capsys, "content", "check", str(workspace / "content/invalid/raw-latex.json"), "--root", str(workspace))
    assert code == 1 and "CONTENT_RAW_LATEX" in err


def test_a_structure_only_success_is_never_exit_zero_when_there_is_something_to_verify(workspace, capsys):
    code, _, _ = run(capsys, "content", "check", "--root", str(workspace), "--no-facts")
    assert code == 3
    path = workspace / "content" / "reminders.json"
    document = minimal()
    document["blocks"][0]["bullets"] = [{"id": "job.01", "text": {"en": "Reminder."}, "never_publish": True}]
    path.write_text(json.dumps(document), encoding="utf-8")
    code, out, _ = run(capsys, "content", "check", str(path), "--root", str(workspace), "--no-facts")
    assert code == 3 and json.loads(out)["status"] == "UNVERIFIED"  # the heading's references are still unverified


def test_missing_or_broken_inputs_exit_two_or_one(workspace, capsys):
    code, _, err = run(capsys, "content", "check", str(workspace / "nope.json"), "--root", str(workspace))
    assert code == 2 and "CONTENT_FILE_UNREADABLE" in err
    (workspace / "facts.md").unlink()
    code, _, err = run(capsys, "content", "check", "--root", str(workspace))
    assert code == 2 and "FACTS_UNREADABLE" in err
    (workspace / "facts.md").write_text("not a fact base", encoding="utf-8")
    code, _, err = run(capsys, "content", "check", "--root", str(workspace))
    assert code == 1 and "CONTENT_FACTS_INVALID" in err
    (workspace / "modularcv.json").write_text('{"surprise": 1}', encoding="utf-8")
    code, _, err = run(capsys, "content", "check", "--root", str(workspace))
    assert code == 2 and "CONFIG_ERROR" in err


def test_content_check_with_a_profile(workspace, capsys):
    code, out, _ = run(capsys, "content", "check", "--root", str(workspace), "--profile", str(workspace / "profile.json"))
    assert code == 0 and json.loads(out)["profile_checked"] is True
    document = json.loads((workspace / "content" / "resume.json").read_text(encoding="utf-8"))
    document["baselines"][0]["family"] = "unknown"
    (workspace / "content" / "resume.json").write_text(json.dumps(document), encoding="utf-8")
    code, _, err = run(capsys, "content", "check", "--root", str(workspace), "--profile", str(workspace / "profile.json"))
    assert code == 1 and "CONTENT_BASELINE_FAMILY_UNKNOWN" in err
    (workspace / "bad-profile.json").write_text("{}", encoding="utf-8")
    code, _, err = run(capsys, "content", "check", "--root", str(workspace), "--profile", str(workspace / "bad-profile.json"))
    assert code == 2 and "PROFILE_" in err


def test_content_fingerprint_command(workspace, capsys):
    code, out, _ = run(capsys, "content", "fingerprint", "--root", str(workspace))
    report = json.loads(out)
    assert code == 0 and report["status"] == "OK"
    model = content.parse_file(workspace / "content" / "resume.json")
    assert report["content_sha256"] == model.content_sha256 == canonical.fingerprint(model.to_model())
    for only, key in (("source", "content_source_sha256"), ("content", "content_sha256")):
        code, out, _ = run(capsys, "content", "fingerprint", "--root", str(workspace), "--only", only)
        assert code == 0 and out.strip() == report[key]
    code, out, _ = run(capsys, "content", "fingerprint", str(workspace / "content/invalid/raw-latex.json"), "--root", str(workspace))
    assert code == 1 and out == ""


def test_content_commands_write_nothing(workspace, capsys):
    before = tree_hash(workspace)
    for argv in (("check",), ("check", "--no-facts"), ("check", "--outline"), ("fingerprint",),
                 ("check", str(workspace / "content/invalid/parity-drift.json"))):
        run(capsys, "content", *argv, "--root", str(workspace))
    assert tree_hash(workspace) == before


def test_content_check_on_the_files_of_the_other_modules_is_a_clean_refusal(workspace, capsys):
    for name in ("facts.md", "profile.json", "import-map.json"):
        code, _, err = run(capsys, "content", "check", str(workspace / name), "--root", str(workspace))
        assert code == 1 and err


# --- robustness ---------------------------------------------------------------------------------------------------

def mutate(rng, document):
    """One random structural damage somewhere in the document."""
    nodes = []

    def walk(node):
        nodes.append(node)
        for child in (node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()):
            walk(child)

    walk(document)
    node = rng.choice([n for n in nodes if isinstance(n, (dict, list)) and n])
    key = rng.choice(list(node) if isinstance(node, dict) else range(len(node)))
    choice = rng.randint(0, 5)
    if choice == 0 and isinstance(node, dict):
        del node[key]
    elif choice == 1:
        node[key] = rng.choice([None, True, 7, 1.5, "", "x y", "Bad Id", [], {}, [1], {"a": 1}, "\\cmd", "a\nb"])
    elif choice == 2 and isinstance(node, dict):
        node["x-" + rng.choice(["a", "B", ""])] = 1
    elif choice == 3 and isinstance(node, dict):
        node[rng.choice(["id", "text", "supports", "extra"])] = rng.choice([None, "dup", [], 3])
    elif choice == 4 and isinstance(node, list):
        node.append(copy.deepcopy(node[key]))
    elif choice == 5 and isinstance(node, list):
        node.reverse()
    return document


def test_random_damage_never_crashes_and_the_result_is_always_consistent():
    rng = random.Random(20260502)
    base = bilingual()
    base["skills"] = [{"id": "cat", "title": {"en": "Tools", "fr": "Outils"},
                       "items": [{"id": "py", "text": {"en": "Python", "fr": "Python"}, "supports": ["fact.one"]}]}]
    base["baselines"] = [{"family": "software", "language": "en", "items": ["job.01"], "skills": ["py"]}]
    outcomes = {"valid": 0, "invalid": 0}
    for _ in range(400):
        document = copy.deepcopy(base)
        for _step in range(rng.randint(1, 3)):
            mutate(rng, document)
        try:
            blob = json.dumps(document).encode("utf-8")
        except (TypeError, ValueError):
            continue
        result = content.check_bytes(blob, factbase())
        assert (result.content is None) == bool(result.errors)
        for error in result.errors:
            assert error.code.startswith("CONTENT_") and error.message
        if result.content is not None:
            outcomes["valid"] += 1
            again = content.check_bytes(blob, factbase())
            assert again.content.content_sha256 == result.content.content_sha256
            assert result.content.to_model()["schema"] == "ResumeContent-v1"
        else:
            outcomes["invalid"] += 1
    assert outcomes["invalid"] > 50  # the damage is real


def test_a_valid_model_survives_a_round_trip_through_its_own_canonical_form():
    first = valid(bilingual()).content
    again = content.check_bytes(canonical.canonical_bytes(first.to_model()), factbase())
    assert not again.errors and again.content.content_sha256 == first.content_sha256


def test_the_accessors_return_copies_not_the_inner_state():
    result = valid(bilingual()).content
    model = result.to_model()
    model["blocks"][0]["bullets"][0]["text"]["en"] = "tampered"
    result.baseline("software", "en")
    assert result.to_model()["blocks"][0]["bullets"][0]["text"]["en"] == "Built a thing."


# --- design rules ---------------------------------------------------------------------------------------------------

def test_the_module_uses_only_the_standard_library_and_the_core_and_touches_no_network():
    tree = ast.parse((REPO / "modularcv" / "content.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
    assert imported <= {"copy", "collections", ".", }, imported
    source = (REPO / "modularcv" / "content.py").read_text(encoding="utf-8")
    assert not re.search(r"\b(socket|urllib|http|requests|subprocess|os\.system)\b", source)


def test_every_error_code_the_module_can_emit_is_documented():
    source = (REPO / "modularcv" / "content.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'(?:error|reader\.error)\(\s*"([A-Z_]+)"', source))
    emitted |= set(re.findall(r'PREFIX \+ "([A-Z_]+)"', source))
    emitted |= {"NOT_UTF8", "NOT_JSON", "DUPLICATE_KEY", "FILE_UNREADABLE", "FACTS_INVALID"}
    contract = (REPO / "docs" / "design" / "CONTRACTS.md").read_text(encoding="utf-8")
    section = contract.split("### 3.2", 1)[1].split("## 4. JobOffer-v1", 1)[0]
    missing = sorted(code for code in emitted if "`%s`" % code not in section and code not in section)
    assert not missing, missing


def test_the_documentation_states_the_limits_of_the_checks():
    contract = (REPO / "docs" / "design" / "CONTRACTS.md").read_text(encoding="utf-8")
    section = contract.split("### 3.2", 1)[1]
    for phrase in ("existence and status", "not semantic", "UNVERIFIED", "exits `3`"):
        assert phrase in section, phrase
    guide = (REPO / "docs" / "CONTENT.md").read_text(encoding="utf-8")
    for phrase in ("never checks", "equivalence", "--no-facts"):
        assert phrase in guide, phrase


# --- M5-R1: the factual heading of a block is tied to the fact base ----------------------------------------------

def test_a_heading_without_supporting_facts_is_refused_with_no_fact_base_needed():
    for change in (lambda d: set_at(d, "blocks.0.supports", []), lambda d: drop_at(d, "blocks.0.supports")):
        result = check(change(minimal()), with_facts=False)
        assert codes(result) == ["CONTENT_UNSUPPORTED_HEADING"] and result.content is None
        assert result.errors[0].path == "blocks[0]"


def test_a_heading_backed_by_a_confirmed_fact_is_valid_and_verified():
    result = valid(minimal())
    assert ("heading", "job", "VERIFIED") in result.references
    assert result.content.to_model()["blocks"][0]["supports"] == ["fact.one"]
    assert result.content.fact_ids() == ("fact.one",)


def test_a_heading_backed_by_a_fact_that_does_not_exist_is_refused():
    result = check(set_at(minimal(), "blocks.0.supports", ["fact.missing"]))
    assert sorted(codes(result)) == ["CONTENT_FACT_UNKNOWN", "CONTENT_UNSUPPORTED_HEADING"]
    assert {e.path for e in result.errors} == {"blocks[0]", "blocks[0].supports[0]"}
    assert ("heading", "job", "REFUSED") in result.references


@pytest.mark.parametrize("fact_id,status", [("fact.derived", "DERIVED"), ("fact.unsure", "NOT_CONFIRMED"),
                                            ("fact.gone", "WITHDRAWN")])
def test_a_heading_backed_by_a_fact_that_is_not_confirmed_is_refused(fact_id, status):
    result = check(set_at(minimal(), "blocks.0.supports", [fact_id]))
    assert sorted(codes(result)) == ["CONTENT_FACT_NOT_CONFIRMED", "CONTENT_UNSUPPORTED_HEADING"]
    assert any(status in e.message for e in result.errors) and result.content is None


def test_one_invalid_reference_among_valid_ones_refuses_the_heading():
    for bad in ("fact.missing", "fact.unsure", "fact.derived", "fact.gone"):
        result = check(set_at(minimal(), "blocks.0.supports", ["fact.one", bad, "fact.two"]))
        assert "CONTENT_UNSUPPORTED_HEADING" in codes(result) and result.content is None, bad


def test_organisational_titles_need_no_proof():
    document = minimal()
    document["skills"] = [{"id": "cat", "title": {"en": "Tools"},
                           "items": [{"id": "py", "text": {"en": "Python"}, "supports": ["fact.one"]}]}]
    assert "supports" not in document["sections"][0] and "supports" not in document["skills"][0]
    result = valid(document)
    assert {kind for kind, _e, _s in result.references} == {"heading", "bullet", "skill"}  # no entry for a title


def test_regression_a_confirmed_bullet_cannot_carry_an_unproven_job_title():
    """The M5 gap: a title, employer or period with no proof was accepted next to a perfectly supported bullet."""
    document = minimal()
    document["blocks"][0]["heading"]["en"] = {"title": "Chief executive", "subtitle": "A company", "period": "1999"}
    set_at(document, "blocks.0.supports", ["fact.unsure"])          # not confirmed: the title is a claim nobody confirmed
    assert document["blocks"][0]["bullets"][0]["supports"] == ["fact.one"]  # the bullet itself is fully proven
    result = check(document)
    assert result.content is None and "CONTENT_UNSUPPORTED_HEADING" in codes(result)
    assert "CONTENT_UNSUPPORTED_BULLET" not in codes(result)
    structural = content.check_data(document).content  # parsed without a fact base: nothing is verified, nothing printable
    assert structural.selectable(factbase(), "en") == ()
    assert structural.selectable_skills(factbase(), "en") == ()


def test_selectable_needs_both_the_bullet_and_its_heading_proven():
    document = minimal()
    document["blocks"][0]["bullets"].append({"id": "job.02", "text": {"en": "Second."}, "supports": ["fact.derived"]})
    parsed = content.check_data(document).content
    assert [e.bullet_id for e in parsed.selectable(factbase(), "en")] == ["job.01"]  # proven bullet, proven heading
    withdrawn = FACTS.replace("[fact.one] CONFIRMED", "[fact.one] WITHDRAWN")
    for heading_fact, text in (("fact.derived", FACTS), ("fact.one", withdrawn), ("fact.absent", FACTS)):
        other = copy.deepcopy(document)
        set_at(other, "blocks.0.supports", [heading_fact])
        assert content.check_data(other).content.selectable(factbase(text), "en") == (), heading_fact
    mixed = copy.deepcopy(document)
    set_at(mixed, "blocks.0.supports", ["fact.one", "fact.unsure"])
    assert content.check_data(mixed).content.selectable(factbase(), "en") == ()  # every supporting fact must be confirmed


def test_selectable_skills_follows_the_fact_base_and_the_language():
    document = bilingual()
    document["skills"] = [{"id": "cat", "title": {"en": "Tools", "fr": "Outils"}, "items": [
        {"id": "py", "text": {"en": "Python", "fr": "Python"}, "supports": ["fact.one"]},
        {"id": "git", "text": {"en": "Git", "fr": "Git"}, "supports": ["fact.derived"]}]}]
    parsed = content.check_data(document).content
    assert parsed.selectable_skills(factbase(), "fr") == (("cat", "py"),)
    assert parsed.selectable_skills(factbase(), "de") == ()
    promoted = FACTS.replace("DERIVED: A derived", "CONFIRMED: A derived")
    assert parsed.selectable_skills(factbase(promoted), "en") == (("cat", "py"), ("cat", "git"))


def test_without_a_fact_base_a_heading_is_unverified_and_the_command_cannot_exit_zero(workspace, capsys):
    result = check(minimal(), with_facts=False)
    assert ("heading", "job", "UNVERIFIED") in result.references
    code, out, err = run(capsys, "content", "check", "--root", str(workspace), "--no-facts", "--outline")
    report = json.loads(out)
    assert code == 3 and report["status"] == "UNVERIFIED" and report["references"]["headings"] == {"UNVERIFIED": 3}
    assert {b["heading_state"] for b in report["outline"]["blocks"]} == {"UNVERIFIED"}
    code, out, _ = run(capsys, "content", "check", "--root", str(workspace), "--outline")
    report = json.loads(out)
    assert code == 0 and report["references"]["headings"] == {"VERIFIED": 3}


def test_the_new_invalid_examples_are_refused(workspace, capsys):
    folder = workspace / "content" / "invalid"
    code, _, err = run(capsys, "content", "check", str(folder / "unproven-heading.json"), "--root", str(workspace))
    assert code == 1 and "CONTENT_UNSUPPORTED_HEADING" in err and "CONTENT_FACT_NOT_CONFIRMED" in err
    assert "UNSUPPORTED_BULLET" not in err
    code, _, err = run(capsys, "content", "check", str(folder / "missing-heading-support.json"), "--root", str(workspace),
                       "--no-facts")
    assert code == 1 and "CONTENT_UNSUPPORTED_HEADING" in err  # structural: refused even without a fact base


@pytest.mark.parametrize("name", sorted(path.name for path in (EXAMPLE_DIR / "content" / "invalid").glob("*.json")))
def test_every_invalid_example_is_refused_and_every_valid_one_is_not(name, workspace, capsys):
    code, out, err = run(capsys, "content", "check", str(workspace / "content" / "invalid" / name), "--root", str(workspace))
    assert code == 1 and json.loads(out)["status"] == "INVALID" and err
    for valid_name in ("resume.json", "resume.fr.json", "resume.en.json"):
        assert run(capsys, "content", "check", str(workspace / "content" / valid_name), "--root", str(workspace))[0] == 0


def test_french_english_and_bilingual_examples_have_proven_headings():
    base = facts.check_file(EXAMPLE_DIR / "facts.md").factbase
    for name, language in (("resume.fr.json", "fr"), ("resume.en.json", "en"), ("resume.json", "en"), ("resume.json", "fr")):
        parsed = content.parse_file(EXAMPLE_DIR / "content" / name, base)
        assert parsed.selectable(base, language), name
        assert all(state == "VERIFIED" for kind, _e, state in content.check_file(
            EXAMPLE_DIR / "content" / name, base).references if kind == "heading")


def test_heading_support_is_stable_in_identifiers_and_fingerprints():
    document = minimal()
    set_at(document, "blocks.0.supports", ["fact.two", "fact.one"])
    first = valid(document).content
    set_at(document, "blocks.0.supports", ["fact.one", "fact.two"])
    second = valid(document).content
    assert first.content_sha256 == second.content_sha256 and first.to_model() == second.to_model()
    assert first.content_sha256 != valid(minimal()).content.content_sha256  # the support is part of the meaning
    again = valid(document).content
    assert again.reservoir()[0].heading_supports == ("fact.one", "fact.two")
    assert [e.bullet_id for e in again.reservoir()] == ["job.01"]


def test_a_heading_diagnostic_never_repeats_a_factual_value():
    document = minimal()
    document["blocks"][0]["heading"]["en"] = {"title": SECRET + " title", "subtitle": SECRET + " employer",
                                              "period": SECRET + " period", "place": SECRET + " place"}
    set_at(document, "blocks.0.supports", ["fact.unsure", "zxq-private-9931"])
    result = check(document)
    assert "CONTENT_UNSUPPORTED_HEADING" in codes(result)
    shown = " ".join("%s %s %s" % (e.code, e.message, e.path) for e in result.errors).lower()
    assert not any(part in shown for part in ("zxq", "9931", "private", "employer", "period value", "place value"))


# --- M5-R1: language parity binds the en/fr pair only ---------------------------------------------------------------

def three_languages():
    document = bilingual()
    document["sections"][0]["title"]["de"] = "Erfahrung"
    block = document["blocks"][0]
    block["languages"] = ["de", "en", "fr"]
    block["heading"]["de"] = {"title": "Entwickler"}
    block["bullets"][0]["text"]["de"] = "Etwas gebaut."
    return document


def test_a_third_language_needs_no_parity_but_en_and_fr_still_do():
    document = three_languages()
    valid(document)
    document["blocks"][0]["bullets"][0]["text"].pop("de")      # a third language may be missing
    document["blocks"][0]["heading"].pop("de")
    document["sections"][0]["title"].pop("de")
    valid(document)
    for language in ("en", "fr"):                               # the pair may not
        broken = three_languages()
        broken["blocks"][0]["bullets"][0]["text"].pop(language)
        assert codes(check(broken)) == ["CONTENT_PARITY_BULLET"]
        broken = three_languages()
        broken["blocks"][0]["heading"].pop(language)
        assert codes(check(broken)) == ["CONTENT_PARITY_HEADING"]
        broken = three_languages()
        broken["sections"][0]["title"].pop(language)
        assert codes(check(broken)) == ["CONTENT_PARITY_TITLE"]


def test_a_block_without_the_en_fr_pair_has_no_parity_obligation():
    document = minimal()
    block = document["blocks"][0]
    block["languages"] = ["de", "en"]
    block["heading"] = {"en": {"title": "Developer"}}
    block["bullets"] = [{"id": "job.01", "text": {"en": "English only."}, "supports": ["fact.one"]},
                        {"id": "job.02", "text": {"de": "Nur Deutsch."}, "supports": ["fact.one"]},
                        {"id": "job.03", "text": {"de": "Beides.", "en": "Both."}, "supports": ["fact.one"]}]
    result = valid(document).content
    assert [e.bullet_id for e in result.selectable(factbase(), "de")] == ["job.02", "job.03"]
    assert [e.bullet_id for e in result.selectable(factbase(), "en")] == ["job.01", "job.03"]


def test_the_general_structural_checks_remain_for_every_language():
    document = three_languages()
    document["blocks"][0]["bullets"][0]["text"]["es"] = "No declarado."   # a language the block does not declare
    assert codes(check(document)) == ["CONTENT_PARITY_BULLET"]
    document = three_languages()
    document["blocks"][0]["heading"]["es"] = {"title": "No declarado"}
    assert codes(check(document)) == ["CONTENT_PARITY_HEADING"]
    only = minimal()
    only["blocks"][0].update(languages=["de"], heading={"de": {"title": "Entwickler"}})
    only["blocks"][0]["bullets"][0]["text"] = {"en": "Wrong language."}
    assert codes(check(only)) == ["CONTENT_PARITY_BULLET"]               # a one-language block needs that language
    only["blocks"][0]["bullets"][0]["text"] = {"de": "Richtig."}
    assert codes(check(only)) == ["CONTENT_PARITY_TITLE"]                # and so does the title of its section
    only["sections"][0]["title"] = {"de": "Erfahrung"}
    valid(only)


def test_skill_categories_in_other_languages_follow_the_same_distinction():
    document = minimal()
    document["skills"] = [{"id": "cat", "title": {"de": "Werkzeuge", "en": "Tools"},
                           "items": [{"id": "py", "text": {"en": "Python"}, "supports": ["fact.one"]}]}]
    valid(document)                                                       # de/en: no pair, no obligation
    document["skills"][0]["title"]["fr"] = "Outils"
    assert codes(check(document)) == ["CONTENT_PARITY_ITEM"]              # en+fr declared: the item needs both
    set_at(document, "skills.0.items.0.text", {"en": "Python", "fr": "Python"})
    valid(document)


def test_baselines_in_a_third_language_only_take_items_written_in_it():
    document = three_languages()
    document["blocks"][0]["bullets"].append({"id": "job.02", "text": {"en": "No german.", "fr": "Pas d'allemand."},
                                             "supports": ["fact.two"]})
    document["baselines"] = [{"family": "software", "language": "de", "items": ["job.01"]}]
    valid(document)
    document["baselines"][0]["items"].append("job.02")
    assert codes(check(document)) == ["CONTENT_BASELINE_LANGUAGE"]


def test_the_documentation_records_the_decisions_taken_in_m5_r1():
    contract = (REPO / "docs" / "design" / "CONTRACTS.md").read_text(encoding="utf-8").split("### 3.2", 1)[1]
    for phrase in ("UNSUPPORTED_HEADING", "organisational", "selectable", "pair", "backslash"):
        assert phrase in contract, phrase
    guide = (REPO / "docs" / "CONTENT.md").read_text(encoding="utf-8")
    for phrase in ("heading", "backslash", "Windows path", "taxonomy", "other language"):
        assert phrase in guide, phrase
