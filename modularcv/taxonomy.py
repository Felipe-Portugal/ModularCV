"""Taxonomy-v1: the controlled vocabulary of capabilities and technologies (`builtin:generic-v1` or a workspace file).

Contract: `docs/design/CONTRACTS.md` section 3.3. The taxonomy is persona-independent: it holds the *names the engine may
recognise* (canonical terms, their explicitly declared aliases, the adjacencies a workspace allows, and the headings that
open the zones of a job posting). It never holds a person's skills, and it proves nothing about anyone.

* A **term** is a `capability` (an identifier such as `backend`, declared on bullets and facts as `capabilities`) or a
  `technology` (a display name such as `Python`, declared as `technologies`).
* An **alias** is an exact spelling declared for a term, per language or for any language. Matching is on whole words after
  casefolding and accent removal (`canonical.fold`). Nothing is stemmed, translated or guessed.
* An **adjacency** `{from, to}` is a directed, single-hop relation: direct proof of `from` makes a requirement for `to`
  `ADJACENT`. It is never transitive and never symmetric unless both directions are declared.
* A **zone** is a part of a posting (requirements, responsibilities, ...) with a priority and a weight, opened by a heading.

Ambiguity is refused: an alias that two terms share, a heading that two zones share, a duplicate id, an adjacency to an
unknown term. Messages never repeat a value of the file (see `docvalidate`).
"""
import copy
import re
from collections import namedtuple

from . import canonical, docvalidate, facts, paths

SCHEMA = "Taxonomy-v1"
PREFIX = "TAXONOMY_"
BUILTIN = "builtin:generic-v1"
KINDS = ("capability", "technology")
PRIORITIES = ("REQUIRED", "PREFERRED")
ANY = "any"
WEIGHT_MAX = 1000.0

CheckResult = namedtuple("CheckResult", "taxonomy errors warnings taxonomy_source_sha256")
Detection = namedtuple("Detection", "term_id zones")


class TaxonomyError(ValueError):
    """The document is not a valid Taxonomy-v1. `errors` holds every problem found."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        first = self.errors[0]
        super().__init__("%s (%s): %s" % (first.code, first.path or "document", first.message))

    @property
    def code(self):
        return self.errors[0].code


class Taxonomy:
    """A valid taxonomy. Read-only by convention: accessors return copies."""

    def __init__(self, model, source_sha256):
        self._model = model
        self.taxonomy_source_sha256 = source_sha256
        self._terms = {term["id"]: term for term in model["terms"]}
        self._zones = {zone["id"]: zone for zone in model["zones"]}
        self._spellings = {}
        for term in model["terms"]:
            for language, spellings in [(ANY, [term["name"]])] + sorted(term["aliases"].items()):
                for spelling in spellings:
                    self._spellings.setdefault((language, canonical.fold(spelling)), term["id"])
        self._headings = {}
        for zone in model["zones"]:
            for language, headings in zone["headings"].items():
                for heading in headings:
                    self._headings[(language, canonical.fold(heading))] = zone["id"]
        self._adjacent = {}
        for edge in model["adjacencies"]:
            self._adjacent.setdefault(edge["to"], []).append(edge["from"])
        self._scanners = {}

    # --- identity -------------------------------------------------------------------------------------------

    def to_model(self):
        return copy.deepcopy(self._model)

    @property
    def taxonomy_sha256(self):
        return canonical.fingerprint(self._model)

    @property
    def id(self):
        return self._model["id"]

    # --- vocabulary -----------------------------------------------------------------------------------------

    def term(self, term_id):
        found = self._terms.get(term_id)
        return copy.deepcopy(found) if found else None

    def terms(self, kind=None):
        return tuple(term["id"] for term in self._model["terms"] if kind is None or term["kind"] == kind)

    def capability_ids(self):
        return frozenset(self.terms("capability"))

    def zone(self, zone_id):
        return copy.deepcopy(self._zones.get(zone_id))

    @property
    def default_zone(self):
        return self._model["default_zone"]

    @property
    def priority_weights(self):
        return dict(self._model["priority_weights"])

    def resolve(self, text, language=None):
        """The term id whose name or alias is exactly `text` (folded), in `language` or any, else None."""
        key = canonical.fold(" ".join(text.split()))
        for scope in ((language, ANY) if language else ()):
            if (scope, key) in self._spellings:
                return self._spellings[(scope, key)]
        if (ANY, key) in self._spellings:
            return self._spellings[(ANY, key)]
        if language is None:  # no language given: any declared spelling counts
            for (scope, spelling), term_id in sorted(self._spellings.items()):
                if spelling == key:
                    return term_id
        return None

    def resolve_declared_technology(self, text):
        """A declared technology name (on a bullet, a fact or a skill) to a technology term id, or None."""
        term_id = self.resolve(text)
        return term_id if term_id and self._terms[term_id]["kind"] == "technology" else None

    def spellings(self, term_id):
        """Every folded spelling of a term (name and aliases, any language): used for the profile's forbidden terms."""
        term = self._terms[term_id]
        found = {canonical.fold(term["name"])}
        for items in term["aliases"].values():
            found.update(canonical.fold(item) for item in items)
        return frozenset(found)

    def adjacent_sources(self, term_id):
        """The terms whose direct proof makes a requirement for `term_id` adjacent (one hop, as declared)."""
        return tuple(sorted(self._adjacent.get(term_id, ())))

    # --- postings -------------------------------------------------------------------------------------------

    def heading_zone(self, line, language):
        """The zone a short heading line opens (`Requirements:`, `## Nice to have`), or None."""
        candidate = line.strip().strip("#*_ \t").rstrip(":").strip("*_ \t")
        if not candidate or len(candidate) > 80:
            return None
        key = canonical.fold(" ".join(candidate.split()))
        return self._headings.get((language, key)) or self._headings.get((ANY, key))

    def _scanner(self, language):
        if language not in self._scanners:
            spellings = {}
            for (scope, spelling), term_id in self._spellings.items():
                if scope in (ANY, language):
                    spellings[spelling] = term_id
            ordered = sorted(spellings, key=lambda item: (-len(item), item))
            pattern = re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(re.escape(item) for item in ordered)) \
                if ordered else None
            self._scanners[language] = (pattern, spellings)
        return self._scanners[language]

    def detect(self, text, language):
        """Terms named in a posting, with the zones they appear in: exact declared spellings only, whole words,
        longest spelling first. The text is data to search, never an instruction. Returns a sorted tuple of `Detection`."""
        pattern, spellings = self._scanner(language)
        zone = self.default_zone
        found = {}
        for raw in canonical.normalise_newlines(text).split("\n"):
            line = raw.strip()
            if not line:
                continue
            opened = self.heading_zone(line, language)
            if opened is not None:
                zone = opened
                continue
            if pattern is None:
                continue
            for match in pattern.finditer(canonical.fold(line)):
                found.setdefault(spellings[match.group(0)], set()).add(zone)
        return tuple(Detection(term_id, tuple(sorted(zones))) for term_id, zones in sorted(found.items()))


# --- checking ---------------------------------------------------------------------------------------------

def _weight(reader, value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        reader.error("BAD_TYPE", path, "must be a number")
        return None
    number = float(value)
    if not 0 < number <= WEIGHT_MAX:
        reader.error("OUT_OF_RANGE", path, "must be greater than 0 and at most %d" % WEIGHT_MAX)
        return None
    return number


def _spellings(reader, value, path):
    items = reader.lst(value, path)
    cleaned = []
    for position, item in enumerate(items or ()):
        text = reader.text(item, docvalidate.index(path, position))
        if text is not None:
            cleaned.append(text)
    return reader.unique(cleaned, path, key=canonical.fold)


def _check_terms(reader, value):
    items = reader.lst(value, "terms", empty_ok=False)
    terms, ids, owners = [], {}, {}
    for position, item in enumerate(items or ()):
        path = docvalidate.index("terms", position)
        data, extensions = reader.obj(item, path, required=("id", "kind", "name"), optional=("aliases",))
        if data is None:
            continue
        term_id = reader.ident(data["id"], docvalidate.join(path, "id")) if "id" in data else None
        if term_id is not None:
            if term_id in ids:
                reader.error("DUPLICATE_ID", docvalidate.join(path, "id"), "this term id is already used")
                term_id = None
            else:
                ids[term_id] = path
        kind = reader.choice(data["kind"], docvalidate.join(path, "kind"), KINDS) if "kind" in data else None
        name = reader.text(data["name"], docvalidate.join(path, "name")) if "name" in data else None
        aliases = {}
        if "aliases" in data:
            alias_path = docvalidate.join(path, "aliases")
            raw = data["aliases"]
            if not isinstance(raw, dict):
                reader.error("BAD_TYPE", alias_path, "must be a JSON object mapping a language code or `any` to spellings")
            else:
                for scope in raw:
                    scope_path = docvalidate.join_key(alias_path, scope)
                    if scope != ANY and reader.lang(scope, scope_path) is None:
                        continue
                    listed = _spellings(reader, raw[scope], scope_path)
                    if listed:
                        aliases[scope] = sorted(listed, key=lambda text: (canonical.fold(text), text))
        if term_id is None or kind is None or name is None:
            continue
        for scope, spellings in [(ANY, [name])] + sorted(aliases.items()):
            for spelling in spellings:
                key = canonical.fold(spelling)
                clash = [other for (s, other_key), other in owners.items() if other_key == key and (s == scope or ANY in (s, scope))]
                if any(other != term_id for other in clash):
                    reader.error("ALIAS_AMBIGUOUS", path, "a name or alias is also a name or alias of another term")
                owners.setdefault((scope, key), term_id)
        record = {"id": term_id, "kind": kind, "name": name, "aliases": aliases}
        if extensions:
            record["extensions"] = extensions
        terms.append(record)
    return sorted(terms, key=lambda term: term["id"])


def _check_zones(reader, value):
    items = reader.lst(value, "zones", empty_ok=False)
    zones, ids, headings = [], {}, {}
    for position, item in enumerate(items or ()):
        path = docvalidate.index("zones", position)
        data, extensions = reader.obj(item, path, required=("id", "priority", "weight", "headings"))
        if data is None:
            continue
        zone_id = reader.ident(data["id"], docvalidate.join(path, "id")) if "id" in data else None
        if zone_id is not None:
            if zone_id in ids:
                reader.error("DUPLICATE_ID", docvalidate.join(path, "id"), "this zone id is already used")
                zone_id = None
            ids[zone_id] = path
        priority = reader.choice(data["priority"], docvalidate.join(path, "priority"), PRIORITIES) \
            if "priority" in data else None
        weight = _weight(reader, data["weight"], docvalidate.join(path, "weight")) if "weight" in data else None
        zone_headings = {}
        if "headings" in data:
            head_path = docvalidate.join(path, "headings")
            raw = data["headings"]
            if not isinstance(raw, dict):
                reader.error("BAD_TYPE", head_path, "must be a JSON object mapping a language code or `any` to headings")
            else:
                for scope in raw:
                    scope_path = docvalidate.join_key(head_path, scope)
                    if scope != ANY and reader.lang(scope, scope_path) is None:
                        continue
                    listed = _spellings(reader, raw[scope], scope_path)
                    for heading in listed:
                        key = (scope, canonical.fold(heading))
                        if key in headings and headings[key] != zone_id:
                            reader.error("HEADING_AMBIGUOUS", scope_path, "a heading opens two different zones")
                        headings[key] = zone_id
                    if listed:
                        zone_headings[scope] = sorted(listed, key=lambda text: (canonical.fold(text), text))
        if zone_id is None or priority is None or weight is None:
            continue
        record = {"id": zone_id, "priority": priority, "weight": weight, "headings": zone_headings}
        if extensions:
            record["extensions"] = extensions
        zones.append(record)
    return sorted(zones, key=lambda zone: zone["id"])


def _check_adjacencies(reader, value, term_ids):
    items = reader.lst(value, "adjacencies")
    edges, seen = [], set()
    for position, item in enumerate(items or ()):
        path = docvalidate.index("adjacencies", position)
        data, extensions = reader.obj(item, path, required=("from", "to"))
        if data is None:
            continue
        source = reader.ident(data["from"], docvalidate.join(path, "from")) if "from" in data else None
        target = reader.ident(data["to"], docvalidate.join(path, "to")) if "to" in data else None
        if source is None or target is None:
            continue
        if source not in term_ids or target not in term_ids:
            reader.error("ADJACENCY_INVALID", path, "an adjacency must name two declared terms")
            continue
        if source == target:
            reader.error("ADJACENCY_INVALID", path, "a term cannot be adjacent to itself")
            continue
        if (source, target) in seen:
            reader.error("DUPLICATE_VALUE", path, "this adjacency is declared twice")
            continue
        seen.add((source, target))
        edge = {"from": source, "to": target}
        if extensions:
            edge["extensions"] = extensions
        edges.append(edge)
    return sorted(edges, key=lambda edge: (edge["from"], edge["to"]))


def check_data(document, source_sha256=None):
    """Check an already decoded JSON value. `taxonomy` is None when `errors` is not empty."""
    reader = docvalidate.Reader(PREFIX)
    data, extensions = reader.obj(document, "", required=("schema", "id", "terms", "zones", "default_zone"),
                                  optional=("priority_weights", "adjacencies"))
    if data is None:
        return CheckResult(None, tuple(reader.problems), (), source_sha256)
    if "schema" in data and data["schema"] != SCHEMA:
        reader.error("UNKNOWN_SCHEMA", "schema", "unsupported schema, expected `%s`" % SCHEMA)
        return CheckResult(None, tuple(reader.problems), (), source_sha256)
    taxonomy_id = reader.ident(data["id"], "id") if "id" in data else None
    terms = _check_terms(reader, data["terms"]) if "terms" in data else []
    zones = _check_zones(reader, data["zones"]) if "zones" in data else []
    default_zone = reader.ident(data["default_zone"], "default_zone") if "default_zone" in data else None
    if default_zone is not None and default_zone not in {zone["id"] for zone in zones}:
        reader.error("INVALID_VALUE", "default_zone", "must name a declared zone")
        default_zone = None
    weights = {"REQUIRED": 4.0, "PREFERRED": 2.0}
    if "priority_weights" in data:
        raw, w_data = data["priority_weights"], None
        w_data, _ext = reader.obj(raw, "priority_weights", optional=PRIORITIES)
        for name in PRIORITIES:
            if w_data is not None and name in w_data:
                number = _weight(reader, w_data[name], docvalidate.join("priority_weights", name))
                if number is not None:
                    weights[name] = number
    adjacencies = _check_adjacencies(reader, data["adjacencies"], {t["id"] for t in terms}) \
        if "adjacencies" in data else []
    if reader.problems:
        return CheckResult(None, tuple(sorted(reader.problems, key=lambda p: (p.path, p.code))), (), source_sha256)
    model = {"schema": SCHEMA, "id": taxonomy_id, "terms": terms, "zones": zones, "default_zone": default_zone,
             "priority_weights": weights, "adjacencies": adjacencies}
    if extensions:
        model["extensions"] = extensions
    return CheckResult(Taxonomy(model, source_sha256), (), (), source_sha256)


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


def builtin():
    """The shipped `generic-v1` taxonomy."""
    result = check_data(copy.deepcopy(GENERIC_V1))
    if result.errors:  # pragma: no cover - guarded by a test
        raise TaxonomyError(result.errors)
    return result.taxonomy


def load(spec, root=None):
    """The taxonomy a profile names: `builtin:generic-v1` or a safe workspace-relative path to a `.json` file.

    Returns a `CheckResult`; an unknown builtin or an unsafe path is `TAXONOMY_FILE_UNREADABLE`."""
    if spec == BUILTIN:
        return CheckResult(builtin(), (), (), None)
    if not isinstance(spec, str) or spec.startswith("builtin:") or paths.relative_path_problem(spec):
        return CheckResult(None, (docvalidate.Problem(PREFIX + "FILE_UNREADABLE", "unknown or unsafe taxonomy reference", ""),),
                           (), None)
    target = paths.resolve_inside(root, spec) if root is not None else None
    if target is None:
        return CheckResult(None, (docvalidate.Problem(PREFIX + "FILE_UNREADABLE", "unknown or unsafe taxonomy reference", ""),),
                           (), None)
    return check_file(target)


def vocabulary_problems(taxonomy, content, factbase):
    """Capabilities declared on bullets and on facts that the taxonomy does not know: `(path, message)` pairs, no value.

    A declared capability must be a canonical term id of kind `capability` (an alias is not a declaration)."""
    known = taxonomy.capability_ids()
    problems = []
    if content is not None:
        for b_position, block in enumerate(content.to_model()["blocks"]):
            for position, bullet in enumerate(block["bullets"]):
                for c_position, capability in enumerate(bullet["capabilities"]):
                    if capability not in known:
                        problems.append(("blocks[%d].bullets[%d].capabilities[%d]" % (b_position, position, c_position),
                                         "the capability is not in the taxonomy"))
    if factbase is not None:
        for position, fact in enumerate(factbase.facts):
            for c_position, capability in enumerate(fact.capabilities):
                if capability not in known:
                    problems.append(("facts[%d].capabilities[%d]" % (position, c_position),
                                     "the capability is not in the taxonomy"))
    return problems


GENERIC_V1 = {
    "schema": SCHEMA,
    "id": "generic-v1",
    "default_zone": "context",
    "priority_weights": {"REQUIRED": 4, "PREFERRED": 2},
    "zones": [
        {"id": "requirement", "priority": "REQUIRED", "weight": 4, "headings": {
            "en": ["requirements", "qualifications", "must have", "what you bring", "what we are looking for",
                   "required skills"],
            "fr": ["exigences", "qualifications", "profil recherche", "competences requises", "ce que vous apportez"]}},
        {"id": "responsibility", "priority": "REQUIRED", "weight": 3, "headings": {
            "en": ["responsibilities", "what you will do", "your role", "duties"],
            "fr": ["responsabilites", "vos missions", "mandat", "ce que vous ferez", "taches"]}},
        {"id": "preferred", "priority": "PREFERRED", "weight": 2, "headings": {
            "en": ["nice to have", "preferred", "bonus", "assets", "preferred qualifications"],
            "fr": ["atouts", "un plus", "souhaite", "qualifications souhaitees"]}},
        {"id": "context", "priority": "PREFERRED", "weight": 1, "headings": {
            "en": ["about us", "about the role", "about the team", "who we are", "benefits"],
            "fr": ["a propos", "a propos du poste", "qui sommes-nous", "avantages"]}},
    ],
    "terms": [
        {"id": "backend", "kind": "capability", "name": "Backend development", "aliases": {
            "en": ["backend", "back-end", "back end", "server-side"], "fr": ["developpement backend", "back-end"]}},
        {"id": "frontend", "kind": "capability", "name": "Frontend development", "aliases": {
            "en": ["frontend", "front-end", "front end"], "fr": ["developpement frontend", "front-end"]}},
        {"id": "api-design", "kind": "capability", "name": "API design", "aliases": {
            "en": ["rest api", "rest apis", "api design", "restful"], "fr": ["api rest", "conception d'api"]}},
        {"id": "testing", "kind": "capability", "name": "Software testing", "aliases": {
            "en": ["testing", "unit testing", "test automation", "automated tests"],
            "fr": ["tests", "tests unitaires", "tests automatises", "automatisation des tests"]}},
        {"id": "devops", "kind": "capability", "name": "DevOps", "aliases": {
            "any": ["ci/cd"], "en": ["continuous integration", "continuous delivery"],
            "fr": ["integration continue", "livraison continue"]}},
        {"id": "databases", "kind": "capability", "name": "Databases", "aliases": {
            "en": ["database", "databases", "data modeling"], "fr": ["base de donnees", "bases de donnees"]}},
        {"id": "data-analysis", "kind": "capability", "name": "Data analysis", "aliases": {
            "en": ["data analysis", "analytics"], "fr": ["analyse de donnees", "analytique"]}},
        {"id": "security", "kind": "capability", "name": "Security", "aliases": {
            "en": ["security", "cybersecurity"], "fr": ["securite", "cybersecurite"]}},
        {"id": "cloud", "kind": "capability", "name": "Cloud computing", "aliases": {
            "en": ["cloud", "cloud computing"], "fr": ["infonuagique", "informatique en nuage"]}},
        {"id": "automation", "kind": "capability", "name": "Automation", "aliases": {
            "en": ["automation", "scripting"], "fr": ["automatisation", "scripts"]}},
        {"id": "collaboration", "kind": "capability", "name": "Collaboration", "aliases": {
            "en": ["teamwork", "collaboration", "code review", "code reviews"],
            "fr": ["travail d'equipe", "collaboration", "revue de code", "revues de code"]}},
        {"id": "project-management", "kind": "capability", "name": "Project management", "aliases": {
            "en": ["project management", "agile", "scrum"], "fr": ["gestion de projet", "agile", "scrum"]}},
        {"id": "communication", "kind": "capability", "name": "Communication", "aliases": {
            "en": ["communication", "documentation"], "fr": ["communication", "documentation"]}},
        {"id": "python", "kind": "technology", "name": "Python"},
        {"id": "java", "kind": "technology", "name": "Java"},
        {"id": "javascript", "kind": "technology", "name": "JavaScript", "aliases": {"any": ["js"]}},
        {"id": "typescript", "kind": "technology", "name": "TypeScript", "aliases": {"any": ["ts"]}},
        {"id": "sql", "kind": "technology", "name": "SQL"},
        {"id": "git", "kind": "technology", "name": "Git"},
        {"id": "docker", "kind": "technology", "name": "Docker"},
        {"id": "kubernetes", "kind": "technology", "name": "Kubernetes", "aliases": {"any": ["k8s"]}},
        {"id": "linux", "kind": "technology", "name": "Linux"},
        {"id": "pytest", "kind": "technology", "name": "pytest"},
        {"id": "csharp", "kind": "technology", "name": "C#", "aliases": {"any": ["c sharp"]}},
        {"id": "cpp", "kind": "technology", "name": "C++"},
    ],
    "adjacencies": [
        {"from": "javascript", "to": "typescript"},
        {"from": "typescript", "to": "javascript"},
        {"from": "docker", "to": "kubernetes"},
        {"from": "docker", "to": "devops"},
        {"from": "git", "to": "devops"},
        {"from": "sql", "to": "databases"},
    ],
}
