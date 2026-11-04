"""Controlled import of a historical Markdown document into a proposed FactBase-v1.

Contract: `docs/design/CONTRACTS.md` section 1.5 and its M4 status. The engine contains **no** rule for any
particular document: everything that classifies a line comes from a `LegacyFactMap-v1` file that lives in
the user's workspace (`docs/IMPORT.md`).

Fail-closed by construction:

* a line the mapping cannot classify is `UNCLASSIFIED` (`FACT_UNMAPPED`) and is **never** written as a fact;
* a line that two rules classify differently is `AMBIGUOUS` and is not written either;
* nothing becomes `CONFIRMED` unless the mapping declares it twice (`allow_confirmed` and a rule status);
  a line rule can only **lower** the status its heading gave, never raise it;
* a date is set only from a pattern the mapping declares, and an invalid one rejects the line;
* the proposed output is parsed back by the real FactBase-v1 parser before anything is written.

The legacy document is only read. The report lists every non-blank line with its decision, its rule and a
hash of its text, **never the text itself**, so the report can be kept next to the private files without
copying their content. Reports and outputs carry no timestamp: the same inputs give the same bytes.
"""
import hashlib
import json
import re
import unicodedata
from collections import namedtuple

from . import canonical, docvalidate, facts

SCHEMA = "LegacyFactMap-v1"
REPORT_SCHEMA = "LegacyImportReport-v1"
PREFIX = "LEGACY_MAP_"

HEADING_ACTIONS = ("map", "ignore", "inherit", "technologies")
PATTERN_MAX = 300
LINE_MAX = 2000
TECHNOLOGY_MAX = 60
SECTION_ID_MAX = facts.ID_MAX - 11  # room for `.` and the ten hex digits of the fact id
ID_HEX_LENGTH = 10
SOURCE_HASH_LENGTH = 12
STATUS_RANK = {facts.CONFIRMED: 3, facts.DERIVED: 2, facts.NOT_CONFIRMED: 1, facts.WITHDRAWN: 1}

ACCEPTED = "ACCEPTED"
DUPLICATE = "DUPLICATE"
IGNORED = "IGNORED"
TECHNOLOGY = "TECHNOLOGY"
UNCLASSIFIED = "UNCLASSIFIED"
AMBIGUOUS = "AMBIGUOUS"
REJECTED = "REJECTED"
PROBLEM_DECISIONS = (UNCLASSIFIED, AMBIGUOUS, REJECTED)

_HEADING = re.compile(r"^(#{1,6}) +(.+)$")
_BULLET = re.compile(r"^[ \t]*(?:[-*+]|\d{1,3}[.)])[ \t]+(.+)$")
_CONTINUATION = re.compile(r"^(?: {2,}|\t)\S")

MappingResult = namedtuple("MappingResult", "mapping errors mapping_sha256")
ImportResult = namedtuple("ImportResult", "report facts_text complete")


class LegacyInputError(ValueError):
    """The legacy document or the mapping cannot be read at all. `code` is a stable machine code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Mapping:
    """A valid mapping, compiled. Built only by `check_mapping_*`."""

    def __init__(self, model, headings, status_rules, date_patterns, ignore_patterns):
        self._model = model
        self.allow_confirmed = model["allow_confirmed"]
        self.headings = headings
        self.status_rules = status_rules
        self.date_patterns = date_patterns
        self.ignore_patterns = ignore_patterns

    def to_model(self):
        return canonical.loads(canonical.canonical_json(self._model))

    @property
    def mapping_sha256(self):
        return canonical.fingerprint(self._model)


# --- the mapping file --------------------------------------------------------------------------------

def _pattern(reader, value, path):
    if not isinstance(value, str) or not value or len(value) > PATTERN_MAX:
        reader.error("BAD_PATTERN", path, "must be a non-empty regular expression of at most %d characters" % PATTERN_MAX)
        return None
    try:
        return re.compile(value)
    except re.error:
        reader.error("BAD_PATTERN", path, "is not a valid regular expression")
        return None


def check_mapping_data(document):
    reader = docvalidate.Reader(PREFIX)
    data, extensions = reader.obj(document, "", required=("schema", "headings"),
                                  optional=("allow_confirmed", "status_rules", "date_patterns", "ignore_patterns"))
    if data is None:
        return MappingResult(None, tuple(reader.problems), None)
    if "schema" in data and data["schema"] != SCHEMA:
        reader.error("UNKNOWN_SCHEMA", "schema", "unsupported schema, expected `%s`" % SCHEMA)
        return MappingResult(None, tuple(reader.problems), None)

    allow = False
    if "allow_confirmed" in data:
        flag = reader.boolean(data["allow_confirmed"], "allow_confirmed")
        allow = bool(flag)

    headings, model_headings = [], []
    raw = reader.lst(data["headings"], "headings", empty_ok=False) if "headings" in data else None
    for position, item in enumerate(raw or ()):
        path = docvalidate.index("headings", position)
        rule, rule_ext = reader.obj(item, path, required=("pattern",),
                                    optional=("action", "section", "title", "status", "lang", "level"))
        if rule is None:
            continue
        compiled = _pattern(reader, rule["pattern"], docvalidate.join(path, "pattern")) if "pattern" in rule else None
        action = "map"
        if "action" in rule:
            action = reader.choice(rule["action"], docvalidate.join(path, "action"), HEADING_ACTIONS)
        level = None
        if rule.get("level") is not None:
            level = reader.integer(rule["level"], docvalidate.join(path, "level"), 1, 6)
        record = {"pattern": rule.get("pattern") if compiled is not None else None, "action": action, "level": level}
        if action == "map":
            section = reader.ident(rule["section"], docvalidate.join(path, "section")) if "section" in rule else None
            if "section" not in rule:
                reader.error("MISSING_FIELD", docvalidate.join(path, "section"), "required by action `map`")
            elif section is not None and len(section) > SECTION_ID_MAX:
                reader.error("INVALID_ID", docvalidate.join(path, "section"),
                             "a section id may have at most %d characters here" % SECTION_ID_MAX)
                section = None
            status = reader.choice(rule["status"], docvalidate.join(path, "status"), facts.STATUSES) \
                if "status" in rule else None
            if "status" not in rule:
                reader.error("MISSING_FIELD", docvalidate.join(path, "status"), "required by action `map`")
            if status == facts.CONFIRMED and not allow:
                reader.error("CONFIRMED_NOT_ALLOWED", docvalidate.join(path, "status"),
                             "CONFIRMED needs `allow_confirmed: true` in the mapping")
                status = None
            title = lang = None
            if rule.get("title") is not None:
                title = reader.text(rule["title"], docvalidate.join(path, "title"))
                if title is not None and any(ch in title for ch in "{}"):
                    reader.error("INVALID_VALUE", docvalidate.join(path, "title"), "a title cannot hold braces")
                    title = None
            if rule.get("lang") is not None:
                lang = reader.lang(rule["lang"], docvalidate.join(path, "lang"))
            record.update({"section": section, "status": status, "title": title or section, "lang": lang})
        else:
            for key in ("section", "title", "status", "lang"):
                if key in rule:
                    reader.error("INVALID_RULE", docvalidate.join(path, key), "not allowed with action `%s`" % action)
        if rule_ext:
            record["extensions"] = rule_ext
        headings.append((compiled, record))
        model_headings.append(record)

    status_rules, model_status = [], []
    raw = reader.lst(data["status_rules"], "status_rules") if "status_rules" in data else None
    for position, item in enumerate(raw or ()):
        path = docvalidate.index("status_rules", position)
        rule, rule_ext = reader.obj(item, path, required=("pattern", "status"))
        if rule is None:
            continue
        compiled = _pattern(reader, rule["pattern"], docvalidate.join(path, "pattern")) if "pattern" in rule else None
        status = reader.choice(rule["status"], docvalidate.join(path, "status"), facts.STATUSES) \
            if "status" in rule else None
        if status == facts.CONFIRMED:
            reader.error("CONFIRMED_NOT_ALLOWED", docvalidate.join(path, "status"),
                         "a line rule can only lower a status, never set CONFIRMED")
            status = None
        if compiled is None or status is None:
            continue
        record = {"pattern": rule["pattern"], "status": status}
        if rule_ext:
            record["extensions"] = rule_ext
        status_rules.append((compiled, status))
        model_status.append(record)

    date_patterns, model_dates = [], []
    raw = reader.lst(data["date_patterns"], "date_patterns") if "date_patterns" in data else None
    for position, item in enumerate(raw or ()):
        path = docvalidate.index("date_patterns", position)
        compiled = _pattern(reader, item, path)
        if compiled is None:
            continue
        if compiled.groups != 1:
            reader.error("BAD_PATTERN", path, "a date pattern must hold exactly one capturing group")
            continue
        date_patterns.append(compiled)
        model_dates.append(item)

    ignore_patterns, model_ignores = [], []
    raw = reader.lst(data["ignore_patterns"], "ignore_patterns") if "ignore_patterns" in data else None
    for position, item in enumerate(raw or ()):
        compiled = _pattern(reader, item, docvalidate.index("ignore_patterns", position))
        if compiled is not None:
            ignore_patterns.append(compiled)
            model_ignores.append(item)

    if reader.problems:
        return MappingResult(None, tuple(sorted(reader.problems, key=lambda p: (p.path, p.code))), None)
    model = {"schema": SCHEMA, "allow_confirmed": allow, "headings": model_headings, "status_rules": model_status,
             "date_patterns": model_dates, "ignore_patterns": model_ignores}
    if extensions:
        model["extensions"] = extensions
    mapping = Mapping(model, headings, status_rules, date_patterns, ignore_patterns)
    return MappingResult(mapping, (), mapping.mapping_sha256)


def check_mapping_bytes(data):
    try:
        document = docvalidate.load(data, PREFIX)
    except docvalidate.DocumentError as error:
        return MappingResult(None, (docvalidate.Problem(error.code, str(error), ""),), None)
    return check_mapping_data(document)


def check_mapping_file(path):
    try:
        with open(str(path), "rb") as handle:
            data = handle.read()
    except OSError as error:
        return MappingResult(None, (docvalidate.Problem(PREFIX + "FILE_UNREADABLE",
                                                        "cannot read the file: %s" % error.strerror, ""),), None)
    return check_mapping_bytes(data)


# --- reading the legacy document ---------------------------------------------------------------------

def _has_control(text):
    return any(ch != "\t" and unicodedata.category(ch) in ("Cc", "Zl", "Zp") for ch in text)


def _collapse(text):
    return " ".join(text.split())


def _units(lines):
    """Split the document into units: ('blank'|'heading'|'bullet'|'text', first line, last line, raw lines)."""
    units, index, total = [], 0, len(lines)
    while index < total:
        raw = lines[index].rstrip()
        if not raw.strip():
            units.append(("blank", index + 1, index + 1, [""]))
            index += 1
        elif _HEADING.match(raw):
            units.append(("heading", index + 1, index + 1, [raw]))
            index += 1
        elif _BULLET.match(raw):
            end, block = index, [raw]
            while end + 1 < total:
                follow = lines[end + 1].rstrip()
                if follow.strip() and not _HEADING.match(follow) and not _BULLET.match(follow) \
                        and _CONTINUATION.match(follow):
                    block.append(follow)
                    end += 1
                else:
                    break
            units.append(("bullet", index + 1, end + 1, block))
            index = end + 1
        else:
            units.append(("text", index + 1, index + 1, [raw]))
            index += 1
    return units


def _context_for_heading(mapping, level, text, previous):
    """The context a heading opens: (context, rule index or None, decision, code)."""
    matches = []
    for number, (compiled, record) in enumerate(mapping.headings):
        if record["level"] is not None and record["level"] != level:
            continue
        if compiled.fullmatch(text):
            matches.append((number, record))
    if not matches:
        return {"state": "unmapped"}, None, "UNMAPPED", "FACT_UNMAPPED"
    effects = {(r["action"], r.get("section"), r.get("status"), r.get("lang")) for _n, r in matches}
    if len(effects) > 1:
        return {"state": "ambiguous"}, matches[0][0], "AMBIGUOUS", "LEGACY_AMBIGUOUS_HEADING"
    number, record = matches[0]
    action = record["action"]
    if action == "inherit":
        return previous, number, "INHERITED", None
    if action == "ignore":
        return {"state": "ignore"}, number, "IGNORED", "LEGACY_IGNORED_BY_RULE"
    if action == "technologies":
        return {"state": "technologies"}, number, "MAPPED", None
    return ({"state": "map", "section": record["section"], "status": record["status"], "lang": record["lang"],
             "title": record["title"], "rule": number}, number, "MAPPED", None)


def _classify_bullet(mapping, context, lines, line_no):
    """Decide one bullet. Returns an entry dict (the fact candidate is under `_fact`)."""
    entry = {"decision": None, "code": None}
    state = context["state"]
    if any(_has_control(raw) for raw in lines):
        entry.update(decision=REJECTED, code="LEGACY_CONTROL_CHARACTER")
        return entry
    if state in ("none", "unmapped"):
        entry.update(decision=UNCLASSIFIED, code="FACT_UNMAPPED")
        return entry
    if state == "ambiguous":
        entry.update(decision=AMBIGUOUS, code="LEGACY_AMBIGUOUS_HEADING")
        return entry
    if state == "ignore":
        entry.update(decision=IGNORED, code="LEGACY_IGNORED_BY_RULE")
        return entry
    first = _BULLET.match(lines[0]).group(1)
    text = _collapse(unicodedata.normalize("NFC", " ".join([first] + [part.strip() for part in lines[1:]])))
    if not text:
        entry.update(decision=REJECTED, code="LEGACY_EMPTY_TEXT")
        return entry
    if len(text) > LINE_MAX:
        entry.update(decision=REJECTED, code="LEGACY_LINE_TOO_LONG")
        return entry
    if state == "technologies":
        if len(text) > TECHNOLOGY_MAX or any(ch in text for ch in ",;{}"):
            entry.update(decision=REJECTED, code="LEGACY_TECHNOLOGY_UNSAFE")
        else:
            entry.update(decision=TECHNOLOGY, _technology=text)
        return entry
    if text.endswith("}"):
        entry.update(decision=REJECTED, code="LEGACY_TEXT_UNSAFE")
        return entry

    status = context["status"]
    lowered = {s for compiled, s in mapping.status_rules if compiled.search(text)}
    if len(lowered) > 1:
        entry.update(decision=AMBIGUOUS, code="LEGACY_CONFLICTING_STATUS_RULES")
        return entry
    if lowered:
        wanted = next(iter(lowered))
        if STATUS_RANK[wanted] > STATUS_RANK[status]:
            entry.update(decision=REJECTED, code="LEGACY_PROMOTION_REFUSED")
            return entry
        status = wanted

    dates = {m.group(1) for m in (compiled.search(text) for compiled in mapping.date_patterns) if m}
    date = None
    if len(dates) > 1:
        entry.update(decision=AMBIGUOUS, code="LEGACY_CONFLICTING_DATES")
        return entry
    if dates:
        found = next(iter(dates))
        if not facts.valid_date(found):
            entry.update(decision=REJECTED, code="LEGACY_INVALID_DATE")
            return entry
        date = found if status == facts.CONFIRMED else None

    section = context["section"]
    fact_id = "%s.%s" % (section, hashlib.sha256(text.encode("utf-8")).hexdigest()[:ID_HEX_LENGTH])
    entry.update(decision=ACCEPTED, section=section, status=status, fact_id=fact_id, dated=date is not None,
                 _fact={"id": fact_id, "section": section, "title": context["title"], "status": status,
                        "text": text, "lang": context["lang"], "date": date, "line": line_no})
    return entry


def _technologies_in(text, vocabulary):
    folded = canonical.fold(text)
    found = []
    for term in vocabulary:
        if re.search(r"(?<!\w)%s(?!\w)" % re.escape(canonical.fold(term)), folded):
            found.append(term)
    return found


def _render(candidates, source_hash, vocabulary):
    sections, order = {}, []
    for fact in candidates:
        if fact["section"] not in sections:
            sections[fact["section"]] = (fact["title"], [])
            order.append(fact["section"])
        sections[fact["section"]][1].append(fact)
    out = [facts.MARKER,
           "<!-- Proposed by `modularcv facts import` (LegacyFactMap-v1). Review every fact before relying on it. -->",
           ""]
    for section in order:
        title, items = sections[section]
        out.append("## %s {#%s}" % (title, section))
        out.append("")
        for fact in items:
            attributes = []
            if fact["lang"]:
                attributes.append("lang: %s" % fact["lang"])
            if fact["date"]:
                attributes.append("confirmed_on: %s" % fact["date"])
            technologies = _technologies_in(fact["text"], vocabulary)
            if technologies:
                attributes.append("technologies: %s" % ", ".join(technologies))
            attributes.append("source: legacy-import:%s:L%d" % (source_hash[:SOURCE_HASH_LENGTH], fact["line"]))
            out.append("- [%s] %s: %s {%s}" % (fact["id"], fact["status"], fact["text"], "; ".join(attributes)))
        out.append("")
    return "\n".join(out)


def run(mapping, data):
    """Import `data` (bytes of the legacy document) with `mapping`. Never writes. Returns an `ImportResult`.

    Raises `LegacyInputError` (`LEGACY_NOT_UTF8`) when the document is not text.
    """
    source_hash = canonical.sha256_text(data)
    try:
        text = canonical.decode_text(data)
    except canonical.CanonicalError:
        raise LegacyInputError("LEGACY_NOT_UTF8", "the legacy document is not valid UTF-8")
    lines = canonical.normalise_text(text).split("\n")

    entries, blank = [], 0
    context = {"state": "none"}
    vocabulary = []
    for kind, first, last, raw in _units(lines):
        if kind == "blank":
            blank += 1
            continue
        entry = {"line": first, "end_line": last, "kind": kind.upper(), "rule": None, "section": None, "status": None,
                 "fact_id": None, "code": None, "decision": None,
                 "unit_sha256": canonical.sha256_text("\n".join(raw))}
        if kind == "heading":
            match = _HEADING.match(raw[0])
            context, rule, decision, code = _context_for_heading(mapping, len(match.group(1)), match.group(2).strip(),
                                                                 context)
            entry.update(decision=decision, code=code, rule=rule)
        elif kind == "bullet":
            entry.update(_classify_bullet(mapping, context, raw, first))
            entry["rule"] = context.get("rule")
        else:
            stripped = raw[0].strip()
            if any(compiled.fullmatch(stripped) for compiled in mapping.ignore_patterns):
                entry.update(decision=IGNORED, code="LEGACY_IGNORED_BY_PATTERN")
            else:
                entry.update(decision=UNCLASSIFIED, code="FACT_UNMAPPED")
        entries.append(entry)

    # Technology vocabulary, in document order; a repeated term is a harmless duplicate.
    seen_terms = set()
    for entry in entries:
        term = entry.pop("_technology", None)
        if term is None:
            continue
        if canonical.fold(term) in seen_terms:
            entry.update(decision=DUPLICATE, code="LEGACY_DUPLICATE_TEXT")
        else:
            seen_terms.add(canonical.fold(term))
            vocabulary.append(term)

    # Duplicates and ambiguities between the accepted candidates.
    groups = {}
    for entry in entries:
        if entry["decision"] == ACCEPTED:
            groups.setdefault(canonical.fold(entry["_fact"]["text"]), []).append(entry)
    for group in groups.values():
        if len(group) < 2:
            continue
        if len({member["status"] for member in group}) > 1:
            for member in group:
                member.update(decision=AMBIGUOUS, code="LEGACY_CONFLICTING_DUPLICATES", fact_id=None)
                member["duplicate_of"] = group[0]["line"]
            continue
        for member in group[1:]:
            member.update(decision=DUPLICATE, code="LEGACY_DUPLICATE_TEXT", fact_id=None)
            member["duplicate_of"] = group[0]["line"]
    taken = {}
    for entry in entries:
        if entry["decision"] != ACCEPTED:
            continue
        previous = taken.setdefault(entry["fact_id"], entry["line"])
        if previous != entry["line"]:
            entry.update(decision=REJECTED, code="LEGACY_ID_COLLISION", fact_id=None)

    candidates = [entry["_fact"] for entry in entries if entry["decision"] == ACCEPTED]
    for entry in entries:
        entry.pop("_fact", None)
        if entry["decision"] not in (ACCEPTED, DUPLICATE) and entry["kind"] == "BULLET":
            entry["section"], entry["status"] = None, None
    counts = {name: 0 for name in (ACCEPTED, DUPLICATE, IGNORED, TECHNOLOGY, UNCLASSIFIED, AMBIGUOUS, REJECTED)}
    for entry in entries:
        if entry["kind"] != "HEADING" and entry["decision"] in counts:
            counts[entry["decision"]] += 1

    facts_text, output = None, None
    if candidates:
        proposed = _render(candidates, source_hash, vocabulary)
        check = facts.check_text(proposed)
        if check.errors:
            raise LegacyInputError("LEGACY_OUTPUT_INVALID", "the proposed fact base failed FactBase-v1 validation (%s)"
                                   % check.errors[0].code)
        facts_text = proposed
        output = {"fact_count": len(check.factbase.facts), "factbase_sha256": check.factbase.factbase_sha256,
                  "facts_source_sha256": check.facts_source_sha256}

    problems = sum(counts[name] for name in PROBLEM_DECISIONS)
    by_status = {status: 0 for status in facts.STATUSES}
    for fact in candidates:
        by_status[fact["status"]] += 1
    report = {
        "schema": REPORT_SCHEMA,
        "mapping_sha256": mapping.mapping_sha256,
        "legacy_source_sha256": source_hash,
        "blank_lines": blank,
        "counts": counts,
        "problems": problems,
        "facts_by_status": by_status,
        "technologies_declared": len(vocabulary),
        "output": output,
        "lines": [{key: entry[key] for key in sorted(entry)} for entry in entries],
    }
    return ImportResult(report, facts_text, problems == 0 and bool(candidates))
