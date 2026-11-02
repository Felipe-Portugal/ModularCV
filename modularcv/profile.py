"""Profile-v1: the candidate's configuration (`profile.json`).

Contract: `docs/design/CONTRACTS.md` section 2 and its M4 status (section 2.1). Persona data lives in the
workspace's profile and fact base, never in code: this module knows no name, employer, school or rule.

Three kinds of content are kept apart and never mixed:

* **private**: identity fields whose `visibility` is `private` (and every `x-` field). They are stored, never
  rendered, never printed by a report;
* **public**: identity fields marked `public`, the only ones `Profile.public_view()` returns;
* **generation preferences**: families, policy, selection, precedence, guidance, taxonomy. Internal: they
  steer the engine and are never printed in a document.

Nothing in a profile is a confirmed fact. An availability or a guidance rule names a **fact id**; it counts
as supported only when the fact base holds that fact as `CONFIRMED` (`confirmed_availability`). Without a
fact base the reference is reported `UNVERIFIED`, never assumed.

Error messages and reports never repeat a value of the profile (see `docvalidate`).
"""
import copy
import math
from collections import namedtuple

from . import canonical, docvalidate, facts, paths

SCHEMA = "Profile-v1"
PREFIX = "PROFILE_"
DEFAULT_TAXONOMY = "builtin:generic-v1"

VISIBILITIES = ("public", "private")
IDENTITY_FIELDS = ("display_name", "headline", "location", "email", "phone")
EMPLOYMENT_KINDS = ("INTERNSHIP", "PERMANENT", "FIXED_TERM", "PART_TIME", "UNSPECIFIED")
GUIDANCE_ACTIONS = ("omit", "soften")
PAGE_TARGET_RANGE = (1, 5)
SELECTION_DEFAULTS = (
    ("baseline_prior", 0.25),
    ("minimum_gain", 1.0),
    ("off_target_penalty", 0.1),
    ("off_target_penalty_cap", 0.6),
    ("named_bonus", 0.5),
    ("inferred_factor", 0.5),
)
SELECTION_LIMIT = 1000000.0
_ABSENT = object()

UNVERIFIED = "UNVERIFIED"
VERIFIED = "VERIFIED"
REFUSED = "REFUSED"

CheckResult = namedtuple("CheckResult", "profile errors warnings profile_source_sha256 availability")
FactReference = namedtuple("FactReference", "path fact_id kind")


class ProfileError(ValueError):
    """The document is not a valid Profile-v1. `errors` holds every problem found."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        first = self.errors[0]
        super().__init__("%s (%s): %s" % (first.code, first.path or "document", first.message))

    @property
    def code(self):
        return self.errors[0].code


class Profile:
    """A valid profile. Read-only by convention: accessors return copies."""

    def __init__(self, model, source_sha256):
        self._model = model
        self.profile_source_sha256 = source_sha256

    # --- identity of the document ------------------------------------------------------------------

    def to_model(self):
        """The canonical model (defaults filled in, sets sorted). Input of `profile_sha256`."""
        return copy.deepcopy(self._model)

    @property
    def profile_sha256(self):
        return canonical.fingerprint(self._model)

    # --- the three kinds of content ----------------------------------------------------------------

    @property
    def languages(self):
        return tuple(self._model["languages"])

    @property
    def default_language(self):
        return self._model["default_language"]

    def public_view(self):
        """The only identity data a document may print: fields marked `public`, nothing else."""
        identity = self._model["identity"]
        shown = {}
        for name in IDENTITY_FIELDS:
            entry = identity.get(name)
            if entry is not None and entry["visibility"] == "public":
                shown[name] = entry["value"]
        links = [{"label": link["label"], "value": link["value"]}
                 for link in identity["links"] if link["visibility"] == "public"]
        return {"languages": list(self._model["languages"]), "default_language": self._model["default_language"],
                "identity": shown, "links": links}

    def identity_visibility(self):
        """Field name -> `public`/`private`, without any value. Safe to print."""
        identity = self._model["identity"]
        result = {name: identity[name]["visibility"] for name in IDENTITY_FIELDS if name in identity}
        for position, link in enumerate(identity["links"]):
            result["links[%d]" % position] = link["visibility"]
        return result

    def private_field_names(self):
        return sorted(name for name, visibility in self.identity_visibility().items() if visibility == "private")

    def internal_preferences(self):
        """Generation preferences: never printed in a document."""
        keys = ("families", "policy", "availability", "taxonomy", "selection", "precedence_rules", "guidance")
        return {key: copy.deepcopy(self._model[key]) for key in keys}

    @property
    def families(self):
        return copy.deepcopy(self._model["families"])

    @property
    def policy(self):
        return copy.deepcopy(self._model["policy"])

    @property
    def require_confirmation_date(self):
        return self._model["policy"]["require_confirmation_date"]

    @property
    def selection(self):
        return dict(self._model["selection"])

    @property
    def availability(self):
        """Declared availabilities. Declared is not confirmed: see `confirmed_availability`."""
        return copy.deepcopy(self._model["availability"])

    def confirmed_availability(self, factbase):
        """Availabilities whose fact is `CONFIRMED` in `factbase`; every other one is left out."""
        confirmed = []
        for entry in self._model["availability"]:
            fact = factbase.get(entry["fact_id"])
            if fact is not None and fact.status == facts.CONFIRMED:
                confirmed.append(copy.deepcopy(entry))
        return confirmed


# --- checking ----------------------------------------------------------------------------------------

def _identity_field(reader, value, path):
    """`{value, visibility}`; visibility is required so that nothing is public by default."""
    data, extensions = reader.obj(value, path, required=("value", "visibility"))
    if data is None:
        return None
    text = reader.text(data["value"], docvalidate.join(path, "value")) if "value" in data else None
    visibility = reader.choice(data["visibility"], docvalidate.join(path, "visibility"), VISIBILITIES) \
        if "visibility" in data else None
    if text is None or visibility is None:
        return None
    entry = {"value": text, "visibility": visibility}
    if extensions:
        entry["extensions"] = extensions
    return entry


def _check_identity(reader, value, path):
    data, extensions = reader.obj(value, path, required=("display_name",), optional=IDENTITY_FIELDS[1:] + ("links",))
    if data is None:
        return None
    identity = {}
    for name in IDENTITY_FIELDS:
        if name in data:
            entry = _identity_field(reader, data[name], docvalidate.join(path, name))
            if entry is not None:
                identity[name] = entry
    links = []
    if "links" in data:
        raw = reader.lst(data["links"], docvalidate.join(path, "links"))
        for position, item in enumerate(raw or ()):
            item_path = docvalidate.index(docvalidate.join(path, "links"), position)
            link, link_ext = reader.obj(item, item_path, required=("value", "visibility"), optional=("label",))
            if link is None:
                continue
            text = reader.text(link["value"], docvalidate.join(item_path, "value")) if "value" in link else None
            visibility = reader.choice(link["visibility"], docvalidate.join(item_path, "visibility"), VISIBILITIES) \
                if "visibility" in link else None
            link_label = reader.text(link["label"], docvalidate.join(item_path, "label")) if "label" in link else None
            if text is None or visibility is None or ("label" in link and link_label is None):
                continue
            record = {"label": link_label, "value": text, "visibility": visibility}
            if link_ext:
                record["extensions"] = link_ext
            links.append(record)
        links = reader.unique(links, docvalidate.join(path, "links"), key=lambda link: canonical.fold(link["value"]))
    identity["links"] = links
    if extensions:
        identity["extensions"] = extensions
    return identity


def _terms(reader, value, path):
    """A set of terms: unique once folded, stored sorted so that the order of the file never matters."""
    items = reader.lst(value, path)
    if items is None:
        return None
    cleaned = []
    for position, item in enumerate(items):
        text = reader.text(item, docvalidate.index(path, position))
        if text is not None:
            cleaned.append(text)
    cleaned = reader.unique(cleaned, path, key=canonical.fold)
    return sorted(cleaned, key=lambda term: (canonical.fold(term), term))


def _check_policy(reader, value, path, languages):
    policy = {"never_publish_terms": [], "omit_by_default_terms": [], "forbidden_words": {},
              "require_confirmation_date": False}
    if value is _ABSENT:
        return policy
    data, extensions = reader.obj(value, path, optional=(
        "never_publish_terms", "omit_by_default_terms", "forbidden_words", "require_confirmation_date"))
    if data is None:
        return policy
    for name in ("never_publish_terms", "omit_by_default_terms"):
        if name in data:
            terms = _terms(reader, data[name], docvalidate.join(path, name))
            if terms is not None:
                policy[name] = terms
    if "forbidden_words" in data:
        words_path = docvalidate.join(path, "forbidden_words")
        words = data["forbidden_words"]
        if not isinstance(words, dict):
            reader.error("BAD_TYPE", words_path, "must be a JSON object mapping language codes to term lists")
        else:
            for code in words:
                code_path = docvalidate.join_key(words_path, code)
                if reader.lang(code, code_path) is None:
                    continue
                if code not in languages:
                    reader.error("UNKNOWN_LANGUAGE", code_path, "the language is not one of the profile languages")
                    continue
                terms = _terms(reader, words[code], code_path)
                if terms is not None:
                    policy["forbidden_words"][code] = terms
    if "require_confirmation_date" in data:
        flag = reader.boolean(data["require_confirmation_date"], docvalidate.join(path, "require_confirmation_date"))
        if flag is not None:
            policy["require_confirmation_date"] = flag
    clash = {canonical.fold(t) for t in policy["never_publish_terms"]} & \
            {canonical.fold(t) for t in policy["omit_by_default_terms"]}
    if clash:
        reader.error("POLICY_CONFLICT", path,
                     "%d term(s) are both never published and omitted by default" % len(clash))
    if extensions:
        policy["extensions"] = extensions
    return policy


def _check_families(reader, value, path, languages, never_publish):
    data = value
    if not isinstance(data, dict):
        reader.error("BAD_TYPE", path, "must be a JSON object mapping family ids to families")
        return None
    if not data:
        reader.error("NO_FAMILY", path, "at least one family is required")
        return None
    forbidden = {canonical.fold(term) for term in never_publish}
    families = {}
    for family_id in data:
        family_path = docvalidate.join_key(path, family_id)
        if reader.ident(family_id, family_path) is None:
            continue
        family, extensions = reader.obj(data[family_id], family_path, required=("label", "languages"),
                                        optional=("core_skills", "excluded_blocks", "clusters", "page_target"))
        if family is None:
            continue
        record = {"label": None, "languages": [], "core_skills": [], "excluded_blocks": {}, "clusters": [],
                  "page_target": None}
        if "label" in family:
            record["label"] = reader.text(family["label"], docvalidate.join(family_path, "label"))
        if "languages" in family:
            raw = reader.lst(family["languages"], docvalidate.join(family_path, "languages"), empty_ok=False)
            codes = []
            for position, item in enumerate(raw or ()):
                item_path = docvalidate.index(docvalidate.join(family_path, "languages"), position)
                code = reader.lang(item, item_path)
                if code is None:
                    continue
                if code not in languages:
                    reader.error("UNKNOWN_LANGUAGE", item_path, "the language is not one of the profile languages")
                    continue
                codes.append(code)
            record["languages"] = sorted(reader.unique(codes, docvalidate.join(family_path, "languages")))
        if "core_skills" in family:
            skills_path = docvalidate.join(family_path, "core_skills")
            raw = reader.lst(family["core_skills"], skills_path)
            skills = []
            for position, item in enumerate(raw or ()):
                text = reader.text(item, docvalidate.index(skills_path, position))
                if text is None:
                    continue
                if canonical.fold(text) in forbidden:
                    reader.error("SKILL_FORBIDDEN", docvalidate.index(skills_path, position),
                                 "a core skill is also a never-publish term")
                    continue
                skills.append(text)
            record["core_skills"] = reader.unique(skills, skills_path, key=canonical.fold)
        if "excluded_blocks" in family:
            blocks_path = docvalidate.join(family_path, "excluded_blocks")
            blocks = family["excluded_blocks"]
            if not isinstance(blocks, dict):
                reader.error("BAD_TYPE", blocks_path, "must be a JSON object mapping block ids to reasons")
            else:
                for block_id in blocks:
                    block_path = docvalidate.join_key(blocks_path, block_id)
                    if reader.ident(block_id, block_path) is None:
                        continue
                    reason = reader.text(blocks[block_id], block_path)
                    if reason is not None:
                        record["excluded_blocks"][block_id] = reason
        if "clusters" in family:
            clusters_path = docvalidate.join(family_path, "clusters")
            raw = reader.lst(family["clusters"], clusters_path)
            clusters = [c for c in (reader.ident(item, docvalidate.index(clusters_path, position))
                                    for position, item in enumerate(raw or ())) if c is not None]
            record["clusters"] = reader.unique(clusters, clusters_path)
        if "page_target" in family and family["page_target"] is not None:
            record["page_target"] = reader.integer(family["page_target"], docvalidate.join(family_path, "page_target"),
                                                   *PAGE_TARGET_RANGE)
        if extensions:
            record["extensions"] = extensions
        families[family_id] = record
    return families


def _check_availability(reader, value, path, refs):
    items = reader.lst(value, path)
    entries, used = [], set()
    for position, item in enumerate(items or ()):
        item_path = docvalidate.index(path, position)
        data, extensions = reader.obj(item, item_path, required=("id", "fact_id", "applies_to"))
        if data is None:
            continue
        entry_id = reader.ident(data["id"], docvalidate.join(item_path, "id")) if "id" in data else None
        fact_id = reader.ident(data["fact_id"], docvalidate.join(item_path, "fact_id")) if "fact_id" in data else None
        kinds = []
        if "applies_to" in data:
            kinds_path = docvalidate.join(item_path, "applies_to")
            raw = reader.lst(data["applies_to"], kinds_path, empty_ok=False)
            for k_position, kind in enumerate(raw or ()):
                checked = reader.choice(kind, docvalidate.index(kinds_path, k_position), EMPLOYMENT_KINDS)
                if checked is not None:
                    kinds.append(checked)
            kinds = sorted(reader.unique(kinds, kinds_path))
        if entry_id is None or fact_id is None or not kinds:
            continue
        for kind in kinds:
            if (fact_id, kind) in used:
                reader.error("DUPLICATE_VALUE", item_path, "this fact is already declared available for this employment kind")
                break
            used.add((fact_id, kind))
        entry = {"id": entry_id, "fact_id": fact_id, "applies_to": kinds}
        if extensions:
            entry["extensions"] = extensions
        entries.append(entry)
        refs.append(FactReference(docvalidate.join(item_path, "fact_id"), fact_id, "availability"))
    reader.unique(entries, path, key=lambda entry: entry["id"])
    return entries


def _check_taxonomy(reader, value, path):
    if not isinstance(value, str):
        reader.error("BAD_TYPE", path, "must be a string")
        return DEFAULT_TAXONOMY
    if value == DEFAULT_TAXONOMY:
        return value
    if value.startswith("builtin:") or paths.relative_path_problem(value) or not value.endswith(".json"):
        reader.error("INVALID_TAXONOMY", path,
                     "must be `%s` or a safe workspace-relative path ending in .json" % DEFAULT_TAXONOMY)
        return DEFAULT_TAXONOMY
    return value


def _check_selection(reader, value, path):
    selection = {name: default for name, default in SELECTION_DEFAULTS}
    if value is _ABSENT:
        return selection
    names = tuple(name for name, _default in SELECTION_DEFAULTS)
    data, _extensions = reader.obj(value, path, optional=names)
    for name in names:
        if data is None or name not in data:
            continue
        number = data[name]
        number_path = docvalidate.join(path, name)
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            reader.error("BAD_TYPE", number_path, "must be a number")
            continue
        number = float(number)
        if not math.isfinite(number) or number < 0 or number > SELECTION_LIMIT:
            reader.error("OUT_OF_RANGE", number_path, "must be between 0 and %d" % SELECTION_LIMIT)
            continue
        if name == "inferred_factor" and number > 1:
            reader.error("OUT_OF_RANGE", number_path, "must be between 0 and 1")
            continue
        selection[name] = number
    if selection["off_target_penalty_cap"] < selection["off_target_penalty"]:
        reader.error("OUT_OF_RANGE", path, "off_target_penalty_cap must be at least off_target_penalty")
    return selection


def _check_precedence(reader, value, path):
    items = reader.lst(value, path)
    rules = []
    for position, item in enumerate(items or ()):
        item_path = docvalidate.index(path, position)
        data, extensions = reader.obj(item, item_path, required=("when_direct", "keep", "over"))
        if data is None:
            continue
        parts = {key: reader.ident(data[key], docvalidate.join(item_path, key)) if key in data else None
                 for key in ("when_direct", "keep", "over")}
        if any(part is None for part in parts.values()):
            continue
        if parts["keep"] == parts["over"]:
            reader.error("PRECEDENCE_INVALID", item_path, "a block cannot take precedence over itself")
            continue
        if extensions:
            parts["extensions"] = extensions
        rules.append(parts)
    rules = reader.unique(rules, path, key=lambda rule: (rule["when_direct"], rule["keep"], rule["over"]))
    if _has_cycle(rules):
        reader.error("PRECEDENCE_CONFLICT", path, "precedence rules contradict each other for one requirement")
    return rules


def _has_cycle(rules):
    """A cycle among `keep -> over` edges of one requirement means two blocks each win over the other."""
    by_requirement = {}
    for rule in rules:
        by_requirement.setdefault(rule["when_direct"], {}).setdefault(rule["keep"], set()).add(rule["over"])
    for edges in by_requirement.values():
        state = {}

        def visit(node):
            state[node] = 1
            for nxt in edges.get(node, ()):
                if state.get(nxt) == 1 or (state.get(nxt) is None and visit(nxt)):
                    return True
            state[node] = 2
            return False

        if any(state.get(node) is None and visit(node) for node in list(edges)):
            return True
    return False


def _check_guidance(reader, value, path, refs):
    items = reader.lst(value, path)
    entries = []
    for position, item in enumerate(items or ()):
        item_path = docvalidate.index(path, position)
        data, extensions = reader.obj(item, item_path, required=("job_key", "rules"))
        if data is None:
            continue
        job_key = reader.ident(data["job_key"], docvalidate.join(item_path, "job_key")) if "job_key" in data else None
        rules_path = docvalidate.join(item_path, "rules")
        raw = reader.lst(data["rules"], rules_path, empty_ok=False) if "rules" in data else None
        rules, seen_facts = [], set()
        for r_position, rule_item in enumerate(raw or ()):
            rule_path = docvalidate.index(rules_path, r_position)
            rule, rule_ext = reader.obj(rule_item, rule_path, required=("fact_id", "action"), optional=("text",))
            if rule is None:
                continue
            fact_id = reader.ident(rule["fact_id"], docvalidate.join(rule_path, "fact_id")) if "fact_id" in rule else None
            action = reader.choice(rule["action"], docvalidate.join(rule_path, "action"), GUIDANCE_ACTIONS) \
                if "action" in rule else None
            if fact_id is None or action is None:
                continue
            record = {"fact_id": fact_id, "action": action, "text": None}
            given = rule.get("text")
            if action == "soften":
                if given is None:
                    reader.error("GUIDANCE_INVALID", rule_path, "`soften` needs a replacement `text`")
                    continue
                record["text"] = reader.text(given, docvalidate.join(rule_path, "text"))
                if record["text"] is None:
                    continue
            elif given is not None:
                reader.error("GUIDANCE_INVALID", rule_path, "`omit` takes no `text`")
                continue
            if fact_id in seen_facts:
                reader.error("GUIDANCE_INVALID", rule_path, "two rules of one job target the same fact")
                continue
            seen_facts.add(fact_id)
            if rule_ext:
                record["extensions"] = rule_ext
            rules.append(record)
            refs.append(FactReference(docvalidate.join(rule_path, "fact_id"), fact_id,
                                      "guidance-soften" if action == "soften" else "guidance-omit"))
        if job_key is None or not rules:
            continue
        entry = {"job_key": job_key, "rules": rules}
        if extensions:
            entry["extensions"] = extensions
        entries.append(entry)
    reader.unique(entries, path, key=lambda entry: entry["job_key"])
    return entries


def _check_languages(reader, data):
    languages, default = [], None
    if "languages" in data:
        raw = reader.lst(data["languages"], "languages", empty_ok=False)
        for position, item in enumerate(raw or ()):
            code = reader.lang(item, docvalidate.index("languages", position))
            if code is not None:
                languages.append(code)
        languages = reader.unique(languages, "languages")
    if "default_language" in data:
        default = reader.lang(data["default_language"], "default_language")
    elif len(languages) == 1:
        default = languages[0]
    elif len(languages) > 1:
        reader.error("DEFAULT_LANGUAGE", "default_language", "required when the profile declares several languages")
    if default is not None and languages and default not in languages:
        reader.error("DEFAULT_LANGUAGE", "default_language", "must be one of `languages`")
        default = None
    return sorted(languages), default


def _verify_references(reader, refs, factbase, require_date):
    """Check every fact reference against the fact base. Returns {fact id: state} for availability."""
    states = {}
    for ref in refs:
        fact = factbase.get(ref.fact_id)
        if fact is None:
            reader.error("FACT_UNKNOWN", ref.path, "the referenced fact does not exist in the fact base")
            states[ref] = REFUSED
        elif ref.kind != "guidance-omit" and fact.status != facts.CONFIRMED:
            reader.error("FACT_NOT_CONFIRMED", ref.path, "the referenced fact is not CONFIRMED (status %s)" % fact.status)
            states[ref] = REFUSED
        elif fact.status == facts.CONFIRMED and require_date and fact.confirmed_on is None:
            reader.error("FACT_DATE_REQUIRED", ref.path, "this workspace requires `confirmed_on` on a CONFIRMED fact")
            states[ref] = REFUSED
        else:
            states[ref] = VERIFIED
    return states


def check_data(document, source_sha256=None, factbase=None):
    """Check an already decoded JSON value. Returns a `CheckResult`; `profile` is None when `errors` is not empty."""
    reader = docvalidate.Reader(PREFIX)
    warnings = []
    optional = ("policy", "availability", "taxonomy", "selection", "precedence_rules", "guidance", "default_language")
    data, extensions = reader.obj(document, "", required=("schema", "languages", "identity", "families"),
                                  optional=optional)
    if data is None:
        return CheckResult(None, tuple(reader.problems), (), source_sha256, ())
    if "schema" in data and data["schema"] != SCHEMA:
        reader.error("UNKNOWN_SCHEMA", "schema", "unsupported schema, expected `%s`" % SCHEMA)
        return CheckResult(None, tuple(reader.problems), (), source_sha256, ())

    languages, default = _check_languages(reader, data)
    identity = _check_identity(reader, data["identity"], "identity") if "identity" in data else None
    policy = _check_policy(reader, data.get("policy", _ABSENT), "policy", languages)
    families = _check_families(reader, data["families"], "families", languages, policy["never_publish_terms"]) \
        if "families" in data else None
    refs = []
    availability = _check_availability(reader, data["availability"], "availability", refs) \
        if "availability" in data else []
    taxonomy = _check_taxonomy(reader, data["taxonomy"], "taxonomy") if "taxonomy" in data else DEFAULT_TAXONOMY
    selection = _check_selection(reader, data.get("selection", _ABSENT), "selection")
    precedence = _check_precedence(reader, data["precedence_rules"], "precedence_rules") \
        if "precedence_rules" in data else []
    guidance = _check_guidance(reader, data["guidance"], "guidance", refs) if "guidance" in data else []

    states = {}
    if refs and not reader.problems:
        if factbase is not None:
            states = _verify_references(reader, refs, factbase, policy["require_confirmation_date"])
        else:
            warnings.append(docvalidate.Problem(PREFIX + "FACTS_NOT_CHECKED",
                                                "fact references were not checked against a fact base", ""))
    if identity is not None and identity.get("display_name", {}).get("visibility") == "private":
        warnings.append(docvalidate.Problem(PREFIX + "DISPLAY_NAME_PRIVATE",
                                            "the display name is private, so a rendered document will not show it",
                                            "identity.display_name"))

    states_by_id = []
    for entry in availability:
        verdict = UNVERIFIED
        for ref, state in states.items():
            if ref.kind == "availability" and ref.fact_id == entry["fact_id"]:
                verdict = state
        states_by_id.append((entry["id"], verdict))

    if reader.problems:
        return CheckResult(None, tuple(_ordered(reader.problems)), tuple(warnings), source_sha256, tuple(states_by_id))

    model = {
        "schema": SCHEMA,
        "languages": languages,
        "default_language": default,
        "identity": identity,
        "families": families,
        "policy": policy,
        "availability": availability,
        "taxonomy": taxonomy,
        "selection": selection,
        "precedence_rules": precedence,
        "guidance": guidance,
    }
    if extensions:
        model["extensions"] = extensions
    return CheckResult(Profile(model, source_sha256), (), tuple(warnings), source_sha256, tuple(states_by_id))


def _ordered(problems):
    return sorted(problems, key=lambda problem: (problem.path, problem.code))


def check_bytes(data, factbase=None):
    """Check the raw bytes of `profile.json`. Never raises on a bad file."""
    source_sha256 = canonical.sha256_text(data)
    try:
        document = docvalidate.load(data, PREFIX)
    except docvalidate.DocumentError as error:
        return CheckResult(None, (docvalidate.Problem(error.code, str(error), ""),), (), source_sha256, ())
    return check_data(document, source_sha256, factbase)


def check_file(path, factbase=None):
    """Like `check_bytes` on a file. An unreadable file is `PROFILE_FILE_UNREADABLE`."""
    try:
        with open(str(path), "rb") as handle:
            data = handle.read()
    except OSError as error:
        return CheckResult(None, (docvalidate.Problem(PREFIX + "FILE_UNREADABLE",
                                                      "cannot read the file: %s" % error.strerror, ""),), (), None, ())
    return check_bytes(data, factbase)


def parse_file(path, factbase=None):
    """The `Profile` of a file, or `ProfileError` carrying every problem."""
    result = check_file(path, factbase)
    if result.errors:
        raise ProfileError(result.errors)
    return result.profile
