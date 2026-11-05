"""M8-B: every command and option shown in the user documents exists (synthetic check: it only reads `--help`, nothing is run for real)."""
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["README.md", "README.fr.md"] + [
    "docs/" + n
    for n in ("QUICKSTART.md", "QUICKSTART.fr.md", "WORKSPACE.md", "PACKAGE.md", "RENDER.md", "PLAN.md", "CONTENT.md", "IMPORT.md")
]


@lru_cache(maxsize=None)
def help_of(path):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8", COLUMNS="200")
    r = subprocess.run(
        [sys.executable, "-m", "modularcv", *path, "--help"], cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8"
    )
    assert r.returncode == 0, (path, r.stderr)
    return r.stdout


def choices(text):
    m = re.search(r"\{([a-z0-9,-]+)\}", text)
    return set(m.group(1).split(",")) if m else set()


def commands(rel):
    path = ROOT / rel
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        while line.rstrip().endswith("\\") and i + 1 < len(lines):  # shell continuation
            i += 1
            line = line.rstrip()[:-1] + " " + lines[i].strip()
        i += 1
        for m in re.finditer(r"python -m modularcv((?: [^`#|\n]+)?)", line):
            tail = m.group(1).split()
            if tail and tail[0] not in {"...", "…"}:
                yield rel, tail


def split(tail):
    """The subcommand path and the options of a documented command."""
    walked = []
    top = choices(help_of(()))
    for tok in tail:
        if tok.startswith("-") or not re.fullmatch(r"[a-z][a-z-]*", tok):
            break
        known = top if not walked else choices(help_of(tuple(walked)))
        if tok in known:
            walked.append(tok)
        else:
            break
    flags = [t for t in tail if re.fullmatch(r"--[a-z][a-z-]*", t)]
    return tuple(walked), flags


CASES = sorted({(rel, tuple(tail)) for rel in DOCS for _, tail in commands(rel)})


def test_the_documents_show_commands():
    assert len(CASES) > 40  # a parser that finds nothing would pass every other test


@pytest.mark.parametrize("rel,tail", CASES, ids=[f"{r}:{' '.join(t)[:60]}" for r, t in CASES])
def test_a_documented_command_and_its_options_exist(rel, tail):
    path, flags = split(list(tail))
    if tail and re.fullmatch(r"[a-z][a-z-]*", tail[0]):
        assert path, f"{rel}: unknown command {tail[0]!r}"
    text = help_of(path)
    for flag in flags:
        assert flag in text, f"{rel}: option {flag} is not an option of `{' '.join(path)}`"
