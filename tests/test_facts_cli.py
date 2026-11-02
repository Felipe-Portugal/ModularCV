import json
import subprocess
import sys
from pathlib import Path

from modularcv import __main__ as cli
from modularcv import facts

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "examples" / "facts.v1.example.md"
VALID = "<!-- modularcv: FactBase-v1 -->\n## S {#s}\n- [a.one] CONFIRMED: Text one.\n- [a.two] DERIVED: Text two.\n"


def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_check_valid_file_exits_0_and_prints_both_fingerprints(capsys):
    code, out, err = run(capsys, "facts", "check", str(EXAMPLE))
    report = json.loads(out)
    expected = facts.parse_file(EXAMPLE)
    assert code == 0 and err == ""
    assert report["status"] == "OK" and report["errors"] == []
    assert report["facts_source_sha256"] == expected.facts_source_sha256
    assert report["factbase_sha256"] == expected.factbase_sha256
    assert report["fact_count"] == 8 and report["publishable"] == 5
    assert report["counts"] == {"CONFIRMED": 5, "DERIVED": 1, "NOT_CONFIRMED": 1, "WITHDRAWN": 1}


def test_check_invalid_file_exits_1_with_codes_and_lines(tmp_path, capsys):
    path = tmp_path / "bad.md"
    path.write_text(VALID + "stray prose\n- [a.one] CONFIRMED: dup {confirmed_on: 2026-02-30}\n", encoding="utf-8")
    code, out, err = run(capsys, "facts", "check", str(path))
    report = json.loads(out)
    assert code == 1 and report["status"] == "INVALID" and report["factbase_sha256"] is None
    assert [(e["code"], e["line"]) for e in report["errors"]] == [
        ("FACT_UNPARSED_LINE", 5), ("FACT_DUPLICATE_ID", 6), ("FACT_INVALID_DATE", 6)]
    assert report["facts_source_sha256"]
    assert "%s:5: FACT_UNPARSED_LINE" % str(path) in err


def test_check_never_prints_fact_text(tmp_path, capsys):
    path = tmp_path / "facts.md"
    path.write_text(VALID.replace("Text one", "ZZ-PRIVATE-ZZ"), encoding="utf-8")
    code, out, err = run(capsys, "facts", "check", str(path))
    assert code == 0 and "ZZ-PRIVATE-ZZ" not in out + err


def test_missing_file_exits_2(tmp_path, capsys):
    code, out, err = run(capsys, "facts", "check", str(tmp_path / "nope.md"))
    assert code == 2 and out == "" and "FACT_FILE_UNREADABLE" in err


def test_empty_file_and_missing_marker_exit_1(tmp_path, capsys):
    empty = tmp_path / "empty.md"
    empty.write_bytes(b"")
    code, out, _ = run(capsys, "facts", "check", str(empty))
    assert code == 1 and json.loads(out)["errors"][0]["code"] == "FACT_EMPTY_FILE"
    nomarker = tmp_path / "nomarker.md"
    nomarker.write_text("## S\n- [a.one] CONFIRMED: x\n", encoding="utf-8")
    code, out, _ = run(capsys, "facts", "check", str(nomarker))
    assert code == 1 and json.loads(out)["errors"][0]["code"] == "FACT_MARKER_MISSING"


def test_marker_only_file_exits_0_with_a_warning(tmp_path, capsys):
    path = tmp_path / "facts.md"
    path.write_text("<!-- modularcv: FactBase-v1 -->\n", encoding="utf-8")
    code, out, _ = run(capsys, "facts", "check", str(path))
    report = json.loads(out)
    assert code == 0 and report["fact_count"] == 0 and report["warnings"][0]["code"] == "FACT_NO_FACTS"


def test_fingerprint_same_for_lf_and_crlf_copies(tmp_path, capsys):
    lf, crlf = tmp_path / "lf.md", tmp_path / "crlf.md"
    lf.write_bytes(VALID.encode("utf-8"))
    crlf.write_bytes(VALID.replace("\n", "\r\n").encode("utf-8"))
    results = []
    for path in (lf, crlf):
        code, out, _ = run(capsys, "facts", "fingerprint", str(path))
        assert code == 0
        report = json.loads(out)
        results.append((report["facts_source_sha256"], report["factbase_sha256"]))
    assert results[0] == results[1]


def test_fingerprint_only_prints_a_single_hash(capsys):
    code, out, _ = run(capsys, "facts", "fingerprint", str(EXAMPLE), "--only", "factbase")
    assert code == 0 and out == facts.parse_file(EXAMPLE).factbase_sha256 + "\n"
    code, out, _ = run(capsys, "facts", "fingerprint", str(EXAMPLE), "--only", "source")
    assert code == 0 and out == facts.parse_file(EXAMPLE).facts_source_sha256 + "\n"


def test_fingerprint_refuses_an_invalid_file(tmp_path, capsys):
    path = tmp_path / "bad.md"
    path.write_text(VALID + "stray\n", encoding="utf-8")
    code, out, _ = run(capsys, "facts", "fingerprint", str(path), "--only", "factbase")
    assert code == 1 and json.loads(out)["factbase_sha256"] is None


def test_default_file_comes_from_the_workspace_configuration(tmp_path, capsys):
    (tmp_path / "facts.md").write_text(VALID, encoding="utf-8")
    code, out, _ = run(capsys, "facts", "check", "--root", str(tmp_path))
    assert code == 0 and json.loads(out)["file"] == "facts.md"
    (tmp_path / "modularcv.json").write_text(json.dumps({"facts": "data/f.md"}), encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "f.md").write_text(VALID, encoding="utf-8")
    code, out, _ = run(capsys, "facts", "check", "--root", str(tmp_path))
    assert code == 0 and json.loads(out)["file"] == "data/f.md"


def test_bad_configuration_exits_2(tmp_path, capsys):
    (tmp_path / "modularcv.json").write_text("{not json", encoding="utf-8")
    code, out, err = run(capsys, "facts", "check", "--root", str(tmp_path))
    assert code == 2 and json.loads(err)["status"] == "CONFIG_ERROR"


def test_require_confirmation_date_flag(tmp_path, capsys):
    path = tmp_path / "facts.md"
    path.write_text(VALID, encoding="utf-8")
    assert run(capsys, "facts", "check", str(path))[0] == 0
    code, out, _ = run(capsys, "facts", "check", str(path), "--require-confirmation-date")
    assert code == 1 and json.loads(out)["errors"][0]["code"] == "FACT_DATE_REQUIRED"


def test_module_entry_point_in_a_real_process():
    done = subprocess.run([sys.executable, "-m", "modularcv", "facts", "check", str(EXAMPLE)],
                          cwd=str(REPO), capture_output=True, text=True)
    assert done.returncode == 0 and json.loads(done.stdout)["status"] == "OK"
    bad = subprocess.run([sys.executable, "-m", "modularcv", "facts", "check", str(REPO / "README.md")],
                         cwd=str(REPO), capture_output=True, text=True)
    assert bad.returncode == 1 and "FACT_MARKER_MISSING" in bad.stderr


def test_existing_commands_are_unchanged(capsys):
    code, out, _ = run(capsys, "check-packages", str(REPO / "tests"))
    assert code in (0, 1) and "contradictions" in json.loads(out)
