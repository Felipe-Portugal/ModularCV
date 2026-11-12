"""The third-party licence bundle shipped under `legal\\` must stay complete, installable and free of anything but its rights holders' data."""
import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest

from modularcv.privacy import scan_text

DESKTOP = Path(__file__).resolve().parents[2]
BUNDLE = DESKTOP / "THIRD_PARTY_LICENSES.txt"
NOTICES = DESKTOP / "THIRD_PARTY_NOTICES.md"
TEXTS = DESKTOP / "licenses" / "texts"

# Addresses that appear inside verbatim third-party copyright notices (rights holders' own, public in their projects).
# Anything else found in the bundle or in the verbatim texts fails the test.
# Kept as (local part, domain) pairs so that this file does not itself trip the privacy scanner.
_ADDRESS_PARTS = [
    ("timo", "alum.mit.edu"), ("zooko", "zooko.com"), ("marek", "popcount.org"), ("jloup", "gzip.org"),
    ("madler", "alumni.caltech.edu"), ("jeff", "FreeBSD.org"), ("jseward", "acm.org"),
    ("jonasschievink", "gmail.com"), ("tituswormer", "gmail.com"),
]
THIRD_PARTY_ADDRESSES = {local + "@" + domain for local, domain in _ADDRESS_PARTS}


def _generator():
    spec = importlib.util.spec_from_file_location("build_third_party_licenses", DESKTOP / "tools" / "build_third_party_licenses.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _inventory_crates():
    section = NOTICES.read_text(encoding="utf-8").split("## Rust crates compiled into", 1)[1]
    rows = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("| ") and len(cells) >= 4 and re.match(r"^\d", cells[1]):
            rows.append((cells[0], cells[1], cells[2]))
    return rows


def test_bundle_is_declared_in_the_installer_resources():
    conf = json.loads((DESKTOP / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    res = conf["bundle"]["resources"]
    assert res["../THIRD_PARTY_LICENSES.txt"] == "legal/THIRD_PARTY_LICENSES.txt"
    assert res["../THIRD_PARTY_NOTICES.md"] == "legal/THIRD_PARTY_NOTICES.md"
    assert res["../../LICENSE"] == "legal/LICENSE"  # the project licence stays a separate file
    assert BUNDLE.is_file() and BUNDLE.stat().st_size > 100_000


def test_every_inventoried_crate_appears_in_the_bundle():
    bundle = BUNDLE.read_text(encoding="utf-8")
    crates = _inventory_crates()
    assert len(crates) >= 200
    missing = [f"{n} {v}" for n, v, _ in crates if f"{n} {v}" not in bundle]
    assert not missing, missing


def test_mpl_crates_have_source_instructions():
    bundle = BUNDLE.read_text(encoding="utf-8")
    mpl = [(n, v) for n, v, lic in _inventory_crates() if lic == "MPL-2.0"]
    assert len(mpl) == 5
    for n, v in mpl:
        assert f"https://static.crates.io/crates/{n}/{n}-{v}.crate" in bundle
    assert "Mozilla Public License Version 2.0" in bundle


def test_each_verbatim_text_is_reproduced_unchanged_with_its_hash():
    gen = _generator()
    bundle = BUNDLE.read_text(encoding="utf-8")
    listed = re.findall(r"^SHA-256 of text : ([0-9a-f]{64}) \((\S+), LF newlines\)$", bundle, re.M)
    assert len(listed) >= 20
    for digest, name in listed:
        text = gen.read_text(TEXTS / name)
        assert gen.sha(text.encode("utf-8")) == digest, name
        if name != "python-license.rst":  # only some sections of that file are reproduced
            assert text.rstrip("\n") in bundle, name


def test_bundle_holds_no_personal_data_beyond_rights_holders_addresses():
    gen = _generator()
    for path in [BUNDLE, TEXTS / "bzip2-LICENSE.txt", TEXTS / "python-license.rst"]:
        text = path.read_text(encoding="utf-8")
        assert gen.SCAN_MARKER in text[:600]  # the scanner skips these files; this test replaces it for them
        for number, kind, value in scan_text(text):
            assert kind == "email" and value in THIRD_PARTY_ADDRESSES, (path.name, number, kind, value)
    # no other verbatim text may carry the scan marker: a stray marker would hide a finding
    for path in TEXTS.iterdir():
        if path.name not in {"bzip2-LICENSE.txt", "python-license.rst"}:
            assert gen.SCAN_MARKER not in path.read_text(encoding="utf-8")


def test_unresolved_items_are_stated_not_hidden():
    bundle = BUNDLE.read_text(encoding="utf-8")
    assert "PART 5. UNRESOLVED ITEMS" in bundle
    assert "Microsoft Visual C++ runtime" in bundle and "open compliance item" in bundle
    assert "not legal advice" in bundle


@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo is needed to list the compiled crates")
def test_committed_bundle_matches_a_fresh_generation():
    gen = _generator()
    assert gen.build() == BUNDLE.read_text(encoding="utf-8"), "rerun desktop/tools/build_third_party_licenses.py"
