"""Optional, controlled compilation of a generated `.tex` with `pdflatex` (M7-A).

`pdflatex` is an optional system dependency; nothing here installs it. When it is absent, `.tex` generation is unaffected and
`compile_tex` raises `PDF_UNAVAILABLE`. The compiler is run with a fixed command line (no user-supplied argument), shell escape
disabled, in a fresh temporary directory that holds only the generated file, with a time limit, no standard input, and a
scrubbed `TEX*` environment. MiKTeX's on-the-fly package installer is disabled so that nothing is downloaded. A TeX compiler
cannot be sandboxed from the network by this module: with the installer disabled and no shell escape, a document built from the
fixed template has no way to reach it, and `docs/RENDER.md` says so.

A compilation yields a PDF, a page count read from the compiler's own log, and a verdict. The PDF is an *artefact*, not an
identity: it is not byte-reproducible. Diagnostics never carry the log: it can quote the CV, so it leaves this module only when
the caller asks for it explicitly.
"""
import os
import re
import shutil
import subprocess
import tempfile
from collections import namedtuple

from . import canonical, docvalidate

PREFIX = "PDF_"
JOBNAME = "resume"
DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300
LOG_LIMIT = 400000
_SCRUBBED = ("TEXINPUTS", "TEXFONTS", "TEXFORMATS", "TEXMFCNF", "TEXMFHOME", "TEXMF", "TEXPSHEADERS", "BIBINPUTS", "BSTINPUTS",
             "LATEXPAND", "TEXINPUTS_", "TFMFONTS", "T1FONTS", "OPENTYPEFONTS", "TTFONTS", "VFFONTS")
_KINDS = ("Undefined control sequence", "Missing $ inserted", "Missing { inserted", "Missing } inserted", "Extra }, or forgotten",
          "Runaway argument", "File ended while scanning", "Emergency stop", "Package inputenc Error", "LaTeX Error: File",
          "LaTeX Error: Missing", "LaTeX Error: Environment", "Font ", "TeX capacity exceeded", "Illegal parameter number",
          "Paragraph ended before", "Misplaced alignment tab", "Too many }'s", "Double superscript", "Double subscript")

Result = namedtuple("Result", "pdf pages pdf_sha256 returncode log")


class PdfError(ValueError):
    """The PDF could not be produced. `errors` holds problems with fixed messages; `details` holds value-free facts
    (return code, the kind and line of the first TeX error) and `log` the compiler output, which may quote the CV."""

    def __init__(self, errors, details=None, log=None):
        self.errors = tuple(errors)
        self.details = dict(details or {})
        self.log = log
        first = self.errors[0]
        super().__init__("%s: %s" % (first.code, first.message))

    @property
    def code(self):
        return self.errors[0].code


def _problem(code, message, path=""):
    return docvalidate.Problem(PREFIX + code, message, path)


def find_pdflatex():
    """The `pdflatex` executable on the PATH, or None. Nothing is searched elsewhere and nothing is installed."""
    return shutil.which("pdflatex")


def _safe_environment():
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in _SCRUBBED and not key.upper().startswith("TEXMF")}
    env["openout_any"] = "p"          # paranoid: no write outside the working directory
    env["shell_escape"] = "f"         # never run a command from a document
    env["SOURCE_DATE_EPOCH"] = env.get("SOURCE_DATE_EPOCH", "0")
    return env


def environment(executable=None):
    """`{"pdflatex": "FOUND"|"ABSENT", "distribution", "version"}`. Never holds a path."""
    executable = executable or find_pdflatex()
    if executable is None:
        return {"pdflatex": "ABSENT", "distribution": None, "version": None}
    try:
        done = subprocess.run([executable, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=30, env=_safe_environment())
        lines = done.stdout.decode("utf-8", "replace").splitlines()
    except (OSError, subprocess.SubprocessError):
        return {"pdflatex": "ABSENT", "distribution": None, "version": None}
    banner = "\n".join(lines[:6])
    distribution = "MiKTeX" if "MiKTeX" in banner else "TeX Live" if "TeX Live" in banner else "unknown"
    return {"pdflatex": "FOUND", "distribution": distribution, "version": (lines[0][:120] if lines else None)}


def _first_error(log):
    """`(kind, line)` of the first TeX error: `kind` comes from a closed list, never from the document."""
    lines = log.splitlines()
    for number, line in enumerate(lines):
        if line.startswith("!"):
            message = line[1:].strip()
            kind = next((known.strip() for known in _KINDS if message.startswith(known)), "OTHER")
            where = None
            for follow in lines[number + 1:number + 6]:
                found = re.match(r"l\.(\d+)", follow)
                if found:
                    where = int(found.group(1))
                    break
            return kind, where
    return None, None


def compile_tex(tex, timeout=DEFAULT_TIMEOUT, executable=None):
    """Compile the bytes `tex` and return a `Result`. Raises `PdfError`; writes nothing outside a temporary directory."""
    if not isinstance(tex, bytes) or not tex:
        raise PdfError([_problem("BAD_INPUT", "the document to compile must be non-empty bytes")])
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= MAX_TIMEOUT:
        raise PdfError([_problem("BAD_TIMEOUT", "the time limit must be an integer number of seconds between 1 and %d" % MAX_TIMEOUT)])
    executable = executable or find_pdflatex()
    if executable is None:
        raise PdfError([_problem("UNAVAILABLE", "pdflatex was not found: the PDF was not compiled, the .tex is unaffected")])
    arguments = [executable, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", "-jobname=" + JOBNAME]
    if environment(executable)["distribution"] == "MiKTeX":
        arguments.append("--disable-installer")
    with tempfile.TemporaryDirectory(prefix="modularcv-") as work:
        source = os.path.join(work, JOBNAME + ".tex")
        with open(source, "xb") as handle:
            handle.write(tex)
        try:
            done = subprocess.run(arguments + [JOBNAME + ".tex"], cwd=work, env=_safe_environment(), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise PdfError([_problem("TIMEOUT", "the compiler exceeded the time limit and was stopped")], {"timeout_seconds": timeout})
        except OSError:
            raise PdfError([_problem("UNAVAILABLE", "pdflatex could not be started")])
        output = done.stdout.decode("utf-8", "replace")[:LOG_LIMIT]
        log_path = os.path.join(work, JOBNAME + ".log")
        log = output
        if os.path.isfile(log_path):
            with open(log_path, "rb") as handle:
                log = handle.read(LOG_LIMIT).decode("utf-8", "replace")
        kind, line = _first_error(log)
        details = {"returncode": done.returncode, "error_kind": kind, "error_line": line}
        pdf_path = os.path.join(work, JOBNAME + ".pdf")
        if done.returncode != 0 or kind is not None:
            raise PdfError([_problem("COMPILE_FAILED", "the compiler reported an error")], details, log)
        if not os.path.isfile(pdf_path):
            raise PdfError([_problem("NO_OUTPUT", "the compiler did not produce the expected PDF")], details, log)
        with open(pdf_path, "rb") as handle:
            data = handle.read()
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
            raise PdfError([_problem("BAD_OUTPUT", "the produced file is not a complete PDF")], details, log)
        found = re.search(r"Output written on %s\.pdf \((\d+) pages?" % JOBNAME, log)
        if not found:
            raise PdfError([_problem("PAGES_UNKNOWN", "the page count could not be read from the compiler log")], details, log)
        return Result(data, int(found.group(1)), canonical.sha256_bytes(data), done.returncode, log)


def page_verdict(page_target, pages):
    """How the real page count compares with the family's target. Nothing here changes the document."""
    if page_target is None:
        return "NO_TARGET"
    if pages is None:
        return "NOT_COMPILED"
    return "TARGET_MET" if pages <= page_target else "TARGET_EXCEEDED"


def looks_like_pdf(data):
    """True for a complete-looking PDF file: starts with `%PDF-` and ends with `%%EOF`. A shape check, not a validation."""
    return isinstance(data, bytes) and data.startswith(b"%PDF-") and b"%%EOF" in data[-2048:]


def count_pages(data):
    """The page count written in the PDF's own page tree, or None when it cannot be established.

    Standard library only: the objects are searched in the file and in its Flate-compressed object streams. The root of the
    page tree is the `/Type /Pages` dictionary without a `/Parent`. This reads the file; it does not render anything."""
    import zlib
    if not looks_like_pdf(data):
        return None
    blobs = [data]
    for found in re.finditer(rb"stream\r?\n", data):
        end = data.find(b"endstream", found.end())
        if end < 0:
            continue
        try:
            blobs.append(zlib.decompressobj().decompress(data[found.end():end]))
        except zlib.error:
            continue
    roots, others = [], []
    for blob in blobs:
        for dictionary in re.finditer(rb"<<[^<>]*>>", blob):
            body = dictionary.group(0)
            if not re.search(rb"/Type\s*/Pages\b", body):
                continue
            count = re.search(rb"/Count\s+(\d+)", body)
            if count:
                (others if b"/Parent" in body else roots).append(int(count.group(1)))
    if roots:
        return max(roots)
    return max(others) if others else None
