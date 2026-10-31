"""Privacy scan: keep personal data out of a repository that will be public.

    python -m modularcv privacy [--root .] [--deny-file private-terms.txt] [--deny TERM ...]
                                [--history]

Detects, in tracked and untracked (non-ignored) files:
- e-mail addresses (except no-reply and reserved example domains);
- North-American phone numbers and Canadian social insurance numbers;
- absolute user paths (`C:\\Users\\name`, `/home/name`, `/Users/name`);
- personal profile URLs (LinkedIn);
- credentials (private keys, common token prefixes);
- every term of a deny list that you keep OUTSIDE the repository (your name, employers,
  schools...). With `--history`, also commit author and committer e-mails.

Exit code 1 when anything is found. The deny list is read, never stored or printed in
full beyond the matched line, and must not itself be committed.
"""
from argparse import ArgumentParser
import re
import subprocess
import sys
from pathlib import Path

ALLOWED_EMAIL = re.compile(r"(noreply|no-reply)|@(example\.(com|org|net|invalid)|[\w.-]*\.invalid|"
                           r"localhost)$", re.I)
PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
    "phone": re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]?[2-9]\d{2}[ .-]\d{4}(?!\d)"),
    "sin": re.compile(r"(?<!\d)\d{3}[ -]\d{3}[ -]\d{3}(?!\d)"),
    "user_path": re.compile(r"[A-Za-z]:\\+Users\\+[^\\\s\"']+|/home/[^/\s\"']+|/Users/[^/\s\"']+"),
    "profile_url": re.compile(r"linkedin\.com/in/[\w%-]+", re.I),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    # Every alternative needs a long body, so the pattern's own source text never matches itself.
    "token": re.compile(r"\b(?:gh[pos]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                        r"sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{12,})"),
}
PLACEHOLDER_USERS = {"user", "username", "you", "name", "yourname", "<user>"}
IGNORE_MARKER = "privacy-scan: ignore-file"
BINARY_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".ico", ".woff", ".woff2"}


def tracked_files(root: Path) -> list:
    """Files Git would commit: tracked plus untracked and not ignored."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others",
                          "--exclude-standard", "-z"], capture_output=True)
    if out.returncode != 0:
        return [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
    names = [n for n in out.stdout.decode("utf-8", "replace").split("\0") if n]
    return [root / n for n in names if (root / n).is_file()]


def scan_text(text: str, deny=()) -> list:
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                value = match.group(0)
                if kind == "email" and ALLOWED_EMAIL.search(value):
                    continue
                if kind == "user_path":
                    user = re.split(r"[\\/]+", value.rstrip("\\/"))[-1].lower()
                    if user in PLACEHOLDER_USERS or not re.match(r"^[\w.-]+$", user):
                        continue
                findings.append((number, kind, value))
        lowered = line.lower()
        for term in deny:
            if term and term.lower() in lowered:
                findings.append((number, "deny_term", term))
    return findings


def scan(root, deny=(), history: bool = False) -> list:
    root = Path(root)
    results = []
    for path in tracked_files(root):
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        for term in deny:                         # file names too
            if term and term.lower() in rel.lower():
                results.append((rel, 0, "deny_term_in_path", term))
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        if IGNORE_MARKER in text[:600]:           # files that hold deliberate fake samples
            continue
        for number, kind, value in scan_text(text, deny):
            results.append((rel, number, kind, value))
    if history:
        log = subprocess.run(["git", "-C", str(root), "log", "--all", "--format=%ae%n%ce%n%an%n%cn"],
                             capture_output=True)
        for value in sorted(set(log.stdout.decode("utf-8", "replace").split())):
            if "@" in value and not ALLOWED_EMAIL.search(value):
                results.append(("(git history)", 0, "commit_email", value))
            if "@" in value and ALLOWED_EMAIL.search(value):
                continue                          # a no-reply address is public by design
            for term in deny:
                if term and term.lower() in value.lower():
                    results.append(("(git history)", 0, "deny_term", term))
    return results


def main(argv=None) -> int:
    parser = ArgumentParser(prog="modularcv privacy", description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--deny-file", help="text file, one private term per line (keep it outside the repo)")
    parser.add_argument("--deny", action="append", default=[], help="a private term (repeatable)")
    parser.add_argument("--history", action="store_true", help="also check commit author e-mails")
    args = parser.parse_args(argv)
    deny = list(args.deny)
    if args.deny_file:
        deny += [line.strip() for line in Path(args.deny_file).read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")]
    findings = scan(args.root, deny, args.history)
    for path, number, kind, value in findings:
        print("%s:%s: %s: %s" % (path, number, kind, value if kind != "token" else value[:6] + "..."))
    print("%d finding(s)" % len(findings), file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
