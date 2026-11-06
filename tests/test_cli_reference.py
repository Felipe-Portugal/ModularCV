"""DOC-1: docs/CLI.md lists exactly the commands, arguments and options of the real command line.

The only thing run is `python -m modularcv ... --help` (nothing is executed for real, nothing is read from a workspace). The tests fail if a
command, an argument or an option appears in the reference without existing, or exists without appearing in it. The prose of the reference is
not checked: for wording and defaults, `--help` is the authority.
"""
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "CLI.md"


def help_of(path):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8", COLUMNS="200")
    r = subprocess.run(
        [sys.executable, "-m", "modularcv", *path, "--help"], cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8"
    )
    assert r.returncode == 0, (path, r.stderr)
    return r.stdout


def subcommands(text):
    """The sub-commands announced by the usage line, ignoring the choices of an option such as `[--only {a,b}]`."""
    usage = re.split(r"\n\s*\n", text.split("usage:", 1)[1])[0]
    usage = re.sub(r"\s+", " ", usage)
    while True:
        stripped = re.sub(r"\[[^\[\]]*\]", "", usage)
        if stripped == usage:
            break
        usage = stripped
    m = re.search(r"\{([a-z0-9,-]+)\}", usage)
    return m.group(1).split(",") if m else []


def options(text):
    return set(re.findall(r"^  (?:-[A-Za-z], )?(--[a-z][a-z0-9-]*)", text, re.M)) - {"--help"}


def arguments(text):
    m = re.search(r"^positional arguments:\n((?:  .*\n?)+)", text, re.M)
    return set(re.findall(r"^  ([A-Za-z_][A-Za-z_0-9]*)\b", m.group(1), re.M)) if m else set()


def walk():
    """Every command path of the command line, with its help text."""
    found = {}
    frontier = [()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        while frontier:
            texts = list(pool.map(help_of, frontier))
            following = []
            for path, text in zip(frontier, texts):
                found[path] = text
                following.extend(path + (name,) for name in subcommands(text))
            frontier = following
    return found


TREE = walk()
LEAVES = sorted(path for path in TREE if path and not subcommands(TREE[path]))


def sections():
    """The reference, cut at its level-3 headings (one per command)."""
    text = DOC.read_text(encoding="utf-8")
    parts = re.split(r"^### ", text, flags=re.M)[1:]
    out = {}
    for part in parts:
        title, _, body = part.partition("\n")
        m = re.fullmatch(r"`python -m modularcv ([a-z][a-z0-9 -]*)`", title.strip())
        assert m, f"unexpected heading in CLI.md: {title!r}"
        path = tuple(m.group(1).split())
        assert path not in out, f"duplicate section: {path}"
        out[path] = body
    return out


SECTIONS = sections()


def test_the_command_tree_was_found():
    assert len(LEAVES) >= 20  # a parser that finds nothing would pass every other test here
    assert ("package", "approve") in LEAVES and ("render",) in LEAVES and ("latex", "check") in LEAVES


def test_every_documented_command_exists():
    unknown = [" ".join(p) for p in SECTIONS if p not in LEAVES]
    assert not unknown, f"documented but not a command (or not a final command): {unknown}"


def test_every_command_is_documented():
    missing = [" ".join(p) for p in LEAVES if p not in SECTIONS]
    assert not missing, f"commands missing from docs/CLI.md: {missing}"


@pytest.mark.parametrize("path", LEAVES, ids=[" ".join(p) for p in LEAVES])
def test_options_and_arguments_of_a_command_match_the_help(path):
    body = SECTIONS.get(path)
    assert body is not None, f"{' '.join(path)} is not documented"
    documented_options = set(re.findall(r"^- `(--[a-z][a-z0-9-]*)`", body, re.M))
    documented_arguments = set(re.findall(r"^Arguments?: `([A-Za-z_][A-Za-z_0-9]*)`", body, re.M))
    real = TREE[path]
    assert documented_options == options(real), (path, "options", documented_options ^ options(real))
    assert documented_arguments == arguments(real), (path, "arguments", documented_arguments ^ arguments(real))


def test_the_group_names_are_the_real_ones():
    """The overview table names only existing top-level commands."""
    text = DOC.read_text(encoding="utf-8")
    top = set(subcommands(TREE[()]))
    table = text.split("## Provenance and audit", 1)[0]
    for name in re.findall(r"`([a-z][a-z-]*)(?: [a-z …-]*)?`", table):
        if name in {"python", "modularcv"}:
            continue
        assert name in top, name
