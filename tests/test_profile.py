"""Profile-v1: validation, visibility, fact references, fingerprints, CLI (M4). Synthetic data only."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from modularcv import __main__ as cli
from modularcv import canonical, config, facts, profile
from synthetic import tree_hash

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = REPO / "examples" / "workspace"

MINIMAL = {
    "schema": "Profile-v1",
    "languages": ["en"],
    "identity": {"display_name": {"value": "Alex Sample", "visibility": "public"}},
    "families": {"software": {"label": "Software", "languages": ["en"]}},
}

FACTS = (
    "<!-- modularcv: FactBase-v1 -->\n## S {#s}\n"
    "- [avail.one] CONFIRMED: Available soon. {confirmed_on: 2026-02}\n"
    "- [avail.undated] CONFIRMED: Available later.\n"
    "- [avail.derived] DERIVED: Might be available.\n"
    "- [avail.unsure] NOT_CONFIRMED: Maybe.\n"
    "- [avail.gone] WITHDRAWN: Retracted.\n"
)


def build(**changes):
    document = copy.deepcopy(MINIMAL)
    document.update(changes)
    return document


def encode(document):
    return json.dumps(document).encode("utf-8")


def codes(result):
    return [error.code for error in result.errors]


def check(document, factbase=None):
    return profile.check_bytes(encode(document), factbase)


@pytest.fixture
def factbase():
    return facts.parse_text(FACTS)


def with_availability(*fact_ids, kinds=("INTERNSHIP",)):
    return build(availability=[{"id": "av-%d" % n, "fact_id": fact_id, "applies_to": list(kinds)}
                               for n, fact_id in enumerate(fact_ids)])


# --- minimal and complete profiles -------------------------------------------------------------------

def test_minimal_profile_is_valid_and_defaults_are_filled():
    result = check(MINIMAL)
    assert result.errors == () and result.warnings == ()
    found = result.profile
    assert found.languages == ("en",) and found.default_language == "en"
    model = found.to_model()
    assert model["policy"] == {"never_publish_terms": [], "omit_by_default_terms": [], "forbidden_words": {},
                               "require_confirmation_date": False}
    assert model["taxonomy"] == "builtin:generic-v1" and model["availability"] == [] and model["guidance"] == []
    assert model["selection"] == {"baseline_prior": 0.25, "minimum_gain": 1.0, "off_target_penalty": 0.1,
                                  "off_target_penalty_cap": 0.6, "named_bonus": 0.5, "inferred_factor": 0.5}
    assert model["families"]["software"]["page_target"] is None
    assert model["identity"]["links"] == []


def test_the_complete_example_is_valid_and_its_availability_verified():
    base = facts.parse_file(EXAMPLE_DIR / "facts.md")
    result = profile.check_file(EXAMPLE_DIR / "profile.json", base)
    assert result.errors == () and result.warnings == ()
    assert result.availability == (("internship-2027", profile.VERIFIED),)
    assert result.profile.require_confirmation_date is False


def test_a_second_language_needs_an_explicit_default():
    result = check(build(languages=["en", "fr"]))
    assert codes(result) == ["PROFILE_DEFAULT_LANGUAGE"]
    ok = check(build(languages=["fr", "en"], default_language="fr"))
    assert ok.errors == () and ok.profile.default_language == "fr" and ok.profile.languages == ("en", "fr")


# --- structure, types, unknown fields ----------------------------------------------------------------

def mutated(path, value, *, drop=False):
    document = copy.deepcopy(MINIMAL)
    node = document
    for key in path[:-1]:
        node = node[key]
    if drop:
        node.pop(path[-1])
    else:
        node[path[-1]] = value
    return document


FAMILY = ("families", "software")
CASES = [
    ("schema-missing", mutated(("schema",), None, drop=True), "PROFILE_MISSING_FIELD"),
    ("schema-unknown", mutated(("schema",), "Profile-v2"), "PROFILE_UNKNOWN_SCHEMA"),
    ("top-unknown-field", build(surprise=1), "PROFILE_UNKNOWN_FIELD"),
    ("bad-extension-name", build(**{"x-Bad": 1}), "PROFILE_BAD_EXTENSION"),
    ("languages-empty", mutated(("languages",), []), "PROFILE_EMPTY_VALUE"),
    ("languages-not-list", mutated(("languages",), "en"), "PROFILE_BAD_TYPE"),
    ("languages-duplicate", build(languages=["en", "en"]), "PROFILE_DUPLICATE_VALUE"),
    ("language-uppercase", build(languages=["EN"], families={"software": {"label": "S", "languages": ["en"]}}),
     "PROFILE_INVALID_LANGUAGE"),
    ("default-outside", build(default_language="fr"), "PROFILE_DEFAULT_LANGUAGE"),
    ("identity-not-object", mutated(("identity",), []), "PROFILE_BAD_TYPE"),
    ("name-missing", mutated(("identity", "display_name"), None, drop=True), "PROFILE_MISSING_FIELD"),
    ("identity-unknown-field", mutated(("identity", "pet"), {"value": "x", "visibility": "public"}),
     "PROFILE_UNKNOWN_FIELD"),
    ("visibility-missing", mutated(("identity", "display_name"), {"value": "A"}), "PROFILE_MISSING_FIELD"),
    ("visibility-invalid", mutated(("identity", "display_name"), {"value": "A", "visibility": "internal"}),
     "PROFILE_INVALID_VALUE"),
    ("value-not-string", mutated(("identity", "display_name"), {"value": 7, "visibility": "public"}),
     "PROFILE_BAD_TYPE"),
    ("value-empty", mutated(("identity", "display_name"), {"value": "  ", "visibility": "public"}),
     "PROFILE_EMPTY_VALUE"),
    ("value-newline", mutated(("identity", "display_name"), {"value": "A\nB", "visibility": "public"}),
     "PROFILE_CONTROL_CHARACTER"),
    ("link-not-object", mutated(("identity", "links"), ["https://example.org"]), "PROFILE_BAD_TYPE"),
    ("link-duplicate", mutated(("identity", "links"), [
        {"value": "https://example.org/a", "visibility": "public"},
        {"value": "HTTPS://EXAMPLE.ORG/A", "visibility": "private"}]), "PROFILE_DUPLICATE_VALUE"),
    ("families-empty", mutated(("families",), {}), "PROFILE_NO_FAMILY"),
    ("families-list", mutated(("families",), []), "PROFILE_BAD_TYPE"),
    ("family-bad-id", mutated(("families",), {"Bad Id": {"label": "S", "languages": ["en"]}}), "PROFILE_INVALID_ID"),
    ("family-no-label", mutated(FAMILY + ("label",), None, drop=True), "PROFILE_MISSING_FIELD"),
    ("family-no-languages", mutated(FAMILY + ("languages",), None, drop=True), "PROFILE_MISSING_FIELD"),
    ("family-empty-languages", mutated(FAMILY + ("languages",), []), "PROFILE_EMPTY_VALUE"),
    ("family-language-outside", mutated(FAMILY + ("languages",), ["fr"]), "PROFILE_UNKNOWN_LANGUAGE"),
    ("family-unknown-field", mutated(FAMILY + ("colour",), "red"), "PROFILE_UNKNOWN_FIELD"),
    ("page-target-zero", mutated(FAMILY + ("page_target",), 0), "PROFILE_OUT_OF_RANGE"),
    ("page-target-string", mutated(FAMILY + ("page_target",), "1"), "PROFILE_BAD_TYPE"),
    ("page-target-bool", mutated(FAMILY + ("page_target",), True), "PROFILE_BAD_TYPE"),
    ("skills-duplicate-folded", mutated(FAMILY + ("core_skills",), ["Résumé", "resume"]), "PROFILE_DUPLICATE_VALUE"),
    ("blocks-bad-id", mutated(FAMILY + ("excluded_blocks",), {"Bad Id": "reason"}), "PROFILE_INVALID_ID"),
    ("blocks-no-reason", mutated(FAMILY + ("excluded_blocks",), {"club": ""}), "PROFILE_EMPTY_VALUE"),
    ("clusters-bad-id", mutated(FAMILY + ("clusters",), ["Not Valid"]), "PROFILE_INVALID_ID"),
    ("policy-not-object", build(policy=[]), "PROFILE_BAD_TYPE"),
    ("policy-unknown", build(policy={"other": []}), "PROFILE_UNKNOWN_FIELD"),
    ("policy-conflict", build(policy={"never_publish_terms": ["Alpha"], "omit_by_default_terms": ["alpha"]}),
     "PROFILE_POLICY_CONFLICT"),
    ("policy-term-duplicate", build(policy={"never_publish_terms": ["Alpha", "ALPHA"]}), "PROFILE_DUPLICATE_VALUE"),
    ("policy-flag-not-bool", build(policy={"require_confirmation_date": "yes"}), "PROFILE_BAD_TYPE"),
    ("forbidden-unknown-language", build(policy={"forbidden_words": {"fr": ["x"]}}), "PROFILE_UNKNOWN_LANGUAGE"),
    ("forbidden-bad-code", build(policy={"forbidden_words": {"english": ["x"]}}), "PROFILE_INVALID_LANGUAGE"),
    ("skill-forbidden", build(policy={"never_publish_terms": ["Python"]},
                              families={"software": {"label": "S", "languages": ["en"], "core_skills": ["python"]}}),
     "PROFILE_SKILL_FORBIDDEN"),
    ("availability-not-list", build(availability={}), "PROFILE_BAD_TYPE"),
    ("availability-missing-fact", build(availability=[{"id": "a", "applies_to": ["INTERNSHIP"]}]),
     "PROFILE_MISSING_FIELD"),
    ("availability-bad-kind", build(availability=[{"id": "a", "fact_id": "f.one", "applies_to": ["GIG"]}]),
     "PROFILE_INVALID_VALUE"),
    ("availability-no-kind", build(availability=[{"id": "a", "fact_id": "f.one", "applies_to": []}]),
     "PROFILE_EMPTY_VALUE"),
    ("availability-duplicate-id", build(availability=[
        {"id": "a", "fact_id": "f.one", "applies_to": ["INTERNSHIP"]},
        {"id": "a", "fact_id": "f.two", "applies_to": ["INTERNSHIP"]}]), "PROFILE_DUPLICATE_VALUE"),
    ("availability-overlap", build(availability=[
        {"id": "a", "fact_id": "f.one", "applies_to": ["INTERNSHIP"]},
        {"id": "b", "fact_id": "f.one", "applies_to": ["INTERNSHIP", "PART_TIME"]}]), "PROFILE_DUPLICATE_VALUE"),
    ("taxonomy-other-builtin", build(taxonomy="builtin:custom"), "PROFILE_INVALID_TAXONOMY"),
    ("taxonomy-parent-path", build(taxonomy="../taxonomy.json"), "PROFILE_INVALID_TAXONOMY"),
    ("taxonomy-absolute", build(taxonomy="/etc/taxonomy.json"), "PROFILE_INVALID_TAXONOMY"),
    ("taxonomy-backslash", build(taxonomy="taxonomy\\mine.json"), "PROFILE_INVALID_TAXONOMY"),
    ("taxonomy-not-json", build(taxonomy="taxonomy.txt"), "PROFILE_INVALID_TAXONOMY"),
    ("selection-unknown-key", build(selection={"speed": 1}), "PROFILE_UNKNOWN_FIELD"),
    ("selection-negative", build(selection={"minimum_gain": -1}), "PROFILE_OUT_OF_RANGE"),
    ("selection-string", build(selection={"minimum_gain": "1"}), "PROFILE_BAD_TYPE"),
    ("selection-bool", build(selection={"minimum_gain": True}), "PROFILE_BAD_TYPE"),
    ("selection-factor-over-one", build(selection={"inferred_factor": 1.5}), "PROFILE_OUT_OF_RANGE"),
    ("selection-cap-below-penalty", build(selection={"off_target_penalty": 0.5, "off_target_penalty_cap": 0.2}),
     "PROFILE_OUT_OF_RANGE"),
    ("selection-huge", build(selection={"named_bonus": 1e300}), "PROFILE_OUT_OF_RANGE"),
    ("precedence-self", build(precedence_rules=[{"when_direct": "r", "keep": "a", "over": "a"}]),
     "PROFILE_PRECEDENCE_INVALID"),
    ("precedence-missing", build(precedence_rules=[{"when_direct": "r", "keep": "a"}]), "PROFILE_MISSING_FIELD"),
    ("precedence-cycle", build(precedence_rules=[{"when_direct": "r", "keep": "a", "over": "b"},
                                                 {"when_direct": "r", "keep": "b", "over": "c"},
                                                 {"when_direct": "r", "keep": "c", "over": "a"}]),
     "PROFILE_PRECEDENCE_CONFLICT"),
    ("precedence-duplicate", build(precedence_rules=[{"when_direct": "r", "keep": "a", "over": "b"},
                                                     {"when_direct": "r", "keep": "a", "over": "b"}]),
     "PROFILE_DUPLICATE_VALUE"),
    ("guidance-soften-no-text", build(guidance=[{"job_key": "j", "rules": [{"fact_id": "f.one", "action": "soften"}]}]),
     "PROFILE_GUIDANCE_INVALID"),
    ("guidance-omit-with-text", build(guidance=[{"job_key": "j", "rules": [
        {"fact_id": "f.one", "action": "omit", "text": "x"}]}]), "PROFILE_GUIDANCE_INVALID"),
    ("guidance-bad-action", build(guidance=[{"job_key": "j", "rules": [{"fact_id": "f.one", "action": "hide"}]}]),
     "PROFILE_INVALID_VALUE"),
    ("guidance-empty-rules", build(guidance=[{"job_key": "j", "rules": []}]), "PROFILE_EMPTY_VALUE"),
    ("guidance-duplicate-job", build(guidance=[
        {"job_key": "j", "rules": [{"fact_id": "f.one", "action": "omit"}]},
        {"job_key": "j", "rules": [{"fact_id": "f.two", "action": "omit"}]}]), "PROFILE_DUPLICATE_VALUE"),
    ("guidance-same-fact-twice", build(guidance=[{"job_key": "j", "rules": [
        {"fact_id": "f.one", "action": "omit"}, {"fact_id": "f.one", "action": "omit"}]}]), "PROFILE_GUIDANCE_INVALID"),
]


@pytest.mark.parametrize("document,code", [(case[1], case[2]) for case in CASES], ids=[case[0] for case in CASES])
def test_invalid_profiles_are_refused_with_a_stable_code(document, code):
    result = check(document)
    assert result.profile is None
    assert code in codes(result)


def test_every_documented_code_is_exercised_here():
    exercised = {case[2] for case in CASES}
    for code in ("PROFILE_NO_FAMILY", "PROFILE_POLICY_CONFLICT", "PROFILE_SKILL_FORBIDDEN", "PROFILE_PRECEDENCE_CONFLICT",
                 "PROFILE_GUIDANCE_INVALID", "PROFILE_INVALID_TAXONOMY", "PROFILE_UNKNOWN_SCHEMA"):
        assert code in exercised


def test_one_check_reports_every_problem_in_path_order():
    document = build(surprise=1, languages=[], policy={"other": 1})
    result = check(document)
    assert {"PROFILE_UNKNOWN_FIELD", "PROFILE_EMPTY_VALUE"} <= set(codes(result))
    assert [e.path for e in result.errors] == sorted(e.path for e in result.errors)


# --- JSON level --------------------------------------------------------------------------------------

@pytest.mark.parametrize("data,code", [
    (b"", "PROFILE_NOT_JSON"),
    (b"{", "PROFILE_NOT_JSON"),
    (b'{"schema": "Profile-v1", "schema": "Profile-v1"}', "PROFILE_DUPLICATE_KEY"),
    (b'{"a": NaN}', "PROFILE_NOT_JSON"),
    (b'{"a": Infinity}', "PROFILE_NOT_JSON"),
    (b"\xff\xfe{}", "PROFILE_NOT_UTF8"),
    (b"[]", "PROFILE_BAD_TYPE"),
    (b'"profile"', "PROFILE_BAD_TYPE"),
    (b"[" * 5000, "PROFILE_NOT_JSON"),
])
def test_unusable_json_is_refused(data, code):
    result = profile.check_bytes(data)
    assert result.profile is None and codes(result)[0] == code


def test_a_missing_file_is_unreadable(tmp_path):
    result = profile.check_file(tmp_path / "nope.json")
    assert codes(result) == ["PROFILE_FILE_UNREADABLE"] and result.profile_source_sha256 is None
    with pytest.raises(profile.ProfileError) as caught:
        profile.parse_file(tmp_path / "nope.json")
    assert caught.value.code == "PROFILE_FILE_UNREADABLE"


# --- extensions --------------------------------------------------------------------------------------

def test_extensions_are_kept_in_the_model_and_the_fingerprint_but_never_public():
    plain = check(MINIMAL).profile
    document = build(**{"x-note": "ZZ-EXT-ZZ"})
    document["identity"]["display_name"]["x-memo"] = {"inner": [1, 2]}
    extended = check(document).profile
    assert extended.to_model()["extensions"] == {"x-note": "ZZ-EXT-ZZ"}
    assert extended.profile_sha256 != plain.profile_sha256
    assert "ZZ-EXT-ZZ" not in json.dumps(extended.public_view())
    assert "ZZ-EXT-ZZ" not in json.dumps(extended.internal_preferences())


def test_extension_order_and_value_form_do_not_change_the_fingerprint():
    one = check(build(**{"x-a": "1", "x-b": "é"})).profile.profile_sha256
    two = check(build(**{"x-b": "e\u0301", "x-a": "1"})).profile.profile_sha256
    assert one == two


# --- fact references: nothing is confirmed without proof ----------------------------------------------

def test_availability_without_a_fact_base_is_unverified_and_warned():
    result = check(with_availability("avail.one"))
    assert result.errors == ()
    assert [w.code for w in result.warnings] == ["PROFILE_FACTS_NOT_CHECKED"]
    assert result.availability == (("av-0", profile.UNVERIFIED),)


def test_availability_backed_by_a_confirmed_fact_is_verified(factbase):
    result = check(with_availability("avail.one"), factbase)
    assert result.errors == () and result.warnings == ()
    assert result.availability == (("av-0", profile.VERIFIED),)
    assert [a["id"] for a in result.profile.confirmed_availability(factbase)] == ["av-0"]


def test_an_unknown_fact_reference_is_refused(factbase):
    result = check(with_availability("avail.nope"), factbase)
    assert codes(result) == ["PROFILE_FACT_UNKNOWN"] and result.availability == (("av-0", profile.REFUSED),)


@pytest.mark.parametrize("fact_id", ["avail.derived", "avail.unsure", "avail.gone"])
def test_availability_needs_a_confirmed_fact(fact_id, factbase):
    result = check(with_availability(fact_id), factbase)
    assert codes(result) == ["PROFILE_FACT_NOT_CONFIRMED"]


def test_the_confirmation_date_policy_applies_to_referenced_facts(factbase):
    document = with_availability("avail.undated")
    assert check(document, factbase).errors == ()
    document["policy"] = {"require_confirmation_date": True}
    assert codes(check(document, factbase)) == ["PROFILE_FACT_DATE_REQUIRED"]


def test_confirmed_availability_never_trusts_the_declaration(factbase):
    found = check(with_availability("avail.one")).profile
    changed = facts.parse_text(FACTS.replace("[avail.one] CONFIRMED", "[avail.one] WITHDRAWN"))
    assert found.availability and found.confirmed_availability(changed) == []


def test_guidance_references(factbase):
    document = build(guidance=[{"job_key": "job-1", "rules": [
        {"fact_id": "avail.derived", "action": "omit"},
        {"fact_id": "avail.one", "action": "soften", "text": "Available for short placements."}]}])
    assert check(document, factbase).errors == ()
    document["guidance"][0]["rules"].append({"fact_id": "avail.unsure", "action": "soften", "text": "Maybe."})
    assert codes(check(document, factbase)) == ["PROFILE_FACT_NOT_CONFIRMED"]
    document["guidance"][0]["rules"][-1] = {"fact_id": "avail.ghost", "action": "omit"}
    assert codes(check(document, factbase)) == ["PROFILE_FACT_UNKNOWN"]


def test_references_are_not_checked_when_the_structure_is_already_invalid(factbase):
    document = with_availability("avail.nope")
    document["surprise"] = 1
    assert codes(check(document, factbase)) == ["PROFILE_UNKNOWN_FIELD"]


# --- visibility: private, public, internal -----------------------------------------------------------

SECRET = "ZZ-SECRET"


def secret_profile():
    document = build(languages=["en", "fr"], default_language="en")
    document["identity"] = {
        "display_name": {"value": SECRET + "-NAME", "visibility": "private"},
        "headline": {"value": SECRET + "-HEAD", "visibility": "public"},
        "email": {"value": SECRET + "-MAIL", "visibility": "private"},
        "phone": {"value": SECRET + "-PHONE", "visibility": "private"},
        "links": [{"label": SECRET + "-LABEL", "value": SECRET + "-URL", "visibility": "private"},
                  {"value": SECRET + "-PUBLIC-URL", "visibility": "public"}],
    }
    document["policy"] = {"never_publish_terms": [SECRET + "-TERM"]}
    document["families"]["software"]["label"] = SECRET + "-FAMILY"
    return document


def test_public_view_holds_only_public_fields():
    found = check(secret_profile()).profile
    view = json.dumps(found.public_view())
    assert SECRET + "-HEAD" in view and SECRET + "-PUBLIC-URL" in view
    for private in ("-NAME", "-MAIL", "-PHONE", "-URL\"", "-LABEL", "-TERM", "-FAMILY"):
        assert SECRET + private not in view
    assert found.public_view()["identity"] == {"headline": SECRET + "-HEAD"}
    assert found.private_field_names() == ["display_name", "email", "links[0]", "phone"]


def test_a_field_is_never_public_by_default():
    document = copy.deepcopy(MINIMAL)
    del document["identity"]["display_name"]["visibility"]
    assert "PROFILE_MISSING_FIELD" in codes(check(document))


def test_a_private_display_name_is_warned_not_published():
    result = check(secret_profile())
    assert [w.code for w in result.warnings] == ["PROFILE_DISPLAY_NAME_PRIVATE"]
    assert "display_name" not in result.profile.public_view()["identity"]


def test_internal_preferences_exclude_identity():
    internal = check(secret_profile()).profile.internal_preferences()
    assert set(internal) == {"families", "policy", "availability", "taxonomy", "selection", "precedence_rules", "guidance"}
    assert SECRET + "-MAIL" not in json.dumps(internal)


def test_accessors_return_copies():
    found = check(MINIMAL).profile
    found.families["software"]["label"] = "tampered"
    found.to_model()["languages"].append("fr")
    found.public_view()["languages"].append("fr")
    assert found.families["software"]["label"] == "Software" and found.languages == ("en",)


def messy_profile():
    """A profile that is wrong everywhere, with a secret in every value."""
    return {
        "schema": "Profile-v1",
        "languages": [SECRET + "-LANG", "en"],
        "default_language": SECRET + "-DEF",
        "identity": {"display_name": {"value": 3, "visibility": SECRET + "-VIS"},
                     "email": {"value": SECRET + "-MAIL\n", "visibility": "public"},
                     SECRET + "@leak.example": {"value": "x", "visibility": "public"}},
        "families": {SECRET + "-FAMILY": {"label": SECRET, "languages": [SECRET]}},
        "policy": {"never_publish_terms": [SECRET + "-T", SECRET + "-T"],
                   "forbidden_words": {SECRET: [SECRET]}},
        "availability": [{"id": SECRET, "fact_id": SECRET, "applies_to": [SECRET]}],
        "taxonomy": SECRET + "/../x",
        "selection": {"minimum_gain": SECRET},
        "guidance": [{"job_key": SECRET, "rules": [{"fact_id": SECRET, "action": SECRET, "text": SECRET}]}],
    }


def test_error_messages_and_paths_never_repeat_a_value():
    result = check(messy_profile())
    assert len(result.errors) > 10
    blob = json.dumps([e.as_dict() for e in result.errors] + [w.as_dict() for w in result.warnings])
    assert SECRET not in blob and "leak.example" not in blob


def test_profile_error_text_never_repeats_a_value():
    error = profile.ProfileError(profile.check_data(messy_profile()).errors)
    assert SECRET not in str(error)


# --- fingerprints ------------------------------------------------------------------------------------

def test_fingerprints_ignore_key_order_line_endings_and_bom():
    text = json.dumps(MINIMAL, indent=2)
    plain = profile.check_bytes(text.encode("utf-8")).profile
    crlf = profile.check_bytes(("\ufeff" + text.replace("\n", "\r\n")).encode("utf-8")).profile
    reordered = profile.check_bytes(json.dumps(dict(reversed(list(MINIMAL.items())))).encode("utf-8")).profile
    assert plain.profile_sha256 == crlf.profile_sha256 == reordered.profile_sha256
    assert plain.profile_source_sha256 == crlf.profile_source_sha256 != reordered.profile_source_sha256


def test_the_source_hash_is_a_normalised_source_hash():
    data = encode(MINIMAL)
    assert profile.check_bytes(data).profile_source_sha256 == canonical.sha256_text(data)


def test_sets_are_order_free_but_ordered_lists_are_not():
    base = build(languages=["en", "fr"], default_language="en",
                 policy={"never_publish_terms": ["b", "a"], "forbidden_words": {"en": ["y", "x"]}})
    base["families"]["software"]["languages"] = ["fr", "en"]
    base["families"]["software"]["core_skills"] = ["Python", "Git"]
    swapped = copy.deepcopy(base)
    swapped["languages"] = ["fr", "en"]
    swapped["policy"]["never_publish_terms"] = ["a", "b"]
    swapped["policy"]["forbidden_words"]["en"] = ["x", "y"]
    swapped["families"]["software"]["languages"] = ["en", "fr"]
    assert check(base).profile.profile_sha256 == check(swapped).profile.profile_sha256
    swapped["families"]["software"]["core_skills"] = ["Git", "Python"]
    assert check(base).profile.profile_sha256 != check(swapped).profile.profile_sha256


def test_explicit_defaults_equal_omitted_defaults_and_int_equals_float():
    omitted = check(MINIMAL).profile.profile_sha256
    explicit = check(build(taxonomy="builtin:generic-v1", selection={"baseline_prior": 0.25, "minimum_gain": 1},
                           policy={"require_confirmation_date": False}, availability=[], guidance=[],
                           precedence_rules=[])).profile.profile_sha256
    assert omitted == explicit


@pytest.mark.parametrize("change", [
    lambda d: d["identity"]["display_name"].update(value="Other Name"),
    lambda d: d["identity"]["display_name"].update(visibility="private"),
    lambda d: d["families"]["software"].update(label="Other"),
    lambda d: d.update(selection={"minimum_gain": 2}),
    lambda d: d.update(policy={"require_confirmation_date": True}),
    lambda d: d.update(taxonomy="taxonomy/mine.json"),
])
def test_a_meaningful_change_changes_the_fingerprint(change):
    document = copy.deepcopy(MINIMAL)
    change(document)
    assert check(document).profile.profile_sha256 != check(MINIMAL).profile.profile_sha256


def test_whitespace_and_unicode_form_of_values_do_not_change_the_fingerprint():
    one = copy.deepcopy(MINIMAL)
    one["identity"]["display_name"]["value"] = "Zoé  Sample"
    two = copy.deepcopy(MINIMAL)
    two["identity"]["display_name"]["value"] = "Zoe\u0301 Sample "
    assert check(one).profile.profile_sha256 == check(two).profile.profile_sha256


def test_the_example_fingerprint_is_stable():
    first = profile.parse_file(EXAMPLE_DIR / "profile.json")
    second = profile.parse_file(EXAMPLE_DIR / "profile.json")
    assert first.profile_sha256 == second.profile_sha256 and len(first.profile_sha256) == 64


# --- workspace configuration -------------------------------------------------------------------------

def test_the_profile_path_is_configurable_and_safe(tmp_path):
    assert config.load(tmp_path)["profile"] == "profile.json"
    (tmp_path / "modularcv.json").write_text(json.dumps({"profile": "config/me.json"}), encoding="utf-8")
    assert config.load(tmp_path)["profile"] == "config/me.json"
    for bad in ("..\\me.json", "../me.json", "/abs/me.json", "C:/me.json", "", 3):
        (tmp_path / "modularcv.json").write_text(json.dumps({"profile": bad}), encoding="utf-8")
        with pytest.raises(config.ConfigError):
            config.load(tmp_path)


# --- command line ------------------------------------------------------------------------------------

def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(str(EXAMPLE_DIR), str(root))
    return root


def test_check_the_example_workspace(workspace, capsys):
    code, out, err = run(capsys, "profile", "check", "--root", str(workspace))
    report = json.loads(out)
    assert code == 0 and err == "" and report["status"] == "OK" and report["facts_checked"] is True
    assert report["availability"] == [{"id": "internship-2027", "state": "VERIFIED"}]
    assert report["identity_visibility"]["phone"] == "private" and report["counts"]["families"] == 1
    assert report["profile_sha256"] == profile.parse_file(workspace / "profile.json").profile_sha256


def test_the_report_never_prints_a_value(tmp_path, capsys):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "profile.json").write_text(json.dumps(secret_profile()), encoding="utf-8")
    code, out, err = run(capsys, "profile", "check", "--root", str(root))
    assert code == 0 and SECRET not in out + err
    code, out, err = run(capsys, "profile", "fingerprint", "--root", str(root))
    assert code == 0 and SECRET not in out + err
    (root / "profile.json").write_text(json.dumps(messy_profile()), encoding="utf-8")
    code, out, err = run(capsys, "profile", "check", "--root", str(root))
    assert code == 1 and SECRET not in out + err and "PROFILE_" in err


def test_invalid_profile_exits_1_with_codes_and_paths(workspace, capsys):
    document = json.loads((workspace / "profile.json").read_text(encoding="utf-8"))
    document["families"]["software"]["languages"] = ["de"]
    (workspace / "profile.json").write_text(json.dumps(document), encoding="utf-8")
    code, out, err = run(capsys, "profile", "check", "--root", str(workspace))
    report = json.loads(out)
    assert code == 1 and report["status"] == "INVALID" and report["profile_sha256"] is None
    assert report["errors"][0]["code"] == "PROFILE_UNKNOWN_LANGUAGE"
    assert "families.software.languages[0]" in err


def test_missing_profile_exits_2(tmp_path, capsys):
    code, out, err = run(capsys, "profile", "check", "--root", str(tmp_path))
    assert code == 2 and out == "" and "PROFILE_FILE_UNREADABLE" in err


def test_an_unsafe_workspace_configuration_exits_2(tmp_path, capsys):
    (tmp_path / "modularcv.json").write_text(json.dumps({"profile": "../x.json"}), encoding="utf-8")
    code, out, err = run(capsys, "profile", "check", "--root", str(tmp_path))
    assert code == 2 and "CONFIG_ERROR" in err


def test_references_need_a_readable_valid_fact_base(workspace, capsys):
    (workspace / "facts.md").unlink()
    code, out, err = run(capsys, "profile", "check", "--root", str(workspace))
    assert code == 2 and "FACTS_UNREADABLE" in err and out == ""
    (workspace / "facts.md").write_text("not a fact base", encoding="utf-8")
    code, out, err = run(capsys, "profile", "check", "--root", str(workspace))
    assert code == 1 and json.loads(out)["errors"][0]["code"] == "PROFILE_FACTS_INVALID"


def test_no_facts_skips_the_references_and_says_so(workspace, capsys):
    (workspace / "facts.md").unlink()
    code, out, _ = run(capsys, "profile", "check", "--root", str(workspace), "--no-facts")
    report = json.loads(out)
    assert code == 0 and report["facts_checked"] is False
    assert report["availability"] == [{"id": "internship-2027", "state": "UNVERIFIED"}]
    assert [w["code"] for w in report["warnings"]] == ["PROFILE_FACTS_NOT_CHECKED"]


def test_a_profile_without_references_needs_no_fact_base(tmp_path, capsys):
    (tmp_path / "profile.json").write_text(json.dumps(MINIMAL), encoding="utf-8")
    code, out, _ = run(capsys, "profile", "check", "--root", str(tmp_path))
    assert code == 0 and json.loads(out)["warnings"] == []


def test_facts_option_selects_another_fact_base(workspace, capsys):
    other = workspace / "other.md"
    other.write_text(FACTS, encoding="utf-8")
    code, out, _ = run(capsys, "profile", "check", "--root", str(workspace), "--facts", str(other))
    assert code == 1 and json.loads(out)["errors"][0]["code"] == "PROFILE_FACT_UNKNOWN"


def test_fingerprint_command(workspace, capsys):
    expected = profile.parse_file(workspace / "profile.json")
    code, out, _ = run(capsys, "profile", "fingerprint", "--root", str(workspace))
    assert code == 0 and json.loads(out)["profile_sha256"] == expected.profile_sha256
    code, out, _ = run(capsys, "profile", "fingerprint", "--root", str(workspace), "--only", "profile")
    assert out.strip() == expected.profile_sha256
    code, out, _ = run(capsys, "profile", "fingerprint", "--root", str(workspace), "--only", "source")
    assert out.strip() == expected.profile_source_sha256
    (workspace / "profile.json").write_text("{}", encoding="utf-8")
    code, out, _ = run(capsys, "profile", "fingerprint", "--root", str(workspace))
    assert code == 1 and out == ""


def test_an_explicit_file_argument_wins_over_the_configuration(workspace, capsys):
    copy_path = workspace / "alt.json"
    copy_path.write_text(json.dumps(MINIMAL), encoding="utf-8")
    code, out, _ = run(capsys, "profile", "check", str(copy_path), "--root", str(workspace))
    assert code == 0 and json.loads(out)["counts"]["availability"] == 0


def test_profile_commands_never_write(workspace, capsys):
    before = tree_hash(workspace)
    for argv in (("profile", "check"), ("profile", "check", "--no-facts"), ("profile", "fingerprint")):
        run(capsys, *argv, "--root", str(workspace))
    assert tree_hash(workspace) == before
    (workspace / "profile.json").write_text("{", encoding="utf-8")
    before = tree_hash(workspace)
    run(capsys, "profile", "check", "--root", str(workspace))
    assert tree_hash(workspace) == before


def test_the_check_is_idempotent(workspace, capsys):
    first = run(capsys, "profile", "check", "--root", str(workspace))
    second = run(capsys, "profile", "check", "--root", str(workspace))
    assert first == second


def test_facts_check_can_use_the_profile_policy(workspace, capsys):
    document = json.loads((workspace / "profile.json").read_text(encoding="utf-8"))
    document["policy"]["require_confirmation_date"] = True
    (workspace / "profile.json").write_text(json.dumps(document), encoding="utf-8")
    code, out, _ = run(capsys, "facts", "check", "--root", str(workspace))
    assert code == 0
    code, out, _ = run(capsys, "facts", "check", "--root", str(workspace), "--use-profile")
    report = json.loads(out)
    assert code == 1 and "FACT_DATE_REQUIRED" in [e["code"] for e in report["errors"]]
    (workspace / "profile.json").write_text("{", encoding="utf-8")
    code, out, err = run(capsys, "facts", "check", "--root", str(workspace), "--use-profile")
    assert code == 2 and "PROFILE_" in err


def test_a_windows_style_root_and_posix_style_root_give_the_same_report(workspace, capsys):
    posix = run(capsys, "profile", "check", "--root", workspace.as_posix())
    native = run(capsys, "profile", "check", "--root", str(workspace))
    assert posix == native


# --- robustness: a mutated document is refused or accepted, never a crash ----------------------------------

SWAPS = [None, 0, -1, 1.5, True, "", "x", "ZZ", [], {}, [None], {"a": 1}, ["a", "a"], {"x-k": 1}]


def paths_of(node, prefix=()):
    yield prefix
    if isinstance(node, dict):
        for key in node:
            yield from paths_of(node[key], prefix + (key,))
    elif isinstance(node, list):
        for position, item in enumerate(node):
            yield from paths_of(item, prefix + (position,))


def swap_at(document, path, value):
    document = copy.deepcopy(document)
    if not path:
        return value
    node = document
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return document


def test_no_mutation_of_the_example_can_crash_the_checker():
    example = json.loads((EXAMPLE_DIR / "profile.json").read_text(encoding="utf-8"))
    base = facts.parse_file(EXAMPLE_DIR / "facts.md")
    checked = 0
    for path in paths_of(example):
        for value in SWAPS:
            result = profile.check_data(swap_at(example, path, value), None, base)
            assert (result.profile is None) == bool(result.errors)
            if result.profile is not None:
                assert len(result.profile.profile_sha256) == 64
            checked += 1
    assert checked > 300


def test_removing_any_single_field_never_crashes_and_required_ones_are_reported():
    example = json.loads((EXAMPLE_DIR / "profile.json").read_text(encoding="utf-8"))
    for path in paths_of(example):
        if not path or not isinstance(path[-1], str):
            continue
        document = copy.deepcopy(example)
        node = document
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
        result = profile.check_data(document)
        assert (result.profile is None) == bool(result.errors)
    for required in ("schema", "languages", "identity", "families"):
        document = copy.deepcopy(example)
        del document[required]
        assert profile.check_data(document).profile is None
