import ast
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from modularcv import canonical, facts

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "examples" / "facts.v1.example.md"
PINNED_EXAMPLE_FINGERPRINT = "ec0ea60ff47ff2227627b308eafc0fd6f389910373692880d17afb35a9a29474"

LF, CRLF = chr(10), chr(13) + chr(10)
MARKER = "<!-- modularcv: FactBase-v1 -->"


def doc(*body, marker=MARKER):
    return "\n".join([marker, "", "## Section {#sec}", ""] + list(body)) + "\n"


def codes(result):
    return [error.code for error in result.errors]


def check(text, **kwargs):
    return facts.check_text(text, **kwargs)


EXPECTED_MODEL = {
    "schema": "FactBase-v1",
    "facts": [
        {"id": "exp.junior-dev.api", "status": "CONFIRMED", "section": "experience", "lang": "en",
         "text": "Built REST endpoints in Python for an internal tool. Wrote automated tests with pytest.",
         "confirmed_on": "2026-01-10", "technologies": ["Python", "pytest"], "capabilities": ["backend", "testing"],
         "source": None, "supersedes": None, "note": None},
        {"id": "exp.junior-dev.review", "status": "CONFIRMED", "section": "experience", "lang": None,
         "text": "Took part in code reviews and sprint ceremonies.", "confirmed_on": None, "technologies": [],
         "capabilities": ["collaboration"], "source": None, "supersedes": None, "note": None},
        {"id": "exp.junior-dev.speed", "status": "NOT_CONFIRMED", "section": "experience", "lang": None,
         "text": "Improved the response time of the endpoints.", "confirmed_on": None, "technologies": [],
         "capabilities": [], "source": None, "supersedes": None, "note": "no measurement exists, do not claim"},
        {"id": "exp.junior-dev.lead", "status": "WITHDRAWN", "section": "experience", "lang": None,
         "text": "Led a team of three developers.", "confirmed_on": None, "technologies": [], "capabilities": [],
         "source": None, "supersedes": None, "note": "retracted, the role was a contribution only"},
        {"id": "exp.junior-dev.lead-v2", "status": "DERIVED", "section": "experience", "lang": None,
         "text": "Coordinated work with two other developers on a shared feature.", "confirmed_on": None,
         "technologies": [], "capabilities": [], "source": None, "supersedes": "exp.junior-dev.lead",
         "note": "wording derived from confirmed facts, needs a human decision"},
        {"id": "edu.beng", "status": "CONFIRMED", "section": "education", "lang": None,
         "text": "B.Eng. in software engineering at Example University, 2024 to expected 2028.",
         "confirmed_on": "2026-01", "technologies": [], "capabilities": [], "source": None, "supersedes": None,
         "note": None},
        {"id": "skill.python", "status": "CONFIRMED", "section": "skills", "lang": None,
         "text": "Python for scripting and automated tests.", "confirmed_on": None, "technologies": ["Python"],
         "capabilities": ["backend"], "source": None, "supersedes": None, "note": None},
        {"id": "skill.git", "status": "CONFIRMED", "section": "skills", "lang": None,
         "text": "Daily use of Git for branches and pull requests.", "confirmed_on": None, "technologies": ["Git"],
         "capabilities": [], "source": "team handbook, fictional", "supersedes": None, "note": None},
    ],
}


# --- example file (criterion 4) -------------------------------------------------------------------

def test_example_parses_to_the_expected_canonical_model():
    result = facts.check_file(EXAMPLE)
    assert result.errors == () and result.warnings == ()
    model = result.factbase.to_model()
    assert canonical.canonical_json(model) == canonical.canonical_json(EXPECTED_MODEL)
    assert result.factbase.factbase_sha256 == canonical.fingerprint(EXPECTED_MODEL)


def test_two_parses_give_the_same_fingerprints_and_the_value_is_pinned():
    first = facts.parse_file(EXAMPLE)
    second = facts.parse_file(EXAMPLE)
    assert first.factbase_sha256 == second.factbase_sha256 == PINNED_EXAMPLE_FINGERPRINT
    assert first.facts_source_sha256 == second.facts_source_sha256
    assert re.fullmatch(r"[0-9a-f]{64}", first.facts_source_sha256)


def test_canonical_model_has_no_line_numbers():
    model = facts.parse_file(EXAMPLE).to_model()
    assert all("line" not in fact for fact in model["facts"])


# --- fingerprints (criteria 5, 6) -------------------------------------------------------------------

BASE = doc("- [a.one] CONFIRMED: First fact.", "- [a.two] CONFIRMED: Second fact.")


def test_blank_lines_and_spacing_change_the_source_hash_not_the_factbase_hash():
    spaced = doc("", "- [a.one]   CONFIRMED:   First   fact.  ", "", "", "- [a.two] CONFIRMED: Second fact.")
    base, other = facts.parse_text(BASE), facts.parse_text(spaced)
    assert base.facts_source_sha256 != other.facts_source_sha256
    assert base.factbase_sha256 == other.factbase_sha256


def test_comments_and_titles_do_not_change_the_factbase_hash():
    commented = doc("<!-- a note -->", "# A title", "- [a.one] CONFIRMED: First fact.", "- [a.two] CONFIRMED: Second fact.")
    assert facts.parse_text(commented).factbase_sha256 == facts.parse_text(BASE).factbase_sha256


def test_reordering_or_editing_a_fact_changes_the_factbase_hash():
    base = facts.parse_text(BASE).factbase_sha256
    reordered = doc("- [a.two] CONFIRMED: Second fact.", "- [a.one] CONFIRMED: First fact.")
    text_changed = doc("- [a.one] CONFIRMED: First fact!", "- [a.two] CONFIRMED: Second fact.")
    status_changed = doc("- [a.one] DERIVED: First fact.", "- [a.two] CONFIRMED: Second fact.")
    attribute_changed = doc("- [a.one] CONFIRMED: First fact. {lang: en}", "- [a.two] CONFIRMED: Second fact.")
    for variant in (reordered, text_changed, status_changed, attribute_changed):
        assert facts.parse_text(variant).factbase_sha256 != base


def test_moving_a_fact_to_another_line_keeps_the_factbase_hash():
    moved = doc("<!-- padding -->", "<!-- padding -->", "- [a.one] CONFIRMED: First fact.", "- [a.two] CONFIRMED: Second fact.")
    assert facts.parse_text(moved).factbase_sha256 == facts.parse_text(BASE).factbase_sha256


def test_continuation_lines_are_joined_with_single_spaces():
    text = doc("- [a.one] CONFIRMED: First", "    fact,   on two", "    lines. {capabilities: x}")
    fact = facts.parse_text(text).facts[0]
    assert fact.text == "First fact, on two lines."
    assert fact.capabilities == ("x",)


# --- line endings, BOM, NFC (criteria 1 to 3 at the facts level) --------------------------------------

def test_crlf_lf_and_cr_copies_have_identical_fingerprints():
    lf = BASE.encode("utf-8")
    crlf = BASE.replace("\n", "\r\n").encode("utf-8")
    cr = BASE.replace("\n", "\r").encode("utf-8")
    results = [facts.check_bytes(data) for data in (lf, crlf, cr)]
    assert all(not r.errors for r in results)
    assert len({r.facts_source_sha256 for r in results}) == 1
    assert len({r.factbase.factbase_sha256 for r in results}) == 1


def test_bom_is_tolerated_and_does_not_change_fingerprints():
    plain = facts.check_bytes(BASE.encode("utf-8"))
    bom = facts.check_bytes(b"\xef\xbb\xbf" + BASE.encode("utf-8"))
    assert not bom.errors
    assert plain.facts_source_sha256 == bom.facts_source_sha256
    assert plain.factbase.factbase_sha256 == bom.factbase.factbase_sha256


def test_nfc_and_nfd_texts_have_the_same_factbase_hash_but_different_source_hash():
    composed = doc("- [a.one] CONFIRMED: café skills.")
    decomposed = doc("- [a.one] CONFIRMED: café skills.")
    a, b = facts.check_text(composed), facts.check_text(decomposed)
    assert a.factbase.factbase_sha256 == b.factbase.factbase_sha256
    assert a.facts_source_sha256 != b.facts_source_sha256
    assert a.factbase.facts[0].text == b.factbase.facts[0].text == "café skills."


def test_invalid_utf8_is_a_stable_error_not_a_crash():
    result = facts.check_bytes(b"\xff\xfe" + BASE.encode("utf-8"))
    assert codes(result) == ["FACT_NOT_UTF8"] and result.factbase is None
    assert result.facts_source_sha256


def test_unreadable_file_is_reported(tmp_path):
    result = facts.check_file(tmp_path / "missing.md")
    assert codes(result) == ["FACT_FILE_UNREADABLE"]


# --- optional date (criteria 6, 7) ------------------------------------------------------------------

def test_a_fact_without_confirmed_on_is_valid_and_carries_null():
    fact = facts.parse_text(doc("- [a.one] CONFIRMED: No date here.")).facts[0]
    assert fact.confirmed_on is None
    assert facts.parse_text(doc("- [a.one] CONFIRMED: No date here.")).to_model()["facts"][0]["confirmed_on"] is None


@pytest.mark.parametrize("value", ["2026", "2026-02", "2026-02-28", "2024-02-29"])
def test_allowed_date_formats(value):
    fact = facts.parse_text(doc("- [a.one] CONFIRMED: Dated. {confirmed_on: %s}" % value)).facts[0]
    assert fact.confirmed_on == value


@pytest.mark.parametrize("value", ["2026-02-30", "2026-13", "2026-00-10", "2025-02-29", "26-01-01", "2026-1-1",
                                    "2026/01/01", "2026-01-01T10:00:00Z", "0000", "next week", "٢٠٢٦"])
def test_invalid_dates_are_rejected_with_the_line_number(value):
    text = doc("- [a.one] CONFIRMED: Fine.", "- [a.two] CONFIRMED: Dated. {confirmed_on: %s}" % value)
    result = check(text)
    assert codes(result) == ["FACT_INVALID_DATE"]
    assert result.errors[0].line == 6 and result.factbase is None


def test_require_confirmation_date_is_opt_in():
    text = doc("- [a.one] CONFIRMED: No date.", "- [a.two] DERIVED: Also none.")
    assert not check(text).errors
    strict = check(text, require_confirmation_date=True)
    assert codes(strict) == ["FACT_DATE_REQUIRED"] and strict.errors[0].line == 5


# --- structural errors (criteria 8 to 11) -------------------------------------------------------------

def test_duplicate_id():
    result = check(doc("- [a.one] CONFIRMED: First.", "- [a.one] DERIVED: Again."))
    assert codes(result) == ["FACT_DUPLICATE_ID"] and result.errors[0].line == 6


def test_unknown_status_including_wrong_case():
    for status in ("MAYBE", "confirmed", "Confirmed", "CONFIRMED_"):
        result = check(doc("- [a.one] %s: Text." % status))
        assert codes(result) == ["FACT_UNKNOWN_STATUS"], status


def test_empty_text():
    for line in ("- [a.one] CONFIRMED:", "- [a.one] CONFIRMED:    ", "- [a.one] CONFIRMED: {lang: en}"):
        assert codes(check(doc(line))) == ["FACT_EMPTY_TEXT"], line


@pytest.mark.parametrize("fact_id", ["", "A.one", "a_one", "a..one", ".a", "a.", "-a", "a b", "x" * 81])
def test_invalid_ids(fact_id):
    assert codes(check(doc("- [%s] CONFIRMED: Text." % fact_id))) == ["FACT_INVALID_ID"]


def test_id_of_80_characters_is_accepted():
    assert not check(doc("- [%s] CONFIRMED: Text." % ("x" * 80))).errors


@pytest.mark.parametrize("line", [
    "Some free prose that could be mistaken for a fact.",
    "- a bullet without an id",
    "- [a.one] CONFIRMED Text without a colon",
    "* [a.one] CONFIRMED: Wrong bullet character.",
    "    an indented line with nothing to continue",
    "### Too deep a heading",
    "[a.one] CONFIRMED: Missing dash.",
    "- [a.one]CONFIRMED: Missing space.",
])
def test_unparsed_lines_are_errors_with_line_numbers(line):
    result = check(doc(line))
    assert codes(result) == ["FACT_UNPARSED_LINE"] and result.errors[0].line == 5
    assert result.factbase is None


def test_an_unrecognised_line_never_hides_inside_a_valid_file():
    text = doc("- [a.one] CONFIRMED: Fine.", "stray prose", "- [a.two] CONFIRMED: Fine.")
    result = check(text)
    assert codes(result) == ["FACT_UNPARSED_LINE"] and result.errors[0].line == 6


def test_a_blank_line_ends_a_fact_so_a_later_indented_line_is_unparsed():
    result = check(doc("- [a.one] CONFIRMED: Fine.", "", "    orphan continuation"))
    assert codes(result) == ["FACT_UNPARSED_LINE"]


def test_text_after_a_comment_end_is_unparsed():
    assert codes(check(doc("<!-- c --> trailing"))) == ["FACT_UNPARSED_LINE"]
    assert codes(check(doc("<!-- open", "still", "--> trailing"))) == ["FACT_UNPARSED_LINE"]


def test_multiline_comment_may_hold_prose_and_fact_like_lines():
    text = doc("<!--", "free prose", "- [b.two] CONFIRMED: inside a comment, not a fact", "-->", "- [a.one] CONFIRMED: Real.")
    parsed = facts.parse_text(text)
    assert [f.id for f in parsed.facts] == ["a.one"]


def test_unterminated_comment():
    assert codes(check(doc("<!-- never closed", "- [a.one] CONFIRMED: Hidden."))) == ["FACT_UNTERMINATED_COMMENT"]


def test_control_characters_are_refused():
    assert codes(check(doc("- [a.one] CONFIRMED: Bad \x07 char."))) == ["FACT_CONTROL_CHARACTER"]
    assert codes(check(doc("- [a.one] CONFIRMED: Line separator."))) == ["FACT_CONTROL_CHARACTER"]


def test_marker_missing_and_unknown_schema():
    no_marker = check("## Section\n- [a.one] CONFIRMED: Text.\n")
    assert codes(no_marker) == ["FACT_MARKER_MISSING"] and no_marker.errors[0].line == 1
    other = check(doc("- [a.one] CONFIRMED: Text.", marker="<!-- modularcv: FactBase-v2 -->"))
    assert codes(other) == ["FACT_UNKNOWN_SCHEMA"]
    assert codes(check("# Title\n" + MARKER + "\n")) == ["FACT_MARKER_MISSING"]


def test_marker_may_follow_blank_lines():
    assert not check("\n\n" + doc("- [a.one] CONFIRMED: Text.")).errors


def test_empty_files_are_refused():
    for blank in ("", "\n\n  \n", "﻿", "﻿\r\n"):
        assert codes(check(blank)) == ["FACT_EMPTY_FILE"], repr(blank)
    assert codes(facts.check_bytes(b"")) == ["FACT_EMPTY_FILE"]


def test_marker_only_file_is_valid_with_a_warning():
    result = check(MARKER + "\n")
    assert not result.errors and [w.code for w in result.warnings] == ["FACT_NO_FACTS"]
    assert result.factbase.facts == () and result.factbase.publishable() == ()


def test_fact_outside_any_section():
    result = check(MARKER + "\n- [a.one] CONFIRMED: Text.\n")
    assert codes(result) == ["FACT_OUTSIDE_SECTION"] and result.errors[0].line == 2


def test_section_ids_explicit_slug_and_duplicates():
    text = "\n".join([MARKER, "## Work experience", "- [a.one] CONFIRMED: A.", "## Éducation & stuff {#edu}",
                      "- [a.two] CONFIRMED: B."]) + "\n"
    parsed = facts.parse_text(text)
    assert [f.section for f in parsed.facts] == ["work-experience", "edu"]
    assert codes(check("\n".join([MARKER, "## One {#x}", "## Two {#x}"]) + "\n")) == ["FACT_DUPLICATE_SECTION"]
    assert codes(check("\n".join([MARKER, "## !!!", "- [a.one] CONFIRMED: A."]) + "\n"))[0] == "FACT_BAD_SECTION_ID"


def test_all_errors_are_reported_in_line_order():
    text = doc("- [a.one] MAYBE: x", "stray", "- [a.two] CONFIRMED: ok {confirmed_on: 2026-02-30}")
    result = check(text)
    assert codes(result) == ["FACT_UNKNOWN_STATUS", "FACT_UNPARSED_LINE", "FACT_INVALID_DATE"]
    assert [e.line for e in result.errors] == [5, 6, 7]


# --- supersedes (criterion 11) -------------------------------------------------------------------

def test_supersedes_must_name_an_existing_withdrawn_fact():
    ok = doc("- [old.one] WITHDRAWN: Old claim.", "- [new.one] CONFIRMED: New claim. {supersedes: old.one}")
    assert facts.parse_text(ok).get("new.one").supersedes == "old.one"
    forward = doc("- [new.one] CONFIRMED: New claim. {supersedes: old.one}", "- [old.one] WITHDRAWN: Old claim.")
    assert not check(forward).errors
    for text in (
        doc("- [new.one] CONFIRMED: New. {supersedes: missing.one}"),
        doc("- [old.one] CONFIRMED: Old.", "- [new.one] CONFIRMED: New. {supersedes: old.one}"),
        doc("- [old.one] DERIVED: Old.", "- [new.one] CONFIRMED: New. {supersedes: old.one}"),
        doc("- [new.one] WITHDRAWN: New. {supersedes: new.one}"),
    ):
        assert codes(check(text)) == ["FACT_BAD_SUPERSEDES"], text


# --- attributes ------------------------------------------------------------------------------------

@pytest.mark.parametrize("line,code", [
    ("- [a.one] CONFIRMED: Text. {colour: red}", "FACT_UNKNOWN_ATTRIBUTE"),
    ("- [a.one] CONFIRMED: Text. {lang: en; lang: fr}", "FACT_DUPLICATE_ATTRIBUTE"),
    ("- [a.one] CONFIRMED: Text. {lang: english}", "FACT_INVALID_LANG"),
    ("- [a.one] CONFIRMED: Text. {lang: EN}", "FACT_INVALID_LANG"),
    ("- [a.one] CONFIRMED: Text. {lang}", "FACT_BAD_ATTRIBUTES"),
    ("- [a.one] CONFIRMED: Text. {note:}", "FACT_EMPTY_ATTRIBUTE"),
    ("- [a.one] CONFIRMED: Text. {technologies: , ,}", "FACT_EMPTY_ATTRIBUTE"),
    ("- [a.one] CONFIRMED: Text. {capabilities: Bad Cap}", "FACT_INVALID_CAPABILITY"),
    ("- [a.one] CONFIRMED: Text.}", "FACT_BAD_ATTRIBUTES"),
    ("- [a.one] CONFIRMED: Text. {supersedes: Not An Id}", "FACT_INVALID_ID"),
])
def test_attribute_errors(line, code):
    assert codes(check(doc(line)))[0] == code


def _fp(attrs, line_ending=LF):
    text = doc("- [a.one] CONFIRMED: Text. {%s}" % attrs).replace(LF, line_ending)
    return facts.check_bytes(text.encode("utf-8"))


def test_extension_attributes_are_kept_in_the_canonical_model():
    base = facts.parse_text(doc("- [a.one] CONFIRMED: Text. {x-review: pending; lang: en}"))
    record = base.to_model()["facts"][0]
    assert record["extensions"] == {"x-review": "pending"}
    assert base.facts[0].extensions == (("x-review", "pending"),)


def test_files_without_extensions_keep_their_previous_model_and_fingerprint():
    assert "extensions" not in facts.parse_file(EXAMPLE).to_model()["facts"][0]


def test_changing_an_extension_value_or_adding_one_changes_the_fingerprint():
    a = _fp("x-review: pending; lang: en").factbase.factbase_sha256
    b = _fp("x-review: done; lang: en").factbase.factbase_sha256
    c = _fp("lang: en").factbase.factbase_sha256
    d = _fp("x-other: pending; lang: en").factbase.factbase_sha256
    assert len({a, b, c, d}) == 4


def test_reordering_equivalent_attributes_keeps_the_fingerprint():
    a = _fp("x-a: 1; x-b: 2; lang: en; technologies: Python, Git")
    b = _fp("lang: en; technologies: Python, Git; x-b: 2; x-a: 1")
    assert a.factbase.factbase_sha256 == b.factbase.factbase_sha256
    assert a.facts_source_sha256 != b.facts_source_sha256


def test_extensions_have_the_same_fingerprint_with_lf_and_crlf():
    lf, crlf = _fp("x-review: pending", LF), _fp("x-review: pending", CRLF)
    assert lf.factbase.factbase_sha256 == crlf.factbase.factbase_sha256
    assert lf.facts_source_sha256 == crlf.facts_source_sha256


def test_extension_values_are_whitespace_collapsed_and_nfc():
    a = _fp("x-k:   café   au  lait")
    b = _fp("x-k: café au lait")
    assert a.factbase.facts[0].extensions == (("x-k", "caf" + chr(0xe9) + " au lait"),)
    assert a.factbase.factbase_sha256 == b.factbase.factbase_sha256


@pytest.mark.parametrize("attrs,code", [
    ("x-a: 1; x-a: 2", "FACT_DUPLICATE_ATTRIBUTE"),
    ("x-a:", "FACT_EMPTY_ATTRIBUTE"),
    ("x-: 1", "FACT_BAD_ATTRIBUTES"),
    ("x-Bad: 1", "FACT_BAD_ATTRIBUTES"),
    ("x-a b: 1", "FACT_BAD_ATTRIBUTES"),
    ("x-a", "FACT_BAD_ATTRIBUTES"),
    ("colour: red", "FACT_UNKNOWN_ATTRIBUTE"),
    ("xreview: 1", "FACT_UNKNOWN_ATTRIBUTE"),
    ("X-review: 1", "FACT_UNKNOWN_ATTRIBUTE"),
])
def test_malformed_extensions_and_unprefixed_unknown_attributes_stay_refused(attrs, code):
    result = _fp(attrs)
    assert [e.code for e in result.errors] == [code] and result.factbase is None


def test_extensions_never_publish_or_promote_a_fact():
    text = doc(
        "- [d.one] DERIVED: Derived. {x-status: CONFIRMED; x-publish: true}",
        "- [n.one] NOT_CONFIRMED: Not. {x-status: CONFIRMED}",
        "- [w.one] WITHDRAWN: Withdrawn. {x-confirmed: yes}",
        "- [c.one] CONFIRMED: Confirmed. {x-status: WITHDRAWN}",
    )
    base = facts.parse_text(text)
    assert [f.status for f in base.facts] == ["DERIVED", "NOT_CONFIRMED", "WITHDRAWN", "CONFIRMED"]
    assert [f.id for f in base.publishable()] == ["c.one"]


def test_braces_inside_the_text_are_kept_when_the_text_does_not_end_with_a_brace():
    assert facts.parse_text(doc("- [a.one] CONFIRMED: Uses {curly} braces in templates.")).facts[0].text == \
        "Uses {curly} braces in templates."


# --- confirmation policy (criterion 12) -------------------------------------------------------------

POLICY = doc(
    "- [c.one] CONFIRMED: Confirmed.",
    "- [d.one] DERIVED: Derived.",
    "- [n.one] NOT_CONFIRMED: Not confirmed.",
    "- [w.one] WITHDRAWN: Withdrawn.",
    "- [c.two] CONFIRMED: Confirmed two.",
)


def test_only_confirmed_facts_are_publishable():
    base = facts.parse_text(POLICY)
    assert [f.id for f in base.publishable()] == ["c.one", "c.two"]
    assert all(f.status == facts.CONFIRMED for f in base.publishable())
    assert base.counts() == {"CONFIRMED": 2, "DERIVED": 1, "NOT_CONFIRMED": 1, "WITHDRAWN": 1}
    assert [f.id for f in base.by_status(facts.DERIVED)] == ["d.one"]


def test_statuses_are_never_promoted_by_parsing_or_reparsing():
    base = facts.parse_text(POLICY)
    assert {f.id: f.status for f in base.facts} == {
        "c.one": "CONFIRMED", "d.one": "DERIVED", "n.one": "NOT_CONFIRMED", "w.one": "WITHDRAWN", "c.two": "CONFIRMED"}
    again = facts.parse_text(POLICY)
    assert again.to_model() == base.to_model()
    # A superseding fact does not change the status of the fact it replaces.
    chained = doc("- [old.one] WITHDRAWN: Old.", "- [new.one] DERIVED: New. {supersedes: old.one}")
    parsed = facts.parse_text(chained)
    assert parsed.get("old.one").status == "WITHDRAWN" and parsed.get("new.one").status == "DERIVED"
    assert parsed.publishable() == ()


def test_facts_are_immutable_and_the_api_has_no_promotion_function():
    fact = facts.parse_text(POLICY).facts[0]
    with pytest.raises(AttributeError):
        fact.status = "CONFIRMED"
    public = [name for name in dir(facts) if not name.startswith("_")]
    assert not [name for name in public if "promot" in name.lower() or "confirm_" in name.lower()]
    assert not [name for name in dir(facts.FactBase) if "promot" in name.lower() or name.startswith("set_")]


# --- messages never echo fact text ---------------------------------------------------------------------

def test_error_messages_do_not_repeat_the_text_of_a_fact():
    secret = "ZZ-PRIVATE-SENTENCE-ZZ"
    result = check(doc("- [a.one] MAYBE: %s" % secret, "stray %s" % secret, "- [a.two] CONFIRMED: %s {confirmed_on: nope}" % secret))
    assert result.errors
    for error in result.errors:
        assert secret not in error.message


# --- API shape -------------------------------------------------------------------------------------

def test_parse_text_raises_with_every_error():
    with pytest.raises(facts.FactBaseError) as caught:
        facts.parse_text(doc("- [a.one] MAYBE: x", "stray"))
    assert caught.value.code == "FACT_UNKNOWN_STATUS"
    assert [e.code for e in caught.value.errors] == ["FACT_UNKNOWN_STATUS", "FACT_UNPARSED_LINE"]
    assert "line 5" in str(caught.value)


def test_error_as_dict():
    result = check(doc("stray"))
    assert result.errors[0].as_dict() == {
        "code": "FACT_UNPARSED_LINE", "line": 5,
        "message": "the line is not a fact, a heading, a comment or a continuation"}


# --- independence (criterion 15) ----------------------------------------------------------------------

def _imports(module):
    found = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(("." * node.level) + (node.module or ""))
            if node.level:
                found.update("." * node.level + alias.name for alias in node.names)
    return found


def test_facts_and_canonical_import_no_adapter_and_no_third_party():
    allowed_std = {"ast", "datetime", "re", "unicodedata", "collections", "hashlib", "json", "math"}
    for module in (facts, canonical):
        for name in _imports(module):
            if name.startswith("."):
                assert name in {".", ".canonical"}, (module.__name__, name)
            else:
                assert name in allowed_std, (module.__name__, name)


def test_importing_facts_in_a_fresh_interpreter_loads_no_adapter_and_no_third_party():
    code = (
        "import json, sys, modularcv.facts\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.startswith('modularcv'))))\n"
    )
    out = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r)\n%s" % (str(REPO), code)],
                         capture_output=True, text=True, check=True)
    loaded = json.loads(out.stdout)
    assert set(loaded) <= {"modularcv", "modularcv.facts", "modularcv.canonical"}, loaded


def test_package_still_declares_no_dependency():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r"^dependencies\s*=\s*\[\s*\]", text, re.MULTILINE)
