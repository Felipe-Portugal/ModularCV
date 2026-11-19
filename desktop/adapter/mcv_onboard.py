"""Start a workspace from the application, and bring an existing CV into it.

Four operations, all in the closed list of the adapter:

  workspace_init   write a minimal valid fact base and profile into an empty workspace
  cv_source_read   read a CV file the user picked (.pdf, .docx, .txt, .md); read-only
  cv_parse         split the text of a CV into a *proposal* (identity, blocks, skills); writes nothing
  cv_apply         write the entries the user reviewed: facts, resume content and identity

Rules kept from the rest of the adapter:
  * No network, no model: the split is a plain reading of headings, bullets and dates. Every line the
    reading cannot place is returned in `unclassified`; nothing is dropped silently.
  * Nothing becomes CONFIRMED on its own. `cv_apply` confirms an entry only when the request marks that
    entry `confirmed` and carries the date the user confirms it (`confirmed_on`).
  * Only confirmed entries enter the resume content (the engine refuses a printable line whose fact is not
    CONFIRMED). The others are kept as NOT_CONFIRMED facts and reported as `parked`.
  * Every file is validated by the engine before anything is written; existing facts, blocks and skills
    are proven unchanged; writes are exclusive (new file) or atomic with a hash re-check (existing file).
  * Standard library only; the engine is not changed.
"""
import base64
import copy
import io
import re
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from mcv_core import (Refusal, atomic_replace, block_end, clean, create_new, dumps, ensure_dir, locate, problems,
                      read_bytes, section_titles, serialise, split_file)
from modularcv import canonical, content, docvalidate, facts, profile, taxonomy

MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_PDF_BYTES = 2500000        # returned as base64 in one answer; the bridge reads at most 4 MB
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 200000
MAX_BLOCKS = 60
MAX_BULLETS = 40
MAX_SKILLS = 300
SOURCE_SUFFIXES = (".pdf", ".docx", ".txt", ".md")
LANGUAGES = ("fr", "en")

SECTION_LABELS = {
    "experience": {"fr": "Expérience", "en": "Experience"},
    "projects": {"fr": "Projets", "en": "Projects"},
    "education": {"fr": "Formation", "en": "Education"},
    "other": {"fr": "Autres", "en": "Other"},
}
#: block kind (request) -> (content section id, content section kind, fact section id, fact id prefix)
KINDS = {
    "experience": ("experience", "experience", "experience", "exp"),
    "project": ("projects", "project", "projects", "proj"),
    "education": ("education", "education", "education", "edu"),
    "other": ("other", "other", "other", "other"),
}
PARKED_NOTE = {"fr": "importé d'un CV, à confirmer", "en": "imported from a CV, to be confirmed"}
FACT_SECTION_TITLES = {"experience": "Experience", "projects": "Projects", "education": "Education",
                       "skills": "Skills", "other": "Other"}


# --------------------------------------------------------------------------- small text helpers

def fold(text):
    """Lower case, no accents, single spaces: for comparisons only, never written."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace("’", "'").split())


def slug(text, limit=40):
    out = re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")[:limit].strip("-")
    return out or "item"


def unique(base, taken):
    candidate, number = base, 2
    while candidate in taken:
        candidate = "%s-%d" % (base, number)
        number += 1
    taken.add(candidate)
    return candidate


def tidy(value):
    """One line, no control character, no backslash or brace (TeX escape and attribute delimiters)."""
    if not isinstance(value, str):
        return ""
    value = "".join(" " if unicodedata.category(ch)[0] == "C" else ch for ch in value)
    value = value.replace("\\", "/").replace("{", "(").replace("}", ")")
    return " ".join(value.split())


def plain_inline(value):
    """`tidy`, and without the inline markers when they would not be a valid `**bold**` / `_italic_`."""
    value = tidy(value)
    if content.inline_markup_problem(value):
        value = " ".join(value.replace("*", "").replace("_", " ").split())
    return value


# --------------------------------------------------------------------------- workspace_init

FACTS_TEMPLATE = """<!-- modularcv: FactBase-v1 -->
<!--
  Fact base created by ModularCV Desktop. A fact line reads:
    - [fact-id] STATUS: text {attribute: value; attribute: value}
  Statuses: CONFIRMED (publishable), DERIVED, NOT_CONFIRMED, WITHDRAWN (never publishable).
-->

# Fact base

## Experience {#experience}

## Projects {#projects}

## Education {#education}

## Skills {#skills}

## Other {#other}
"""


def op_workspace_init(request):
    root = request.get("root")
    cfg, files = locate(root)
    name = tidy(request.get("display_name"))
    language = request.get("language")
    if not name or len(name) > 120:
        raise Refusal("VALIDATION_FAILED", "a display name of 1 to 120 characters is expected")
    if language not in LANGUAGES:
        raise Refusal("VALIDATION_FAILED", "the language must be fr or en")
    for key in ("facts", "profile", "content"):
        if Path(files[key]).exists():
            raise Refusal("OUTPUT_EXISTS", "this folder already holds a %s file; nothing was written" % key)

    fact_bytes = FACTS_TEMPLATE.encode("utf-8")
    checked = facts.check_bytes(fact_bytes)
    if checked.errors:
        raise Refusal("VALIDATION_FAILED", "the engine rejects the new fact base", problems(checked.errors))
    document = {
        "schema": profile.SCHEMA, "languages": [language], "default_language": language,
        "identity": {"display_name": {"value": name, "visibility": "public"}},
        "families": {"general": {"label": "CV général" if language == "fr" else "General CV",
                                 "languages": [language], "page_target": 1}},
        "taxonomy": profile.DEFAULT_TAXONOMY,
    }
    profile_bytes = dumps(document)
    checked_profile = profile.check_bytes(profile_bytes, checked.factbase)
    if checked_profile.errors:
        raise Refusal("VALIDATION_FAILED", "the engine rejects the new profile", problems(checked_profile.errors))

    for target in (files["facts"], files["profile"]):
        if Path(target).parent.resolve() != Path(root).resolve():
            raise Refusal("CONFIG_ERROR", "the configured files are not directly in the workspace folder")
    create_new(files["facts"], fact_bytes, root)
    create_new(files["profile"], profile_bytes, root)
    return {"ok": True, "created": [Path(files["facts"]).name, Path(files["profile"]).name]}


# --------------------------------------------------------------------------- cv_source_read

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_text(data):
    """Paragraphs of a .docx as lines; list paragraphs start with a bullet. Read-only, no macro, no link followed."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        info = archive.getinfo("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise Refusal("UNSUPPORTED_FILE", "this is not a readable .docx document")
    if info.file_size > MAX_DOCX_XML_BYTES:
        raise Refusal("SOURCE_TOO_LARGE", "the document is too large to be read")
    xml = archive.read(info)
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise Refusal("UNSUPPORTED_FILE", "the document declares XML entities; it is refused")
    try:
        tree = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        raise Refusal("UNSUPPORTED_FILE", "the document content cannot be read")
    lines = []
    for paragraph in tree.iter(_W + "p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == _W + "t":
                parts.append(node.text or "")
            elif node.tag == _W + "tab":
                parts.append("\t")
            elif node.tag in (_W + "br", _W + "cr"):
                parts.append("\n")
        text = "".join(parts)
        listed = paragraph.find("%spPr/%snumPr" % (_W, _W)) is not None
        for position, piece in enumerate(text.split("\n")):
            piece = piece.strip()
            if piece:
                lines.append(("• " + piece) if listed and position == 0 else piece)
    return "\n".join(lines)


def op_cv_source_read(request):
    locate(request.get("root"), keys=())
    source = request.get("source")
    if not isinstance(source, str) or not source.strip():
        raise Refusal("VALIDATION_FAILED", "a file is expected")
    path = Path(source)
    suffix = path.suffix.lower()
    if suffix not in SOURCE_SUFFIXES:
        raise Refusal("UNSUPPORTED_FILE", "only .pdf, .docx, .txt and .md files can be read")
    try:
        if not path.is_file():
            raise Refusal("FILE_UNREADABLE", "the file does not exist")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise Refusal("SOURCE_TOO_LARGE", "the file is larger than 10 MB")
        data = path.read_bytes()
    except OSError as error:
        raise Refusal("FILE_UNREADABLE", "cannot read the file: %s" % error.strerror)
    if len(data) > MAX_SOURCE_BYTES:
        raise Refusal("SOURCE_TOO_LARGE", "the file is larger than 10 MB")
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise Refusal("UNSUPPORTED_FILE", "this is not a PDF document")
        if len(data) > MAX_PDF_BYTES:
            raise Refusal("SOURCE_TOO_LARGE", "the PDF is larger than 2.5 MB; paste its text instead")
        return {"ok": True, "kind": "pdf", "name": path.name, "bytes": len(data), "base64": base64.b64encode(data).decode("ascii")}
    if suffix == ".docx":
        text = docx_text(data)
    else:
        try:
            text = canonical.decode_text(data)
        except canonical.CanonicalError:
            raise Refusal("UNSUPPORTED_FILE", "the file is not valid UTF-8 text")
    if len(text) > MAX_TEXT_CHARS:
        raise Refusal("SOURCE_TOO_LARGE", "the document holds too much text")
    return {"ok": True, "kind": "text", "name": path.name, "bytes": len(data), "text": text}


# --------------------------------------------------------------------------- cv_parse

HEADINGS = {
    "experience": ("experience", "experiences", "experience professionnelle", "experiences professionnelles",
                   "experience de travail", "experiences de travail", "parcours professionnel", "emploi", "emplois",
                   "experience pertinente", "stages", "work experience", "professional experience", "employment",
                   "employment history", "work history", "career history", "relevant experience", "internships"),
    "education": ("formation", "formations", "education", "etudes", "scolarite", "diplomes", "formation academique",
                  "formation scolaire", "parcours academique", "cursus", "academic background", "education and training"),
    "skills": ("competences", "competences techniques", "competences cles", "connaissances", "connaissances techniques",
               "aptitudes", "habiletes", "savoir-faire", "outils", "technologies", "langages", "langages de programmation",
               "skills", "technical skills", "key skills", "core skills", "programming languages", "tools", "expertise"),
    "project": ("projets", "projets personnels", "projets academiques", "realisations", "projects", "personal projects",
                "academic projects", "selected projects", "portfolio"),
    "languages": ("langues", "langues parlees", "languages", "spoken languages"),
    "other": ("certifications", "certificats", "certificates", "licences et certifications", "benevolat", "implication",
              "engagement", "prix", "distinctions", "prix et distinctions", "publications", "activites",
              "activites parascolaires", "volunteering", "volunteer experience", "awards", "honors", "honours",
              "activities", "extracurricular activities", "leadership"),
    "ignored": ("profil", "profil professionnel", "resume", "resume professionnel", "sommaire", "objectif",
                "objectif de carriere", "a propos", "a propos de moi", "interets", "centres d'interet", "loisirs",
                "references", "coordonnees", "contact", "informations personnelles", "profile", "summary",
                "professional summary", "objective", "career objective", "about", "about me", "interests", "hobbies",
                "personal information"),
}
_HEADING_BY_TEXT = {phrase: kind for kind, phrases in HEADINGS.items() for phrase in phrases}
_FRENCH_HINTS = set("experience professionnelle formation competences langues projets et de la le les des avec pour "
                    "chez depuis aujourd'hui present developpement gestion".split())
_ENGLISH_HINTS = set("experience education skills languages projects and the of with for at since present "
                     "development management work".split())

_BULLET = re.compile(r"^\s*(?:[•●▪■◦○∙·‣⁃*►▸➤➢✓✔\-–—]|o(?=\s+\S{2})|\d{1,2}[.)])\s+(?P<text>\S.*)$")
_MONTH = (r"(?:janv(?:ier)?|f[ée]vr(?:ier)?|mars|avr(?:il)?|mai|juin|juil(?:let)?|ao[uû]t|sept(?:embre)?|oct(?:obre)?|"
          r"nov(?:embre)?|d[ée]c(?:embre)?|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
          r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_YEAR = r"(?:19|20)\d{2}"
_POINT = r"(?:(?:%s\s+)?%s|\d{1,2}[/.]%s|%s[/.-]\d{1,2})" % (_MONTH, _YEAR, _YEAR, _YEAR)
_NOW = r"(?:pr[ée]sent|aujourd'?hui|actuel(?:lement)?|en cours|maintenant|current|now|today|ongoing)"
_PERIOD = re.compile(
    r"(?<![\w/])(?:(?:depuis|since)\s+)?%s(?:\s*(?:[-–—]|à|au|to|until)\s*(?:%s|%s))?(?:\s*\((?:pr[ée]vu|expected|en cours)\))?(?![\w/])"
    % (_POINT, _POINT, _NOW), re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LINK = re.compile(r"(?:https?://|www\.)[^\s|,;]+|(?:[a-z]{2,3}\.)?(?:linkedin\.com|github\.com|gitlab\.com)/[^\s|,;]+", re.IGNORECASE)
_PHONE = re.compile(r"(?<![\w/])\+?\d[\d\s().-]{7,}\d(?!\w)")
_PLACE = re.compile(r"^[^\W\d_][\w' .-]{1,30},\s*[^\W\d_][\w' .-]{1,30}$")
_HEADING_SPLIT = re.compile(r"\s+[|•·–—-]\s+|\s+@\s+|\s+chez\s+|\s+at\s+|\t+|\s{3,}")
_ITEM_SPLIT = "|•·●;,"


def heading_kind(line):
    text = fold(line).strip(" :-–—•|#*_").strip()
    if not text or len(text) > 45:
        return None
    return _HEADING_BY_TEXT.get(text)


def split_top_level(text, separators):
    """Split on separators that are not inside parentheses."""
    items, depth, current = [], 0, []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]" and depth:
            depth -= 1
        if ch in separators and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    items.append("".join(current))
    return [item.strip(" .\t-–—") for item in items if item.strip(" .\t-–—")]


def take_period(line):
    """(period, rest): the first date or date range of the line, and the line without it."""
    match = _PERIOD.search(line)
    if not match:
        return "", line
    period = " ".join(match.group(0).split())
    rest = (line[:match.start()] + " " + line[match.end():])
    rest = re.sub(r"\(\s*\)|\[\s*\]", " ", rest)
    rest = " ".join(rest.split()).strip(" ,|•·–—-:;")
    return period, rest


def _new_block(kind):
    return {"kind": kind, "title": "", "subtitle": "", "period": "", "place": "", "bullets": [], "_lines": 0}


def _add_heading_line(block, line):
    period, rest = take_period(line)
    if period and not block["period"]:
        block["period"] = period
    elif period:
        rest = line
    if not rest:
        return
    block["_lines"] += 1
    for part in [p.strip(" ,;:") for p in _HEADING_SPLIT.split(rest) if p.strip(" ,;:")]:
        if not block["title"]:
            block["title"] = part
        elif not block["subtitle"]:
            block["subtitle"] = part
        elif not block["place"] and len(part) <= 60:
            block["place"] = part
        else:
            block["subtitle"] = (block["subtitle"] + ", " + part)[:200]


def _is_description(line):
    return len(line) > 90 or (line.endswith((".", ";")) and len(line.split()) > 6)


def parse_blocks(kind, lines):
    blocks, current = [], None
    for line in lines:
        bullet = _BULLET.match(line)
        if bullet:
            if current is None:
                current = _new_block(kind)
                blocks.append(current)
            current["bullets"].append(bullet.group("text").strip())
            continue
        text = line.strip()
        first_alpha = next((ch for ch in text if ch.isalpha()), "")
        if current is not None and current["bullets"]:
            if first_alpha and first_alpha.islower() and not _PERIOD.search(text):
                current["bullets"][-1] += " " + text      # a wrapped bullet
                continue
            current = _new_block(kind)
            blocks.append(current)
            _add_heading_line(current, text)
            continue
        if current is None:
            current = _new_block(kind)
            blocks.append(current)
            _add_heading_line(current, text)
        elif _is_description(text):
            current["bullets"].append(text)
        elif current["_lines"] >= 3 or (current["_lines"] >= 2 and current["period"]):
            current = _new_block(kind)
            blocks.append(current)
            _add_heading_line(current, text)
        else:
            _add_heading_line(current, text)
    for block in blocks:
        del block["_lines"]
    return [b for b in blocks if b["title"] or b["bullets"]]


def parse_skills(lines, default_title, technical=True):
    categories, order = {}, []

    def category(title):
        key = fold(title)
        if key not in categories:
            categories[key] = {"title": title, "technical": technical, "items": []}
            order.append(key)
        return categories[key]

    leftovers = []
    for line in lines:
        bullet = _BULLET.match(line)
        text = (bullet.group("text") if bullet else line).strip()
        title = default_title
        head, colon, tail = text.partition(":")
        if colon and tail.strip() and len(head.strip()) <= 40 and "(" not in head:
            title, text = head.strip(), tail.strip()
        for item in split_top_level(text, _ITEM_SPLIT):
            if len(item) > 80:
                leftovers.append(item)
            elif fold(item) not in {fold(existing) for existing in category(title)["items"]}:
                category(title)["items"].append(item)
    return [categories[key] for key in order if categories[key]["items"]], leftovers


def parse_identity(lines):
    identity = {"display_name": "", "headline": "", "location": "", "email": "", "phone": "", "links": []}
    leftovers = []
    for line in lines:
        rest = line
        email = _EMAIL.search(rest)
        if email:
            identity["email"] = identity["email"] or email.group(0)
            rest = rest.replace(email.group(0), " ")
        for link in _LINK.findall(rest):
            if link not in identity["links"]:
                identity["links"].append(link.rstrip(".)"))
            rest = rest.replace(link, " ")
        phone = _PHONE.search(rest)
        if phone and sum(ch.isdigit() for ch in phone.group(0)) >= 9:
            identity["phone"] = identity["phone"] or " ".join(phone.group(0).split())
            rest = rest.replace(phone.group(0), " ")
        for piece in [p.strip(" ,:-–—") for p in re.split(r"[|•·]|\s{3,}", rest) if p.strip(" ,:-–—")]:
            words = piece.split()
            letters_only = all(ch.isalpha() or ch in " '-." for ch in piece)
            if not identity["display_name"] and letters_only and 2 <= len(words) <= 5 and len(piece) <= 60:
                identity["display_name"] = piece
            elif not identity["location"] and _PLACE.match(piece) and len(piece) <= 50:
                identity["location"] = piece
            elif not identity["headline"] and identity["display_name"] and not any(ch.isdigit() for ch in piece) and len(piece) <= 90:
                identity["headline"] = piece
            else:
                leftovers.append(piece)
    return identity, leftovers


def guess_language(lines):
    words = [w for line in lines for w in fold(line).split()]
    french = sum(1 for w in words if w in _FRENCH_HINTS)
    english = sum(1 for w in words if w in _ENGLISH_HINTS)
    return "fr" if french >= english else "en"


def parse_cv(text):
    lines = [" ".join(line.replace("\t", "   ").split(" ")).rstrip() for line in canonical.normalise_text(text).split("\n")]
    lines = [line.strip() if not _BULLET.match(line) else line for line in lines]
    lines = [line for line in lines if line.strip()]
    language = guess_language(lines)
    groups, current = [("header", "", [])], None
    for line in lines:
        kind = heading_kind(line)
        if kind:
            current = (kind, line.strip(" :"), [])
            groups.append(current)
        else:
            groups[-1][2].append(line)

    proposal = {"language": language, "identity": None, "blocks": [], "skills": [], "unclassified": [],
                "sections_found": [g[0] for g in groups[1:]]}
    for kind, title, body in groups:
        if kind == "header":
            proposal["identity"], leftovers = parse_identity(body)
            proposal["unclassified"].extend({"section": "", "text": item} for item in leftovers)
        elif kind in ("experience", "education", "project", "other"):
            proposal["blocks"].extend(parse_blocks(kind, body))
        elif kind in ("skills", "languages"):
            default = title or ("Compétences" if language == "fr" else "Skills")
            categories, leftovers = parse_skills(body, default, technical=(kind == "skills"))
            proposal["skills"].extend(categories)
            proposal["unclassified"].extend({"section": title, "text": item} for item in leftovers)
        else:
            proposal["unclassified"].extend({"section": title, "text": item} for item in body)
    return proposal


def op_cv_parse(request):
    locate(request.get("root"), keys=())
    text = request.get("text")
    if not isinstance(text, str) or not text.strip():
        raise Refusal("VALIDATION_FAILED", "the text of a CV is expected")
    if len(text) > MAX_TEXT_CHARS:
        raise Refusal("SOURCE_TOO_LARGE", "the text is too long")
    proposal = parse_cv(text)
    return dict(proposal, ok=True, lines=len([l for l in text.splitlines() if l.strip()]))


# --------------------------------------------------------------------------- cv_apply

def _status(entry, date):
    if entry.get("confirmed") is True:
        if not date:
            raise Refusal("CONFIRMATION_REQUIRED", "confirming an entry needs the date you confirm it (confirmed_on)")
        return facts.CONFIRMED, date
    return facts.NOT_CONFIRMED, None


def _technologies(text, language, known_taxonomy, skill_names):
    """Technologies named in the sentence itself: taxonomy terms of kind technology, and the user's own skill names."""
    found, seen = [], set()

    def add(name):
        if name and fold(name) not in seen and not any(ch in name for ch in "{},;") and len(name) <= 40:
            seen.add(fold(name))
            found.append(name)

    for detection in known_taxonomy.detect(text, language):
        term = known_taxonomy.term(detection.term_id)
        if term and term.get("kind") == "technology":
            add(term.get("name") or detection.term_id)
    folded = fold(text)
    for name in skill_names:
        if re.search(r"(?<!\w)%s(?!\w)" % re.escape(fold(name)), folded):
            if not any(fold(name) == s for s in seen):
                add(name)
    return found


def _fact_record(fact_id, status, date, text, language, technologies=()):
    return {"id": fact_id, "status": status, "text": text, "lang": language, "confirmed_on": date,
            "technologies": list(technologies), "capabilities": [], "source": None, "supersedes": None,
            "note": None if status == facts.CONFIRMED else PARKED_NOTE.get(language, PARKED_NOTE["en"])}


def _insert_fact(lines, section, title, new_line):
    """Append `new_line` after the last fact of `section`; the section heading is added at the end when missing."""
    heading = next((i for i, line in enumerate(lines) if (facts._SECTION.match(line) or None) and
                    section == (facts._SECTION.match(line).group("id") if facts._SECTION.match(line).group("id") is not None
                                else facts.slugify(facts._SECTION.match(line).group("title")))), None)
    if heading is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(["", "## %s {#%s}" % (title, section), "", new_line, ""])
        return
    stop = next((i for i in range(heading + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    last, index = None, heading + 1
    while index < stop:
        if lines[index].startswith("- ["):
            last = block_end(lines, index) - 1
            index = last + 1
        else:
            index += 1
    if last is None:
        lines[heading + 1:heading + 1] = ["", new_line]
    else:
        lines.insert(last + 1, new_line)


def _comparable(fact):
    return (fact.id, fact.status, fact.text, fact.section, fact.lang, fact.confirmed_on, tuple(fact.technologies),
            tuple(fact.capabilities), fact.source, fact.supersedes, fact.note, tuple(sorted(dict(fact.extensions).items())))


def _identity_changes(request_identity, document):
    """The Profile-v1 identity after the reviewed values are applied (only the fields the user sent)."""
    identity = copy.deepcopy(document.get("identity") or {})
    if not isinstance(request_identity, dict):
        return identity, False
    changed = False
    for field in profile.IDENTITY_FIELDS:
        entry = request_identity.get(field)
        if not isinstance(entry, dict):
            continue
        value = tidy(entry.get("value"))
        visibility = entry.get("visibility")
        if not value:
            continue
        if visibility not in profile.VISIBILITIES:
            raise Refusal("VALIDATION_FAILED", "every identity field needs a visibility (public or private)")
        if identity.get(field) != {"value": value, "visibility": visibility}:
            identity[field] = {"value": value, "visibility": visibility}
            changed = True
    links = request_identity.get("links")
    if isinstance(links, list):
        present = {link.get("value") for link in identity.get("links", []) if isinstance(link, dict)}
        for link in links:
            if not isinstance(link, dict):
                continue
            value, label = tidy(link.get("value")), tidy(link.get("label"))
            if not value or value in present:
                continue
            if link.get("visibility") not in profile.VISIBILITIES or not label:
                raise Refusal("VALIDATION_FAILED", "every link needs a label and a visibility (public or private)")
            identity.setdefault("links", []).append({"label": label, "value": value, "visibility": link["visibility"]})
            present.add(value)
            changed = True
    return identity, changed


def op_cv_apply(request):
    root = request.get("root")
    cfg, files = locate(root)
    language = request.get("language")
    date = clean(request.get("confirmed_on"))
    if date and not facts.DATE_PATTERN.match(date):
        raise Refusal("VALIDATION_FAILED", "the confirmation date must read YYYY, YYYY-MM or YYYY-MM-DD")
    blocks_in = request.get("blocks") or []
    skills_in = request.get("skills") or []
    if not isinstance(blocks_in, list) or not isinstance(skills_in, list) or len(blocks_in) > MAX_BLOCKS:
        raise Refusal("VALIDATION_FAILED", "a list of blocks and a list of skill categories are expected")

    raw_facts = read_bytes(files["facts"])
    raw_profile = read_bytes(files["profile"])
    if raw_facts is None or raw_profile is None:
        raise Refusal("FILE_UNREADABLE", "the workspace has no fact base or no profile yet; create the profile first")
    before = facts.check_bytes(raw_facts)
    if before.errors:
        raise Refusal("FILE_NOT_EDITABLE", "the fact file is already invalid; fix it before importing", problems(before.errors))
    before_profile = profile.check_bytes(raw_profile, before.factbase)
    if before_profile.errors or before_profile.profile is None:
        raise Refusal("FILE_NOT_EDITABLE", "the profile is already invalid; fix it before importing", problems(before_profile.errors))
    profile_document = docvalidate.load(raw_profile, "PROFILE_")
    declared = list(profile_document.get("languages") or [])
    if language not in declared:
        raise Refusal("VALIDATION_FAILED", "the language of the import must be one of the profile's languages")
    raw_content = read_bytes(files["content"])
    if raw_content is not None:
        before_content = content.check_bytes(raw_content, before.factbase, before_profile.profile)
        if before_content.errors:
            raise Refusal("FILE_NOT_EDITABLE", "the resume content is already invalid; fix it before importing",
                          problems(before_content.errors))
        document = docvalidate.load(raw_content, "CONTENT_")
    else:
        document = {"schema": content.SCHEMA, "sections": [], "blocks": [], "skills": []}
    original_document = copy.deepcopy(document)
    try:
        known_taxonomy = taxonomy.load(before_profile.profile.internal_preferences()["taxonomy"], Path(root)).taxonomy
    except taxonomy.TaxonomyError:
        known_taxonomy = None
    if known_taxonomy is None:
        known_taxonomy = taxonomy.builtin()

    fact_ids = {fact.id for fact in before.factbase.facts}
    block_ids = {b.get("id") for b in document.get("blocks", []) if isinstance(b, dict)}
    bullet_ids = {bullet.get("id") for b in document.get("blocks", []) if isinstance(b, dict)
                  for bullet in b.get("bullets", []) if isinstance(bullet, dict)}
    category_ids = {c.get("id") for c in document.get("skills", []) if isinstance(c, dict)}
    item_ids = {i.get("id") for c in document.get("skills", []) if isinstance(c, dict)
                for i in c.get("items", []) if isinstance(i, dict)}
    section_ids = {s.get("id") for s in document.get("sections", []) if isinstance(s, dict)}
    orders = {}
    for existing in document.get("blocks", []):
        if isinstance(existing, dict) and isinstance(existing.get("order"), int):
            orders[existing.get("section")] = max(orders.get(existing.get("section"), 0), existing["order"])

    skill_names = []
    for category in skills_in:
        if isinstance(category, dict) and category.get("technical", True):
            skill_names.extend(tidy(item.get("text")) for item in category.get("items") or [] if isinstance(item, dict))
    skill_names = [name for name in skill_names if name]

    new_facts = []          # (fact section id, record)
    counts = {"blocks": 0, "bullets": 0, "skills": 0, "confirmed": 0, "parked": 0}

    def add_fact(section, record):
        new_facts.append((section, record))
        if record["status"] == facts.CONFIRMED:
            counts["confirmed"] += 1

    for position, entry in enumerate(blocks_in):
        if not isinstance(entry, dict) or entry.get("kind") not in KINDS:
            raise Refusal("VALIDATION_FAILED", "block %d has no known kind" % (position + 1))
        content_section, section_kind, fact_section, prefix = KINDS[entry["kind"]]
        heading = {key: tidy(entry.get(key))[:content.HEADING_MAX] for key in content.HEADING_FIELDS}
        if not heading["title"]:
            raise Refusal("VALIDATION_FAILED", "block %d has no title" % (position + 1))
        bullets = entry.get("bullets") or []
        if not isinstance(bullets, list) or len(bullets) > MAX_BULLETS:
            raise Refusal("VALIDATION_FAILED", "block %d has too many lines" % (position + 1))
        base = slug(heading["title"], 32)
        block_id = unique(base, block_ids)
        head_fact = unique("%s.%s" % (prefix, base), fact_ids)
        status, when = _status(entry, date)
        head_text = ", ".join(heading[key] for key in content.HEADING_FIELDS if heading[key]).rstrip(".") + "."
        add_fact(fact_section, _fact_record(head_fact, status, when, head_text, language))
        placed = status == facts.CONFIRMED          # an unconfirmed heading cannot be printed: its block stays out
        if not placed:
            counts["parked"] += 1
        block = {"id": block_id, "section": content_section, "order": orders.get(content_section, 0) + 1,
                 "languages": [language], "supports": [head_fact],
                 "heading": {language: {key: value for key, value in heading.items() if value}}, "bullets": []}
        number = 0
        for line in bullets:
            if not isinstance(line, dict):
                raise Refusal("VALIDATION_FAILED", "block %d holds a line that is not an entry" % (position + 1))
            text = plain_inline(line.get("text"))
            if not text:
                continue
            if len(text) > content.TEXT_MAX:
                raise Refusal("VALIDATION_FAILED", "a line of block %d is longer than %d characters" % (position + 1, content.TEXT_MAX))
            number += 1
            technologies = _technologies(text, language, known_taxonomy, skill_names)
            fact_id = unique("%s.%02d" % (head_fact, number), fact_ids)
            status, when = _status(line, date)
            add_fact(fact_section, _fact_record(fact_id, status, when, text, language, technologies))
            if not placed or status != facts.CONFIRMED:
                counts["parked"] += 1
                continue
            bullet = {"id": unique("%s.%02d" % (block_id, number), bullet_ids), "text": {language: text}, "supports": [fact_id]}
            if technologies:
                bullet["technologies"] = technologies
            block["bullets"].append(bullet)
            counts["bullets"] += 1
        if not placed:
            block_ids.discard(block_id)
            continue
        orders[content_section] = block["order"]
        if not block["bullets"]:
            block["protected"] = True       # a heading-only entry (a degree, a certificate) is printed only when protected
        if content_section not in section_ids:
            titles = {code: SECTION_LABELS[content_section].get(code, SECTION_LABELS[content_section]["en"]) for code in declared}
            document.setdefault("sections", []).append({"id": content_section, "kind": section_kind, "title": titles})
            section_ids.add(content_section)
        document.setdefault("blocks", []).append(block)
        counts["blocks"] += 1

    total_items = 0
    for position, entry in enumerate(skills_in):
        if not isinstance(entry, dict):
            raise Refusal("VALIDATION_FAILED", "skill category %d is not an entry" % (position + 1))
        title = tidy(entry.get("title"))[:content.HEADING_MAX]
        items_in = entry.get("items") or []
        if not title or not isinstance(items_in, list):
            raise Refusal("VALIDATION_FAILED", "skill category %d has no title" % (position + 1))
        technical = entry.get("technical", True) is True
        items = []
        for item in items_in:
            if not isinstance(item, dict):
                raise Refusal("VALIDATION_FAILED", "skill category %d holds an item that is not an entry" % (position + 1))
            text = plain_inline(item.get("text"))
            if not text:
                continue
            if len(text) > 200:
                raise Refusal("VALIDATION_FAILED", "a skill of category %d is longer than 200 characters" % (position + 1))
            total_items += 1
            if total_items > MAX_SKILLS:
                raise Refusal("VALIDATION_FAILED", "too many skills in one import")
            declared_technology = technical and len(text) <= 40 and not any(ch in text for ch in "{},;")
            fact_id = unique("skill.%s" % slug(text), fact_ids)
            status, when = _status(item, date)
            add_fact("skills", _fact_record(fact_id, status, when, text, language, [text] if declared_technology else []))
            if status != facts.CONFIRMED:
                counts["parked"] += 1
                continue
            record = {"id": unique(slug(text), item_ids), "text": {language: text}, "supports": [fact_id]}
            if declared_technology:
                record["technologies"] = [text]
            items.append(record)
            counts["skills"] += 1
        if items:
            document.setdefault("skills", []).append({"id": unique(slug(title), category_ids), "title": {language: title}, "items": items})

    identity, identity_changed = _identity_changes(request.get("identity"), profile_document)
    if not new_facts and not identity_changed:
        raise Refusal("NO_CHANGE", "nothing to import")

    # ---- candidates, all validated by the engine before any write ------------------------------------------------
    fact_candidate = raw_facts
    if new_facts:
        bom, eol, lines = split_file(raw_facts)
        for section, record in new_facts:
            _insert_fact(lines, section, FACT_SECTION_TITLES[section], serialise(record, {}))
        fact_candidate = bom + eol.join(lines).encode("utf-8")
    after = facts.check_bytes(fact_candidate)
    if after.errors:
        raise Refusal("VALIDATION_FAILED", "the engine rejects the fact base with the imported entries", problems(after.errors))
    kept = [_comparable(f) for f in after.factbase.facts if f.id in {b.id for b in before.factbase.facts}]
    if kept != [_comparable(f) for f in before.factbase.facts]:
        raise Refusal("VALIDATION_FAILED", "an existing fact would change; import cancelled")
    for section, record in new_facts:
        mine = after.factbase.get(record["id"])
        if mine is None or mine.status != record["status"] or mine.text != record["text"] or mine.confirmed_on != record["confirmed_on"]:
            raise Refusal("VALIDATION_FAILED", "an imported entry would not read back as entered (check special characters)")

    profile_candidate = raw_profile
    if identity_changed:
        new_profile = copy.deepcopy(profile_document)
        new_profile["identity"] = identity
        profile_candidate = dumps(new_profile)
    after_profile = profile.check_bytes(profile_candidate, after.factbase)
    if after_profile.errors or after_profile.profile is None:
        raise Refusal("VALIDATION_FAILED", "the engine rejects the profile with the imported identity", problems(after_profile.errors))

    content_changed = document != original_document
    content_candidate = raw_content
    if content_changed:
        content_candidate = dumps(document)
        after_content = content.check_bytes(content_candidate, after.factbase, after_profile.profile)
        if after_content.errors:
            raise Refusal("VALIDATION_FAILED", "the engine rejects the resume content with the imported entries",
                          problems(after_content.errors))
        reread = docvalidate.load(content_candidate, "CONTENT_")
        for key in ("blocks", "skills", "sections"):
            old = original_document.get(key) or []
            if (reread.get(key) or [])[:len(old)] != old:
                raise Refusal("VALIDATION_FAILED", "an existing part of the resume content would change; import cancelled")

    # ---- writes: facts first (the content refers to them), then content, then profile -----------------------------
    def no_check(_):
        return None

    if new_facts:
        atomic_replace(files["facts"], fact_candidate, canonical.sha256_text(raw_facts), no_check, root)
    if content_changed:
        if raw_content is None:
            target = Path(files["content"])
            relative = target.resolve().relative_to(Path(root).resolve()).parts
            if len(relative) == 2:
                ensure_dir(root, relative[0])
            elif len(relative) != 1:
                raise Refusal("CONFIG_ERROR", "the configured content path is nested too deeply to be created here")
            create_new(target, content_candidate, root)
        else:
            atomic_replace(files["content"], content_candidate, canonical.sha256_text(raw_content), no_check, root)
    if identity_changed:
        atomic_replace(files["profile"], profile_candidate, canonical.sha256_text(raw_profile), no_check, root)
    return {"ok": True, "message": "imported", "facts_added": len(new_facts), "confirmed": counts["confirmed"],
            "blocks_added": counts["blocks"], "bullets_added": counts["bullets"], "skills_added": counts["skills"],
            "parked": counts["parked"],
            "content_created": raw_content is None and content_changed, "identity_updated": identity_changed}


OPERATIONS = {
    "workspace_init": op_workspace_init,
    "cv_source_read": op_cv_source_read,
    "cv_parse": op_cv_parse,
    "cv_apply": op_cv_apply,
}
