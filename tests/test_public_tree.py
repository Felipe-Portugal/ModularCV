"""M8-B: the public distribution is coherent with itself (synthetic checks on the files of the tree, no private data).

The same tests run in the private working tree (where PUBLIC_EXCLUDE.txt lists what is left out of the public snapshot) and in the public
snapshot or a source archive (where that list is absent and the excluded files are not there).
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"build", "dist", "node_modules", "__pycache__"}


def excluded():
    f = ROOT / "PUBLIC_EXCLUDE.txt"
    if not f.exists():
        return set()
    return {
        line.strip()
        for line in f.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def markdown_files():
    skip = excluded()
    for p in sorted(ROOT.rglob("*.md")):
        rel = p.relative_to(ROOT)
        if any(part.startswith(".") or part in SKIP_DIRS or part.endswith(".egg-info") for part in rel.parts):
            continue
        if rel.as_posix() in skip:
            continue
        yield p


def links(path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"```.*?```", "", text, flags=re.S)  # a link shown inside a code block is an example
    text = re.sub(r"`[^`\n]*`", "", text)
    for m in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", text):
        target = m.group(1)
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
            continue
        yield target.split("#", 1)[0]


def test_the_exclusion_list_is_well_formed():
    skip = excluded()
    if not skip:
        pytest.skip("PUBLIC_EXCLUDE.txt is not part of this distribution")
    assert "skills/cv-panel/normes-ets.md" in skip
    assert "PROJECT_STATE.md" in skip and "PUBLIC_EXCLUDE.txt" in skip
    for rel in skip:
        assert not rel.startswith(("/", "..")) and "\\" not in rel and ".." not in rel.split("/"), rel


def test_every_relative_link_of_a_public_document_resolves_to_a_public_file():
    skip = excluded()
    broken = []
    for md in markdown_files():
        for target in links(md):
            if not target:
                continue
            resolved = (md.parent / target).resolve()
            try:
                rel = resolved.relative_to(ROOT).as_posix()
            except ValueError:
                broken.append((md.name, target, "outside the tree"))
                continue
            if not resolved.exists():
                broken.append((md.relative_to(ROOT).as_posix(), target, "missing"))
            elif rel in skip:
                broken.append((md.relative_to(ROOT).as_posix(), target, "not distributed"))
    assert not broken, broken


def test_no_public_document_depends_on_the_school_summary_file():
    """The summary of the school's documents is not distributed: no public file may need it."""
    for rel in ("modularcv", "templates", "schemas", "examples"):
        for p in (ROOT / rel).rglob("*"):
            if p.is_file() and p.suffix in {".py", ".json", ".md"}:
                assert "normes-ets" not in p.read_text(encoding="utf-8", errors="ignore"), p
    skill = (ROOT / "skills" / "cv-panel" / "SKILL.md").read_text(encoding="utf-8")
    assert "s'il existe" in skill or "s'il est présent" in skill  # the file is optional and supplied by the user


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_python_policy_is_the_same_everywhere():
    """Requires-Python, classifiers and the documents all announce Python 3.12 to 3.14, and nothing else."""
    py = read("pyproject.toml")
    assert re.search(r'^requires-python = ">=3\.12,<3\.15"$', py, re.M)
    announced = set(re.findall(r'"Programming Language :: Python :: (3\.\d+)"', py))
    assert announced == {"3.12", "3.13", "3.14"}
    for rel in ("README.md", "README.fr.md", "docs/QUICKSTART.md", "docs/QUICKSTART.fr.md"):
        text = read(rel)
        assert "3.12" in text and "3.14" in text, rel
        assert ">=3.12,<3.15" in text.replace(" ", "").replace(" ", "") or ">= 3.12" in text, rel
        assert not re.search(r"Python 3\.9\+|>= ?3\.9\b", text), rel


def test_the_readmes_state_the_limits_they_must_not_hide():
    for rel, needles in (
        ("README.md", ("not tested", "not authenticated", "not a cryptographic proof", "--compile", "TeX Live", "certified")),
        ("README.fr.md", ("non testé", "pas authentifié", "pas une preuve", "--compile", "TeX Live", "certifié")),
    ):
        text = read(rel)
        for needle in needles:
            assert needle.lower() in text.lower() or (needle == "certified" and "nothing is certified" in text), (rel, needle)
