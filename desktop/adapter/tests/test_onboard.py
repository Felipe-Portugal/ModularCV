"""Onboarding operations of the Desktop adapter: workspace_init, cv_source_read, cv_parse, cv_apply.

Fictional data only. Every write is checked through the real engine (`read`, `facts check`).
"""
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "desktop" / "adapter" / "mcv_adapter.py"
sys.path.insert(0, str(REPO / "desktop" / "adapter"))

import mcv_onboard  # noqa: E402

CV = """Camille Exemple
Développeuse logicielle
Exempleville, QC | camille@example.com | +1 555 010 0199 | https://example.org/camille

PROFIL
Développeuse attachée à la qualité logicielle.

EXPÉRIENCE PROFESSIONNELLE
Développeuse backend — Exemple Logiciels inc. (fictive)
Exempleville, QC | Janvier 2023 – Présent
• Développement d'API REST en Python pour un outil interne utilisé
  par trois équipes.
• Rédaction de tests automatisés avec pytest.
- Participation aux revues de code.

Stagiaire en développement
Société Fictive ltée, Exempleville
Mai 2022 - Août 2022
• Automatisation de rapports avec SQL.

FORMATION
Baccalauréat en génie logiciel
Université Exemple, Exempleville
2019 – 2023

COMPÉTENCES
Langages : Python, SQL, JavaScript (React, Node.js)
Outils : Git, Docker

LANGUES
Français (langue maternelle), Anglais (avancé)

CENTRES D'INTÉRÊT
Escalade, lecture
"""


def call(root, op, **payload):
    request = dict(payload, op=op, root=str(root))
    run = subprocess.run([sys.executable, "-I", str(ADAPTER)], input=json.dumps(request).encode("utf-8"),
                         capture_output=True, cwd=str(REPO))
    assert run.returncode == 0, run.stderr.decode("utf-8", "replace")
    return json.loads(run.stdout.decode("utf-8"))


@pytest.fixture
def profile_dir(tmp_path):
    root = tmp_path / "profile"
    root.mkdir()
    assert call(root, "workspace_init", display_name="Camille Exemple", language="fr")["ok"] is True
    return root


def reviewed(proposal, confirm=True):
    blocks = [dict(b, confirmed=confirm, bullets=[{"text": t, "confirmed": confirm} for t in b["bullets"]]) for b in proposal["blocks"]]
    skills = [dict(c, items=[{"text": t, "confirmed": confirm} for t in c["items"]]) for c in proposal["skills"]]
    return blocks, skills


# ----------------------------------------------------------------------------------------- workspace_init

def test_init_writes_a_workspace_the_engine_accepts(profile_dir):
    state = call(profile_dir, "read")
    assert state["facts"]["valid"] is True and state["profile"]["valid"] is True and state["content"]["present"] is False
    assert state["profile"]["data"]["identity"]["display_name"] == {"value": "Camille Exemple", "visibility": "public"}
    assert state["profile"]["data"]["languages"] == ["fr"]
    assert {s["id"] for s in state["facts"]["sections"]} == {"experience", "projects", "education", "skills", "other"}
    check = subprocess.run([sys.executable, "-m", "modularcv", "facts", "check", "--root", str(profile_dir)], capture_output=True, cwd=str(REPO))
    assert check.returncode == 0


def test_init_never_touches_an_existing_file(profile_dir):
    before = (profile_dir / "facts.md").read_bytes()
    again = call(profile_dir, "workspace_init", display_name="Someone", language="en")
    assert again["code"] == "OUTPUT_EXISTS"
    assert (profile_dir / "facts.md").read_bytes() == before


@pytest.mark.parametrize("payload", [{"display_name": "", "language": "fr"}, {"display_name": "A", "language": "de"},
                                     {"display_name": "x" * 121, "language": "fr"}, {"language": "fr"}])
def test_init_refuses_bad_input_and_writes_nothing(tmp_path, payload):
    assert call(tmp_path, "workspace_init", **payload)["code"] == "VALIDATION_FAILED"
    assert list(tmp_path.iterdir()) == []


# ----------------------------------------------------------------------------------------- cv_source_read

def docx(paragraphs):
    body = "".join("<w:p>%s<w:r><w:t>%s</w:t></w:r></w:p>" % ("<w:pPr><w:numPr/></w:pPr>" if listed else "", text)
                   for text, listed in paragraphs)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           "<w:body>%s</w:body></w:document>" % body)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_source_reads_text_and_docx(profile_dir, tmp_path):
    (tmp_path / "cv.txt").write_text(CV, encoding="utf-8")
    text = call(profile_dir, "cv_source_read", source=str(tmp_path / "cv.txt"))
    assert text["kind"] == "text" and "Camille Exemple" in text["text"]
    (tmp_path / "cv.docx").write_bytes(docx([("EXPERIENCE", False), ("Junior developer", False), ("Built REST endpoints.", True)]))
    word = call(profile_dir, "cv_source_read", source=str(tmp_path / "cv.docx"))
    assert word["text"].split("\n") == ["EXPERIENCE", "Junior developer", "• Built REST endpoints."]


def test_source_returns_a_pdf_as_bytes_for_the_viewer(profile_dir, tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4\nfictional\n")
    pdf = call(profile_dir, "cv_source_read", source=str(tmp_path / "cv.pdf"))
    assert pdf["kind"] == "pdf" and pdf["base64"] and "text" not in pdf


def test_source_refusals(profile_dir, tmp_path):
    (tmp_path / "cv.exe").write_bytes(b"MZ")
    (tmp_path / "fake.pdf").write_bytes(b"not a pdf")
    (tmp_path / "fake.docx").write_bytes(b"not a zip")
    (tmp_path / "big.pdf").write_bytes(b"%PDF-" + b"0" * mcv_onboard.MAX_PDF_BYTES)
    (tmp_path / "entities.docx").write_bytes(docx([("x", False)]).replace(b"x", b"x"))
    assert call(profile_dir, "cv_source_read", source=str(tmp_path / "cv.exe"))["code"] == "UNSUPPORTED_FILE"
    assert call(profile_dir, "cv_source_read", source=str(tmp_path / "fake.pdf"))["code"] == "UNSUPPORTED_FILE"
    assert call(profile_dir, "cv_source_read", source=str(tmp_path / "fake.docx"))["code"] == "UNSUPPORTED_FILE"
    assert call(profile_dir, "cv_source_read", source=str(tmp_path / "big.pdf"))["code"] == "SOURCE_TOO_LARGE"
    assert call(profile_dir, "cv_source_read", source=str(tmp_path / "absent.txt"))["code"] == "FILE_UNREADABLE"
    assert call(profile_dir, "cv_source_read")["code"] == "VALIDATION_FAILED"


def test_docx_with_entity_declarations_is_refused():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "b">]><d/>')
    with pytest.raises(mcv_onboard.Refusal) as refusal:
        mcv_onboard.docx_text(buffer.getvalue())
    assert refusal.value.code == "UNSUPPORTED_FILE"


# ----------------------------------------------------------------------------------------- cv_parse

def test_parse_splits_a_cv_and_accounts_for_every_line(profile_dir):
    proposal = call(profile_dir, "cv_parse", text=CV)
    assert proposal["language"] == "fr"
    assert proposal["identity"] == {"display_name": "Camille Exemple", "headline": "Développeuse logicielle", "location": "Exempleville, QC",
                                    "email": "camille@example.com", "phone": "+1 555 010 0199", "links": ["https://example.org/camille"]}
    first, second, degree = proposal["blocks"]
    assert (first["kind"], first["title"], first["subtitle"], first["period"], first["place"]) == (
        "experience", "Développeuse backend", "Exemple Logiciels inc. (fictive)", "Janvier 2023 – Présent", "Exempleville, QC")
    assert first["bullets"] == ["Développement d'API REST en Python pour un outil interne utilisé par trois équipes.",
                                "Rédaction de tests automatisés avec pytest.", "Participation aux revues de code."]
    assert (second["title"], second["period"], second["bullets"]) == ("Stagiaire en développement", "Mai 2022 - Août 2022",
                                                                        ["Automatisation de rapports avec SQL."])
    assert (degree["kind"], degree["title"], degree["period"], degree["bullets"]) == ("education", "Baccalauréat en génie logiciel", "2019 – 2023", [])
    assert [(c["title"], c["technical"], c["items"]) for c in proposal["skills"]] == [
        ("Langages", True, ["Python", "SQL", "JavaScript (React, Node.js)"]), ("Outils", True, ["Git", "Docker"]),
        ("LANGUES", False, ["Français (langue maternelle)", "Anglais (avancé)"])]
    assert [u["text"] for u in proposal["unclassified"]] == ["Développeuse attachée à la qualité logicielle.", "Escalade, lecture"]


def test_parse_reads_english_headings_and_writes_nothing(profile_dir):
    before = sorted(p.name for p in profile_dir.iterdir())
    proposal = call(profile_dir, "cv_parse", text="Jordan Example\n\nWORK EXPERIENCE\nJunior developer at Example Company\nMay 2025 to Present\n"
                                                  "* Built REST endpoints in Python.\n\nEDUCATION\nB.Eng. in software engineering\nExample University\n2024 - 2028 (expected)\n\nSKILLS\nPython, Git\n")
    assert proposal["language"] == "en"
    assert [(b["kind"], b["title"], b["subtitle"], b["period"]) for b in proposal["blocks"]] == [
        ("experience", "Junior developer", "Example Company", "May 2025 to Present"),
        ("education", "B.Eng. in software engineering", "Example University", "2024 - 2028 (expected)")]
    assert sorted(p.name for p in profile_dir.iterdir()) == before


def test_parse_without_a_known_heading_proposes_nothing(profile_dir):
    proposal = call(profile_dir, "cv_parse", text="Jordan Example\nSome free text about me.\nAnother line.\n")
    assert proposal["blocks"] == [] and proposal["skills"] == [] and proposal["sections_found"] == []


def test_parse_refuses_an_empty_or_huge_text(profile_dir):
    assert call(profile_dir, "cv_parse", text="  \n ")["code"] == "VALIDATION_FAILED"
    assert call(profile_dir, "cv_parse", text="x" * (mcv_onboard.MAX_TEXT_CHARS + 1))["code"] == "SOURCE_TOO_LARGE"


# ----------------------------------------------------------------------------------------- cv_apply

def test_apply_never_confirms_without_a_date(profile_dir):
    blocks, skills = reviewed(call(profile_dir, "cv_parse", text=CV))
    before = (profile_dir / "facts.md").read_bytes()
    assert call(profile_dir, "cv_apply", language="fr", blocks=blocks, skills=skills)["code"] == "CONFIRMATION_REQUIRED"
    assert call(profile_dir, "cv_apply", language="fr", confirmed_on="yesterday", blocks=blocks, skills=skills)["code"] == "VALIDATION_FAILED"
    assert (profile_dir / "facts.md").read_bytes() == before and not (profile_dir / "content").exists()


def test_apply_writes_facts_and_content_the_engine_accepts(profile_dir):
    blocks, skills = reviewed(call(profile_dir, "cv_parse", text=CV))
    blocks[0]["bullets"][2]["confirmed"] = False
    identity = {"email": {"value": "camille@example.com", "visibility": "public"}, "phone": {"value": "+1 555 010 0199", "visibility": "private"},
                "links": [{"label": "Site", "value": "https://example.org/camille", "visibility": "private"}]}
    done = call(profile_dir, "cv_apply", language="fr", confirmed_on="2026-01-10", blocks=blocks, skills=skills, identity=identity)
    assert done["ok"] is True, done
    assert (done["facts_added"], done["confirmed"], done["parked"], done["blocks_added"], done["bullets_added"], done["skills_added"]) == (14, 13, 1, 3, 3, 7)
    assert done["content_created"] is True and done["identity_updated"] is True

    state = call(profile_dir, "read")
    assert state["facts"]["valid"] and state["profile"]["valid"] and state["content"]["valid"], state
    assert state["content"]["warnings"] == []
    assert state["facts"]["counts"] == {"CONFIRMED": 13, "DERIVED": 0, "NOT_CONFIRMED": 1, "WITHDRAWN": 0}
    by_id = {f["id"]: f for f in state["facts"]["facts"]}
    assert by_id["exp.developpeuse-backend"]["text"] == "Développeuse backend, Exemple Logiciels inc. (fictive), Janvier 2023 – Présent, Exempleville, QC."
    assert by_id["exp.developpeuse-backend.01"]["technologies"] == ["Python"] and by_id["exp.developpeuse-backend.01"]["confirmed_on"] == "2026-01-10"
    assert by_id["exp.developpeuse-backend.03"]["status"] == "NOT_CONFIRMED" and by_id["exp.developpeuse-backend.03"]["confirmed_on"] is None
    assert by_id["skill.francais-langue-maternelle"]["technologies"] == []
    assert state["profile"]["data"]["identity"]["phone"] == {"value": "+1 555 010 0199", "visibility": "private"}

    document = json.loads((profile_dir / "content" / "resume.json").read_text(encoding="utf-8"))
    assert [(b["id"], b["section"], b["order"], len(b["bullets"]), b.get("protected", False)) for b in document["blocks"]] == [
        ("developpeuse-backend", "experience", 1, 2, False), ("stagiaire-en-developpement", "experience", 2, 1, False),
        ("baccalaureat-en-genie-logiciel", "education", 1, 0, True)]
    assert all(b["languages"] == ["fr"] for b in document["blocks"])


def test_apply_keeps_unconfirmed_entries_out_of_the_content(profile_dir):
    blocks, skills = reviewed(call(profile_dir, "cv_parse", text=CV), confirm=False)
    done = call(profile_dir, "cv_apply", language="fr", blocks=blocks, skills=skills)
    assert (done["ok"], done["confirmed"], done["parked"], done["blocks_added"], done["content_created"]) == (True, 0, 14, 0, False)
    assert not (profile_dir / "content").exists()
    state = call(profile_dir, "read")
    assert state["facts"]["valid"] and state["facts"]["counts"]["NOT_CONFIRMED"] == 14 and state["facts"]["counts"]["CONFIRMED"] == 0


def test_apply_appends_and_leaves_existing_entries_unchanged(profile_dir):
    blocks, skills = reviewed(call(profile_dir, "cv_parse", text=CV))
    assert call(profile_dir, "cv_apply", language="fr", confirmed_on="2026-01-10", blocks=blocks, skills=skills)["ok"] is True
    first = json.loads((profile_dir / "content" / "resume.json").read_text(encoding="utf-8"))
    facts_before = call(profile_dir, "read")["facts"]["facts"]
    more = [{"kind": "experience", "title": "Développeuse backend", "subtitle": "Autre Société (fictive)", "period": "2021", "confirmed": True,
             "bullets": [{"text": "Maintenance d'un service en Python.", "confirmed": True}]}]
    done = call(profile_dir, "cv_apply", language="fr", confirmed_on="2026-02", blocks=more, skills=[{"title": "Langages", "items": [{"text": "Python", "confirmed": True}]}])
    assert done["ok"] is True, done
    second = json.loads((profile_dir / "content" / "resume.json").read_text(encoding="utf-8"))
    assert second["blocks"][:3] == first["blocks"] and second["skills"][:3] == first["skills"]
    assert (second["blocks"][3]["id"], second["blocks"][3]["order"], second["blocks"][3]["supports"]) == ("developpeuse-backend-2", 3, ["exp.developpeuse-backend-2"])
    assert second["skills"][3]["id"] == "langages-2" and second["skills"][3]["items"][0]["supports"] == ["skill.python-2"]
    state = call(profile_dir, "read")
    def without_line(items):
        return [{k: v for k, v in f.items() if k != "line"} for f in items]

    kept = [f for f in state["facts"]["facts"] if f["id"] in {x["id"] for x in facts_before}]
    assert state["content"]["valid"] and without_line(kept) == without_line(facts_before)


def test_apply_refusals_write_nothing(profile_dir, tmp_path):
    before = {p.name: p.read_bytes() for p in profile_dir.iterdir() if p.is_file()}
    block = {"kind": "experience", "title": "Développeuse", "bullets": []}
    assert call(profile_dir, "cv_apply", language="en", blocks=[block], skills=[])["code"] == "VALIDATION_FAILED"            # not a profile language
    assert call(profile_dir, "cv_apply", language="fr", blocks=[dict(block, title=" ")], skills=[])["code"] == "VALIDATION_FAILED"
    assert call(profile_dir, "cv_apply", language="fr", blocks=[dict(block, kind="hobby")], skills=[])["code"] == "VALIDATION_FAILED"
    assert call(profile_dir, "cv_apply", language="fr", blocks=[], skills=[])["code"] == "NO_CHANGE"
    assert call(profile_dir, "cv_apply", language="fr", blocks=[], skills=[], identity={"email": {"value": "a@example.com"}})["code"] == "VALIDATION_FAILED"
    assert call(profile_dir, "cv_apply", language="fr", blocks=[dict(block, bullets=[{"text": "x" * 1001}])], skills=[])["code"] == "VALIDATION_FAILED"
    assert {p.name: p.read_bytes() for p in profile_dir.iterdir() if p.is_file()} == before
    assert call(tmp_path, "cv_apply", language="fr", blocks=[block], skills=[])["code"] == "FILE_UNREADABLE"                 # no profile yet


def test_apply_neutralises_characters_the_formats_reserve(profile_dir):
    block = {"kind": "project", "title": "Outil {interne}", "confirmed": True,
             "bullets": [{"text": "Script C:\\outils\\run **non fermé avec {accolades}.", "confirmed": True}]}
    done = call(profile_dir, "cv_apply", language="fr", confirmed_on="2026", blocks=[block], skills=[])
    assert done["ok"] is True, done
    state = call(profile_dir, "read")
    assert state["facts"]["valid"] and state["content"]["valid"]
    texts = [f["text"] for f in state["facts"]["facts"]]
    assert texts == ["Outil (interne).", "Script C:/outils/run non fermé avec (accolades)."]


def test_operations_are_in_the_closed_list():
    import mcv_adapter
    assert set(mcv_onboard.OPERATIONS) == {"workspace_init", "cv_source_read", "cv_parse", "cv_apply"}
    assert set(mcv_onboard.OPERATIONS) <= set(mcv_adapter.OPERATIONS)
