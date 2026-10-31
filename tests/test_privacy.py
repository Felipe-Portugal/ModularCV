# privacy-scan: ignore-file  (this test file holds deliberate fake samples)
"""The privacy scan finds personal data and ignores harmless placeholders."""
import subprocess

from modularcv import privacy

GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@users.noreply.github.com",
       "-c", "commit.gpgsign=false"]


def kinds(text, deny=()):
    return {kind for _n, kind, _v in privacy.scan_text(text, deny)}


def test_personal_identifiers_are_detected():
    assert "email" in kinds("write to jane.doe@university.ca please")
    assert "phone" in kinds("call (514) 555-0100 tomorrow")
    assert "phone" in kinds("514-555-0100")
    assert "sin" in kinds("SIN 123 456 789")
    assert "user_path" in kinds(r"open C:\Users\jdoe\Documents\cv.tex")
    assert "user_path" in kinds("see /home/jdoe/cv")
    assert "profile_url" in kinds("https://www.linkedin.com/in/jane-doe-1a2b3c")
    assert "private_key" in kinds("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert "token" in kinds("token ghp_abcdefghijklmnopqrstuvwxyz0123456789")


def test_harmless_placeholders_are_ignored():
    assert kinds("contact: someone@example.com, a@b.example.invalid, 123+x@users.noreply.github.com") == set()
    assert kinds(r"use C:\Users\<user>\Documents or /home/user/cv or /Users/name/x") == set()
    assert kinds("version 1.2.3 and year 2026 and sha 0123456789abcdef") == set()


def test_deny_terms_are_matched_case_insensitively():
    assert "deny_term" in kinds("My name is JANE DOE", deny=["jane doe"])
    assert kinds("nothing here", deny=["jane doe"]) == set()


def test_a_tree_scan_reports_files_and_paths(tmp_path):
    (tmp_path / "ok.md").write_text("nothing private\n", encoding="utf-8")
    (tmp_path / "bad.md").write_text("mail me: jane.doe@university.ca\n", encoding="utf-8")
    (tmp_path / "jane-doe-notes.md").write_text("clean\n", encoding="utf-8")
    found = privacy.scan(tmp_path, deny=["jane-doe"])
    assert ("bad.md", 1, "email", "jane.doe@university.ca") in found
    assert any(kind == "deny_term_in_path" for _p, _n, kind, _v in found)
    assert not any(p == "ok.md" for p, *_ in found)


def test_gitignored_files_are_not_scanned(tmp_path):
    subprocess.run(GIT + ["init", "-q"], cwd=str(tmp_path), check=True)
    (tmp_path / ".gitignore").write_text("private/\n", encoding="utf-8")
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "facts.md").write_text("jane.doe@university.ca\n", encoding="utf-8")
    assert privacy.scan(tmp_path) == []


def test_history_scan_flags_a_personal_commit_email(tmp_path):
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=jane.doe@university.ca",
                    "-c", "commit.gpgsign=false", "init", "-q"], cwd=str(tmp_path), check=True)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=jane.doe@university.ca",
                    "-c", "commit.gpgsign=false", "commit", "-q", "-m", "m"],
                   cwd=str(tmp_path), check=True)
    assert any(kind == "commit_email" for _p, _n, kind, _v in privacy.scan(tmp_path, history=True))


def test_history_scan_accepts_a_noreply_email_even_with_a_matching_deny_term(tmp_path):
    identity = ["-c", "user.name=ModularCV", "-c", "user.email=1234+handle@users.noreply.github.com",
                "-c", "commit.gpgsign=false"]
    subprocess.run(["git", *identity, "init", "-q"], cwd=str(tmp_path), check=True)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", *identity, "commit", "-q", "-m", "m"], cwd=str(tmp_path), check=True)
    assert privacy.scan(tmp_path, deny=["handle"], history=True) == []
    assert any(kind == "deny_term" for _p, _n, kind, _v in
               privacy.scan(tmp_path, deny=["modularcv"], history=True))


def test_the_command_exit_code_reflects_findings(tmp_path, capsys):
    (tmp_path / "a.md").write_text("clean\n", encoding="utf-8")
    assert privacy.main(["--root", str(tmp_path)]) == 0
    (tmp_path / "a.md").write_text("jane.doe@university.ca\n", encoding="utf-8")
    assert privacy.main(["--root", str(tmp_path)]) == 1
