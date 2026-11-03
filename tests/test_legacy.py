"""Controlled import of a historical document (LegacyFactMap-v1) and `facts import` (M4). Synthetic data only."""
import copy
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from modularcv import __main__ as cli
from modularcv import canonical, facts, legacy
from synthetic import tree_hash

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = REPO / "examples" / "workspace"

MAPPING = {
    "schema": "LegacyFactMap-v1",
    "headings": [{"pattern": "Experience", "section": "experience", "status": "DERIVED"}],
}


def mapping_with(**changes):
    document = copy.deepcopy(MAPPING)
    document.update(changes)
    return document


def compiled(document):
    result = legacy.check_mapping_data(document)
    assert result.errors == (), [e.as_dict() for e in result.errors]
    return result.mapping


def doc(*lines):
    return "\n".join(lines) + "\n"


def run_import(text, mapping=None):
    return legacy.run(compiled(mapping or MAPPING), text.encode("utf-8"))


def decisions(result):
    return [(e["line"], e["decision"], e["code"]) for e in result.report["lines"]]


def fact_id(section, text):
    return "%s.%s" % (section, hashlib.sha256(text.encode("utf-8")).hexdigest()[:10])


def parsed(result):
    return facts.parse_text(result.facts_text)


def mapping_codes(document):
    return [e.code for e in legacy.check_mapping_data(document).errors]


# --- the mapping file --------------------------------------------------------------------------------

def test_the_example_mapping_is_valid():
    result = legacy.check_mapping_file(EXAMPLE_DIR / "import-map.json")
    assert result.errors == () and len(result.mapping_sha256) == 64


@pytest.mark.parametrize("document,code", [
    (mapping_with(schema="LegacyFactMap-v2"), "LEGACY_MAP_UNKNOWN_SCHEMA"),
    (mapping_with(surprise=1), "LEGACY_MAP_UNKNOWN_FIELD"),
    ({"schema": "LegacyFactMap-v1"}, "LEGACY_MAP_MISSING_FIELD"),
    (mapping_with(headings=[]), "LEGACY_MAP_EMPTY_VALUE"),
    (mapping_with(headings=[{"pattern": "(", "section": "s", "status": "DERIVED"}]), "LEGACY_MAP_BAD_PATTERN"),
    (mapping_with(headings=[{"pattern": "", "section": "s", "status": "DERIVED"}]), "LEGACY_MAP_BAD_PATTERN"),
    (mapping_with(headings=[{"pattern": "x" * 301, "section": "s", "status": "DERIVED"}]), "LEGACY_MAP_BAD_PATTERN"),
    (mapping_with(headings=[{"pattern": "E", "status": "DERIVED"}]), "LEGACY_MAP_MISSING_FIELD"),
    (mapping_with(headings=[{"pattern": "E", "section": "s"}]), "LEGACY_MAP_MISSING_FIELD"),
    (mapping_with(headings=[{"pattern": "E", "section": "Bad Id", "status": "DERIVED"}]), "LEGACY_MAP_INVALID_ID"),
    (mapping_with(headings=[{"pattern": "E", "section": "s" * 70, "status": "DERIVED"}]), "LEGACY_MAP_INVALID_ID"),
    (mapping_with(headings=[{"pattern": "E", "section": "s", "status": "SURE"}]), "LEGACY_MAP_INVALID_VALUE"),
    (mapping_with(headings=[{"pattern": "E", "section": "s", "status": "DERIVED", "level": 7}]),
     "LEGACY_MAP_OUT_OF_RANGE"),
    (mapping_with(headings=[{"pattern": "E", "section": "s", "status": "DERIVED", "title": "A {b}"}]),
     "LEGACY_MAP_INVALID_VALUE"),
    (mapping_with(headings=[{"pattern": "E", "section": "s", "status": "DERIVED", "lang": "english"}]),
     "LEGACY_MAP_INVALID_LANGUAGE"),
    (mapping_with(headings=[{"pattern": "E", "action": "ignore", "section": "s"}]), "LEGACY_MAP_INVALID_RULE"),
    (mapping_with(headings=[{"pattern": "E", "action": "inherit", "status": "DERIVED"}]), "LEGACY_MAP_INVALID_RULE"),
    (mapping_with(headings=[{"pattern": "E", "action": "delete"}]), "LEGACY_MAP_INVALID_VALUE"),
    (mapping_with(headings=[{"pattern": "E", "section": "s", "status": "CONFIRMED"}]),
     "LEGACY_MAP_CONFIRMED_NOT_ALLOWED"),
    (mapping_with(allow_confirmed="yes"), "LEGACY_MAP_BAD_TYPE"),
    (mapping_with(status_rules=[{"pattern": "x", "status": "CONFIRMED"}], allow_confirmed=True),
     "LEGACY_MAP_CONFIRMED_NOT_ALLOWED"),
    (mapping_with(status_rules=[{"pattern": "(", "status": "NOT_CONFIRMED"}]), "LEGACY_MAP_BAD_PATTERN"),
    (mapping_with(status_rules=[{"pattern": "x"}]), "LEGACY_MAP_MISSING_FIELD"),
    (mapping_with(date_patterns=["no group here"]), "LEGACY_MAP_BAD_PATTERN"),
    (mapping_with(date_patterns=["(a)(b)"]), "LEGACY_MAP_BAD_PATTERN"),
    (mapping_with(date_patterns="x"), "LEGACY_MAP_BAD_TYPE"),
    (mapping_with(ignore_patterns=["["]), "LEGACY_MAP_BAD_PATTERN"),
])
def test_invalid_mappings_are_refused_with_a_stable_code(document, code):
    assert code in mapping_codes(document)


def test_mapping_json_problems_are_refused():
    assert legacy.check_mapping_bytes(b"{").errors[0].code == "LEGACY_MAP_NOT_JSON"
    assert legacy.check_mapping_bytes(b'{"a":1,"a":2}').errors[0].code == "LEGACY_MAP_DUPLICATE_KEY"
    assert legacy.check_mapping_bytes(b"\xff").errors[0].code == "LEGACY_MAP_NOT_UTF8"
    assert legacy.check_mapping_bytes(b"[]").errors[0].code == "LEGACY_MAP_BAD_TYPE"


def test_a_missing_mapping_file_is_unreadable(tmp_path):
    result = legacy.check_mapping_file(tmp_path / "none.json")
    assert result.errors[0].code == "LEGACY_MAP_FILE_UNREADABLE" and result.mapping is None


def test_mapping_extensions_are_kept_in_the_fingerprint():
    plain = legacy.check_mapping_data(MAPPING).mapping_sha256
    extended = legacy.check_mapping_data(mapping_with(**{"x-owner": "me"})).mapping_sha256
    assert plain != extended


def test_mapping_fingerprint_ignores_key_order_and_file_formatting():
    one = legacy.check_mapping_bytes(json.dumps(MAPPING, indent=4).encode()).mapping_sha256
    two = legacy.check_mapping_bytes(json.dumps(dict(reversed(list(MAPPING.items())))).encode()).mapping_sha256
    assert one == two


# --- classification: accepted, unclassified, ignored --------------------------------------------------

def test_a_valid_import_is_complete_and_proposes_a_valid_factbase():
    result = run_import(doc("# Notes", "", "## Experience", "", "- Built tools.", "- Wrote tests."))
    assert result.complete and result.report["problems"] == 0
    base = parsed(result)
    assert [f.id for f in base.facts] == [fact_id("experience", "Built tools."), fact_id("experience", "Wrote tests.")]
    assert {f.status for f in base.facts} == {"DERIVED"}
    assert result.report["output"]["factbase_sha256"] == base.factbase_sha256
    assert result.report["output"]["facts_source_sha256"] == canonical.sha256_text(result.facts_text)


def test_a_line_the_mapping_cannot_classify_is_never_imported():
    result = run_import(doc("## Experience", "- Built tools.", "", "ZZ-LOOSE-PROSE here", "", "## Hobbies", "- ZZ-HOBBY"))
    assert not result.complete
    kinds = {(e["line"], e["decision"], e["code"]) for e in result.report["lines"]}
    assert (4, "UNCLASSIFIED", "FACT_UNMAPPED") in kinds and (7, "UNCLASSIFIED", "FACT_UNMAPPED") in kinds
    assert "ZZ-LOOSE-PROSE" not in result.facts_text and "ZZ-HOBBY" not in result.facts_text
    assert result.report["counts"]["UNCLASSIFIED"] == 2 and result.report["problems"] == 2


def test_bullets_before_any_heading_are_unclassified():
    result = run_import(doc("- Orphan bullet.", "## Experience", "- Kept."))
    assert decisions(result)[0] == (1, "UNCLASSIFIED", "FACT_UNMAPPED")


def test_prose_tables_and_rules_are_unclassified_unless_ignored():
    text = doc("## Experience", "| a | b |", "---", "* star bullet", "1. numbered", "2) paren")
    result = run_import(text)
    assert result.report["counts"]["UNCLASSIFIED"] == 2 and result.report["counts"]["ACCEPTED"] == 3
    ignoring = run_import(text, mapping_with(ignore_patterns=["---", r"\|.*\|"]))
    assert ignoring.complete and ignoring.report["counts"]["IGNORED"] == 2


def test_nothing_accepted_means_no_output_and_not_complete():
    result = run_import(doc("just prose", "", "more"))
    assert result.facts_text is None and result.report["output"] is None and not result.complete
    empty = run_import("")
    assert empty.facts_text is None and not empty.complete and empty.report["lines"] == []


def test_continuation_lines_belong_to_their_bullet():
    result = run_import(doc("## Experience", "- Built tools", "  with several parts", "\tand a tail.", "- Next."))
    assert result.complete
    first = result.report["lines"][1]
    assert (first["line"], first["end_line"]) == (2, 4)
    assert parsed(result).facts[0].text == "Built tools with several parts and a tail."


def test_an_unindented_following_line_is_not_a_continuation():
    result = run_import(doc("## Experience", "- Built tools", "dangling words"))
    assert decisions(result)[-1] == (3, "UNCLASSIFIED", "FACT_UNMAPPED")


def test_headings_choose_the_section_and_title():
    mapping = mapping_with(headings=[
        {"pattern": "Work", "section": "experience", "title": "Experience", "status": "DERIVED", "lang": "en"},
        {"pattern": "Travail", "section": "experience", "status": "NOT_CONFIRMED", "lang": "fr"}])
    result = run_import(doc("## Work", "- Alpha.", "## Travail", "- Beta."), mapping)
    base = parsed(result)
    assert [(f.section, f.status, f.lang) for f in base.facts] == [
        ("experience", "DERIVED", "en"), ("experience", "NOT_CONFIRMED", "fr")]
    assert "## Experience {#experience}" in result.facts_text


def test_heading_level_restricts_a_rule():
    mapping = mapping_with(headings=[{"pattern": "Experience", "section": "e", "status": "DERIVED", "level": 3}])
    result = run_import(doc("## Experience", "- Not level three."), mapping)
    assert decisions(result)[1] == (2, "UNCLASSIFIED", "FACT_UNMAPPED")
    assert run_import(doc("### Experience", "- Level three."), mapping).complete


def test_ignored_headings_skip_their_bullets_and_inherit_keeps_the_parent():
    mapping = mapping_with(headings=[
        {"pattern": "Experience", "section": "experience", "status": "DERIVED"},
        {"pattern": "Skipped", "action": "ignore"},
        {"pattern": "Detail", "action": "inherit", "level": 3}])
    result = run_import(doc("## Experience", "- One.", "### Detail", "- Two.", "## Skipped", "- Three.", "### Detail",
                            "- Four."), mapping)
    by_line = {e["line"]: e["decision"] for e in result.report["lines"]}
    assert by_line[2] == "ACCEPTED" and by_line[4] == "ACCEPTED"
    assert by_line[6] == "IGNORED" and by_line[8] == "IGNORED"  # an inherited context keeps the ignore
    assert result.complete


def test_an_unmatched_subheading_closes_the_section():
    result = run_import(doc("## Experience", "- One.", "### Unknown detail", "- Two."))
    assert decisions(result)[-1] == (4, "UNCLASSIFIED", "FACT_UNMAPPED")


# --- no implicit promotion to CONFIRMED -----------------------------------------------------------------

def test_the_default_mapping_never_produces_a_confirmed_fact():
    result = run_import(doc("## Experience", "- Confirmed by me, honest. CONFIRMED", "- Another."))
    assert result.report["facts_by_status"]["CONFIRMED"] == 0
    assert all(f.status == "DERIVED" for f in parsed(result).facts)
    assert parsed(result).publishable() == ()


def test_confirmed_needs_two_explicit_declarations():
    one = mapping_with(headings=[{"pattern": "Experience", "section": "e", "status": "CONFIRMED"}])
    assert "LEGACY_MAP_CONFIRMED_NOT_ALLOWED" in mapping_codes(one)
    two = mapping_with(allow_confirmed=True, headings=one["headings"])
    result = run_import(doc("## Experience", "- Verified."), two)
    assert result.report["facts_by_status"]["CONFIRMED"] == 1 and len(parsed(result).publishable()) == 1


def test_a_line_rule_can_lower_a_status():
    mapping = mapping_with(status_rules=[{"pattern": r"\[not confirmed\]", "status": "NOT_CONFIRMED"}])
    result = run_import(doc("## Experience", "- Fine.", "- Doubtful. [not confirmed]"), mapping)
    assert [f.status for f in parsed(result).facts] == ["DERIVED", "NOT_CONFIRMED"]


def test_a_line_rule_can_never_raise_a_status():
    mapping = mapping_with(
        headings=[{"pattern": "Experience", "section": "e", "status": "NOT_CONFIRMED"}],
        status_rules=[{"pattern": "verified", "status": "DERIVED"}])
    result = run_import(doc("## Experience", "- It is verified."), mapping)
    assert decisions(result)[1] == (2, "REJECTED", "LEGACY_PROMOTION_REFUSED")
    assert result.facts_text is None and not result.complete


def test_lateral_moves_between_non_publishable_statuses_are_not_promotions():
    mapping = mapping_with(
        headings=[{"pattern": "Experience", "section": "e", "status": "NOT_CONFIRMED"}],
        status_rules=[{"pattern": "retracted", "status": "WITHDRAWN"}])
    result = run_import(doc("## Experience", "- It was retracted."), mapping)
    assert parsed(result).facts[0].status == "WITHDRAWN"


def test_conflicting_status_rules_are_ambiguous():
    mapping = mapping_with(status_rules=[{"pattern": "alpha", "status": "NOT_CONFIRMED"},
                                         {"pattern": "beta", "status": "WITHDRAWN"}])
    result = run_import(doc("## Experience", "- alpha and beta.", "- alpha only."), mapping)
    assert decisions(result)[1] == (2, "AMBIGUOUS", "LEGACY_CONFLICTING_STATUS_RULES")
    assert [f.status for f in parsed(result).facts] == ["NOT_CONFIRMED"]


def test_equal_status_rules_that_both_match_are_not_ambiguous():
    mapping = mapping_with(status_rules=[{"pattern": "alpha", "status": "NOT_CONFIRMED"},
                                         {"pattern": "beta", "status": "NOT_CONFIRMED"}])
    assert run_import(doc("## Experience", "- alpha and beta."), mapping).complete


# --- dates are never invented ---------------------------------------------------------------------------

DATE_MAPPING = {"allow_confirmed": True, "date_patterns": [r"\(on (\d{4}-\d{2}-\d{2})\)"],
                "headings": [{"pattern": "Experience", "section": "e", "status": "CONFIRMED"}]}


def test_no_date_is_ever_inserted():
    result = run_import(doc("## Experience", "- No date here."), mapping_with(**DATE_MAPPING))
    assert parsed(result).facts[0].confirmed_on is None and result.report["lines"][1]["dated"] is False


def test_a_declared_pattern_sets_a_valid_date():
    result = run_import(doc("## Experience", "- Did it (on 2026-02-03)."), mapping_with(**DATE_MAPPING))
    assert parsed(result).facts[0].confirmed_on == "2026-02-03" and result.report["lines"][1]["dated"] is True


def test_an_invalid_date_rejects_the_line():
    result = run_import(doc("## Experience", "- Did it (on 2026-02-30)."), mapping_with(**DATE_MAPPING))
    assert decisions(result)[1] == (2, "REJECTED", "LEGACY_INVALID_DATE") and result.facts_text is None


def test_two_different_dates_are_ambiguous():
    mapping = mapping_with(**DATE_MAPPING)
    mapping["date_patterns"].append(r"\[(\d{4}-\d{2}-\d{2})\]")
    result = run_import(doc("## Experience", "- Did it (on 2026-02-03) [2026-03-04]."), mapping)
    assert decisions(result)[1] == (2, "AMBIGUOUS", "LEGACY_CONFLICTING_DATES")
    same = run_import(doc("## Experience", "- Did it (on 2026-02-03) [2026-02-03]."), mapping)
    assert parsed(same).facts[0].confirmed_on == "2026-02-03"


def test_a_date_is_only_applied_to_confirmed_facts():
    mapping = mapping_with(**DATE_MAPPING)
    mapping["status_rules"] = [{"pattern": "(?i)maybe", "status": "NOT_CONFIRMED"}]
    result = run_import(doc("## Experience", "- Maybe did it (on 2026-02-03)."), mapping)
    fact = parsed(result).facts[0]
    assert fact.status == "NOT_CONFIRMED" and fact.confirmed_on is None


# --- duplicates and ambiguities ------------------------------------------------------------------------

def test_an_exact_duplicate_is_listed_and_not_imported_twice():
    result = run_import(doc("## Experience", "- Same words.", "- Same   words.", "- SAME WORDS."))
    assert result.complete and len(parsed(result).facts) == 1
    assert decisions(result)[2:] == [(3, "DUPLICATE", "LEGACY_DUPLICATE_TEXT"), (4, "DUPLICATE", "LEGACY_DUPLICATE_TEXT")]
    assert result.report["lines"][2]["duplicate_of"] == 2


def test_the_same_text_with_two_statuses_is_ambiguous_and_imported_nowhere():
    mapping = mapping_with(headings=[
        {"pattern": "Good", "section": "good", "status": "DERIVED"},
        {"pattern": "Bad", "section": "bad", "status": "NOT_CONFIRMED"}])
    result = run_import(doc("## Good", "- Same claim.", "## Bad", "- Same claim.", "- Other."), mapping)
    assert [d[1:] for d in decisions(result) if d[0] in (2, 4)] == [("AMBIGUOUS", "LEGACY_CONFLICTING_DUPLICATES")] * 2
    assert [f.text for f in parsed(result).facts] == ["Other."]
    assert not result.complete


def test_the_same_text_in_two_sections_with_one_status_is_a_duplicate():
    mapping = mapping_with(headings=[
        {"pattern": "A", "section": "a", "status": "DERIVED"}, {"pattern": "B", "section": "b", "status": "DERIVED"}])
    result = run_import(doc("## A", "- Same claim.", "## B", "- Same claim."), mapping)
    assert result.complete and [f.section for f in parsed(result).facts] == ["a"]


def test_a_heading_matched_by_rules_with_different_effects_is_ambiguous():
    mapping = mapping_with(headings=[
        {"pattern": "Experience", "section": "a", "status": "DERIVED"},
        {"pattern": "Exp.*", "section": "b", "status": "DERIVED"}])
    result = run_import(doc("## Experience", "- Claim."), mapping)
    assert decisions(result) == [(1, "AMBIGUOUS", "LEGACY_AMBIGUOUS_HEADING"), (2, "AMBIGUOUS", "LEGACY_AMBIGUOUS_HEADING")]
    assert result.facts_text is None


def test_two_rules_with_the_same_effect_are_not_ambiguous():
    mapping = mapping_with(headings=[
        {"pattern": "Experience", "section": "a", "status": "DERIVED"},
        {"pattern": "Exp.*", "section": "a", "status": "DERIVED"}])
    assert run_import(doc("## Experience", "- Claim."), mapping).complete


# --- technologies ---------------------------------------------------------------------------------------

TECH_MAPPING = mapping_with(headings=[
    {"pattern": "Experience", "section": "experience", "status": "DERIVED"},
    {"pattern": "Tools", "action": "technologies"}])


def test_declared_technologies_are_attached_by_whole_word_only():
    text = doc("## Tools", "- Python", "- C++", "- Git", "- python", "## Experience",
               "- Wrote Python and C++ code.", "- Pythonic habits, gitignore tricks.", "- ÉCOLE python notes.")
    result = run_import(text, TECH_MAPPING)
    assert result.complete and result.report["technologies_declared"] == 3
    technologies = [f.technologies for f in parsed(result).facts]
    assert technologies == [("Python", "C++"), (), ("Python",)]
    assert result.report["counts"]["TECHNOLOGY"] == 3 and result.report["counts"]["DUPLICATE"] == 1


def test_the_technology_list_can_come_after_the_facts():
    result = run_import(doc("## Experience", "- Wrote Python code.", "## Tools", "- Python"), TECH_MAPPING)
    assert parsed(result).facts[0].technologies == ("Python",)


def test_unsafe_technology_names_are_rejected():
    result = run_import(doc("## Tools", "- A, B", "- C;D", "- {E}", "- " + "x" * 61, "## Experience", "- Fact."), TECH_MAPPING)
    assert [d[2] for d in decisions(result) if d[1] == "REJECTED"] == ["LEGACY_TECHNOLOGY_UNSAFE"] * 4


# --- unsafe content ------------------------------------------------------------------------------------

def test_text_that_cannot_be_represented_is_rejected():
    result = run_import(doc("## Experience", "- Ends with a brace {like this}", "- Fine."))
    assert decisions(result)[1] == (2, "REJECTED", "LEGACY_TEXT_UNSAFE")
    assert [f.text for f in parsed(result).facts] == ["Fine."]


def test_braces_inside_the_text_are_kept_safely():
    result = run_import(doc("## Experience", "- Used {curly} placeholders inside."))
    assert parsed(result).facts[0].text == "Used {curly} placeholders inside."


def test_control_characters_and_overlong_lines_are_rejected():
    result = run_import("## Experience\n- Bad \x07 bell\n- " + "w" * 2001 + "\n- Fine.\n")
    assert [d[1:] for d in decisions(result)[1:3]] == [("REJECTED", "LEGACY_CONTROL_CHARACTER"),
                                                       ("REJECTED", "LEGACY_LINE_TOO_LONG")]


def test_a_bullet_marker_without_text_is_not_a_fact():
    result = run_import(doc("## Experience", "-", "- ", "- Fine."))
    assert [d[1] for d in decisions(result)[1:3]] == ["UNCLASSIFIED", "UNCLASSIFIED"]


def test_a_document_that_is_not_utf8_is_refused():
    with pytest.raises(legacy.LegacyInputError) as caught:
        legacy.run(compiled(MAPPING), b"## Experience\n- caf\xe9\n")
    assert caught.value.code == "LEGACY_NOT_UTF8"


# --- traceability and determinism -----------------------------------------------------------------------

def test_every_fact_names_its_origin():
    text = doc("## Experience", "- First.", "", "- Second.")
    result = run_import(text)
    digest = canonical.sha256_text(text)[:12]
    sources = [f.source for f in parsed(result).facts]
    assert sources == ["legacy-import:%s:L2" % digest, "legacy-import:%s:L4" % digest]
    assert result.report["legacy_source_sha256"] == canonical.sha256_text(text)
    assert result.report["mapping_sha256"] == compiled(MAPPING).mapping_sha256


def test_the_report_lists_every_non_blank_line_and_never_its_text():
    text = doc("## Experience", "- ZZ-PRIVATE-A", "", "ZZ-PRIVATE-B", "", "- ZZ-PRIVATE-C")
    result = run_import(text)
    rendered = json.dumps(result.report)
    assert "ZZ-PRIVATE" not in rendered
    assert [e["line"] for e in result.report["lines"]] == [1, 2, 4, 6] and result.report["blank_lines"] == 3
    assert result.report["lines"][1]["unit_sha256"] == canonical.sha256_text("- ZZ-PRIVATE-A")


def test_ids_depend_on_the_text_not_on_the_position_or_spacing():
    one = run_import(doc("## Experience", "- Alpha beta.", "- Gamma."))
    two = run_import(doc("## Experience", "", "- Gamma.", "", "-   Alpha    beta.  "))
    assert {f.id for f in parsed(one).facts} == {f.id for f in parsed(two).facts}
    assert fact_id("experience", "Alpha beta.") in {f.id for f in parsed(one).facts}


def test_the_same_inputs_give_the_same_bytes():
    text = doc("## Experience", "- Alpha.", "stray", "- Beta.")
    first, second = run_import(text), run_import(text)
    assert first.facts_text == second.facts_text
    assert json.dumps(first.report, sort_keys=True) == json.dumps(second.report, sort_keys=True)
    assert "202" not in first.facts_text.split("\n")[1]  # no timestamp in the header comment


@pytest.mark.parametrize("variant", [
    lambda t: t.replace("\n", "\r\n"),
    lambda t: t.replace("\n", "\r"),
    lambda t: "﻿" + t,
    lambda t: "﻿" + t.replace("\n", "\r\n"),
])
def test_line_endings_and_bom_of_the_legacy_document_do_not_change_the_result(variant):
    text = doc("# Notes", "## Experience", "- Alpha.", "  more.", "- Beta.")
    expected = run_import(text)
    got = legacy.run(compiled(MAPPING), variant(text).encode("utf-8"))
    assert got.facts_text == expected.facts_text and got.report == expected.report


def test_unicode_forms_give_the_same_ids():
    composed = run_import(doc("## Experience", "- Café menu."))
    decomposed = run_import(doc("## Experience", "- Café menu."))
    assert parsed(composed).facts[0].id == parsed(decomposed).facts[0].id


def test_the_proposed_text_always_round_trips_through_the_real_parser():
    result = run_import(doc("## Experience", "- A: colon, comma; semicolon.", "- Quote \"x\" and 'y'.", "- Trailing <!-- c -->"))
    assert facts.check_text(result.facts_text).errors == ()
    assert [f.text for f in parsed(result).facts] == ["A: colon, comma; semicolon.", "Quote \"x\" and 'y'.",
                                                     "Trailing <!-- c -->"]


def test_the_example_import_is_complete_and_audited_line_by_line():
    mapping = legacy.check_mapping_file(EXAMPLE_DIR / "import-map.json").mapping
    result = legacy.run(mapping, (EXAMPLE_DIR / "legacy-notes.md").read_bytes())
    assert result.complete
    base = parsed(result)
    assert base.counts() == {"CONFIRMED": 2, "DERIVED": 1, "NOT_CONFIRMED": 1, "WITHDRAWN": 0}
    assert [f.confirmed_on for f in base.facts] == ["2026-01-10", None, None, None]
    assert [f.technologies for f in base.facts] == [("Python",), (), (), ()]
    non_blank = [n for n, line in enumerate((EXAMPLE_DIR / "legacy-notes.md").read_text().split("\n"), 1) if line.strip()]
    assert [e["line"] for e in result.report["lines"]] == non_blank


# --- command line ---------------------------------------------------------------------------------------

def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(str(EXAMPLE_DIR), str(root))
    return root


def import_args(root, *extra, out="proposed.md", report="report.json"):
    base = ["facts", "import", "--root", str(root), "--mapping", "import-map.json", "--in", "legacy-notes.md"]
    if out:
        base += ["--out", out]
    if report:
        base += ["--report", report]
    return base + list(extra)


def test_dry_run_prints_the_report_and_writes_nothing(workspace, capsys):
    before = tree_hash(workspace)
    code, out, err = run(capsys, *import_args(workspace, "--dry-run"))
    assert code == 0 and err == "" and tree_hash(workspace) == before
    report = json.loads(out)
    assert report["schema"] == "LegacyImportReport-v1" and report["counts"]["ACCEPTED"] == 4
    assert not (workspace / "proposed.md").exists() and not (workspace / "report.json").exists()


def test_dry_run_needs_no_output_paths_and_is_idempotent(workspace, capsys):
    argv = import_args(workspace, "--dry-run", out=None, report=None)
    first, second = run(capsys, *argv), run(capsys, *argv)
    assert first == second and first[0] == 0


def test_a_real_run_writes_a_valid_factbase_and_a_report(workspace, capsys):
    legacy_before = (workspace / "legacy-notes.md").read_bytes()
    code, out, err = run(capsys, *import_args(workspace))
    summary = json.loads(out)
    assert code == 0 and err == "" and summary["status"] == "COMPLETE" and summary["facts_written"] is True
    assert summary["problems"] == [] and summary["out"] == "proposed.md"
    proposed = workspace / "proposed.md"
    assert facts.check_file(proposed).errors == ()
    assert b"\r" not in proposed.read_bytes()
    report = json.loads((workspace / "report.json").read_text(encoding="utf-8"))
    assert report["output"]["facts_source_sha256"] == facts.check_file(proposed).facts_source_sha256
    assert (workspace / "legacy-notes.md").read_bytes() == legacy_before  # the historical document is untouched
    code, out, _ = run(capsys, "facts", "check", str(proposed))
    assert code == 0 and json.loads(out)["fact_count"] == 4


def test_the_written_files_equal_the_dry_run_report(workspace, capsys):
    _, dry, _ = run(capsys, *import_args(workspace, "--dry-run"))
    run(capsys, *import_args(workspace))
    assert json.loads(dry) == json.loads((workspace / "report.json").read_text(encoding="utf-8"))


def incomplete(workspace):
    with open(str(workspace / "legacy-notes.md"), "a", encoding="utf-8") as handle:
        handle.write("\nA loose sentence ZZ-LOOSE the mapping does not know.\n")


def test_an_incomplete_import_exits_1_writes_the_report_only(workspace, capsys):
    incomplete(workspace)
    code, out, err = run(capsys, *import_args(workspace))
    summary = json.loads(out)
    assert code == 1 and summary["status"] == "INCOMPLETE" and summary["facts_written"] is False
    rows = (workspace / "legacy-notes.md").read_text(encoding="utf-8").splitlines()
    loose = [number for number, row in enumerate(rows, 1) if "ZZ-LOOSE" in row]
    assert summary["problems"] == [{"line": loose[0], "code": "FACT_UNMAPPED", "decision": "UNCLASSIFIED"}]
    assert not (workspace / "proposed.md").exists() and (workspace / "report.json").exists()
    assert "ZZ-LOOSE" not in out + err + (workspace / "report.json").read_text(encoding="utf-8")


def test_allow_partial_writes_the_classified_facts_and_still_exits_1(workspace, capsys):
    incomplete(workspace)
    code, out, _ = run(capsys, *import_args(workspace, "--allow-partial"))
    assert code == 1 and json.loads(out)["facts_written"] is True
    written = (workspace / "proposed.md").read_text(encoding="utf-8")
    assert "ZZ-LOOSE" not in written and facts.check_text(written).errors == ()


def test_nothing_imported_writes_only_the_report(workspace, capsys):
    (workspace / "legacy-notes.md").write_text("only prose\n", encoding="utf-8")
    code, out, _ = run(capsys, *import_args(workspace, "--allow-partial"))
    assert code == 1 and json.loads(out)["status"] == "NOTHING_IMPORTED"
    assert not (workspace / "proposed.md").exists() and (workspace / "report.json").exists()


def test_the_import_never_overwrites_a_file(workspace, capsys):
    (workspace / "proposed.md").write_text("mine", encoding="utf-8")
    before = tree_hash(workspace)
    code, out, err = run(capsys, *import_args(workspace))
    assert code == 2 and out == "" and "IMPORT_OUTPUT_EXISTS" in err and tree_hash(workspace) == before
    (workspace / "proposed.md").unlink()
    (workspace / "report.json").write_text("mine", encoding="utf-8")
    before = tree_hash(workspace)
    code, _, err = run(capsys, *import_args(workspace))
    assert code == 2 and "IMPORT_OUTPUT_EXISTS" in err and tree_hash(workspace) == before


def test_the_historical_document_can_never_be_an_output(workspace, capsys):
    before = tree_hash(workspace)
    for argv in (import_args(workspace, out="legacy-notes.md"), import_args(workspace, report="legacy-notes.md"),
                 import_args(workspace, out="import-map.json"), import_args(workspace, out="a.md", report="a.md")):
        code, _, err = run(capsys, *argv)
        assert code == 2 and ("IMPORT_PATH_CONFLICT" in err or "IMPORT_OUTPUT_EXISTS" in err)
    assert tree_hash(workspace) == before


def test_outputs_and_mapping_must_stay_inside_the_workspace(workspace, tmp_path, capsys):
    outside = tmp_path / "outside.md"
    for argv, expected in (
            (import_args(workspace, out=str(outside)), "IMPORT_OUTPUT_OUTSIDE_WORKSPACE"),
            (import_args(workspace, out="../escape.md"), "IMPORT_OUTPUT_OUTSIDE_WORKSPACE"),
            (import_args(workspace, out=".git/proposed.md"), "IMPORT_OUTPUT_OUTSIDE_WORKSPACE"),
            (import_args(workspace, report="../escape.json"), "IMPORT_OUTPUT_OUTSIDE_WORKSPACE")):
        code, _, err = run(capsys, *argv)
        assert code == 2 and expected in err
    shutil.copy(str(workspace / "import-map.json"), str(tmp_path / "map.json"))
    argv = import_args(workspace, "--dry-run")
    argv[argv.index("--mapping") + 1] = str(tmp_path / "map.json")
    code, _, err = run(capsys, *argv)
    assert code == 2 and "IMPORT_MAPPING_OUTSIDE_WORKSPACE" in err
    assert not outside.exists() and not (tmp_path / "escape.md").exists()


def test_the_legacy_document_may_live_outside_the_workspace(workspace, tmp_path, capsys):
    elsewhere = tmp_path / "old-notes.md"
    shutil.copy(str(workspace / "legacy-notes.md"), str(elsewhere))
    argv = import_args(workspace, "--dry-run", out=None, report=None)
    argv[argv.index("--in") + 1] = str(elsewhere)
    code, out, _ = run(capsys, *argv)
    assert code == 0 and json.loads(out)["counts"]["ACCEPTED"] == 4


def test_both_outputs_are_required_unless_dry_run(workspace, capsys):
    for argv in (import_args(workspace, out=None), import_args(workspace, report=None), import_args(workspace, out=None, report=None)):
        code, _, err = run(capsys, *argv)
        assert code == 2 and "IMPORT_OUTPUT_REQUIRED" in err


def test_an_invalid_mapping_exits_2_without_writing(workspace, capsys):
    (workspace / "import-map.json").write_text(json.dumps(mapping_with(surprise=1)), encoding="utf-8")
    before = tree_hash(workspace)
    code, out, err = run(capsys, *import_args(workspace))
    assert code == 2 and out == "" and "LEGACY_MAP_UNKNOWN_FIELD" in err and "MAPPING_INVALID" in err
    assert tree_hash(workspace) == before


def test_missing_or_unreadable_inputs_exit_2(workspace, capsys):
    (workspace / "legacy-notes.md").unlink()
    code, _, err = run(capsys, *import_args(workspace))
    assert code == 2 and "LEGACY_FILE_UNREADABLE" in err
    (workspace / "legacy-notes.md").write_bytes(b"## Experience\n- caf\xe9\n")
    code, _, err = run(capsys, *import_args(workspace))
    assert code == 2 and "LEGACY_NOT_UTF8" in err
    (workspace / "import-map.json").unlink()
    code, _, err = run(capsys, *import_args(workspace))
    assert code == 2 and "LEGACY_MAP_FILE_UNREADABLE" in err
    assert not (workspace / "proposed.md").exists() and not (workspace / "report.json").exists()


def test_a_bad_workspace_configuration_exits_2(workspace, capsys):
    (workspace / "modularcv.json").write_text(json.dumps({"surprise": 1}), encoding="utf-8")
    code, _, err = run(capsys, *import_args(workspace, "--dry-run"))
    assert code == 2 and "CONFIG_ERROR" in err


def test_relative_paths_with_subfolders_and_absolute_paths_are_accepted(workspace, capsys):
    (workspace / "imports").mkdir()
    code, _, _ = run(capsys, *import_args(workspace, out="imports/proposed.md", report="imports/report.json"))
    assert code == 0 and (workspace / "imports" / "proposed.md").is_file()
    code, _, _ = run(capsys, *import_args(workspace, out=str(workspace / "abs.md"), report=str(workspace / "abs.json")))
    assert code == 0 and (workspace / "abs.md").is_file()


@pytest.mark.skipif(sys.platform != "win32", reason="backslash separators are a Windows form")
def test_windows_separators_and_case_are_understood(workspace, capsys):
    (workspace / "imports").mkdir()
    code, _, _ = run(capsys, *import_args(workspace, out="imports\\win.md", report="imports\\win.json"))
    assert code == 0 and (workspace / "imports" / "win.md").is_file()
    before = tree_hash(workspace)
    code, _, err = run(capsys, *import_args(workspace, out="LEGACY-NOTES.MD"))
    assert code == 2 and tree_hash(workspace) == before


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")
def test_a_symlink_cannot_smuggle_an_output_outside(workspace, tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(str(outside), str(workspace / "link"))
    code, _, err = run(capsys, *import_args(workspace, out="link/p.md", report="link/r.json"))
    assert code == 2 and "OUTSIDE_WORKSPACE" in err and not list(outside.iterdir())


def test_a_crlf_legacy_file_gives_the_same_output(workspace, capsys):
    run(capsys, *import_args(workspace))
    expected = (workspace / "proposed.md").read_bytes()
    text = (workspace / "legacy-notes.md").read_bytes().replace(b"\n", b"\r\n")
    (workspace / "legacy-notes.md").write_bytes(text)
    run(capsys, *import_args(workspace, out="again.md", report="again.json"))
    assert (workspace / "again.md").read_bytes() == expected


def test_repeating_the_import_elsewhere_gives_identical_files(workspace, capsys):
    run(capsys, *import_args(workspace))
    run(capsys, *import_args(workspace, out="second.md", report="second.json"))
    assert (workspace / "proposed.md").read_bytes() == (workspace / "second.md").read_bytes()
    assert (workspace / "report.json").read_bytes() == (workspace / "second.json").read_bytes()


def test_the_output_is_a_proposal_that_publishes_only_what_the_mapping_confirmed(workspace, capsys):
    run(capsys, *import_args(workspace))
    base = facts.parse_file(workspace / "proposed.md")
    assert [f.status for f in base.publishable()] == ["CONFIRMED", "CONFIRMED"]
    assert all(f.status != "CONFIRMED" for f in base.facts if f.line > 0 and "to-check" in f.section)


def test_no_private_text_reaches_the_console(workspace, capsys):
    (workspace / "legacy-notes.md").write_text(
        "# T\n## Experience (checked)\n- ZZ-SECRET-FACT\n\nZZ-SECRET-PROSE\n", encoding="utf-8")
    for extra in (("--dry-run",), ()):
        code, out, err = run(capsys, *import_args(workspace, *extra, out=None if extra else "o.md",
                                                  report=None if extra else "r.json"))
        assert "ZZ-SECRET" not in out + err


# --- robustness ----------------------------------------------------------------------------------------

def test_no_mutation_of_the_example_mapping_can_crash_the_checker():
    example = json.loads((EXAMPLE_DIR / "import-map.json").read_text(encoding="utf-8"))
    swaps = [None, 0, -1, True, "", "x", "(", [], {}, [None], {"a": 1}, "(a)", ["(a)"]]
    count = 0

    def walk(node, prefix=()):
        yield prefix
        if isinstance(node, dict):
            for key in node:
                yield from walk(node[key], prefix + (key,))
        elif isinstance(node, list):
            for position, item in enumerate(node):
                yield from walk(item, prefix + (position,))

    for path in walk(example):
        for value in swaps:
            document = copy.deepcopy(example)
            if path:
                node = document
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = value
            else:
                document = value
            result = legacy.check_mapping_data(document)
            assert (result.mapping is None) == bool(result.errors)
            count += 1
    assert count > 150


def test_random_documents_never_crash_and_always_yield_a_valid_proposal():
    import random
    pool = ["# Notes", "## Experience", "### Detail", "## Tools", "- Python", "- A bullet with Python.", "  continued",
            "* star", "1. one", "---", "plain prose", "| a | b |", "", "- dup", "- dup", "- ends }", "- Trailing {x}",
            "- date (confirmed 2026-02-30)", "- ok (confirmed 2026-01-10)", "- [not confirmed] thing", "\t- tab bullet",
            "-", "- ", "## Experience (checked)", "## Experience (to check)", "##", "#", "- café", "- Café"]
    mapping = legacy.check_mapping_file(EXAMPLE_DIR / "import-map.json").mapping
    rng = random.Random(20260101)
    for _ in range(300):
        text = "\n".join(rng.choice(pool) for _ in range(rng.randint(0, 25))) + rng.choice(["", "\n", "\r\n"])
        result = legacy.run(mapping, text.encode("utf-8"))
        report = result.report
        assert sum(report["counts"].values()) == sum(1 for e in report["lines"] if e["kind"] != "HEADING")
        if result.facts_text is not None:
            check = facts.check_text(result.facts_text)
            assert check.errors == ()
            accepted = [e["fact_id"] for e in report["lines"] if e["decision"] == "ACCEPTED"]
            assert [f.id for f in check.factbase.facts] == accepted
            assert all(f.status != "CONFIRMED" or f.section == "experience" for f in check.factbase.facts)
        else:
            assert report["counts"]["ACCEPTED"] == 0
        again = legacy.run(mapping, text.encode("utf-8"))
        assert again.facts_text == result.facts_text and again.report == report


# --- M4-R1: the CONFIRMED policy, proven rather than assumed --------------------------------------------

ALL_STATUSES = ("CONFIRMED", "DERIVED", "NOT_CONFIRMED", "WITHDRAWN")
SAFE_STATUSES = ("DERIVED", "NOT_CONFIRMED", "WITHDRAWN")
RANKS = {"CONFIRMED": 3, "DERIVED": 2, "NOT_CONFIRMED": 1, "WITHDRAWN": 1}


@pytest.mark.parametrize("flag", [None, False, "true", "yes", 1, 0, [], {}])
def test_a_confirmed_rule_is_invalid_unless_allow_confirmed_is_exactly_true(flag):
    document = mapping_with(headings=[{"pattern": "Experience", "section": "e", "status": "CONFIRMED"}])
    if flag is not None:
        document["allow_confirmed"] = flag
    result = legacy.check_mapping_data(document)
    assert result.mapping is None
    assert "LEGACY_MAP_CONFIRMED_NOT_ALLOWED" in [e.code for e in result.errors]


def test_allow_confirmed_alone_confirms_nothing():
    document = mapping_with(allow_confirmed=True)  # the heading rule still says DERIVED
    result = run_import(doc("## Experience", "- Plainly stated.", "- CONFIRMED verified true"), document)
    assert result.report["facts_by_status"]["CONFIRMED"] == 0
    assert all(f.status == "DERIVED" for f in parsed(result).facts)


def test_text_that_says_it_is_confirmed_is_never_trusted():
    words = ["CONFIRMED", "confirmed", "verified", "Status: CONFIRMED", "[x] confirmed", "(confirmed 2026-01-01)"]
    result = run_import(doc("## Experience", *["- Did a thing, %s." % word for word in words]))
    assert result.report["facts_by_status"]["CONFIRMED"] == 0 and parsed(result).publishable() == ()


@pytest.mark.parametrize("heading", ALL_STATUSES)
@pytest.mark.parametrize("rule", SAFE_STATUSES)
def test_a_line_rule_never_raises_the_status_its_heading_gave(heading, rule):
    mapping = mapping_with(
        allow_confirmed=True,
        headings=[{"pattern": "H", "section": "h", "status": heading}],
        status_rules=[{"pattern": "marker", "status": rule}])
    result = run_import(doc("## H", "- Plain line.", "- Line with marker."), mapping)
    entries = {e["line"]: e for e in result.report["lines"]}
    assert entries[2]["status"] == heading  # an unmarked line keeps the heading status
    if RANKS[rule] <= RANKS[heading]:
        assert entries[3]["decision"] == "ACCEPTED" and entries[3]["status"] == rule
    else:
        assert entries[3]["decision"] == "REJECTED" and entries[3]["code"] == "LEGACY_PROMOTION_REFUSED"
        assert "marker" not in result.facts_text
    for fact in parsed(result).facts:
        assert RANKS[fact.status] <= RANKS[heading]


def test_a_line_rule_naming_confirmed_is_refused_even_with_allow_confirmed():
    document = mapping_with(allow_confirmed=True, status_rules=[{"pattern": "x", "status": "CONFIRMED"}])
    assert "LEGACY_MAP_CONFIRMED_NOT_ALLOWED" in mapping_codes(document)


def test_two_heading_rules_that_disagree_on_confirmation_confirm_nothing():
    mapping = mapping_with(allow_confirmed=True, headings=[
        {"pattern": "Experience", "section": "e", "status": "CONFIRMED"},
        {"pattern": "Exp.*", "section": "e", "status": "DERIVED"}])
    result = run_import(doc("## Experience", "- A claim.", "- Another."), mapping)
    assert result.facts_text is None and result.report["counts"]["AMBIGUOUS"] == 2
    assert result.report["facts_by_status"]["CONFIRMED"] == 0 and not result.complete


def test_the_same_text_under_a_confirmed_and_a_derived_heading_is_confirmed_nowhere():
    mapping = mapping_with(allow_confirmed=True, headings=[
        {"pattern": "Checked", "section": "checked", "status": "CONFIRMED"},
        {"pattern": "Unchecked", "section": "unchecked", "status": "DERIVED"}])
    result = run_import(doc("## Checked", "- Shared claim.", "## Unchecked", "- Shared claim.", "- Own claim."), mapping)
    assert [(f.text, f.status) for f in parsed(result).facts] == [("Own claim.", "DERIVED")]
    assert result.report["counts"]["AMBIGUOUS"] == 2


def test_conflicting_status_rules_cannot_be_used_to_settle_a_status():
    mapping = mapping_with(allow_confirmed=True,
                           headings=[{"pattern": "H", "section": "h", "status": "CONFIRMED"}],
                           status_rules=[{"pattern": "a", "status": "DERIVED"}, {"pattern": "b", "status": "NOT_CONFIRMED"}])
    result = run_import(doc("## H", "- a and b."), mapping)
    assert result.facts_text is None and result.report["counts"]["AMBIGUOUS"] == 1


def test_an_inherited_context_never_raises_a_status():
    mapping = mapping_with(allow_confirmed=True, headings=[
        {"pattern": "Parent", "section": "p", "status": "DERIVED"},
        {"pattern": "Child", "action": "inherit"}])
    result = run_import(doc("## Parent", "- One.", "### Child", "- Two."), mapping)
    assert {f.status for f in parsed(result).facts} == {"DERIVED"}


def test_a_date_pattern_cannot_confirm_a_fact():
    mapping = mapping_with(date_patterns=[r"\((\d{4}-\d{2}-\d{2})\)"])
    result = run_import(doc("## Experience", "- Did it (2026-01-10)."), mapping)
    fact = parsed(result).facts[0]
    assert fact.status == "DERIVED" and fact.confirmed_on is None


def test_every_confirmed_fact_is_traceable_to_the_rule_that_authorised_it():
    mapping_document = legacy.check_mapping_file(EXAMPLE_DIR / "import-map.json").mapping.to_model()
    result = legacy.run(compiled(mapping_document), (EXAMPLE_DIR / "legacy-notes.md").read_bytes())
    confirmed = [e for e in result.report["lines"] if e["decision"] == "ACCEPTED" and e["status"] == "CONFIRMED"]
    assert len(confirmed) == 2
    for entry in confirmed:
        authorising = mapping_document["headings"][entry["rule"]]
        assert authorising["status"] == "CONFIRMED" and mapping_document["allow_confirmed"] is True


def test_random_documents_and_mappings_never_confirm_without_authorisation():
    import random
    rng = random.Random(4242)
    words = ["confirmed", "verified", "CONFIRMED", "marker", "alpha", "beta", "(on 2026-01-02)", "[ok]"]
    for _ in range(200):
        headings = [{"pattern": "H%d" % n, "section": "s%d" % n, "status": rng.choice(SAFE_STATUSES)} for n in range(3)]
        if rng.random() < 0.3:
            headings.append({"pattern": "H.", "section": "any", "status": rng.choice(SAFE_STATUSES)})
        rules = [{"pattern": rng.choice(words[:5]), "status": rng.choice(SAFE_STATUSES)} for _ in range(rng.randint(0, 3))]
        document = mapping_with(allow_confirmed=rng.random() < 0.5, headings=headings, status_rules=rules,
                                date_patterns=[r"\(on (\d{4}-\d{2}-\d{2})\)"] if rng.random() < 0.5 else [])
        mapping = compiled(document)
        lines = []
        for _ in range(rng.randint(1, 20)):
            lines.append(rng.choice(["## H%d" % rng.randint(0, 3), "### Sub", "- " + " ".join(rng.sample(words, 3)), "prose"]))
        result = legacy.run(mapping, ("\n".join(lines) + "\n").encode("utf-8"))
        assert result.report["facts_by_status"]["CONFIRMED"] == 0
        assert result.facts_text is None or all(f.status != "CONFIRMED" for f in parsed(result).facts)


def test_the_documentation_separates_authorisation_from_verification():
    guide = (REPO / "docs" / "IMPORT.md").read_text(encoding="utf-8")
    contract = (REPO / "docs" / "design" / "CONTRACTS.md").read_text(encoding="utf-8")
    assert "## Authorisation is not verification" in guide
    assert "allow_confirmed" in guide and "fact by fact" in guide
    assert "Mapping authorisation is not human verification" in contract


def test_the_cli_refuses_a_confirmed_rule_the_mapping_did_not_authorise(workspace, capsys):
    document = json.loads((workspace / "import-map.json").read_text(encoding="utf-8"))
    document["allow_confirmed"] = False
    (workspace / "import-map.json").write_text(json.dumps(document), encoding="utf-8")
    before = tree_hash(workspace)
    code, out, err = run(capsys, *import_args(workspace))
    assert code == 2 and "LEGACY_MAP_CONFIRMED_NOT_ALLOWED" in err and tree_hash(workspace) == before


# --- M4 closure: a proposal can never be written over the active fact base ---------------------------------

FACT_BASE_REFUSAL = "IMPORT_OUTPUT_IS_FACT_BASE"


def refused_fact_base(capsys, workspace, argv):
    before = tree_hash(workspace)
    code, out, err = run(capsys, *argv)
    assert code == 2 and out == "" and FACT_BASE_REFUSAL in err
    assert tree_hash(workspace) == before
    return err


def make_link(link, target, directory):
    try:
        os.symlink(str(target), str(link), target_is_directory=directory)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlinks cannot be created here")


@pytest.mark.parametrize("name", ["facts.md", "./facts.md", "sub/../facts.md"])
def test_out_naming_the_fact_base_is_refused_even_by_an_equivalent_path(workspace, capsys, name):
    (workspace / "sub").mkdir()
    refused_fact_base(capsys, workspace, import_args(workspace, out=name))


def test_out_naming_the_fact_base_by_an_absolute_path_is_refused(workspace, capsys):
    refused_fact_base(capsys, workspace, import_args(workspace, out=str(workspace / "facts.md")))


def test_the_refusal_applies_when_the_fact_base_does_not_exist_yet(workspace, capsys):
    (workspace / "facts.md").unlink()
    refused_fact_base(capsys, workspace, import_args(workspace, out="facts.md"))
    assert not (workspace / "facts.md").exists()


def test_the_report_cannot_be_written_over_the_fact_base_either(workspace, capsys):
    refused_fact_base(capsys, workspace, import_args(workspace, report="facts.md"))
    (workspace / "facts.md").unlink()
    refused_fact_base(capsys, workspace, import_args(workspace, report="facts.md"))


def test_the_refusal_follows_a_configured_fact_base_name_and_folder(workspace, capsys):
    (workspace / "data").mkdir()
    (workspace / "modularcv.json").write_text(json.dumps({"facts": "data/base.md"}), encoding="utf-8")
    refused_fact_base(capsys, workspace, import_args(workspace, out="data/base.md"))
    refused_fact_base(capsys, workspace, import_args(workspace, out="data/../data/base.md"))
    code, _, _ = run(capsys, *import_args(workspace, out="facts.md", report="r.json"))  # the old default name is now free
    assert code == 2  # it exists (the example fact base), so the overwrite rule answers instead
    assert FACT_BASE_REFUSAL not in capsys.readouterr().err


@pytest.mark.skipif(sys.platform != "win32", reason="a case-insensitive file system is needed")
def test_a_different_letter_case_does_not_get_around_the_refusal(workspace, capsys):
    refused_fact_base(capsys, workspace, import_args(workspace, out="FACTS.MD"))
    (workspace / "facts.md").unlink()
    refused_fact_base(capsys, workspace, import_args(workspace, out="Facts.Md"))


def test_a_symlink_to_the_fact_base_cannot_be_used_as_the_output(workspace, capsys):
    make_link(workspace / "alias.md", workspace / "facts.md", False)
    refused_fact_base(capsys, workspace, import_args(workspace, out="alias.md"))


def test_a_dangling_symlink_to_a_missing_fact_base_cannot_be_used_as_the_output(workspace, capsys):
    (workspace / "facts.md").unlink()
    make_link(workspace / "alias.md", workspace / "facts.md", False)
    refused_fact_base(capsys, workspace, import_args(workspace, out="alias.md"))
    assert not (workspace / "facts.md").exists()


def test_a_symlinked_folder_leading_to_the_fact_base_is_refused(workspace, capsys):
    make_link(workspace / "here", workspace, True)
    refused_fact_base(capsys, workspace, import_args(workspace, out="here/facts.md"))


def test_a_fact_base_that_is_itself_a_symlink_is_protected_by_its_target(workspace, capsys):
    (workspace / "real").mkdir()
    shutil.move(str(workspace / "facts.md"), str(workspace / "real" / "facts.md"))
    make_link(workspace / "facts.md", workspace / "real" / "facts.md", False)
    refused_fact_base(capsys, workspace, import_args(workspace, out="facts.md"))
    refused_fact_base(capsys, workspace, import_args(workspace, out="real/facts.md"))


def test_the_refusal_also_applies_to_a_dry_run_and_writes_nothing(workspace, capsys):
    refused_fact_base(capsys, workspace, import_args(workspace, "--dry-run", out="facts.md", report=None))


def test_the_refusal_message_is_stable_and_does_not_reveal_paths(workspace, capsys):
    err = refused_fact_base(capsys, workspace, import_args(workspace, out=str(workspace / "facts.md")))
    assert json.loads(err.strip().splitlines()[-1])["status"] == FACT_BASE_REFUSAL
    assert str(workspace) not in err and workspace.name not in err and "facts.md" not in err
    other = refused_fact_base(capsys, workspace, import_args(workspace, out="./sub/../facts.md"))
    assert other == err  # the same fixed text whatever the spelling


def test_a_separate_proposal_file_is_still_written_and_the_fact_base_is_untouched(workspace, capsys):
    fact_base = (workspace / "facts.md").read_bytes()
    code, _, err = run(capsys, *import_args(workspace, out="proposals/new-facts.md"))
    assert code == 2 and "IMPORT_WRITE_FAILED" in err  # the folder must exist: the import creates no directories
    (workspace / "proposals").mkdir()
    code, _, _ = run(capsys, *import_args(workspace, out="proposals/new-facts.md", report="proposals/report.json"))
    assert code == 0 and (workspace / "proposals" / "new-facts.md").is_file()
    assert (workspace / "facts.md").read_bytes() == fact_base
    assert facts.check_file(workspace / "proposals" / "new-facts.md").errors == ()


def test_overwriting_another_existing_file_is_still_refused(workspace, capsys):
    (workspace / "proposed.md").write_text("mine", encoding="utf-8")
    before = tree_hash(workspace)
    code, _, err = run(capsys, *import_args(workspace))
    assert code == 2 and "IMPORT_OUTPUT_EXISTS" in err and FACT_BASE_REFUSAL not in err
    assert tree_hash(workspace) == before


def test_a_dry_run_towards_a_separate_file_still_writes_nothing(workspace, capsys):
    before = tree_hash(workspace)
    code, out, _ = run(capsys, *import_args(workspace, "--dry-run", out="proposed.md", report=None))
    assert code == 0 and json.loads(out)["counts"] and tree_hash(workspace) == before


def test_a_dangling_symlink_elsewhere_is_not_written_through(workspace, capsys):
    make_link(workspace / "alias.md", workspace / "nowhere.md", False)
    before = tree_hash(workspace)
    code, _, err = run(capsys, *import_args(workspace, out="alias.md"))
    assert code == 2 and "IMPORT_OUTPUT_EXISTS" in err and not (workspace / "nowhere.md").exists()
    assert tree_hash(workspace) == before
