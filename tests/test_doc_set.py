"""DOC-1: the public document set is coherent (synthetic checks on the files of the tree, no private data).

Release status, English/French parity of the entry points, the presence of the community files, and the absence of personal paths.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def fenced(rel, language):
    return re.findall(r"```%s\n(.*?)```" % language, read(rel), flags=re.S)


def link_targets(rel):
    text = re.sub(r"```.*?```", "", read(rel), flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    out = set()
    for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", text):
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
            continue
        out.add(target.split("#", 1)[0].replace(".fr.md", ".md"))
    return out


COMMUNITY = ("CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "LICENSE")
GUIDES = ("docs/CLI.md", "docs/INSTALL_WINDOWS.md", "docs/INSTALL_WINDOWS.fr.md")


@pytest.mark.parametrize("rel", COMMUNITY + GUIDES)
def test_the_new_documents_exist_and_are_not_empty(rel):
    assert len(read(rel).strip()) > 200, rel


def test_the_source_archive_carries_the_community_files():
    manifest = read("MANIFEST.in")
    for name in ("CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md"):
        assert name in manifest, name


def test_the_entry_documents_stay_true_before_and_after_a_release():
    """State-independent wording: the documents say where releases are listed and that there is no package index, never that none exists."""
    for rel in ("README.md", "README.fr.md", "SECURITY.md", "CONTRIBUTING.md", "docs/INSTALL_WINDOWS.md", "docs/INSTALL_WINDOWS.fr.md"):
        text = read(rel)
        assert not re.search(r"/releases/(tag|download|latest)", text), rel  # no link to one release: the Releases page is named, not linked
        assert not re.search(r"pypi\.org/project/modularcv|pip install modularcv\b|pip install --upgrade modularcv", text, re.I), rel
        assert not re.search(r"release candidate|version candidate|not (yet )?released|aucune version|no versioned release", text, re.I), rel
    assert "Releases page" in read("README.md") and "not on PyPI" in read("README.md")
    assert "page Releases" in read("README.fr.md") and "pas sur PyPI" in read("README.fr.md")
    assert "Releases page" in read("SECURITY.md") and "Releases page" in read("CONTRIBUTING.md")
    assert "0.2.0" in read("pyproject.toml")  # the version is unchanged


def test_the_changelog_matches_the_release_state():
    """From the release on: `0.2.0` is the first release and carries the real publication date."""
    changelog = read("CHANGELOG.md")
    assert "ModularCV 0.2.0 is the first release" in changelog
    assert "not a public release" in changelog  # the first commit's `0.1.0` is an internal state, never presented as a release
    heading = re.search(r"^## \[0\.2\.0\][^\n]*$", changelog, re.M)
    assert heading and re.fullmatch(r"## \[0\.2\.0\] - \d{4}-\d{2}-\d{2}", heading.group(0))
    assert not re.search(r"not released|release candidate|No version of ModularCV has been released", changelog)
    assert not re.search(r"/releases/(tag|download|latest)", changelog)


def test_the_security_policy_uses_private_reporting_and_promises_nothing_it_cannot_keep():
    text = read("SECURITY.md")
    assert "Report a vulnerability" in text and "Security** tab" in text
    assert "No response time, fix time or outcome is promised" in text
    assert "No e-mail address is offered" in text
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}", text)  # no invented address
    assert "docs/PACKAGE.md" in text and "not authenticated" in text and "not a sandbox" in text  # the known limits are named


def test_the_contributing_guide_states_the_project_principles():
    text = read("CONTRIBUTING.md")
    for needle in ("3.12", "3.14", "python -m pytest", "python -m modularcv privacy", "Fail closed", "No invention of facts",
                   "without a remote AI service", "cover letters", "SECURITY.md", "no-reply"):
        assert needle in text, needle


def test_the_changelog_only_announces_what_the_command_line_has():
    """Every command named in the changelog exists in the command reference (which is itself checked against `--help`)."""
    changelog = read("CHANGELOG.md")
    reference = read("docs/CLI.md")
    for command in re.findall(r"`((?:facts|profile|content|offer|taxonomy|package|snapshot|latex) [a-z]+)`", changelog):
        assert "python -m modularcv %s`" % command in reference, command
    for command in ("matrix", "plan", "assemble", "render", "provenance", "check-packages", "privacy"):
        assert "python -m modularcv %s`" % command in reference, command


def test_the_windows_guides_have_the_same_commands_in_both_languages():
    def commands(rel):
        lines = []
        for block in fenced(rel, "powershell"):
            for line in block.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("git commit -m"):
                    lines.append(line)
        return lines

    assert commands("docs/INSTALL_WINDOWS.md") == commands("docs/INSTALL_WINDOWS.fr.md")
    assert len(commands("docs/INSTALL_WINDOWS.md")) > 15

    def codes(rel):
        return sorted(set(re.findall(r"`([A-Z][A-Z_]{5,})`", read(rel))))

    assert codes("docs/INSTALL_WINDOWS.md") == codes("docs/INSTALL_WINDOWS.fr.md")


def test_the_readmes_link_the_same_documents():
    english, french = link_targets("README.md"), link_targets("README.fr.md")
    assert english == french, (english ^ french)
    for needed in ("CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "docs/CLI.md", "docs/INSTALL_WINDOWS.md"):
        assert needed in english, needed


def test_the_readmes_keep_the_scope_and_the_release_status():
    for rel, needles in (
        ("README.md", ("generates **CVs**", "does not generate or rewrite cover letters", "Releases page", "not on PyPI")),
        ("README.fr.md", ("génère des **CV**", "ne génère ni ne réécrit de lettres", "page Releases", "pas sur PyPI")),
    ):
        text = read(rel)
        for needle in needles:
            assert needle in text, (rel, needle)


def test_the_new_documents_hold_no_local_or_personal_path():
    pattern = re.compile(r"[A-Za-z]:\\Users\\(?!<)[^\\\s]+|/home/(?!user\b)[a-z][^/\s]*/|/Users/(?!name\b)[A-Za-z][^/\s]*/")
    for rel in COMMUNITY[:3] + GUIDES + ("docs/QUICKSTART.md", "docs/QUICKSTART.fr.md"):
        assert not pattern.search(read(rel)), rel
