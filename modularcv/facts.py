"""FactBase-v1: strict parser and canonical model of `facts.md`.

Contract: `docs/design/CONTRACTS.md` section 1. The file is human-edited Markdown; every line must be a
marker, a heading, a comment, a fact, a continuation of a fact, or blank. Anything else is an error:
nothing the parser does not understand is ever treated as usable prose.

Only `CONFIRMED` facts are publishable. No function here changes a status.
Error messages never repeat the text of a fact (the file may be private).
"""
import datetime
import re
import unicodedata
from collections import namedtuple

from . import canonical

SCHEMA = "FactBase-v1"
MARKER = "<!-- modularcv: %s -->" % SCHEMA

CONFIRMED = "CONFIRMED"
DERIVED = "DERIVED"
NOT_CONFIRMED = "NOT_CONFIRMED"
WITHDRAWN = "WITHDRAWN"
STATUSES = (CONFIRMED, DERIVED, NOT_CONFIRMED, WITHDRAWN)

ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
ID_MAX = 80
EXTENSION_PATTERN = re.compile(r"^x-[a-z0-9]+(?:[.-][a-z0-9]+)*$")
LANG_PATTERN = re.compile(r"^[a-z]{2}$")
DATE_PATTERN = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$", re.ASCII)

_MARKER_LINE = re.compile(r"^<!--\s*modularcv:\s*(\S+)\s*-->$")
_SECTION = re.compile(r"^## +(?P<title>.*?)(?: +\{#(?P<id>[^}\s]*)\})? *$")
_TITLE = re.compile(r"^# +\S")
_FACT = re.compile(r"^- \[(?P<id>[^\]]*)\] +(?P<status>[^\s:]+):(?: +(?P<rest>.*))?$")
_CONTINUATION = re.compile(r"^ {4}\S")

ATTRIBUTES = ("lang", "confirmed_on", "technologies", "capabilities", "source", "supersedes", "note")
_LIST_ATTRIBUTES = ("technologies", "capabilities")


class FactError(namedtuple("FactError", "code message line")):
    """One problem found in the file. `line` is 1-based, or None for a whole-file problem."""

    def as_dict(self):
        return {"code": self.code, "line": self.line, "message": self.message}


Fact = namedtuple(
    "Fact",
    "id status text section lang confirmed_on technologies capabilities source supersedes note extensions line",
)


class FactBaseError(ValueError):
    """The file is not a valid FactBase-v1. `errors` holds every problem found, in line order."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        first = self.errors[0]
        where = "" if first.line is None else " (line %d)" % first.line
        super().__init__("%s%s: %s" % (first.code, where, first.message))

    @property
    def code(self):
        return self.errors[0].code


class FactBase:
    """A valid fact base. Immutable by convention: there is no way to change a status."""

    def __init__(self, facts, source_sha256):
        self.facts = tuple(facts)
        self.facts_source_sha256 = source_sha256

    def publishable(self):
        """The only facts a generated document may rely on: `CONFIRMED`, nothing else."""
        return tuple(fact for fact in self.facts if fact.status == CONFIRMED)

    def by_status(self, status):
        return tuple(fact for fact in self.facts if fact.status == status)

    def get(self, fact_id):
        for fact in self.facts:
            if fact.id == fact_id:
                return fact
        return None

    def counts(self):
        return {status: len(self.by_status(status)) for status in STATUSES}

    def to_model(self):
        """The canonical model of the contract. Line numbers are not part of it."""
        def model(fact):
            record = {
                "id": fact.id,
                "status": fact.status,
                "text": fact.text,
                "section": fact.section,
                "lang": fact.lang,
                "confirmed_on": fact.confirmed_on,
                "technologies": list(fact.technologies),
                "capabilities": list(fact.capabilities),
                "source": fact.source,
                "supersedes": fact.supersedes,
                "note": fact.note,
            }
            if fact.extensions:  # omitted when empty, so files without `x-` keep their fingerprint
                record["extensions"] = dict(fact.extensions)
            return record

        return {"schema": SCHEMA, "facts": [model(fact) for fact in self.facts]}

    @property
    def factbase_sha256(self):
        return canonical.fingerprint(self.to_model())


CheckResult = namedtuple("CheckResult", "factbase errors warnings facts_source_sha256")


# --- helpers ---------------------------------------------------------------------------------------

def _collapse(text):
    return " ".join(text.split())


def valid_id(value):
    return bool(value) and len(value) <= ID_MAX and ID_PATTERN.match(value) is not None


def valid_date(value):
    """`YYYY`, `YYYY-MM` or `YYYY-MM-DD`, calendar-valid. No time, no zone."""
    match = DATE_PATTERN.match(value)
    if not match:
        return False
    year, month, day = match.groups()
    try:
        datetime.date(int(year), int(month) if month else 1, int(day) if day else 1)
    except ValueError:
        return False
    return True


def slugify(title):
    folded = unicodedata.normalize("NFKD", title)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


def _split_attributes(text):
    """Separate the trailing `{...}` attribute block from the text.

    Returns (text, block). `block` is None when the text does not end with `}` and False when it does
    but no `{` opens it (an error: the closing brace must belong to an attribute block).
    """
    if not text.endswith("}"):
        return text, None
    start = text.rfind("{")
    if start == -1:
        return text, False
    return text[:start].rstrip(), text[start + 1:-1]


def _parse_attribute_block(block, add):
    """Parse `key: value; key: value`. `add(code, message)` records an error. Returns a dict."""
    values = {}
    for part in block.split(";"):
        part = part.strip()
        if not part:
            continue
        key, colon, value = part.partition(":")
        key, value = key.strip(), value.strip()
        if not colon or not key:
            add("FACT_BAD_ATTRIBUTES", "an attribute must read `name: value`")
            continue
        if key.startswith("x-"):
            if not EXTENSION_PATTERN.match(key):
                add("FACT_BAD_ATTRIBUTES", "an extension name must read `x-` then a lowercase identifier")
                continue
        elif key not in ATTRIBUTES:
            add("FACT_UNKNOWN_ATTRIBUTE", "unknown attribute `%s`" % key)
            continue
        if key in values:
            add("FACT_DUPLICATE_ATTRIBUTE", "attribute `%s` appears twice" % key)
            continue
        if not value:
            add("FACT_EMPTY_ATTRIBUTE", "attribute `%s` has no value" % key)
            continue
        values[key] = value
    return values


# --- parser ----------------------------------------------------------------------------------------

def _parse(text, require_confirmation_date):
    errors, warnings = [], []

    def error(code, message, line=None):
        errors.append(FactError(code, message, line))

    if not text.strip():
        error("FACT_EMPTY_FILE", "the file is empty")
        return [], errors, warnings

    lines = text.split("\n")
    first = next(index for index, line in enumerate(lines) if line.strip())
    marker = _MARKER_LINE.match(lines[first].strip())
    if marker is None:
        error("FACT_MARKER_MISSING", "the first non-blank line must be `%s`" % MARKER, first + 1)
        return [], errors, warnings
    if marker.group(1) != SCHEMA:
        error("FACT_UNKNOWN_SCHEMA", "unsupported schema `%s`, expected `%s`" % (marker.group(1), SCHEMA), first + 1)
        return [], errors, warnings

    facts = []
    pending = None  # dict of the fact being read (its continuation lines may follow)
    section = None
    section_ids = {}
    ids = {}
    in_comment = False

    def close():
        nonlocal pending
        if pending is not None:
            _finish_fact(pending, section_of=pending["section"], facts=facts, ids=ids, error=error,
                         require_confirmation_date=require_confirmation_date)
            pending = None

    for index in range(first + 1, len(lines)):
        number = index + 1
        line = lines[index]

        if in_comment:
            end = line.find("-->")
            if end == -1:
                continue
            in_comment = False
            if line[end + 3:].strip():
                error("FACT_UNPARSED_LINE", "text follows the end of a comment", number)
            continue

        if not line.strip():
            close()
            continue

        bad = [ch for ch in line if ch != "\t" and unicodedata.category(ch) in ("Cc", "Zl", "Zp")]
        if bad:
            close()
            error("FACT_CONTROL_CHARACTER", "the line holds a control or separator character", number)
            continue

        if pending is not None and _CONTINUATION.match(line):
            pending["lines"].append(line.strip())
            continue

        close()

        if line.lstrip().startswith("<!--"):
            if line != line.lstrip():
                error("FACT_UNPARSED_LINE", "a comment must start at the beginning of the line", number)
                continue
            body = line[4:]
            end = body.find("-->")
            if end == -1:
                in_comment = True
            elif body[end + 3:].strip():
                error("FACT_UNPARSED_LINE", "text follows the end of a comment", number)
            continue

        section_match = _SECTION.match(line)
        if section_match is not None:
            title, explicit = section_match.group("title"), section_match.group("id")
            section_id = explicit if explicit is not None else slugify(title)
            if not valid_id(section_id):
                error("FACT_BAD_SECTION_ID", "the section id is empty or not a valid identifier", number)
                section = None
            elif section_id in section_ids:
                error("FACT_DUPLICATE_SECTION", "section `%s` already defined at line %d" % (section_id, section_ids[section_id]), number)
                section = section_id
            else:
                section_ids[section_id] = number
                section = section_id
            continue
        if _TITLE.match(line):
            continue

        fact_match = _FACT.match(line)
        if fact_match is not None:
            pending = {
                "line": number,
                "id": fact_match.group("id"),
                "status": fact_match.group("status"),
                "lines": [(fact_match.group("rest") or "").strip()],
                "section": section,
            }
            continue

        if line.startswith("    ") or line.startswith("\t"):
            error("FACT_UNPARSED_LINE", "an indented line must continue a fact on the line just before", number)
        elif line.startswith("- "):
            error("FACT_UNPARSED_LINE", "a list item must read `- [id] STATUS: text`", number)
        else:
            error("FACT_UNPARSED_LINE", "the line is not a fact, a heading, a comment or a continuation", number)

    close()
    if in_comment:
        error("FACT_UNTERMINATED_COMMENT", "a comment is never closed", None)

    by_id = {fact.id: fact for fact in facts}
    for fact in facts:
        if fact.supersedes is None:
            continue
        target = by_id.get(fact.supersedes)
        if target is None:
            error("FACT_BAD_SUPERSEDES", "fact `%s` supersedes `%s`, which does not exist" % (fact.id, fact.supersedes), fact.line)
        elif target.id == fact.id:
            error("FACT_BAD_SUPERSEDES", "fact `%s` cannot supersede itself" % fact.id, fact.line)
        elif target.status != WITHDRAWN:
            error("FACT_BAD_SUPERSEDES", "fact `%s` supersedes `%s`, which is not WITHDRAWN" % (fact.id, target.id), fact.line)

    if not facts and not errors:
        warnings.append(FactError("FACT_NO_FACTS", "the file holds the marker but no fact", None))
    errors.sort(key=lambda item: (item.line is None, item.line or 0, item.code))
    return facts, errors, warnings


def _finish_fact(pending, section_of, facts, ids, error, require_confirmation_date):
    line = pending["line"]
    problems = []

    def add(code, message):
        problems.append((code, message))

    fact_id, status = pending["id"], pending["status"]
    if not valid_id(fact_id):
        add("FACT_INVALID_ID", "the fact id is empty, longer than %d characters or not a valid identifier" % ID_MAX)
    elif fact_id in ids:
        add("FACT_DUPLICATE_ID", "fact id `%s` already defined at line %d" % (fact_id, ids[fact_id]))
    else:
        ids[fact_id] = line
    if status not in STATUSES:
        add("FACT_UNKNOWN_STATUS", "unknown status `%s`, expected one of %s" % (status, ", ".join(STATUSES)))
    if section_of is None:
        add("FACT_OUTSIDE_SECTION", "a fact must sit under a `## section` heading")

    body = _collapse(" ".join(part for part in pending["lines"] if part))
    body, block = _split_attributes(body)
    attributes = {}
    if block is False:
        add("FACT_BAD_ATTRIBUTES", "the text ends with `}` but no `{` opens an attribute block")
    elif block is not None:
        attributes = _parse_attribute_block(block, add)
    text = _collapse(body)
    if not text:
        add("FACT_EMPTY_TEXT", "the fact has no text")

    lang = attributes.get("lang")
    if lang is not None and not LANG_PATTERN.match(lang):
        add("FACT_INVALID_LANG", "`lang` must be a two-letter lowercase code")
    confirmed_on = attributes.get("confirmed_on")
    if confirmed_on is not None and not valid_date(confirmed_on):
        add("FACT_INVALID_DATE", "`confirmed_on` must be a valid YYYY, YYYY-MM or YYYY-MM-DD date")
    supersedes = attributes.get("supersedes")
    if supersedes is not None and not valid_id(supersedes):
        add("FACT_INVALID_ID", "`supersedes` is not a valid identifier")
    technologies = _items(attributes.get("technologies"))
    capabilities = _items(attributes.get("capabilities"))
    if any(not valid_id(item) for item in capabilities):
        add("FACT_INVALID_CAPABILITY", "each capability must be a lowercase identifier")
    if "technologies" in attributes and not technologies:
        add("FACT_EMPTY_ATTRIBUTE", "attribute `technologies` has no value")
    if "capabilities" in attributes and not capabilities:
        add("FACT_EMPTY_ATTRIBUTE", "attribute `capabilities` has no value")
    if require_confirmation_date and status == CONFIRMED and confirmed_on is None:
        add("FACT_DATE_REQUIRED", "this workspace requires `confirmed_on` on every CONFIRMED fact")

    if problems:
        for code, message in problems:
            error(code, message, line)
        return
    facts.append(Fact(
        id=fact_id, status=status, text=text, section=section_of, lang=lang, confirmed_on=confirmed_on,
        technologies=technologies, capabilities=capabilities, source=attributes.get("source"),
        supersedes=supersedes, note=attributes.get("note"), line=line,
        extensions=tuple(sorted((k, _collapse(v)) for k, v in attributes.items() if k.startswith("x-"))),
    ))


def _items(value):
    if value is None:
        return ()
    return tuple(item for item in (_collapse(part) for part in value.split(",")) if item)


# --- public API ------------------------------------------------------------------------------------

def check_text(text, require_confirmation_date=False, source_sha256=None):
    """Parse `text` (str). Never raises on a bad file: returns a `CheckResult`.

    `factbase` is None whenever `errors` is not empty.
    """
    if source_sha256 is None:
        source_sha256 = canonical.sha256_text(text)
    normalised = canonical.normalise_text(text)
    facts, errors, warnings = _parse(normalised, require_confirmation_date)
    factbase = None if errors else FactBase(facts, source_sha256)
    return CheckResult(factbase, tuple(errors), tuple(warnings), source_sha256)


def check_bytes(data, require_confirmation_date=False):
    """Like `check_text` on raw file bytes: strict UTF-8, BOM tolerated, source hash on the bytes."""
    source_sha256 = canonical.sha256_text(data)
    try:
        text = canonical.decode_text(data)
    except canonical.CanonicalError as error:
        return CheckResult(None, (FactError("FACT_NOT_UTF8", str(error), None),), (), source_sha256)
    return check_text(text, require_confirmation_date, source_sha256)


def check_file(path, require_confirmation_date=False):
    """Like `check_bytes` on a file. An unreadable file is `FACT_FILE_UNREADABLE`."""
    try:
        with open(str(path), "rb") as handle:
            data = handle.read()
    except OSError as error:
        return CheckResult(None, (FactError("FACT_FILE_UNREADABLE", "cannot read the file: %s" % error.strerror, None),), (), None)
    return check_bytes(data, require_confirmation_date)


def parse_text(text, require_confirmation_date=False):
    """The fact base of `text`, or `FactBaseError` carrying every error."""
    result = check_text(text, require_confirmation_date)
    if result.errors:
        raise FactBaseError(result.errors)
    return result.factbase


def parse_file(path, require_confirmation_date=False):
    result = check_file(path, require_confirmation_date)
    if result.errors:
        raise FactBaseError(result.errors)
    return result.factbase
