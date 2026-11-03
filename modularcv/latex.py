"""Deterministic, generic LaTeX rendering of an `AssembledResume-v1` (M7-A).

Contract and rules: `docs/RENDER.md`. Every text that reaches the document is **untrusted data**: it passes through `escape`,
the one place where text becomes LaTeX, and is never read as LaTeX. The template is fixed in this module; the data only ever
appears as the argument of a fixed command, after escaping. The only markup that survives is the pair ResumeContent-v1 itself
defines (`**bold**`, `_italic_`), turned into `\\textbf{}` and `\\textit{}` by this module, never by the text.

Escaping is a closed table, not a blacklist:

* the ten LaTeX special characters, plus `[` and `]` (an optional argument after `\\item`), have a fixed replacement;
* characters that would form a ligature with themselves (`--`, `''`, ``` `` ```, `<<`, `>>`, `,,`, and `!` or `?` before a
  backquote) are separated by `{}`, so the printed characters are exactly the written ones;
* printable ASCII and the Latin letters and punctuation listed in `SAFE_RANGES` pass through (`T1` + `utf8` handle them);
* anything else (a control character, a character the font setup cannot print) is **refused**, never replaced or dropped.

The output is a single UTF-8 text, LF line endings, no date and nothing random: the same assembly gives the same bytes.
"""
from . import assemble as assemblemod, canonical, docvalidate

PREFIX = "RENDER_"
TEMPLATE_ID = "generic-v1"
PAPERS = ("a4paper", "letterpaper")
DEFAULT_PAPER = "a4paper"

SPECIALS = {
    "\\": "\\textbackslash{}", "{": "\\{", "}": "\\}", "$": "\\$", "&": "\\&", "#": "\\#", "_": "\\_", "%": "\\%",
    "~": "\\textasciitilde{}", "^": "\\textasciicircum{}", "[": "{[}", "]": "{]}", "\u00a0": "~",
}
SELF_LIGATURES = frozenset("-'`<>,")
SAFE_RANGES = (
    (0x20, 0x7E),          # printable ASCII
    (0xA1, 0xA1), (0xA9, 0xA9), (0xAB, 0xAB), (0xB0, 0xB0), (0xB7, 0xB7), (0xBB, 0xBB), (0xBF, 0xBF),
    # Latin-1 and Latin Extended-A letters, minus the multiplication/division signs and the nine letters T1 + utf8 cannot
    # print (U+0126, 0127, 0138, 013F, 0140, 0149, 0166, 0167, 017F): each was checked with a real compilation
    (0xC0, 0xD6), (0xD8, 0xF6), (0xF8, 0x125), (0x128, 0x137), (0x139, 0x13E), (0x141, 0x148), (0x14A, 0x165), (0x168, 0x17E),
    (0x2013, 0x2014), (0x2018, 0x2019), (0x201C, 0x201D), (0x2022, 0x2022), (0x2026, 0x2026), (0x20AC, 0x20AC),
)
_SAFE_CODES = frozenset(code for low, high in SAFE_RANGES for code in range(low, high + 1)) | {0xA0}


class RenderError(ValueError):
    """The assembly cannot be rendered. `errors` holds every problem found (code, fixed message, path); never a text."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        first = self.errors[0]
        super().__init__("%s (%s): %s" % (first.code, first.path or "assembly", first.message))

    @property
    def code(self):
        return self.errors[0].code


def _problem(code, message, path=""):
    return docvalidate.Problem(PREFIX + code, message, path)


def escape(text, path=""):
    """The LaTeX source that prints exactly `text`. Raises `RenderError` for a character that cannot be printed safely."""
    if not isinstance(text, str):
        raise RenderError([_problem("BAD_TEXT", "a text is required", path)])
    out = []
    size = len(text)
    for index, char in enumerate(text):
        code = ord(char)
        if char in SPECIALS:
            out.append(SPECIALS[char])
            continue
        if code not in _SAFE_CODES:
            raise RenderError([_problem("UNSUPPORTED_CHARACTER", "a character cannot be printed safely (control or unsupported)", path)])
        out.append(char)
        following = text[index + 1] if index + 1 < size else ""
        if (char in SELF_LIGATURES and following == char) or (char in "!?" and following == "`"):
            out.append("{}")
    return "".join(out)


def inline(spans, path=""):
    """LaTeX for the spans of `assemble.inline_spans`: escaped text, `\\textbf` and `\\textit` only."""
    parts = []
    for span in spans:
        piece = escape(span["text"], path)
        if span["italic"]:
            piece = "\\textit{%s}" % piece
        if span["bold"]:
            piece = "\\textbf{%s}" % piece
        parts.append(piece)
    return "".join(parts)


PREAMBLE = r"""\documentclass[10pt,%(paper)s]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage[margin=1.8cm]{geometry}
\usepackage{enumitem}
\input{glyphtounicode}
\pdfgentounicode=1
\pagestyle{empty}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0pt}
\setlist[itemize]{leftmargin=1.3em,itemsep=1pt,topsep=2pt,parsep=0pt,partopsep=0pt}
\newcommand{\cvsection}[1]{\par\vspace{9pt}{\large\bfseries #1}\par\vspace{1pt}\hrule\vspace{4pt}}
\begin{document}
"""


def render(assembly, paper=DEFAULT_PAPER):
    """The `.tex` source (a str, LF line endings) of `assembly`. Raises `RenderError`. Pure: changes nothing."""
    if paper not in PAPERS:
        raise RenderError([_problem("BAD_OPTION", "the paper must be one of the supported sizes", "paper")])
    if not isinstance(assembly, dict) or assembly.get("schema") != assemblemod.SCHEMA \
            or not assemblemod.verify_assembly_fingerprint(assembly) or assembly.get("ready_to_send") is not False:
        raise RenderError([_problem("ASSEMBLY_INVALID", "the assembly is not an intact AssembledResume-v1", "assembly")])
    lines = [
        "%% ModularCV %s template. Generated file: edit the sources, not this file." % TEMPLATE_ID,
        "%% plan_sha256: %s" % assembly["source"]["plan_sha256"],
        "%% assembly_sha256: %s" % assembly["assembly_sha256"],
        "%% language: %s" % assembly["language"],
    ]
    lines.extend((PREAMBLE % {"paper": paper}).splitlines())
    header = assembly["header"]
    lines.append("\\begin{center}")
    lines.append("{\\LARGE\\bfseries %s}\\par" % escape(header["display_name"], "header.display_name"))
    contact = [escape(header[name], "header." + name) for name in ("location", "email", "phone") if name in header]
    contact += [escape(link["value"] if not link.get("label") else "%s: %s" % (link["label"], link["value"]),
                       "header.links[%d]" % position) for position, link in enumerate(header["links"])]
    if contact:
        lines.append("\\vspace{3pt}")
        lines.append(" \\textbar{} ".join(contact))
    lines.append("\\end{center}")
    for section in assembly["sections"]:
        lines.append("\\cvsection{%s}" % escape(section["title"], "section:" + section["id"]))
        for block in section["blocks"]:
            path = "block:" + block["id"]
            heading = block["heading"]
            # no \hfill: right-aligned text is read out of order by text extraction (ATS), so the details follow the title
            lines.append("\\noindent \\textbf{%s}\\par" % escape(heading["title"], path))
            details = [("\\textit{%s}" % escape(heading[name], path)) if name == "subtitle" else escape(heading[name], path)
                       for name in ("subtitle", "place", "period") if heading.get(name)]
            if details:
                lines.append("\\noindent %s\\par" % " \\textbar{} ".join(details))
            if block["bullets"]:
                lines.append("\\begin{itemize}")
                for bullet in block["bullets"]:
                    lines.append("\\item %s" % inline(bullet["spans"], "bullet:" + bullet["id"]))
                lines.append("\\end{itemize}")
            lines.append("\\vspace{3pt}")
    if assembly["skills"] is not None:
        lines.append("\\cvsection{%s}" % escape(assembly["skills"]["title"], "skills"))
        for category in assembly["skills"]["categories"]:
            items = ", ".join(inline(item["spans"], "skill:" + item["id"]) for item in category["items"])
            lines.append("\\noindent \\textbf{%s}: %s\\par" % (escape(category["title"], "category:" + category["id"]), items))
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"


def tex_bytes(text):
    """The exact bytes of the file: UTF-8 without a byte order mark, LF line endings."""
    return text.encode("utf-8")


def tex_sha256(data):
    """The fingerprint of the exact bytes of the `.tex` file (what packages and identities refer to)."""
    return canonical.sha256_bytes(data)

