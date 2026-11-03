"""JobOffer-v1: validation, normalisation, fingerprints, language, requirement extraction, CLI (M6). Synthetic data only."""
import copy
import json
import shutil
import unicodedata
from pathlib import Path

import pytest

from modularcv import __main__ as cli
from modularcv import canonical, joboffer, taxonomy
from engine_data import encode, make_offer, offer_doc, tax
from synthetic import tree_hash

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = REPO / "examples" / "workspace"
SECRET = "ZXQ private é 9931"


def check(document):
    return joboffer.check_bytes(encode(document))


def codes(result):
    return [e.code for e in result.errors]


def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(str(EXAMPLE_DIR), str(root))
    return root


# --- validity ---------------------------------------------------------------------------------------------

def test_a_minimal_offer_is_valid_with_the_contract_defaults():
    offer = make_offer()
    model = offer.to_model()
    assert model["language"] == "en" and model["employment_type"] == "UNSPECIFIED" and model["requirements"] == []
    default = joboffer.check_data({"schema": "JobOffer-v1", "job_key": "k", "title": "T", "company": "C", "description": "D"})
    assert default.offer.declared_language == "auto" and default.offer.employment_type == "UNSPECIFIED"


def test_a_complete_offer_is_valid():
    document = offer_doc(
        employment_type="INTERNSHIP", location="Somewhere", workplace_type="Hybrid", source_url="https://example.org/job/1",
        source_system="manual", posted_on="2026-03", captured_at="2026-03-02T10:00:00Z", source_ref="opaque-123",
        requirements=[{"id": "r1", "term": "Python", "priority": "REQUIRED"},
                      {"id": "r2", "term": "Docker", "priority": "PREFERRED"}],
        **{"x-note": {"a": 1}})
    document["description_sha256"] = canonical.sha256_text(document["description"])
    result = check(document)
    assert not result.errors
    model = result.offer.to_model()
    assert model["posted_on"] == "2026-03" and [r["id"] for r in model["requirements"]] == ["r1", "r2"]
    assert model["extensions"] == {"x-note": {"a": 1}}


def test_the_example_offers_are_valid():
    for name in ("backend-intern.json", "backend-intern.fr.json"):
        assert not joboffer.check_file(EXAMPLE_DIR / "offers" / name).errors


@pytest.mark.parametrize("change,code", [
    (lambda d: d.update(schema="JobOffer-v2"), "OFFER_UNKNOWN_SCHEMA"),
    (lambda d: d.pop("job_key"), "OFFER_MISSING_FIELD"), (lambda d: d.pop("title"), "OFFER_MISSING_FIELD"),
    (lambda d: d.pop("company"), "OFFER_MISSING_FIELD"), (lambda d: d.pop("description"), "OFFER_MISSING_FIELD"),
    (lambda d: d.update(job_key="Bad Key"), "OFFER_INVALID_ID"), (lambda d: d.update(job_key="k\n"), "OFFER_INVALID_ID"),
    (lambda d: d.update(title=""), "OFFER_EMPTY_VALUE"), (lambda d: d.update(title=5), "OFFER_BAD_TYPE"),
    (lambda d: d.update(title="a\nb"), "OFFER_CONTROL_CHARACTER"), (lambda d: d.update(company="x" * 301), "OFFER_TOO_LONG"),
    (lambda d: d.update(description="   \n\n "), "OFFER_EMPTY_VALUE"), (lambda d: d.update(description=3), "OFFER_BAD_TYPE"),
    (lambda d: d.update(description="a\x00b"), "OFFER_CONTROL_CHARACTER"),
    (lambda d: d.update(description="x" * 100001), "OFFER_TOO_LONG"),
    (lambda d: d.update(language="de"), "OFFER_INVALID_VALUE"), (lambda d: d.update(language="EN"), "OFFER_INVALID_VALUE"),
    (lambda d: d.update(employment_type="INTERN"), "OFFER_INVALID_VALUE"),
    (lambda d: d.update(source_url="ftp://example.org"), "OFFER_INVALID_VALUE"),
    (lambda d: d.update(source_url="https://a b"), "OFFER_INVALID_VALUE"),
    (lambda d: d.update(posted_on="2026-02-30"), "OFFER_INVALID_VALUE"), (lambda d: d.update(posted_on=2026), "OFFER_INVALID_VALUE"),
    (lambda d: d.update(captured_at="2026-03-02"), "OFFER_INVALID_VALUE"),
    (lambda d: d.update(captured_at="2026-13-02T10:00:00Z"), "OFFER_INVALID_VALUE"),
    (lambda d: d.update(description_sha256="0" * 64), "OFFER_DESCRIPTION_HASH_MISMATCH"),
    (lambda d: d.update(requirements="Python"), "OFFER_BAD_TYPE"),
    (lambda d: d.update(requirements=[{"id": "r1", "term": "Python"}]), "OFFER_MISSING_FIELD"),
    (lambda d: d.update(requirements=[{"id": "r1", "term": "Python", "priority": "MUST"}]), "OFFER_INVALID_VALUE"),
    (lambda d: d.update(requirements=[{"id": "Bad", "term": "Python", "priority": "REQUIRED"}]), "OFFER_INVALID_ID"),
    (lambda d: d.update(surprise=1), "OFFER_UNKNOWN_FIELD"), (lambda d: d.update(**{"x-": 1}), "OFFER_BAD_EXTENSION"),
])
def test_invalid_offers_are_refused_with_a_stable_code(change, code):
    document = offer_doc()
    change(document)
    result = check(document)
    assert code in codes(result) and result.offer is None


@pytest.mark.parametrize("data,code", [(b"\xff\xfe", "OFFER_NOT_UTF8"), (b"{x", "OFFER_NOT_JSON"), (b"", "OFFER_NOT_JSON"),
                                       (b'{"a":1,"a":2}', "OFFER_DUPLICATE_KEY"), (b'{"a":NaN}', "OFFER_NOT_JSON"),
                                       (b"[]", "OFFER_BAD_TYPE"), (b"[" * 5000 + b"]" * 5000, "OFFER_NOT_JSON")])
def test_unusable_offer_files_are_refused(data, code):
    assert code in codes(joboffer.check_bytes(data))
    assert codes(joboffer.check_file(Path("no-such-offer.json"))) == ["OFFER_FILE_UNREADABLE"]


def test_explicit_requirements_cannot_be_inconsistent():
    requirements = [{"id": "r1", "term": "Python", "priority": "REQUIRED"}, {"id": "r2", "term": "python", "priority": "PREFERRED"}]
    assert codes(check(offer_doc(requirements=requirements))) == ["OFFER_REQUIREMENT_CONFLICT"]
    requirements[1]["priority"] = "REQUIRED"
    assert codes(check(offer_doc(requirements=requirements))) == ["OFFER_DUPLICATE_VALUE"]
    requirements[1].update(term="Docker", id="r1")
    assert codes(check(offer_doc(requirements=requirements))) == ["OFFER_DUPLICATE_ID"]


def test_the_supplied_description_hash_is_verified_not_trusted():
    document = offer_doc()
    document["description_sha256"] = canonical.sha256_text(document["description"])
    assert not check(document).errors
    document["description"] += "\nOne more line."
    assert codes(check(document)) == ["OFFER_DESCRIPTION_HASH_MISMATCH"]


def test_errors_never_repeat_a_value_of_the_offer():
    document = offer_doc(title=SECRET + "\n", company=SECRET * 40, description=SECRET + "\x00", job_key=SECRET,
                         posted_on=SECRET, source_url=SECRET, language=SECRET, requirements=[{"id": SECRET, "term": 5, "priority": SECRET}])
    document[SECRET] = SECRET
    document["x-" + SECRET] = SECRET
    result = check(document)
    shown = " ".join("%s %s %s" % (e.code, e.message, e.path) for e in result.errors).lower()
    assert shown and "zxq" not in shown and "9931" not in shown and "private" not in shown


# --- normalisation and fingerprints -----------------------------------------------------------------------

def test_the_description_is_nfc_lf_with_trailing_space_and_outer_blank_lines_dropped():
    decomposed = unicodedata.normalize("NFD", "Exigences :\r\n- Développement  \r\n\r\n")
    offer = make_offer("\r\n" + decomposed)
    assert offer.description == "Exigences :\n- Développement"
    assert unicodedata.is_normalized("NFC", offer.description) if hasattr(unicodedata, "is_normalized") else True


def test_offer_sha256_is_the_contract_fingerprint_of_its_identity_fields():
    offer = make_offer("Requirements:\n- Python")
    expected = canonical.fingerprint({"job_key": "job-1", "title": "Developer", "company": "Example Co (fictional)",
                                      "location": None, "description": "Requirements:\n- Python", "language": "en",
                                      "employment_type": "UNSPECIFIED"})
    assert offer.offer_sha256 == expected


def test_informational_fields_and_layout_never_change_either_fingerprint_except_the_source_hash():
    base = check(offer_doc())
    reference = base.offer.offer_sha256
    for change in ({"source_url": "https://example.org/x"}, {"posted_on": "2026-01-01"}, {"captured_at": "2026-01-01T00:00:00Z"},
                   {"source_ref": "abc"}, {"source_system": "s"}, {"workplace_type": "Remote"}, {"x-extra": 1}):
        assert check(offer_doc(**change)).offer.offer_sha256 == reference, change
    spread = json.dumps(offer_doc(), indent=4, sort_keys=True).encode("utf-8")
    assert joboffer.check_bytes(spread).offer.offer_sha256 == reference
    assert joboffer.check_bytes(spread).offer_source_sha256 != base.offer_source_sha256
    crlf = joboffer.check_bytes(json.dumps(offer_doc(), indent=2).replace("\n", "\r\n").encode("utf-8"))
    assert crlf.offer_source_sha256 == joboffer.check_bytes(json.dumps(offer_doc(), indent=2).encode("utf-8")).offer_source_sha256
    assert joboffer.check_bytes(b"\xef\xbb\xbf" + encode(offer_doc())).offer.offer_sha256 == reference


@pytest.mark.parametrize("change", [{"title": "Other"}, {"company": "Other"}, {"description": "Other text"}, {"language": "fr"},
                                    {"employment_type": "PERMANENT"}, {"location": "Elsewhere"}, {"job_key": "job-2"}])
def test_each_identity_field_moves_the_offer_fingerprint(change):
    assert check(offer_doc(**change)).offer.offer_sha256 != check(offer_doc()).offer.offer_sha256


def test_explicit_requirements_join_the_identity_only_when_present_and_ignore_their_order():
    plain = check(offer_doc()).offer.offer_sha256
    one = [{"id": "r1", "term": "Python", "priority": "REQUIRED"}, {"id": "r2", "term": "Docker", "priority": "PREFERRED"}]
    first = check(offer_doc(requirements=one)).offer.offer_sha256
    assert first != plain
    assert check(offer_doc(requirements=list(reversed(one)))).offer.offer_sha256 == first
    one[1]["priority"] = "REQUIRED"
    assert check(offer_doc(requirements=one)).offer.offer_sha256 != first


def test_the_description_hash_is_the_normalised_source_hash_of_the_text():
    offer = make_offer("Line one\r\nLine two")
    assert offer.description_sha256 == canonical.sha256_text("Line one\nLine two")


# --- language ---------------------------------------------------------------------------------------------

def test_the_declared_language_wins_and_auto_uses_a_deterministic_recorded_detector():
    assert make_offer(language="fr").resolve_language("en") == ("fr", "declared")
    english = make_offer("We are looking for a developer to work with our team and you will build services for the company.",
                         language="auto")
    french = make_offer("Nous recherchons un développeur pour travailler avec notre équipe et vous serez dans une équipe de la société.",
                        language="auto")
    assert english.resolve_language() == ("en", "detected") and french.resolve_language("en") == ("fr", "detected")
    tied = make_offer("Python pytest Docker", title="Dev", language="auto")
    assert tied.resolve_language() == (None, None) and tied.resolve_language("fr") == ("fr", "default")
    assert tied.resolve_language("de") == (None, None)
    assert joboffer.detect_language("the and of") == "en" and joboffer.detect_language("le la des") == "fr"
    assert joboffer.detect_language("") is None


# --- requirements ---------------------------------------------------------------------------------------------

def test_requirements_come_from_explicit_entries_and_exact_taxonomy_spellings():
    offer = make_offer("About us: we love Python.\nRequirements:\n- pytest\n- REST APIs\nNice to have:\n- Docker\n",
                       requirements=[{"id": "must-sql", "term": "SQL", "priority": "REQUIRED"},
                                     {"id": "obscure", "term": "Fortran", "priority": "PREFERRED"}])
    requirements, problems = joboffer.extract_requirements(offer, tax(), "en")
    assert not problems
    by_id = {r["id"]: r for r in requirements}
    assert by_id["req.python"]["priority"] == "PREFERRED" and by_id["req.python"]["sources"] == ["context"]
    assert by_id["req.pytest"]["priority"] == "REQUIRED" and by_id["req.api-design"]["weight"] == 4.0
    assert by_id["req.docker"]["priority"] == "PREFERRED" and by_id["must-sql"]["term_id"] == "sql"
    assert by_id["obscure"]["term_id"] is None and by_id["obscure"]["label"] == "Fortran"
    assert [r["id"] for r in requirements][:3] == ["must-sql", "req.api-design", "req.pytest"]  # required first, by weight, then id


def test_a_term_found_twice_keeps_the_strongest_priority_and_weight():
    offer = make_offer("Nice to have:\n- Python\nRequirements:\n- Python\n")
    requirements, _ = joboffer.extract_requirements(offer, tax(), "en")
    assert [(r["id"], r["priority"], r["weight"], r["sources"]) for r in requirements if r["id"] == "req.python"] == [
        ("req.python", "REQUIRED", 4.0, ["preferred", "requirement"])]


def test_an_explicit_entry_and_a_text_mention_of_one_term_merge_under_the_explicit_id():
    offer = make_offer("Nice to have:\n- Docker\n", requirements=[{"id": "need-docker", "term": "docker", "priority": "REQUIRED"}])
    requirements, problems = joboffer.extract_requirements(offer, tax(), "en")
    assert not problems and [(r["id"], r["priority"], r["sources"]) for r in requirements] == [
        ("need-docker", "REQUIRED", ["declared", "preferred"])]


def test_inconsistent_explicit_requirements_are_refused_once_resolved():
    offer = make_offer(requirements=[{"id": "a", "term": "JavaScript", "priority": "REQUIRED"},
                                     {"id": "b", "term": "JS", "priority": "PREFERRED"}])
    _requirements, problems = joboffer.extract_requirements(offer, tax(), "en")
    assert [p.code for p in problems] == ["OFFER_REQUIREMENT_DUPLICATE_TERM"]
    offer = make_offer("Requirements:\n- Python\n", requirements=[{"id": "req.python", "term": "Docker", "priority": "REQUIRED"}])
    _requirements, problems = joboffer.extract_requirements(offer, tax(), "en")
    assert [p.code for p in problems] == ["OFFER_REQUIREMENT_ID_COLLISION"]


def test_extraction_is_stable_across_calls_and_untouched_inputs():
    offer = make_offer()
    before = offer.to_model()
    first = joboffer.extract_requirements(offer, tax(), "en")
    assert first == joboffer.extract_requirements(offer, tax(), "en") and offer.to_model() == before


# --- command line ---------------------------------------------------------------------------------------------

def test_offer_check_reports_requirements_without_the_text(workspace, capsys):
    code, out, err = run(capsys, "offer", "check", str(workspace / "offers" / "backend-intern.json"), "--root", str(workspace))
    report = json.loads(out)
    assert code == 0 and report["status"] == "OK" and report["semantic_understanding"] is False
    assert report["unknown_terms"] == 1 and {r["id"] for r in report["requirements"]} >= {"req.python", "must-cobol"}
    assert "Experience building" not in out and "Example Software" not in out
    code, out, _ = run(capsys, "offer", "check", str(workspace / "offers" / "backend-intern.fr.json"), "--root", str(workspace))
    report = json.loads(out)
    assert code == 0 and report["language"] == "fr" and report["language_method"] == "detected"


def test_offer_check_undecided_language_and_invalid_inputs(workspace, capsys, tmp_path):
    path = workspace / "offers" / "tied.json"
    path.write_text(json.dumps(offer_doc("Python", language="auto")), encoding="utf-8")
    code, out, _ = run(capsys, "offer", "check", str(path), "--root", str(workspace))
    assert code == 1 and json.loads(out)["status"] == "LANGUAGE_UNDECIDED"
    path.write_text(json.dumps(offer_doc(language="de")), encoding="utf-8")
    code, _, err = run(capsys, "offer", "check", str(path), "--root", str(workspace))
    assert code == 1 and "OFFER_INVALID_VALUE" in err
    code, _, err = run(capsys, "offer", "check", str(tmp_path / "nope.json"), "--root", str(workspace))
    assert code == 2 and "OFFER_FILE_UNREADABLE" in err
    code, _, err = run(capsys, "offer", "check", str(workspace / "offers" / "backend-intern.json"), "--taxonomy", "builtin:x")
    assert code == 2


def test_offer_fingerprint_command(workspace, capsys):
    path = str(workspace / "offers" / "backend-intern.json")
    parsed = joboffer.check_file(path)
    code, out, _ = run(capsys, "offer", "fingerprint", path)
    assert code == 0 and json.loads(out)["offer_sha256"] == parsed.offer.offer_sha256
    for only, expected in (("source", parsed.offer_source_sha256), ("offer", parsed.offer.offer_sha256)):
        code, out, _ = run(capsys, "offer", "fingerprint", path, "--only", only)
        assert code == 0 and out.strip() == expected


def test_offer_commands_write_nothing(workspace, capsys):
    before = tree_hash(workspace)
    for argv in (("check", str(workspace / "offers" / "backend-intern.json")), ("fingerprint", str(workspace / "offers" / "backend-intern.json"))):
        run(capsys, "offer", *argv, "--root", str(workspace))
    assert tree_hash(workspace) == before
