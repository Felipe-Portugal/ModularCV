"""The /cv-panel skill keeps its contract: seven readers, review only, facts first."""
from pathlib import Path
import re

SKILL = Path(__file__).resolve().parents[1] / "skills" / "cv-panel"


def text(name):
    return (SKILL / name).read_text(encoding="utf-8")


def test_frontmatter_names_the_skill_and_credits_the_original():
    head = re.match(r"---\n(.*?)\n---\n", text("SKILL.md"), re.S).group(1)
    assert re.search(r"^name: cv-panel$", head, re.M)
    assert "description:" in head and "license: MIT" in head and "Alex Chen" in head


def test_the_seven_readers_are_present():
    body = text("SKILL.md")
    for reader in ("Filtre automatique", "Recruteur RH", "Gestionnaire technique",
                   "Conseiller en stage de l'ÉTS", "Candidat concurrent", "Coéquipier",
                   "Vérificateur de faits"):
        assert reader in body, reader


def test_the_skill_reviews_and_never_rewrites_or_invents():
    body = text("SKILL.md")
    assert "ne réécris pas" in body and "facts.md" in body
    assert "Ne produis pas de CV réécrit" in body
    assert "jamais sans confirmation" in body


def test_the_ets_norms_are_complete():
    norms = text("normes-ets.md")
    for item in ("Connaissances particulières", "Projets d'études", "une page", "3 ou 4 cm",
                 "Objet :", "p.j. Curriculum vitae", "infinitif"):
        assert item in norms, item


def test_the_original_license_notice_is_kept():
    notice = text("NOTICE.md")
    assert "Alex Chen" in notice and "MIT License" in notice
    assert "Permission is hereby granted" in notice
