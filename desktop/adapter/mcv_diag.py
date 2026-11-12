"""Environment diagnostics for ModularCV Desktop: embedded engine, Git, provenance, LaTeX.

Read-only and offline. It never installs, downloads or launches anything except `git --version` and
`pdflatex --version` (through the engine's own `pdf.environment()`), each with a timeout. Paths, names and workspace
content never appear in the answer: only closed codes and tool versions.

Run as `python -I mcv_diag.py [--root <workspace>]` (development) or through the embedded engine (`mcv-engine diagnose`).
Prints one JSON object and exits 0.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `python -I` does not add the script folder
from mcv_core import Refusal, locate  # also puts the engine on sys.path
from modularcv import __version__, pdf, provenance


def _git():
    exe = shutil.which("git")
    if exe is None:
        return {"status": "ABSENT", "version": None}
    try:
        done = subprocess.run([exe, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=10)
        text = done.stdout.decode("utf-8", "replace").strip().splitlines()
        return {"status": "FOUND" if done.returncode == 0 else "ABSENT", "version": (text[0][:80] if text else None)}
    except (OSError, subprocess.SubprocessError):
        return {"status": "ABSENT", "version": None}


def _provenance(root, git_found):
    if root is None:
        return {"status": "NOT_CHECKED", "code": None, "reason": None}
    if not git_found:
        return {"status": "UNVERIFIABLE", "code": "GIT_UNAVAILABLE", "reason": None}
    try:
        cfg, files = locate(root, ("facts", "profile", "content"))
        names = [Path(p).resolve().relative_to(Path(root).resolve()).as_posix() for p in files.values()]
        provenance.resolve_source_commit(root, names)
        return {"status": "VERIFIED", "code": None, "reason": None}
    except provenance.SourceProvenanceError as error:
        return {"status": "UNVERIFIABLE", "code": error.status, "reason": error.reason}
    except (Refusal, ValueError, OSError):
        return {"status": "NOT_CHECKED", "code": "WORKSPACE_UNREADABLE", "reason": None}


def diagnose(root=None):
    git = _git()
    latex = pdf.environment()
    return {
        "ok": True,
        "engine": {"status": "OK", "version": __version__, "python": sys.version.split()[0],
                   "embedded": bool(getattr(sys, "frozen", False))},
        "git": git,
        "provenance": _provenance(root, git["status"] == "FOUND"),
        "latex": dict(latex, compile="AVAILABLE" if latex["pdflatex"] == "FOUND" else "UNAVAILABLE"),
        "offline": True,
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = None
    if len(argv) == 2 and argv[0] == "--root":
        root = argv[1] if Path(argv[1]).is_dir() else None
    elif argv:
        sys.stdout.write(json.dumps({"ok": False, "code": "BAD_REQUEST", "message": "usage: diagnose [--root <workspace>]", "details": []}))
        return 2
    sys.stdout.write(json.dumps(diagnose(root), ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
