"""JobOffer-v1: the engine's only input about a job posting (`offers/<job_key>.json`).

Contract: `docs/design/CONTRACTS.md` section 4 and its M6 status (section 4.1). An offer is **external, untrusted data**:
its text is searched for the terms a taxonomy declares and is never read as an instruction. Nothing here calls a model,
the network or an adapter, and the engine claims no semantic understanding of the posting: requirements come from
(a) the explicit `requirements` list when the offer has one and (b) exact, whole-word matches of declared taxonomy
spellings in the description, grouped by the zone (requirements, responsibilities, ...) they appear in.

Error messages and reports never repeat a value of the offer (see `docvalidate`).
"""
import copy
import datetime
import re
import unicodedata
from collections import namedtuple

from . import canonical, docvalidate, facts, profile

SCHEMA = "JobOffer-v1"
PREFIX = "OFFER_"
LANGUAGES = ("fr", "en", "auto")
EMPLOYMENT_KINDS = profile.EMPLOYMENT_KINDS
PRIORITIES = ("REQUIRED", "PREFERRED")
DESCRIPTION_MAX = 100000
LINE_MAX = 300
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Function words used by the deterministic language detector (casefolded, accents removed). Small on purpose: it only
# decides between `en` and `fr` and records that it did so; a tie is reported, never guessed.
_STOPWORDS = {
    "en": frozenset("the and of to in for with you we are will a is on as be our your or an at by this that".split()),
    "fr": frozenset("le la les des et de du pour avec vous nous est une un en sur au aux dans par que qui notre votre ou ce".split()),
}

CheckResult = namedtuple("CheckResult", "offer errors warnings offer_source_sha256")


class OfferError(ValueError):
    """The document is not a valid JobOffer-v1. `errors` holds every problem found."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        first = self.errors[0]
        super().__init__("%s (%s): %s" % (first.code, first.path or "document", first.message))

    @property
    def code(self):
        return self.errors[0].code


class JobOffer:
    """A valid offer. Read-only by convention: accessors return copies."""

    def __init__(self, model, source_sha256):
        self._model = model
        self.offer_source_sha256 = source_sha256

    def to_model(self):
        return copy.deepcopy(self._model)

    @property
    def job_key(self):
        return self._model["job_key"]

    @property
    def declared_language(self):
        return self._model["language"]

    @property
    def employment_type(self):
        return self._model["employment_type"]

    @property
    def description(self):
        return self._model["description"]

    @property
    def description_sha256(self):
        return self._model["description_sha256"]

    @property
    def explicit_requirements(self):
        return copy.deepcopy(self._model["requirements"])

    @property
    def offer_sha256(self):
        """Canonical fingerprint of the identity of the offer (CONTRACTS.md section 4). Timestamps, URLs and other
        informational fields never take part. The explicit `requirements` join the identity only when there are some,
        so an offer without them keeps exactly the fingerprint the contract defines."""
        model = self._model
        identity = {key: model[key] for key in ("job_key", "title", "company", "location", "description", "language",
                                                "employment_type")}
        if model["requirements"]:
            identity["requirements"] = model["requirements"]
        return canonical.fingerprint(identity)

    def resolve_language(self, default=None):
        """`(language, method)`: the declared language, else the deterministic detector, else `default`.

        `method` is `declared`, `detected`, `default` or None when nothing decides (then `language` is None)."""
        if self.declared_language != "auto":
            return self.declared_language, "declared"
        detected = detect_language(self._model["title"] + "\n" + self._model["description"])
        if detected is not None:
            return detected, "detected"
        if default in ("fr", "en"):
            return default, "default"
        return None, None


def detect_language(text):
    """`en`, `fr` or None (no clear winner). Counts function words only; deterministic and explainable."""
    words = [canonical.fold(word) for word in re.findall(r"[^\W\d_]+", text)]
    scores = {language: sum(1 for word in words if word in vocabulary) for language, vocabulary in _STOPWORDS.items()}
    if scores["en"] == scores["fr"]:
        return None
    return "en" if scores["en"] > scores["fr"] else "fr"


# --- checking ---------------------------------------------------------------------------------------------

def _line(reader, value, path, limit=LINE_MAX):
    text = reader.text(value, path)
    if text is not None and len(text) > limit:
        reader.error("TOO_LONG", path, "the text is longer than %d characters" % limit)
        return None
    return text


def _description(reader, value, path):
    """The posting text: NFC, LF line endings, trailing spaces and outer blank lines dropped, tabs and line breaks kept."""
    if not isinstance(value, str):
        reader.error("BAD_TYPE", path, "must be a string")
        return None, None
    if any(unicodedata.category(ch) in ("Cc", "Zl", "Zp") and ch not in "\n\r\t" for ch in value):
        reader.error("CONTROL_CHARACTER", path, "the value holds a control or separator character")
        return None, None
    raw_hash = canonical.sha256_text(value)
    text = "\n".join(line.rstrip() for line in canonical.normalise_text(value).split("\n")).strip("\n")
    if not text.strip():
        reader.error("EMPTY_VALUE", path, "must not be empty")
        return None, None
    if len(text) > DESCRIPTION_MAX:
        reader.error("TOO_LONG", path, "the description is longer than %d characters" % DESCRIPTION_MAX)
        return None, None
    return text, raw_hash


def _check_requirements(reader, value, path):
    items = reader.lst(value, path)
    entries, ids, terms = [], set(), {}
    for position, item in enumerate(items or ()):
        item_path = docvalidate.index(path, position)
        data, extensions = reader.obj(item, item_path, required=("id", "term", "priority"))
        if data is None:
            continue
        entry_id = reader.ident(data["id"], docvalidate.join(item_path, "id")) if "id" in data else None
        term = _line(reader, data["term"], docvalidate.join(item_path, "term"), 100) if "term" in data else None
        priority = reader.choice(data["priority"], docvalidate.join(item_path, "priority"), PRIORITIES) \
            if "priority" in data else None
        if entry_id is not None:
            if entry_id in ids:
                reader.error("DUPLICATE_ID", docvalidate.join(item_path, "id"), "this requirement id is already used")
                continue
            ids.add(entry_id)
        if entry_id is None or term is None or priority is None:
            continue
        key = canonical.fold(term)
        if key in terms:
            reader.error("REQUIREMENT_CONFLICT" if terms[key] != priority else "DUPLICATE_VALUE", item_path,
                         "the same term is listed twice" + (" with another priority" if terms[key] != priority else ""))
            continue
        terms[key] = priority
        entry = {"id": entry_id, "term": term, "priority": priority}
        if extensions:
            entry["extensions"] = extensions
        entries.append(entry)
    return sorted(entries, key=lambda entry: entry["id"])


def _timestamp(reader, value, path):
    if not isinstance(value, str) or not _TIMESTAMP.match(value):
        reader.error("INVALID_VALUE", path, "must read YYYY-MM-DDTHH:MM:SSZ (UTC)")
        return None
    try:
        datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        reader.error("INVALID_VALUE", path, "must read YYYY-MM-DDTHH:MM:SSZ (UTC)")
        return None
    return value


def check_data(document, source_sha256=None):
    """Check an already decoded JSON value. `offer` is None when `errors` is not empty."""
    reader = docvalidate.Reader(PREFIX)
    optional = ("language", "employment_type", "location", "workplace_type", "source_url", "source_system", "posted_on",
                "captured_at", "source_ref", "description_sha256", "requirements")
    data, extensions = reader.obj(document, "", required=("schema", "job_key", "title", "company", "description"),
                                  optional=optional)
    if data is None:
        return CheckResult(None, tuple(reader.problems), (), source_sha256)
    if "schema" in data and data["schema"] != SCHEMA:
        reader.error("UNKNOWN_SCHEMA", "schema", "unsupported schema, expected `%s`" % SCHEMA)
        return CheckResult(None, tuple(reader.problems), (), source_sha256)

    job_key = reader.ident(data["job_key"], "job_key") if "job_key" in data else None
    title = _line(reader, data["title"], "title") if "title" in data else None
    company = _line(reader, data["company"], "company") if "company" in data else None
    description, raw_hash = _description(reader, data["description"], "description") if "description" in data else (None, None)
    language = "auto"
    if data.get("language") is not None:
        language = reader.choice(data["language"], "language", LANGUAGES)
    employment = "UNSPECIFIED"
    if data.get("employment_type") is not None:
        employment = reader.choice(data["employment_type"], "employment_type", EMPLOYMENT_KINDS)
    informational = {}
    for name in ("location", "workplace_type", "source_system", "source_ref"):
        informational[name] = _line(reader, data[name], name, 200) if data.get(name) is not None else None
    url = None
    if data.get("source_url") is not None:
        url = _line(reader, data["source_url"], "source_url", 500)
        if url is not None and (not re.match(r"^https?://\S+$", url)):
            reader.error("INVALID_VALUE", "source_url", "must be an http or https address with no space")
            url = None
    posted_on = None
    if data.get("posted_on") is not None:
        posted_on = data["posted_on"]
        if not isinstance(posted_on, str) or not facts.valid_date(posted_on):
            reader.error("INVALID_VALUE", "posted_on", "must be a calendar-valid date (YYYY-MM-DD, YYYY-MM or YYYY)")
            posted_on = None
    captured_at = _timestamp(reader, data["captured_at"], "captured_at") if data.get("captured_at") is not None else None
    if data.get("description_sha256") is not None and raw_hash is not None:
        supplied = data["description_sha256"]
        if not isinstance(supplied, str) or supplied != raw_hash:
            reader.error("DESCRIPTION_HASH_MISMATCH", "description_sha256",
                         "the supplied hash does not match the hash of the description")
    requirements = _check_requirements(reader, data["requirements"], "requirements") if "requirements" in data else []

    if reader.problems or None in (job_key, title, company, description, language, employment):
        return CheckResult(None, tuple(sorted(reader.problems, key=lambda p: (p.path, p.code))), (), source_sha256)
    model = {"schema": SCHEMA, "job_key": job_key, "title": title, "company": company, "description": description,
             "description_sha256": raw_hash, "language": language, "employment_type": employment,
             "source_url": url, "posted_on": posted_on, "captured_at": captured_at, "requirements": requirements}
    model.update(informational)
    if extensions:
        model["extensions"] = extensions
    return CheckResult(JobOffer(model, source_sha256), (), (), source_sha256)


def check_bytes(data):
    source_sha256 = canonical.sha256_text(data)
    try:
        document = docvalidate.load(data, PREFIX)
    except docvalidate.DocumentError as error:
        return CheckResult(None, (docvalidate.Problem(error.code, str(error), ""),), (), source_sha256)
    return check_data(document, source_sha256)


def check_file(path):
    try:
        with open(str(path), "rb") as handle:
            data = handle.read()
    except OSError as error:
        return CheckResult(None, (docvalidate.Problem(PREFIX + "FILE_UNREADABLE",
                                                      "cannot read the file: %s" % error.strerror, ""),), (), None)
    return check_bytes(data)


# --- requirements -----------------------------------------------------------------------------------------

def extract_requirements(offer, taxonomy, language):
    """`(requirements, problems)`: the requirements of an offer under a taxonomy, in a stable order.

    Each requirement is `{id, term_id, kind, label, priority, weight, sources}`. `term_id` is None for an explicit
    term the taxonomy does not know (`label` then holds it, and the matrix will answer `ABSENT`, never a match).
    Explicit entries keep their id; terms found in the description are named `req.<term id>`. Two requirements for
    one term are refused (`OFFER_REQUIREMENT_DUPLICATE_TERM`), and so is an id collision."""
    problems = []
    weights = taxonomy.priority_weights
    by_term, by_id, explicit_ids = {}, {}, set()
    for entry in offer.explicit_requirements:
        term_id = taxonomy.resolve(entry["term"], language)
        record = {"id": entry["id"], "term_id": term_id, "kind": taxonomy.term(term_id)["kind"] if term_id else None,
                  "label": None if term_id else entry["term"], "priority": entry["priority"],
                  "weight": weights[entry["priority"]], "sources": ["declared"]}
        explicit_ids.add(entry["id"])
        if term_id is not None:
            if term_id in by_term:
                problems.append(docvalidate.Problem(PREFIX + "REQUIREMENT_DUPLICATE_TERM",
                                                    "two explicit requirements resolve to the same taxonomy term", "requirements"))
                continue
            by_term[term_id] = record
        by_id[entry["id"]] = record
    for detection in taxonomy.detect(offer.description, language):
        priorities, weight_found = set(), 0.0
        for zone_id in detection.zones:
            zone = taxonomy.zone(zone_id)
            priorities.add(zone["priority"])
            weight_found = max(weight_found, zone["weight"])
        priority = "REQUIRED" if "REQUIRED" in priorities else "PREFERRED"
        existing = by_term.get(detection.term_id)
        if existing is not None:
            if existing["priority"] == "PREFERRED" and priority == "REQUIRED":
                existing["priority"] = "REQUIRED"
            existing["weight"] = max(existing["weight"], weight_found)
            existing["sources"] = sorted(set(existing["sources"]) | set(detection.zones))
            continue
        generated = "req." + detection.term_id
        if generated in explicit_ids:
            problems.append(docvalidate.Problem(PREFIX + "REQUIREMENT_ID_COLLISION",
                                                "an explicit requirement id equals the id generated for another term", "requirements"))
            continue
        record = {"id": generated, "term_id": detection.term_id, "kind": taxonomy.term(detection.term_id)["kind"],
                  "label": None, "priority": priority, "weight": weight_found, "sources": sorted(detection.zones)}
        by_term[detection.term_id] = record
        by_id[generated] = record
    ordered = sorted(by_id.values(), key=lambda r: (r["priority"] != "REQUIRED", -r["weight"], r["id"]))
    return ordered, problems
