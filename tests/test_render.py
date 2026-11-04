"""Plan verification, assembly, LaTeX rendering and optional PDF compilation (M7-A). Synthetic data only."""
import copy
import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from modularcv import __main__ as cli
from modularcv import assemble, canonical, content as contentmod, latex, pdf, plan as planmod
from engine_data import FACTS, bullet, content_doc, factbase, make_content, make_offer, make_profile, profile_doc, tax
from synthetic import tree_hash

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = REPO / "examples" / "workspace"
SECRET = "Zyxel-Quasar-7731"
REAL_PDFLATEX = pdf.find_pdflatex() is not None


def parts(document=None, facts_text=FACTS, description="Requirements:\n- Python\n- pytest\n", language="en", **profile_changes):
    offer, taxo = make_offer(description), tax()
    prof = make_profile(**profile_changes)
    base, cont = factbase(facts_text), make_content(document)
    plan, _matrix = planmod.build_plan(offer, taxo, prof, base, cont, None, language)
    return plan, (offer, taxo, prof, base, cont)


def assembled(**kwargs):
    plan, sources = parts(**kwargs)
    return assemble.assemble(plan, *sources), plan, sources


def rehash(plan):
    plan = copy.deepcopy(plan)
    plan["plan_sha256"] = canonical.fingerprint({k: v for k, v in plan.items() if k != "plan_sha256"})
    return plan


def tampered(plan, change):
    plan = copy.deepcopy(plan)
    change(plan)
    return rehash(plan)


def codes(error):
    return [e.code for e in error.value.errors]


def refused(plan, sources):
    with pytest.raises(assemble.AssemblyError) as raised:
        assemble.assemble(plan, *sources)
    return raised


def tex_of(**kwargs):
    model, _plan, _sources = assembled(**kwargs)
    return latex.render(model)


def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(str(EXAMPLE_DIR), str(root))
    (root / "plans").mkdir()
    (root / "out").mkdir()
    return root


def write_plan(workspace, capsys, offer="backend-intern.json", name="p.json"):
    code, _out, _err = run(capsys, "plan", "--offer", str(workspace / "offers" / offer), "--root", str(workspace),
                           "--out", "plans/" + name)
    assert code == 0
    return str(workspace / "plans" / name)


def render_args(workspace, plan_path, *extra, offer="backend-intern.json"):
    return ("render", "--plan", plan_path, "--offer", str(workspace / "offers" / offer), "--root", str(workspace)) + extra


# --- assembly of a valid plan ----------------------------------------------------------------------------------

def test_a_valid_plan_assembles_into_a_structured_cv_without_latex():
    model, plan, _sources = assembled()
    assert model["schema"] == "AssembledResume-v1" and model["status"] == "ASSEMBLED_NOT_REVIEWED" and model["ready_to_send"] is False
    assert model["language"] == "en" and model["source"]["plan_sha256"] == plan["plan_sha256"]
    assert [s["id"] for s in model["sections"]] == ["experience"]
    block = model["sections"][0]["blocks"][0]
    assert block["id"] == "job" and block["reason"] == "SELECTED" and block["heading_supports"] == ["f.job"]
    assert block["heading"] == {"title": "Developer"} and [b["id"] for b in block["bullets"]] == ["job.py", "job.test"]
    assert model["skills"]["title"] == "Skills" and [i["id"] for c in model["skills"]["categories"] for i in c["items"]] == ["python"]
    assert model["fact_ids"] == ["f.job", "f.py", "f.test"] or set(model["fact_ids"]) >= {"f.job", "f.py", "f.test"}
    assert assemble.verify_assembly_fingerprint(model) and "\\" not in json.dumps(model)
    assert model["layout"] == {"page_target": None, "pages": None, "status": "NOT_COMPILED"}


def test_the_assembly_prints_exactly_the_approved_words_and_adds_none():
    model, plan, (_o, _t, _p, _b, cont) = assembled()
    written = {b["id"]: b["text"] for blk in cont.to_model()["blocks"] for b in blk["bullets"]}
    for section in model["sections"]:
        for block in section["blocks"]:
            for item in block["bullets"]:
                assert item["text"] == written[item["id"]]["en"]
    selected = {e["id"] for e in plan["selected"]["bullets"]}
    printed = {b["id"] for s in model["sections"] for blk in s["blocks"] for b in blk["bullets"]}
    assert printed == selected                                              # nothing added, nothing dropped
    assert model["header"] == {"display_name": "Alex Sample", "links": []}


def test_the_selection_comes_from_the_plan_even_when_the_content_has_more():
    model, plan, _ = assembled(description="Requirements:\n- Python\n")
    printed = [b["id"] for s in model["sections"] for blk in s["blocks"] for b in blk["bullets"]]
    assert printed == ["job.py"] and "job.docker" not in printed


def test_sections_and_blocks_follow_the_content_order_not_the_file_order():
    document = content_doc()
    document["sections"].append({"id": "projects", "kind": "project", "title": {"en": "Projects", "fr": "Projets"}})
    document["blocks"].append({"id": "proj", "section": "projects", "order": 1, "languages": ["en", "fr"], "supports": ["f.job2"],
                               "heading": {"en": {"title": "Tool"}, "fr": {"title": "Outil"}},
                               "bullets": [bullet("proj.t", "Tests.", "Tests.", ["f.test"], ["pytest"], ["testing"])]})
    document["blocks"][0]["order"] = 2
    document["blocks"].append({"id": "earlier", "section": "experience", "order": 1, "languages": ["en", "fr"],
                               "supports": ["f.job2"], "heading": {"en": {"title": "Earlier"}, "fr": {"title": "Avant"}},
                               "bullets": [bullet("earlier.p", "More Python.", "Plus de Python.", ["f.py"], ["Python"], ["backend"])]})
    shuffled = copy.deepcopy(document)
    shuffled["blocks"].reverse()
    first, _p, _s = assembled(document=document)
    second, _p, _s = assembled(document=shuffled)
    assert [(s["id"], [b["id"] for b in s["blocks"]]) for s in first["sections"]] == \
           [("experience", ["earlier", "job"]), ("projects", ["proj"])]
    assert first["assembly_sha256"] == second["assembly_sha256"]


def test_a_protected_block_keeps_its_proven_heading_and_no_bullet():
    document = content_doc()
    document["sections"].append({"id": "education", "kind": "education", "title": {"en": "Education", "fr": "Formation"}})
    document["blocks"].append({"id": "edu", "section": "education", "order": 1, "languages": ["en", "fr"], "supports": ["f.job2"],
                               "protected": True, "heading": {"en": {"title": "Degree", "period": "2024"}, "fr": {"title": "Diplôme"}},
                               "bullets": [bullet("edu.x", "Studied.", "Étudié.", ["f.job2"])]})
    model, _plan, _s = assembled(document=document)
    education = next(s for s in model["sections"] if s["id"] == "education")
    assert education["blocks"] == [{"id": "edu", "reason": "PROTECTED", "heading": {"title": "Degree", "period": "2024"},
                                    "heading_supports": ["f.job2"], "bullets": []}]
    text = latex.render(model)
    assert "Degree" in text and "Studied" not in text


def test_the_header_prints_public_identity_only_and_never_the_headline():
    identity = {"display_name": {"value": "Alex Sample", "visibility": "public"},
                "headline": {"value": SECRET + " headline", "visibility": "public"},
                "email": {"value": "alex@example.com", "visibility": "public"},
                "phone": {"value": "+1 555 0100", "visibility": "private"},
                "links": [{"label": "Site", "value": "https://example.org/a", "visibility": "public"},
                          {"value": "https://example.org/private", "visibility": "private"}]}
    model, _p, _s = assembled(identity=identity)
    assert model["header"] == {"display_name": "Alex Sample", "email": "alex@example.com",
                               "links": [{"label": "Site", "value": "https://example.org/a"}]}
    assert {"code": "HEADLINE_NOT_PRINTED"} in model["warnings"]
    text = latex.render(model)
    assert SECRET not in text and "555" not in text and "private" not in text


def test_a_private_display_name_is_refused():
    identity = {"display_name": {"value": "Alex Sample", "visibility": "private"}}
    plan, sources = parts(identity=identity)
    assert codes(refused(plan, sources)) == ["ASSEMBLY_HEADER_NAME_PRIVATE"]


# --- invalid, altered, obsolete plans ---------------------------------------------------------------------------

def test_a_plan_that_is_not_a_plan_is_refused_before_anything_else():
    _plan, sources = parts()
    for candidate, expected in (([], "ASSEMBLY_PLAN_NOT_OBJECT"), ({}, "ASSEMBLY_PLAN_SCHEMA"), ("x", "ASSEMBLY_PLAN_NOT_OBJECT")):
        with pytest.raises(assemble.AssemblyError) as raised:
            assemble.assemble(candidate, *sources)
        assert codes(raised)[0] == expected
    plan, sources = parts()
    for change in (lambda p: p.update(plan_status="READY_TO_SEND"), lambda p: p.update(tailored_cv_id="x"),
                   lambda p: p.update(review={"status": "APPROVED"}), lambda p: p.update(schema="Other-v1"),
                   lambda p: p.update(family="Bad Family"), lambda p: p["inputs"].pop("matrix_sha256"),
                   lambda p: p["selected"].pop("skills")):
        assert codes(refused(tampered(plan, change), sources))[0] in ("ASSEMBLY_PLAN_STATUS", "ASSEMBLY_PLAN_SCHEMA",
                                                                       "ASSEMBLY_PLAN_FIELD")


def test_an_edited_plan_is_refused_by_its_fingerprint():
    plan, sources = parts()
    edited = copy.deepcopy(plan)
    edited["selected"]["bullets"][0]["gain"] = 99
    assert codes(refused(edited, sources)) == ["ASSEMBLY_PLAN_FINGERPRINT"]
    with pytest.raises(assemble.AssemblyError):
        assemble.check_fingerprint(edited)
    assemble.check_fingerprint(plan)


def test_an_edited_plan_with_a_recomputed_fingerprint_is_not_reproducible():
    plan, sources = parts()
    for change in (lambda p: p["selected"]["bullets"][0].update(gain=99),
                   lambda p: p["selected"]["bullets"].append(dict(p["selected"]["bullets"][0], id="job.docker")),
                   lambda p: p.update(extra="x"), lambda p: p["limits"].append("x")):
        forged = tampered(plan, change)
        assemble.check_fingerprint(forged)                                          # the hash was recomputed: it passes
        assert codes(refused(forged, sources))[0] in ("ASSEMBLY_PLAN_NOT_REPRODUCIBLE", "ASSEMBLY_ITEM_UNKNOWN")
        with pytest.raises(assemble.AssemblyError):
            assemble.check_reproducible(forged, *sources)
    assemble.check_reproducible(plan, *sources)


def test_a_plan_built_from_other_sources_is_obsolete():
    plan, (offer, taxo, prof, base, cont) = parts()
    other = {
        "inputs.factbase_sha256": (offer, taxo, prof, factbase(FACTS + "- [f.new] CONFIRMED: A new fact.\n"), cont),
        "inputs.profile_sha256": (offer, taxo, make_profile(policy={"never_publish_terms": ["Kubernetes"]}), base, cont),
        "inputs.offer_sha256": (make_offer("Requirements:\n- Docker\n"), taxo, prof, base, cont),
        "inputs.content_sha256": (offer, taxo, prof, base, make_content(_with_extra_bullet())),
    }
    for path, sources in other.items():
        raised = refused(plan, sources)
        assert codes(raised)[0] == "ASSEMBLY_SOURCE_MISMATCH" and path in [e.path for e in raised.value.errors]
        with pytest.raises(assemble.AssemblyError):
            assemble.check_sources(plan, *sources)
    assemble.check_sources(plan, offer, taxo, prof, base, cont)


def _with_extra_bullet():
    document = content_doc()
    document["blocks"][0]["bullets"].append(bullet("job.extra", "Extra.", "Extra.", ["f.py"], ["Python"], ["backend"]))
    return document


def test_a_formatting_only_change_of_the_fact_file_still_makes_the_plan_obsolete():
    plan, (offer, taxo, prof, _b, cont) = parts()
    spaced = factbase(FACTS + "\n\n")
    assert spaced.factbase_sha256 == factbase().factbase_sha256 and spaced.facts_source_sha256 != factbase().facts_source_sha256
    assert "inputs.facts_source_sha256" in [e.path for e in refused(plan, (offer, taxo, prof, spaced, cont)).value.errors]


def test_a_fact_withdrawn_after_the_plan_was_made_stops_the_assembly():
    plan, (offer, taxo, prof, _base, cont) = parts()
    for status in ("WITHDRAWN", "NOT_CONFIRMED", "DERIVED"):
        later = factbase(FACTS.replace("[f.py] CONFIRMED", "[f.py] " + status))
        assert codes(refused(plan, (offer, taxo, prof, later, cont)))[0] == "ASSEMBLY_SOURCE_MISMATCH"
        # even if every fingerprint check were bypassed, the independent re-validation refuses the bullet and the skill
        with pytest.raises(assemble.AssemblyError) as raised:
            assemble.check_publishable(plan, offer, taxo, prof, later, cont)
        assert set(codes(raised)) == {"ASSEMBLY_FACT_NOT_CONFIRMED"}
        assert any(e.path.startswith("selected.skills") for e in raised.value.errors)


def test_an_unproven_heading_is_refused_even_under_a_proven_bullet():
    plan, (offer, taxo, prof, _base, cont) = parts()
    later = factbase(FACTS.replace("[f.job] CONFIRMED", "[f.job] WITHDRAWN"))
    with pytest.raises(assemble.AssemblyError) as raised:
        assemble.check_publishable(plan, offer, taxo, prof, later, cont)
    assert "ASSEMBLY_HEADING_UNPROVEN" in codes(raised)


def test_an_unverified_skill_is_refused():
    plan, (offer, taxo, prof, base, cont) = parts()
    document = content_doc()
    document["skills"][0]["items"][0]["supports"] = ["f.k8s"]
    with pytest.raises(assemble.AssemblyError) as raised:
        assemble.check_publishable(plan, offer, taxo, prof, base, make_content(document))
    assert codes(raised) == ["ASSEMBLY_FACT_NOT_CONFIRMED"] and raised.value.errors[0].path == "selected.skills[0]"


def test_a_forged_plan_cannot_select_what_the_profile_or_the_content_forbid():
    document = content_doc()
    document["blocks"][0]["bullets"].append(bullet("job.secret", "Private note.", "Note.", ["f.py"], never_publish=True))
    document["blocks"][0]["bullets"].append(bullet("job.k8s", "Kubernetes.", "Kubernetes.", ["f.k8s"], ["Kubernetes"]))
    document["blocks"].append({"id": "onlyen", "section": "experience", "order": 2, "languages": ["en"], "supports": ["f.job2"],
                               "heading": {"en": {"title": "English only"}},
                               "bullets": [{"id": "onlyen.1", "text": {"en": "Only English."}, "supports": ["f.py"],
                                            "technologies": ["Python"], "capabilities": ["backend"]}]})
    plan, (offer, taxo, prof, base, cont) = parts(document=document)

    def add(bullet_id):
        def change(p):
            p["selected"]["bullets"].append(dict(p["selected"]["bullets"][0], id=bullet_id))
            p["selected"]["blocks"][0]["bullets"].append(bullet_id)
        return change

    for bullet_id, expected in (("job.secret", "ASSEMBLY_ITEM_NOT_PUBLISHABLE"), ("job.k8s", "ASSEMBLY_FACT_NOT_CONFIRMED"),
                                ("job.unknown", "ASSEMBLY_ITEM_UNKNOWN")):
        with pytest.raises(assemble.AssemblyError) as raised:
            assemble.check_publishable(tampered(plan, add(bullet_id)), offer, taxo, prof, base, cont)
        assert expected in codes(raised)
    french, _ = planmod.build_plan(offer, taxo, prof, base, cont, None, "fr")
    forged = tampered(french, lambda p: (p["selected"]["bullets"].append(dict(p["selected"]["bullets"][0], id="onlyen.1", block="onlyen")),
                                         p["selected"]["blocks"].append({"id": "onlyen", "reason": "SELECTED",
                                                                          "heading_supports": ["f.job2"], "bullets": ["onlyen.1"]})))
    with pytest.raises(assemble.AssemblyError) as raised:
        assemble.check_publishable(forged, offer, taxo, prof, base, cont)
    assert codes(raised).count("ASSEMBLY_LANGUAGE_UNAVAILABLE") == 2
    twice = tampered(plan, lambda p: p["selected"]["bullets"].append(dict(p["selected"]["bullets"][0])))
    with pytest.raises(assemble.AssemblyError) as raised:
        assemble.check_publishable(twice, offer, taxo, prof, base, cont)
    assert "ASSEMBLY_DUPLICATE_SELECTION" in codes(raised)


def test_forbidden_words_and_terms_added_after_the_plan_are_caught_independently():
    plan, (offer, taxo, _prof, base, cont) = parts()
    for policy in ({"never_publish_terms": ["Python"]}, {"forbidden_words": {"en": ["services"]}}):
        stricter = make_profile(policy=policy)
        with pytest.raises(assemble.AssemblyError) as raised:
            assemble.check_publishable(plan, offer, taxo, stricter, base, cont)
        assert "ASSEMBLY_ITEM_NOT_PUBLISHABLE" in codes(raised)
        assert codes(refused(plan, (offer, taxo, stricter, base, cont)))[0] == "ASSEMBLY_SOURCE_MISMATCH"


def test_a_missing_language_stops_the_plan_before_it_reaches_the_assembly():
    document = content_doc()
    document["blocks"][0]["languages"] = ["en"]
    document["blocks"][0]["heading"].pop("fr")
    for item in document["blocks"][0]["bullets"]:
        item["text"].pop("fr")
    document["skills"][0]["items"][0]["text"].pop("fr")
    document["skills"][0]["items"][1]["text"].pop("fr")
    document["sections"][0]["title"].pop("fr")
    document["skills"][0]["title"].pop("fr")
    with pytest.raises(planmod.PlanError):
        parts(document=document, language="fr")
    plan, (offer, taxo, prof, base, cont) = parts(document=document)
    french = tampered(plan, lambda p: p.update(language="fr"))
    assert codes(refused(french, (offer, taxo, prof, base, cont)))[0] in ("ASSEMBLY_PLAN_REFUSED", "ASSEMBLY_PLAN_NOT_REPRODUCIBLE")


def test_a_label_is_needed_only_for_a_language_the_template_knows():
    document = content_doc()
    for section in document["sections"]:
        section["title"]["de"] = "Erfahrung"
    for block in document["blocks"]:
        block["languages"] = ["de"]
        block["heading"] = {"de": block["heading"]["en"]}
        for item in block["bullets"]:
            item["text"] = {"de": item["text"]["en"]}
    for category in document["skills"]:
        category["title"] = {"de": "Werkzeuge"}
        for item in category["items"]:
            item["text"] = {"de": item["text"]["en"]}
    document["sections"][0]["title"] = {"de": "Erfahrung"}
    prof = dict(languages=["de"], default_language="de",
                families={"software": {"label": "S", "languages": ["de"], "clusters": ["backend", "testing"]}})
    plan, sources = parts(document=document, language="de", **prof)
    assert codes(refused(plan, sources)) == ["ASSEMBLY_LABEL_UNAVAILABLE"]


# --- soften, page target, no silent rewrite --------------------------------------------------------------------------

def test_a_soften_directive_stays_pending_and_the_text_is_not_changed():
    guidance = [{"job_key": "job-1", "rules": [{"fact_id": "f.py", "action": "soften", "text": "SOFTENED-" + SECRET}]}]
    model, plan, _s = assembled(guidance=guidance)
    assert model["pending_directives"] == [{"type": "bullet", "id": "job.py", "directive": "soften"}]
    assert next(b for s in model["sections"] for blk in s["blocks"] for b in blk["bullets"] if b["id"] == "job.py")["text"] == "Built services in Python."
    text = latex.render(model)
    assert SECRET not in text and "SOFTENED" not in text and "Built services in Python." in text


def test_the_page_target_is_recorded_and_never_changes_the_content():
    families = {"software": {"label": "S", "languages": ["en", "fr"], "clusters": ["backend", "testing"], "page_target": 1}}
    with_target, _p, _s = assembled(families=families)
    without, _p, _s = assembled()
    assert with_target["layout"] == {"page_target": 1, "pages": None, "status": "NOT_COMPILED"}
    assert with_target["sections"] == without["sections"] and with_target["skills"] == without["skills"]
    assert pdf.page_verdict(None, 3) == "NO_TARGET" and pdf.page_verdict(2, None) == "NOT_COMPILED"
    assert pdf.page_verdict(2, 2) == "TARGET_MET" and pdf.page_verdict(1, 2) == "TARGET_EXCEEDED"


def test_unsatisfied_required_requirements_travel_with_the_assembly_but_are_not_printed():
    model, plan, _s = assembled(description="Requirements:\n- Python\n- Linux\n")
    assert [u["id"] for u in model["unsatisfied_required"]] == ["req.linux"]
    assert "Linux" not in latex.render(model)


def test_the_engine_changes_none_of_its_inputs_when_assembling_and_rendering():
    plan, sources = parts()
    before = (copy.deepcopy(plan), [s.to_model() for s in sources[1:]], sources[0].to_model())
    model = assemble.assemble(plan, *sources)
    latex.render(model)
    after = (plan, [s.to_model() for s in sources[1:]], sources[0].to_model())
    assert before == after


# --- LaTeX escaping and injection -------------------------------------------------------------------------------------

def test_each_special_character_has_one_fixed_replacement():
    expected = {"\\": "\\textbackslash{}", "{": "\\{", "}": "\\}", "$": "\\$", "&": "\\&", "#": "\\#", "_": "\\_", "%": "\\%",
                "~": "\\textasciitilde{}", "^": "\\textasciicircum{}", "[": "{[}", "]": "{]}"}
    for char, replacement in expected.items():
        assert latex.escape("a" + char + "b") == "a" + replacement + "b"


def test_the_ligatures_of_the_font_are_broken_so_that_the_printed_characters_are_the_written_ones():
    assert latex.escape("a -- b --- c") == "a -{}- b -{}-{}- c"
    assert latex.escape("''") == "'{}'" and latex.escape("``") == "`{}`" and latex.escape("<<>>") == "<{}<>{}>"
    assert latex.escape(",,") == ",{}," and latex.escape("!`") == "!{}`" and latex.escape("?`") == "?{}`"
    assert latex.escape("pre-existing, it's <ok>") == "pre-existing, it's <ok>"


def test_accents_and_listed_punctuation_pass_through_and_the_rest_is_refused():
    assert latex.escape("Développeur à Montréal – « test » … 5 € ° ’") == "Développeur à Montréal – « test » … 5 € ° ’"
    assert latex.escape("a\u00a0b") == "a~b"
    for bad in ("a\nb", "a\tb", "a\x00b", "a\x7fb", "\u2192", "\u202e", "\u200b", "\ufeff", "\u00ad", "\U0001f600", "\u0301", "\u00d7"):
        with pytest.raises(latex.RenderError) as raised:
            latex.escape(bad, "bullet:x")
        assert codes(raised) == ["RENDER_UNSUPPORTED_CHARACTER"] and raised.value.errors[0].path == "bullet:x"
        assert bad not in str(raised.value)
    with pytest.raises(latex.RenderError):
        latex.escape(None)


def unescape(source):
    """Inverse of the escaping table, to prove nothing is lost or invented."""
    reverse = {v: k for k, v in latex.SPECIALS.items() if k != "\u00a0"}
    source = source.replace("{}", "\x00")
    for replacement in sorted(reverse, key=len, reverse=True):
        source = source.replace(replacement.replace("{}", "\x00"), "\x01" + reverse[replacement] + "\x02")
    return source.replace("\x00", "").replace("\x01", "").replace("\x02", "")


def test_escaping_round_trips_over_random_texts_and_leaves_no_active_character():
    rng = random.Random(7311)
    alphabet = list("abcXYZ019 .,;:!?-'`<>\"/()*+=@|") + list("\\{}$&#_%~^[]") + list("éèàçôœÉ«»–—’")
    for _ in range(600):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
        source = latex.escape(text)
        assert unescape(source) == text
        stripped = source
        for replacement in sorted(latex.SPECIALS.values(), key=len, reverse=True):
            stripped = stripped.replace(replacement, "")
        stripped = stripped.replace("{}", "")
        assert not set(stripped) & set("\\{}$&#_%~^[]")


def test_inline_formatting_is_limited_to_bold_and_italic_and_the_text_never_becomes_a_command():
    spans = assemble.inline_spans("Built **REST** with _care_ and snake_case, 100% $x$")
    assert [(s["text"], s["bold"], s["italic"]) for s in spans] == [
        ("Built ", False, False), ("REST", True, False), (" with ", False, False), ("care", False, True),
        (" and snake_case, 100% $x$", False, False)]
    assert latex.inline(spans) == "Built \\textbf{REST} with \\textit{care} and snake\\_case, 100\\% \\$x\\$"
    nested = assemble.inline_spans("**a _b_ c**")
    assert [(s["text"], s["bold"], s["italic"]) for s in nested] == [("a ", True, False), ("b", True, True), (" c", True, False)]
    assert latex.inline(nested) == "\\textbf{a }\\textbf{\\textit{b}}\\textbf{ c}"
    for invalid in ("**open", "_open", "a ** b", "****", "_a **b_ c**"):
        assert assemble.inline_spans(invalid) is None


def test_inline_spans_agree_with_the_content_validator_on_random_texts():
    rng = random.Random(902)
    for _ in range(2000):
        text = "".join(rng.choice("ab _*") for _ in range(rng.randint(0, 9)))
        spans = assemble.inline_spans(text)
        assert (spans is None) == contentmod.inline_markup_problem(text), text
        if spans is not None:
            assert len("".join(s["text"] for s in spans)) <= len(text)


ALLOWED_COMMANDS = {
    "documentclass", "usepackage", "input", "pdfgentounicode", "pagestyle", "setlength", "setlist", "newcommand", "begin", "end",
    "LARGE", "bfseries", "large", "par", "vspace", "hrule", "noindent", "textbf", "textit", "textbar", "item", "cvsection",
    "textbackslash", "textasciitilde", "textasciicircum", "empty", "parindent", "parskip", "ifpdf", "{", "}", "$", "&", "#", "_",
    "%",
}


def commands_of(source):
    return set(re.findall(r"\\([A-Za-z]+|.)", source))


def test_the_document_uses_only_the_commands_of_the_fixed_template_whatever_the_data_says():
    hostile = ["\\input{/etc/passwd}", "\\write18{rm -rf /}", "}\\end{document}", "$\\sum$", "\\immediate\\write", "%\\begin{x}",
               "\\catcode`\\{=12", "\\usepackage{shellesc}", "\\href{http://x}{y}", "{\\bf x}", "\\verb|x|"]
    identity = {"display_name": {"value": hostile[0] + hostile[1], "visibility": "public"},
                "location": {"value": hostile[2], "visibility": "public"}, "email": {"value": hostile[3], "visibility": "public"},
                "phone": {"value": hostile[4], "visibility": "public"},
                "links": [{"label": hostile[5], "value": hostile[6], "visibility": "public"},
                          {"value": hostile[7] + hostile[8] + hostile[9] + hostile[10], "visibility": "public"}]}
    text = tex_of(identity=identity)
    assert commands_of(text) <= ALLOWED_COMMANDS
    assert text.count("\\input") == 1 and "\\write" not in text and "\\immediate" not in text and "\\catcode" not in text
    assert text.count("\\begin{document}") == 1 and text.count("\\end{document}") == 1 and text.endswith("\\end{document}\n")
    assert "textbackslash{}input" in text


def test_headings_and_every_field_are_escaped_too():
    document = content_doc()
    document["sections"][0]["title"]["en"] = "Work & Study 100%"
    document["blocks"][0]["heading"]["en"] = {"title": "Dev_ops {lead}", "subtitle": "R&D #1", "period": "2025 – 2026", "place": "A~B"}
    document["blocks"][0]["bullets"][0]["text"]["en"] = "Cut costs by 30% with $ & # tools {x} ^y~ [z]"
    text = tex_of(document=document)
    for needle in ("Work \\& Study 100\\%", "Dev\\_ops \\{lead\\}", "R\\&D \\#1", "A\\textasciitilde{}B",
                   "Cut costs by 30\\% with \\$ \\& \\# tools \\{x\\} \\textasciicircum{}y\\textasciitilde{} {[}z{]}"):
        assert needle in text
    assert commands_of(text) <= ALLOWED_COMMANDS


def test_an_unprintable_character_stops_the_render_without_echoing_it():
    document = content_doc()
    document["blocks"][0]["bullets"][0]["text"]["en"] = "Built \u2192 " + SECRET
    model, _p, _s = assembled(document=document)
    with pytest.raises(latex.RenderError) as raised:
        latex.render(model)
    assert codes(raised) == ["RENDER_UNSUPPORTED_CHARACTER"] and raised.value.errors[0].path == "bullet:job.py"
    assert SECRET not in str(raised.value) and "\u2192" not in str(raised.value)


def test_the_renderer_refuses_an_assembly_that_is_not_intact_or_that_claims_readiness():
    model, _p, _s = assembled()
    for change in (lambda m: m["header"].update(display_name="Someone else"), lambda m: m.update(ready_to_send=True),
                   lambda m: m.update(schema="Other-v1")):
        forged = copy.deepcopy(model)
        change(forged)
        with pytest.raises(latex.RenderError) as raised:
            latex.render(forged)
        assert codes(raised) == ["RENDER_ASSEMBLY_INVALID"]
    forged = copy.deepcopy(model)
    forged["ready_to_send"] = True
    forged["assembly_sha256"] = canonical.fingerprint({k: v for k, v in forged.items() if k != "assembly_sha256"})
    with pytest.raises(latex.RenderError):
        latex.render(forged)
    with pytest.raises(latex.RenderError) as raised:
        latex.render(model, "a0paper")
    assert codes(raised) == ["RENDER_BAD_OPTION"]


# --- French and English ---------------------------------------------------------------------------------------------

def test_french_and_english_documents_use_the_text_of_their_own_language():
    english = tex_of(language="en")
    french = tex_of(language="fr", description="Exigences :\n- Python\n- pytest\n")
    assert "Built services in Python." in english and "Services en Python." not in english and "Skills" in english
    assert "Services en Python." in french and "Built services" not in french and "Compétences" in french
    assert "Développeur" in french and "% language: fr" in french and "% language: en" in english


# --- determinism ----------------------------------------------------------------------------------------------------------

def test_the_same_inputs_give_the_same_bytes_whatever_the_key_and_block_order():
    document = content_doc()
    reordered = json.loads(json.dumps(document, sort_keys=True))
    reordered["blocks"].reverse()
    first, second = tex_of(document=document), tex_of(document=reordered)
    assert first == second and latex.tex_bytes(first) == latex.tex_bytes(second)
    assert latex.tex_sha256(latex.tex_bytes(first)) == canonical.sha256_bytes(latex.tex_bytes(first))


def test_the_tex_is_lf_utf8_without_bom_date_or_random_value():
    data = latex.tex_bytes(tex_of(language="fr", description="Exigences :\n- Python\n"))
    assert b"\r" not in data and not data.startswith(b"\xef\xbb\xbf") and data.endswith(b"\n") and not data.endswith(b"\n\n")
    text = data.decode("utf-8")
    assert not re.search(r"\b(19|20)\d\d-\d\d-\d\d\b", text.split("\\begin{document}")[0])
    assert "\\today" not in text and "\\date" not in text and "\\year" not in text
    assert all(len(line) < 400 for line in text.splitlines())


def test_the_fingerprint_follows_the_bytes_and_the_options():
    model, _p, _s = assembled()
    a4, letter = latex.render(model), latex.render(model, "letterpaper")
    assert a4 != letter and "letterpaper" in letter and latex.tex_sha256(latex.tex_bytes(a4)) != latex.tex_sha256(latex.tex_bytes(letter))
    other = assembled(description="Requirements:\n- Python\n")[0]
    assert latex.render(other) != a4


def test_rendering_twice_in_a_changed_environment_gives_the_same_bytes(monkeypatch):
    first = tex_of()
    monkeypatch.setenv("TZ", "Pacific/Auckland")
    monkeypatch.setenv("LANG", "tr_TR.UTF-8")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "12345")
    assert tex_of() == first


# --- optional compilation: simulated ------------------------------------------------------------------------------------

GOOD_PDF = b"%PDF-1.5\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class FakeCompiler:
    """Replaces `subprocess.run` inside `modularcv.pdf`; records how the compiler would have been started."""

    def __init__(self, scenario="ok"):
        self.scenario, self.calls = scenario, []

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, stdout=b"pdfTeX 3.141592653-2.6-1.40.25 (TeX Live 2023)\n")
        work = kwargs["cwd"]
        if self.scenario == "timeout":
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        if self.scenario == "oserror":
            raise OSError("cannot start")
        if self.scenario == "error":
            log = "This is pdfTeX\n! Undefined control sequence.\nl.12 \\item %s\n" % SECRET
            Path(work, "resume.log").write_text(log, encoding="utf-8")
            return subprocess.CompletedProcess(args, 1, stdout=log.encode("utf-8"))
        log = "Output written on resume.pdf (%s).\n" % ("2 pages, 100 bytes" if self.scenario != "nopages" else "?")
        Path(work, "resume.log").write_text(log, encoding="utf-8")
        if self.scenario != "nopdf":
            Path(work, "resume.pdf").write_bytes(b"not a pdf" if self.scenario == "badpdf" else GOOD_PDF)
        return subprocess.CompletedProcess(args, 0, stdout=log.encode("utf-8"))


@pytest.fixture
def fake(monkeypatch):
    def install(scenario="ok"):
        compiler = FakeCompiler(scenario)
        monkeypatch.setattr(pdf.subprocess, "run", compiler)
        monkeypatch.setattr(pdf, "find_pdflatex", lambda: "fake-pdflatex")
        return compiler
    return install


def test_the_compiler_is_started_with_a_fixed_safe_command_line(fake):
    compiler = fake()
    result = pdf.compile_tex(b"\\documentclass{article}\n", 42)
    args, kwargs = next(c for c in compiler.calls if "--version" not in c[0])
    assert args[0] == "fake-pdflatex" and args[1:5] == ["-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", "-jobname=resume"]
    assert args[-1] == "resume.tex" and not any("\\" in a or SECRET in a for a in args)
    assert kwargs["timeout"] == 42 and kwargs["stdin"] == subprocess.DEVNULL and "shell" not in kwargs
    assert kwargs["env"]["shell_escape"] == "f" and kwargs["env"]["openout_any"] == "p"
    assert os.path.basename(kwargs["cwd"]).startswith("modularcv-") and not os.path.exists(kwargs["cwd"])   # removed afterwards
    assert result.pages == 2 and result.pdf == GOOD_PDF and result.pdf_sha256 == canonical.sha256_bytes(GOOD_PDF)


def test_the_environment_of_the_compiler_is_scrubbed(fake, monkeypatch):
    monkeypatch.setenv("TEXINPUTS", "/tmp/evil")
    monkeypatch.setenv("TEXMFHOME", "/tmp/evil")
    compiler = fake()
    pdf.compile_tex(b"x\n")
    env = next(c for c in compiler.calls if "--version" not in c[0])[1]["env"]
    assert "TEXINPUTS" not in env and "TEXMFHOME" not in env


@pytest.mark.parametrize("scenario,code", [("timeout", "PDF_TIMEOUT"), ("oserror", "PDF_UNAVAILABLE"), ("error", "PDF_COMPILE_FAILED"),
                                           ("nopdf", "PDF_NO_OUTPUT"), ("badpdf", "PDF_BAD_OUTPUT"), ("nopages", "PDF_PAGES_UNKNOWN")])
def test_every_way_a_compilation_can_fail_is_refused_with_a_stable_code(fake, scenario, code):
    fake(scenario)
    with pytest.raises(pdf.PdfError) as raised:
        pdf.compile_tex(b"x\n")
    assert raised.value.code == code and SECRET not in str(raised.value) and SECRET not in json.dumps(raised.value.details)


def test_a_failed_compilation_reports_the_kind_and_line_of_the_error_not_the_text(fake):
    fake("error")
    with pytest.raises(pdf.PdfError) as raised:
        pdf.compile_tex(b"x\n")
    assert raised.value.details == {"returncode": 1, "error_kind": "Undefined control sequence", "error_line": 12}
    assert SECRET in raised.value.log                                      # held back: only written when the caller asks


def test_the_time_limit_and_the_input_are_checked(fake):
    fake()
    for timeout in (0, -1, 301, "5", True, 1.5):
        with pytest.raises(pdf.PdfError) as raised:
            pdf.compile_tex(b"x\n", timeout)
        assert raised.value.code == "PDF_BAD_TIMEOUT"
    for data in (b"", "text", None):
        with pytest.raises(pdf.PdfError) as raised:
            pdf.compile_tex(data)
        assert raised.value.code == "PDF_BAD_INPUT"


def test_without_pdflatex_the_tex_is_unaffected_and_the_gap_is_declared(monkeypatch):
    monkeypatch.setattr(pdf, "find_pdflatex", lambda: None)
    with pytest.raises(pdf.PdfError) as raised:
        pdf.compile_tex(b"x\n")
    assert raised.value.code == "PDF_UNAVAILABLE"
    assert pdf.environment() == {"pdflatex": "ABSENT", "distribution": None, "version": None}
    assert tex_of().startswith("% ModularCV generic-v1 template")


# --- optional compilation: the real compiler ------------------------------------------------------------------------------

needs_pdflatex = pytest.mark.skipif(not REAL_PDFLATEX, reason="pdflatex is not installed: real PDF compilation not exercised")


@needs_pdflatex
def test_the_generated_tex_really_compiles_to_a_pdf_in_both_languages():
    for language, description in (("en", "Requirements:\n- Python\n- pytest\n"), ("fr", "Exigences :\n- Python\n- pytest\n")):
        result = pdf.compile_tex(latex.tex_bytes(tex_of(language=language, description=description)))
        assert result.pdf.startswith(b"%PDF-") and result.pages == 1 and result.returncode == 0


@needs_pdflatex
def test_every_character_the_renderer_accepts_and_escapes_compiles():
    safe = "".join(chr(c) for c in sorted(latex._SAFE_CODES) if chr(c) not in "\\_*" and c != 0xA0)
    text = "ASCII and accents: %s | specials: $ & # %% { } ~ ^ [ ] | ligatures: -- --- '' `` << >> ,, !` ?` | snake_case" % safe
    document = content_doc()
    document["blocks"][0]["bullets"][0]["text"]["en"] = text
    document["blocks"][0]["bullets"][1]["text"]["en"] = "**Bold** and _italic_ with a\u00a0non-breaking space"
    source = tex_of(document=document)
    result = pdf.compile_tex(latex.tex_bytes(source))
    assert result.pages == 1


@needs_pdflatex
def test_a_broken_document_really_fails_with_a_value_free_diagnosis():
    broken = ("\\documentclass{article}\n\\begin{document}\n%s \\undefinedcommand\n\\end{document}\n" % SECRET).encode("utf-8")
    with pytest.raises(pdf.PdfError) as raised:
        pdf.compile_tex(broken)
    assert raised.value.code == "PDF_COMPILE_FAILED" and raised.value.details["error_kind"] == "Undefined control sequence"
    assert SECRET not in json.dumps(raised.value.details) and SECRET not in str(raised.value)


@needs_pdflatex
def test_a_document_cannot_run_a_command_or_write_outside_the_working_directory(tmp_path):
    marker = tmp_path / "escaped.txt"
    hostile = ("\\documentclass{article}\n\\begin{document}\n\\immediate\\write18{echo x > %s}\n"
               "\\immediate\\openout3=%s\n\\immediate\\write3{x}\nhello\n\\end{document}\n" % (marker.as_posix(), marker.as_posix()))
    try:
        pdf.compile_tex(hostile.encode("utf-8"))
    except pdf.PdfError:
        pass
    assert not marker.exists()


# --- command line ---------------------------------------------------------------------------------------------------------------

def test_assemble_and_render_on_the_example_workspace(workspace, capsys):
    plan_path = write_plan(workspace, capsys)
    code, out, err = run(capsys, "assemble", "--plan", plan_path, "--offer", str(workspace / "offers" / "backend-intern.json"),
                         "--root", str(workspace), "--outline")
    outline = json.loads(out)
    assert code == 0 and err == "" and outline["status"] == "ASSEMBLED_NOT_REVIEWED"
    assert "REST endpoints" not in out and "Jordan" not in out and "example.com" not in out      # an outline holds no text
    code, out, _err = run(capsys, "assemble", "--plan", plan_path, "--offer", str(workspace / "offers" / "backend-intern.json"),
                          "--root", str(workspace))
    assert code == 0 and json.loads(out)["assembly_sha256"] == outline["assembly_sha256"]
    code, out, err = run(capsys, *render_args(workspace, plan_path))
    assert code == 0 and out.startswith("% ModularCV generic-v1") and "Built REST endpoints in \\textbf{Python}" in out


def test_render_writes_a_new_tex_and_reports_its_fingerprint(workspace, capsys):
    plan_path = write_plan(workspace, capsys)
    before = tree_hash(workspace)
    run(capsys, *render_args(workspace, plan_path))
    assert tree_hash(workspace) == before                                           # no --out: nothing is written
    code, out, _err = run(capsys, *render_args(workspace, plan_path, "--out", "out/resume.tex"))
    report = json.loads(out)
    data = (workspace / "out" / "resume.tex").read_bytes()
    assert code == 0 and report["tex"]["sha256"] == latex.tex_sha256(data) == canonical.sha256_bytes(data)
    assert report["ready_to_send"] is False and report["review"] == "NOT_REVIEWED" and report["pdf"] == {"status": "NOT_REQUESTED"}
    assert report["layout"] == {"page_target": 1, "pages": None, "page_verdict": "NOT_COMPILED"}
    assert b"\r" not in data and report["warnings"] and "Jordan" not in out and "REST" not in out
    code, out2, _err = run(capsys, *render_args(workspace, plan_path, "--out", "out/again.tex"))
    assert json.loads(out2)["tex"]["sha256"] == report["tex"]["sha256"]


def test_outputs_are_new_files_inside_the_workspace_and_never_an_input(workspace, capsys, tmp_path):
    plan_path = write_plan(workspace, capsys)
    run(capsys, *render_args(workspace, plan_path, "--out", "out/resume.tex"))
    cases = (("out/resume.tex", "OUTPUT_EXISTS"), ("facts.md", "OUTPUT_BAD_EXTENSION"), ("../escape.tex", "OUTPUT_OUTSIDE_WORKSPACE"),
             ("plans/p.json", "OUTPUT_BAD_EXTENSION"), ("out/x.pdf", "OUTPUT_BAD_EXTENSION"), (str(tmp_path / "x.tex"), "OUTPUT_OUTSIDE_WORKSPACE"),
             (".git/x.tex", "OUTPUT_OUTSIDE_WORKSPACE"))
    for target, expected in cases:
        code, out, err = run(capsys, *render_args(workspace, plan_path, "--out", target))
        assert code == 2 and expected in err and out == "", target
    assert not (tmp_path / "x.tex").exists() and not (tmp_path.parent / "escape.tex").exists()
    for flag in ("--pdf", "--log"):
        code, _out, err = run(capsys, *render_args(workspace, plan_path, flag, "out/a" + (".pdf" if flag == "--pdf" else ".log")))
        assert code == 2 and "OUTPUT_REQUIRED" in err


def test_the_plan_and_the_offer_can_never_be_overwritten_by_an_output(workspace, capsys):
    plan_path = write_plan(workspace, capsys)
    shutil.copy(plan_path, str(workspace / "plans" / "p.tex"))
    before = (Path(plan_path).read_bytes(), (workspace / "offers" / "backend-intern.json").read_bytes())
    code, _out, err = run(capsys, *render_args(workspace, plan_path, "--out", "plans/p.tex"))
    assert code == 2 and "OUTPUT_EXISTS" in err
    assert before == (Path(plan_path).read_bytes(), (workspace / "offers" / "backend-intern.json").read_bytes())
    code, _out, err = run(capsys, "assemble", "--plan", plan_path, "--offer", str(workspace / "offers" / "backend-intern.json"),
                          "--root", str(workspace), "--out", "plans/p.json")
    assert code == 2 and "OUTPUT_IS_AN_INPUT" in err


def test_a_symbolic_link_cannot_lead_the_output_out_of_the_workspace(workspace, capsys, tmp_path):
    plan_path = write_plan(workspace, capsys)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(str(outside), str(workspace / "out" / "link"), target_is_directory=True)
        os.symlink(str(outside / "target.tex"), str(workspace / "out" / "dangling.tex"))
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links cannot be created here")
    for target in ("out/link/x.tex", "out/dangling.tex"):
        code, _out, err = run(capsys, *render_args(workspace, plan_path, "--out", target))
        assert code == 2 and ("OUTPUT_OUTSIDE_WORKSPACE" in err or "OUTPUT_EXISTS" in err), target
    assert list(outside.iterdir()) == []


def test_a_dangling_symbolic_link_inside_the_workspace_is_not_written_through(workspace, capsys):
    """M8-A: `Path.resolve()` follows a dangling link on POSIX, so the guard must also look at the path as written."""
    plan_path = write_plan(workspace, capsys)
    try:
        os.symlink(str(workspace / "out" / "nowhere.tex"), str(workspace / "out" / "alias.tex"))
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links cannot be created here")
    before = tree_hash(workspace)
    code, _out, err = run(capsys, *render_args(workspace, plan_path, "--out", "out/alias.tex"))
    assert code == 2 and "OUTPUT_EXISTS" in err and not (workspace / "out" / "nowhere.tex").exists()
    assert tree_hash(workspace) == before


def test_an_altered_or_obsolete_plan_stops_the_command_and_names_the_layer(workspace, capsys):
    plan_path = write_plan(workspace, capsys)
    edited = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    edited["selected"]["bullets"][0]["gain"] = 99
    (workspace / "plans" / "edited.json").write_text(json.dumps(edited), encoding="utf-8")
    before = tree_hash(workspace)
    code, out, err = run(capsys, *render_args(workspace, str(workspace / "plans" / "edited.json"), "--out", "out/x.tex"))
    assert code == 1 and out == "" and "ASSEMBLY_PLAN_FINGERPRINT" in err and "assemble:" in err
    (workspace / "facts.md").write_text((workspace / "facts.md").read_text(encoding="utf-8") + "\n", encoding="utf-8")
    before = tree_hash(workspace)
    code, out, err = run(capsys, *render_args(workspace, plan_path, "--out", "out/x.tex"))
    assert code == 1 and "ASSEMBLY_SOURCE_MISMATCH" in err and tree_hash(workspace) == before
    assert not (workspace / "out" / "x.tex").exists()


def test_an_unreadable_or_malformed_plan_file(workspace, capsys, tmp_path):
    code, _out, err = run(capsys, *render_args(workspace, str(tmp_path / "missing.json")))
    assert code == 2 and "ASSEMBLY_PLAN_FILE_UNREADABLE" in err
    for name, data in (("notjson.json", b"{"), ("dup.json", b'{"a": 1, "a": 2}'), ("nan.json", b"NaN"), ("bin.json", b"\xff\xfe")):
        (workspace / "plans" / name).write_bytes(data)
        code, _out, err = run(capsys, *render_args(workspace, str(workspace / "plans" / name)))
        assert code == 1 and "ASSEMBLY_PLAN_" in err, name
    (workspace / "plans" / "list.json").write_text("[]", encoding="utf-8")
    code, _out, err = run(capsys, *render_args(workspace, str(workspace / "plans" / "list.json")))
    assert code == 1 and "ASSEMBLY_PLAN_NOT_OBJECT" in err


def test_an_invalid_input_stops_render_at_the_stage_before_the_plan_is_read(workspace, capsys):
    plan_path = write_plan(workspace, capsys)
    bad = (EXAMPLE_DIR / "content" / "invalid" / "unproven-heading.json").read_text(encoding="utf-8")
    (workspace / "content" / "resume.json").write_text(bad, encoding="utf-8")
    code, out, err = run(capsys, *render_args(workspace, plan_path, "--out", "out/x.tex"))
    assert code == 1 and out == "" and "content:" in err and "CONTENT_UNSUPPORTED_HEADING" in err


def test_the_diagnostics_never_repeat_the_private_text(workspace, capsys):
    content_path = workspace / "content" / "resume.json"
    document = json.loads(content_path.read_text(encoding="utf-8"))
    document["blocks"][0]["bullets"][0]["text"]["en"] = "Built \u2192 " + SECRET
    document["blocks"][0]["bullets"][0]["text"]["fr"] = "Construit \u2192 " + SECRET
    content_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    plan_path = write_plan(workspace, capsys)
    code, out, err = run(capsys, *render_args(workspace, plan_path, "--out", "out/x.tex"))
    assert code == 1 and "RENDER_UNSUPPORTED_CHARACTER" in err and "bullet:junior-dev.01" in err
    assert SECRET not in out + err and not (workspace / "out" / "x.tex").exists()


def test_pdf_requested_without_a_compiler_writes_the_tex_and_exits_four(workspace, capsys, monkeypatch):
    plan_path = write_plan(workspace, capsys)
    monkeypatch.setattr(pdf, "find_pdflatex", lambda: None)
    code, out, err = run(capsys, *render_args(workspace, plan_path, "--out", "out/r.tex", "--pdf", "out/r.pdf"))
    report = json.loads(out)
    assert code == 4 and "PDF_UNAVAILABLE" in err and report["pdf"]["status"] == "UNAVAILABLE"
    assert report["pdf_compilation_validated"] is False and (workspace / "out" / "r.tex").exists() and not (workspace / "out" / "r.pdf").exists()


def test_a_failed_compilation_exits_five_keeps_the_tex_and_hides_the_log_unless_asked(workspace, capsys, fake):
    plan_path = write_plan(workspace, capsys)
    fake("error")
    code, out, err = run(capsys, *render_args(workspace, plan_path, "--out", "out/r.tex", "--pdf", "out/r.pdf"))
    assert code == 5 and "PDF_COMPILE_FAILED" in err and json.loads(out)["pdf"]["status"] == "FAILED"
    assert SECRET not in out + err and (workspace / "out" / "r.tex").exists() and not (workspace / "out" / "r.pdf").exists()
    code, out, err = run(capsys, *render_args(workspace, plan_path, "--out", "out/s.tex", "--pdf", "out/s.pdf", "--log", "out/s.log"))
    report = json.loads(out)
    assert code == 5 and report["pdf"]["log"] == {"out": "out/s.log", "may_contain_resume_text": True}
    assert SECRET in (workspace / "out" / "s.log").read_text(encoding="utf-8") and SECRET not in out + err


def test_a_simulated_successful_compilation_reports_pages_against_the_target(workspace, capsys, fake):
    plan_path = write_plan(workspace, capsys)
    fake("ok")
    code, out, _err = run(capsys, *render_args(workspace, plan_path, "--out", "out/r.tex", "--pdf", "out/r.pdf"))
    report = json.loads(out)
    assert code == 0 and report["pdf"]["pages"] == 2 and report["pdf"]["byte_reproducible"] is False
    assert report["layout"] == {"page_target": 1, "pages": 2, "page_verdict": "TARGET_EXCEEDED"}
    assert (workspace / "out" / "r.pdf").read_bytes() == GOOD_PDF
    assert (workspace / "out" / "r.tex").read_bytes() == (workspace / "out" / "r.tex").read_bytes()


@needs_pdflatex
def test_the_real_pipeline_writes_a_tex_and_a_pdf(workspace, capsys):
    plan_path = write_plan(workspace, capsys)
    code, out, err = run(capsys, *render_args(workspace, plan_path, "--out", "out/r.tex", "--pdf", "out/r.pdf"))
    report = json.loads(out)
    assert code == 0 and report["pdf"]["status"] == "COMPILED" and report["pdf_compilation_validated"] is True
    assert (workspace / "out" / "r.pdf").read_bytes().startswith(b"%PDF-") and report["layout"]["pages"] == 1
    assert report["layout"]["page_verdict"] == "TARGET_MET" and not (workspace / "out" / "resume.log").exists()


def test_latex_check_reports_availability(capsys, monkeypatch):
    monkeypatch.setattr(pdf, "find_pdflatex", lambda: None)
    code, out, _err = run(capsys, "latex", "check")
    assert code == 1 and json.loads(out)["pdflatex"] == "ABSENT" and json.loads(out)["optional_dependency"] is True


# --- invariants over random worlds (fixed seed) ----------------------------------------------------------------------------------

def test_random_worlds_assemble_and_render_only_what_is_proven_and_escape_everything():
    rng = random.Random(20261103)
    pieces = ["Python", "tests", "100%", "R&D", "a_b", "$5", "{x}", "#1", "x~y", "a^b", "[z]", "--", "''", "é", "–", "**b**", "_i_"]
    rendered = 0
    for _ in range(80):
        document = content_doc()
        document["blocks"][0]["bullets"] = [
            bullet("b.%d" % n, " ".join(rng.sample(pieces, 4)), " ".join(rng.sample(pieces, 4)), [rng.choice(["f.py", "f.test", "f.k8s", "f.lead"])],
                   ["Python"], ["backend"]) for n in range(rng.randint(1, 5))]
        try:
            cont = contentmod.check_data(document).content
            if cont is None:
                continue
            plan, _m = planmod.build_plan(make_offer("Requirements:\n- Python\n"), tax(), make_profile(), factbase(), cont, None, "en")
            model = assemble.assemble(plan, make_offer("Requirements:\n- Python\n"), tax(), make_profile(), factbase(), cont)
        except (planmod.PlanError, assemble.AssemblyError):
            continue
        text = latex.render(model)
        rendered += 1
        assert commands_of(text) <= ALLOWED_COMMANDS
        assert latex.render(model) == text
        proven = {b["id"] for blk in cont.to_model()["blocks"] for b in blk["bullets"] if set(b["supports"]) <= {"f.py", "f.test"}}
        printed = {b["id"] for s in model["sections"] for blk in s["blocks"] for b in blk["bullets"]}
        assert printed <= proven and printed == {e["id"] for e in plan["selected"]["bullets"]}
    assert rendered > 40
