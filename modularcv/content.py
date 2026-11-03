"""ResumeContent-v1: the structured, validated text of a resume (`content/resume.json`).

Contract: `docs/design/CONTRACTS.md` section 3 and its M5 status (section 3.2). The module knows no name, employer,
school or sentence: all the text belongs to the user's workspace. The engine writes **no new sentence**; it only
validates, fingerprints and exposes what the file says.

What is checked, and what is not:

* **Structure** (always): the shape, the identifiers, the order, the FR/EN parity *by entity id*, the inline subset, and
  the refusal of raw LaTeX.
* **References to the fact base** (only when a `FactBase` is given): every fact a bullet, a skill or a block heading
  (title, employer, period, place: the factual fields) leans on exists and is `CONFIRMED`. Section and category
  titles are organisational and need none. Without a fact base the references are reported `UNVERIFIED`, never assumed.
* **Never checked**: that a text *means* what its supporting facts say, or that the French and the English text of an
  entity say the same thing. Support is explicit and human-made; the engine proves existence and status only.

Nothing in a content file is a confirmed fact, and the file has no status field: a bullet is publishable only because
the fact base says so. Error messages and reports never repeat a value of the document (see `docvalidate`).
"""
import copy
from collections import namedtuple

from . import canonical, docvalidate, facts

SCHEMA = "ResumeContent-v1"
PREFIX = "CONTENT_"

SECTION_KINDS = ("experience", "project", "education", "other")
HEADING_FIELDS = ("title", "subtitle", "period", "place")
ORDER_RANGE = (1, 9999)
TEXT_MAX = 1000
HEADING_MAX = 200

VERIFIED = "VERIFIED"
UNVERIFIED = "UNVERIFIED"
REFUSED = "REFUSED"
NEVER_PUBLISH = "NEVER_PUBLISH"

CheckResult = namedtuple("CheckResult", "content errors warnings content_source_sha256 references")
Reference = namedtuple("Reference", "path fact_id kind entity_path")
Entry = namedtuple("Entry", "bullet_id block_id section_id section_position block_order position languages text supports "
                            "heading_supports technologies capabilities follows condenses never_publish protected")

# The pair whose parity the contract requires (CONTRACTS.md section 3.1). Any other language is allowed
# without an obligation: it only has to be declared by the entity that uses it.
PARITY_PAIR = frozenset(("en", "fr"))


def required_languages(declared):
    """The languages every text of an entity declaring `declared` must be written in.

    A single declared language is required. Of several, `en` and `fr` are required when both are declared
    (the parity of the contract); no other language is ever required, so a third language may be partial."""
    declared = set(declared)
    if len(declared) == 1:
        return declared
    return set(PARITY_PAIR) if PARITY_PAIR <= declared else set()


def parity_holds(present, declared):
    """True when `present` uses only declared languages and includes the required ones."""
    present = set(present)
    return present <= set(declared) and required_languages(declared) <= present


class ContentError(ValueError):
    """The document is not a valid ResumeContent-v1. `errors` holds every problem found."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        first = self.errors[0]
        super().__init__("%s (%s): %s" % (first.code, first.path or "document", first.message))

    @property
    def code(self):
        return self.errors[0].code


class ResumeContent:
    """A valid content file. Read-only by convention: accessors return copies."""

    def __init__(self, model, source_sha256):
        self._model = model
        self.content_source_sha256 = source_sha256

    def to_model(self):
        """The canonical model (defaults filled in, sets sorted, blocks in print order). Input of `content_sha256`."""
        return copy.deepcopy(self._model)

    @property
    def content_sha256(self):
        return canonical.fingerprint(self._model)

    @property
    def languages(self):
        """Every language some text of the file is written in."""
        found = set()
        for block in self._model["blocks"]:
            found.update(block["languages"])
        for category in self._model["skills"]:
            found.update(category["title"])
        return tuple(sorted(found))

    def counts(self):
        blocks = self._model["blocks"]
        bullets = [bullet for block in blocks for bullet in block["bullets"]]
        return {
            "sections": len(self._model["sections"]),
            "blocks": len(blocks),
            "bilingual_blocks": sum(1 for block in blocks if len(block["languages"]) > 1),
            "bullets": len(bullets),
            "never_publish_bullets": sum(1 for bullet in bullets if bullet["never_publish"]),
            "skill_categories": len(self._model["skills"]),
            "skill_items": sum(len(category["items"]) for category in self._model["skills"]),
            "baselines": len(self._model["baselines"]),
        }

    def fact_ids(self):
        """Every fact id the file leans on, sorted. A reference, not a proof: see `selectable`."""
        found = set()
        for block in self._model["blocks"]:
            found.update(block["supports"])
            for bullet in block["bullets"]:
                found.update(bullet["supports"])
        for category in self._model["skills"]:
            for item in category["items"]:
                found.update(item["supports"])
        return tuple(sorted(found))

    def reservoir(self):
        """Every bullet, in print order, with its explicit support. Nothing is filtered: see `selectable`."""
        entries = []
        positions = {section["id"]: number for number, section in enumerate(self._model["sections"])}
        for block in self._model["blocks"]:
            for position, bullet in enumerate(block["bullets"]):
                entries.append(Entry(
                    bullet["id"], block["id"], block["section"], positions[block["section"]], block["order"], position,
                    tuple(block["languages"]), dict(bullet["text"]), tuple(bullet["supports"]),
                    tuple(block["supports"]), tuple(bullet["technologies"]), tuple(bullet["capabilities"]), bullet["follows"],
                    tuple(bullet["condenses"]), bullet["never_publish"], block["protected"]))
        return tuple(entries)

    def selectable(self, factbase, language):
        """The bullets a document in `language` may print: written in that language, not `never_publish`, with
        support that exists and is `CONFIRMED` in `factbase` **for the bullet and for the heading of its block**
        (a proven bullet under an unproven title, employer or period is not printable). The content cannot promote
        anything itself: an unverified field is never selectable."""
        by_id = {fact.id: fact for fact in factbase.facts}
        return tuple(entry for entry in self.reservoir()
                     if not entry.never_publish and language in entry.text
                     and _proven(by_id, entry.supports) and _proven(by_id, entry.heading_supports))

    def selectable_skills(self, factbase, language):
        """The skill items written in `language` whose support exists and is `CONFIRMED` in `factbase`, in print
        order, as `(category id, item id)` pairs."""
        by_id = {fact.id: fact for fact in factbase.facts}
        return tuple((category["id"], item["id"]) for category in self._model["skills"] for item in category["items"]
                     if language in item["text"] and _proven(by_id, item["supports"]))

    def baseline(self, family, language):
        """The baseline of a family and language as a copy, or None."""
        for baseline in self._model["baselines"]:
            if baseline["family"] == family and baseline["language"] == language:
                return copy.deepcopy(baseline)
        return None


def _proven(by_id, fact_ids):
    """Non-empty support, every fact existing and `CONFIRMED`."""
    return bool(fact_ids) and all(fact_id in by_id and by_id[fact_id].status == facts.CONFIRMED for fact_id in fact_ids)


# --- text ---------------------------------------------------------------------------------------------

def _plain(reader, value, path, limit):
    """A single-line text with no backslash. A backslash is TeX's escape: raw LaTeX is refused, the renderer escapes.

    `%`, `&`, `$`, `#`, `_`, `{`, `}`, `~` and `^` are ordinary characters here (\"50% faster\", \"R&D\", \"C#\")."""
    text = reader.text(value, path)
    if text is None:
        return None
    if len(text) > limit:
        reader.error("TOO_LONG", path, "the text is longer than %d characters" % limit)
        return None
    if "\\" in text:
        reader.error("RAW_LATEX", path, "a backslash starts raw LaTeX, which is refused; write plain text")
        return None
    return text


def inline_markup_problem(text):
    """True when `text` misuses the inline subset: `**bold**` and `_italic_`, balanced, not empty, not crossed.

    An underscore inside a word (`snake_case`) is ordinary text; it opens italics only at the start of a word."""
    stack = []  # (marker, index where its content starts)
    i, size = 0, len(text)
    while i < size:
        if text.startswith("**", i):
            if stack and stack[-1][0] == "**":
                if i == stack[-1][1]:
                    return True
                stack.pop()
            elif any(marker == "**" for marker, _ in stack):
                return True
            else:
                stack.append(("**", i + 2))
            i += 2
            continue
        if text[i] == "_":
            before = text[i - 1] if i else ""
            after = text[i + 1] if i + 1 < size else ""
            opener = (not before or not before.isalnum()) and bool(after) and not after.isspace() and after != "_"
            closer = bool(before) and not before.isspace() and before != "_" and (not after or not after.isalnum())
            italic_open = any(marker == "_" for marker, _ in stack)
            if italic_open and closer:
                if stack[-1][0] != "_" or i == stack[-1][1]:
                    return True
                stack.pop()
            elif not italic_open and opener:
                stack.append(("_", i + 1))
        i += 1
    return bool(stack)


def _inline(reader, value, path):
    text = _plain(reader, value, path, TEXT_MAX)
    if text is not None and inline_markup_problem(text):
        reader.error("INLINE_MARKUP", path, "emphasis markers (`**` and `_`) must be balanced, not empty and not crossed")
        return None
    return text


def _language_map(reader, value, path, check):
    """{language: checked value}, or None when the object or one of its entries is unusable."""
    if not isinstance(value, dict):
        reader.error("BAD_TYPE", path, "must be a JSON object mapping language codes to values")
        return None
    if not value:
        reader.error("EMPTY_VALUE", path, "must not be empty")
        return None
    result, usable = {}, True
    for code in value:
        code_path = docvalidate.join_key(path, code)
        if reader.lang(code, code_path) is None:
            usable = False
            continue
        checked = check(value[code], code_path)
        if checked is None:
            usable = False
            continue
        result[code] = checked
    return result if usable else None


def _identifier_list(reader, value, path, sort):
    """A list of identifiers without repeats (sorted when the order carries no meaning)."""
    items = reader.lst(value, path)
    found = []
    for position, item in enumerate(items or ()):
        checked = reader.ident(item, docvalidate.index(path, position))
        if checked is not None:
            found.append(checked)
    found = reader.unique(found, path)
    return sorted(found) if sort else found


def _register(reader, registry, value, path):
    """Record an identifier in its namespace; a second use is `CONTENT_DUPLICATE_ID`."""
    if value is None:
        return
    if value in registry:
        reader.error("DUPLICATE_ID", path, "this identifier is already used in its namespace")
    else:
        registry[value] = path


def _technologies(reader, value, path):
    """Display names; the order the user wrote is kept (it may be the display order)."""
    items = reader.lst(value, path)
    found = []
    for position, item in enumerate(items or ()):
        text = _plain(reader, item, docvalidate.index(path, position), HEADING_MAX)
        if text is not None:
            found.append(text)
    return reader.unique(found, path, key=canonical.fold)


# --- entities -----------------------------------------------------------------------------------------

def _check_sections(reader, value, ids):
    items = reader.lst(value, "sections", empty_ok=False)
    sections = []
    for position, item in enumerate(items or ()):
        path = docvalidate.index("sections", position)
        data, extensions = reader.obj(item, path, required=("id", "kind", "title"))
        if data is None:
            continue
        section_id = reader.ident(data["id"], docvalidate.join(path, "id")) if "id" in data else None
        kind = reader.choice(data["kind"], docvalidate.join(path, "kind"), SECTION_KINDS) if "kind" in data else None
        title = _language_map(reader, data["title"], docvalidate.join(path, "title"),
                              lambda v, p: _plain(reader, v, p, HEADING_MAX)) if "title" in data else None
        _register(reader, ids["sections"], section_id, docvalidate.join(path, "id"))
        if section_id is None or kind is None or title is None:
            continue
        record = {"id": section_id, "kind": kind, "title": title}
        if extensions:
            record["extensions"] = extensions
        sections.append(record)
    return sections


def _check_heading(reader, value, path):
    data, extensions = reader.obj(value, path, required=("title",), optional=HEADING_FIELDS[1:])
    if data is None:
        return None
    record, usable = {}, True
    for name in HEADING_FIELDS:
        given = data.get(name)
        if name not in data or (given is None and name != "title"):
            record[name] = None
            continue
        checked = _plain(reader, given, docvalidate.join(path, name), HEADING_MAX)
        usable = usable and checked is not None
        record[name] = checked
    if extensions:
        record["extensions"] = extensions
    return record if usable and record["title"] is not None else None


def _check_bullet(reader, value, path, languages, ids, refs, bullet_ids):
    data, extensions = reader.obj(value, path, required=("id", "text"), optional=(
        "supports", "technologies", "capabilities", "follows", "condenses", "never_publish"))
    if data is None:
        return None
    bullet_id = reader.ident(data["id"], docvalidate.join(path, "id")) if "id" in data else None
    _register(reader, ids["bullets"], bullet_id, docvalidate.join(path, "id"))
    text = _language_map(reader, data["text"], docvalidate.join(path, "text"),
                         lambda v, p: _inline(reader, v, p)) if "text" in data else None
    if text is not None and languages and not parity_holds(text, languages):
        reader.error("PARITY_BULLET", docvalidate.join(path, "text"),
                     "a bullet must be written in declared languages only, and in en and fr when its block declares both")
    never = False
    if "never_publish" in data:
        flag = reader.boolean(data["never_publish"], docvalidate.join(path, "never_publish"))
        never = bool(flag)
    supports = _identifier_list(reader, data["supports"], docvalidate.join(path, "supports"), True) \
        if "supports" in data else []
    if not supports and not never and bullet_id is not None:
        reader.error("UNSUPPORTED_BULLET", path, "a publishable bullet must name the facts that support it")
    technologies = _technologies(reader, data["technologies"], docvalidate.join(path, "technologies")) \
        if "technologies" in data else []
    capabilities = _identifier_list(reader, data["capabilities"], docvalidate.join(path, "capabilities"), True) \
        if "capabilities" in data else []
    follows = None
    if data.get("follows") is not None:
        follows = reader.ident(data["follows"], docvalidate.join(path, "follows"))
    condenses = _identifier_list(reader, data["condenses"], docvalidate.join(path, "condenses"), True) \
        if "condenses" in data else []
    for fact_position, fact_id in enumerate(supports):
        refs.append(Reference(docvalidate.index(docvalidate.join(path, "supports"), fact_position), fact_id,
                              "unpublished" if never else "bullet", path))
    if bullet_id is None or text is None:
        return None
    bullet_ids.append(bullet_id)
    record = {"id": bullet_id, "text": text, "supports": supports, "technologies": technologies,
              "capabilities": capabilities, "follows": follows, "condenses": condenses, "never_publish": never}
    if extensions:
        record["extensions"] = extensions
    return record


def _check_blocks(reader, value, ids, refs, section_ids):
    items = reader.lst(value, "blocks", empty_ok=False)
    blocks, orders = [], {}
    for position, item in enumerate(items or ()):
        path = docvalidate.index("blocks", position)
        data, extensions = reader.obj(item, path, required=("id", "section", "order", "languages", "heading"),
                                      optional=("protected", "bullets", "supports"))
        if data is None:
            continue
        block_id = reader.ident(data["id"], docvalidate.join(path, "id")) if "id" in data else None
        _register(reader, ids["blocks"], block_id, docvalidate.join(path, "id"))
        section = reader.ident(data["section"], docvalidate.join(path, "section")) if "section" in data else None
        if section is not None and section not in section_ids:
            reader.error("UNKNOWN_SECTION", docvalidate.join(path, "section"), "the section does not exist")
            section = None
        order = reader.integer(data["order"], docvalidate.join(path, "order"), *ORDER_RANGE) \
            if "order" in data else None
        if section is not None and order is not None:
            if (section, order) in orders:
                reader.error("DUPLICATE_ORDER", docvalidate.join(path, "order"),
                             "two blocks of one section share this order")
            orders[(section, order)] = True
        languages = []
        if "languages" in data:
            raw = reader.lst(data["languages"], docvalidate.join(path, "languages"), empty_ok=False)
            for l_position, code in enumerate(raw or ()):
                checked = reader.lang(code, docvalidate.index(docvalidate.join(path, "languages"), l_position))
                if checked is not None:
                    languages.append(checked)
            languages = sorted(reader.unique(languages, docvalidate.join(path, "languages")))
        heading = _check_heading_map(reader, data["heading"], docvalidate.join(path, "heading")) \
            if "heading" in data else None
        if heading is not None and languages and not parity_holds(heading, languages):
            reader.error("PARITY_HEADING", docvalidate.join(path, "heading"),
                         "the heading must use declared languages only, and en and fr when the block declares both")
        supports = _identifier_list(reader, data["supports"], docvalidate.join(path, "supports"), True) \
            if "supports" in data else []
        if not supports and block_id is not None:
            reader.error("UNSUPPORTED_HEADING", path,
                         "the heading (title, employer, period, place) must name the facts that support it")
        for fact_position, fact_id in enumerate(supports):
            refs.append(Reference(docvalidate.index(docvalidate.join(path, "supports"), fact_position), fact_id,
                                  "heading", path))
        protected = False
        if "protected" in data:
            flag = reader.boolean(data["protected"], docvalidate.join(path, "protected"))
            protected = bool(flag)
        bullets, bullet_ids = [], []
        bullets_path = docvalidate.join(path, "bullets")
        for b_position, bullet_item in enumerate(reader.lst(data.get("bullets", []), bullets_path) or ()):
            bullet = _check_bullet(reader, bullet_item, docvalidate.index(bullets_path, b_position), languages, ids,
                                   refs, bullet_ids)
            if bullet is not None:
                bullets.append(bullet)
        if None in (block_id, section, order, heading) or not languages:
            continue
        record = {"id": block_id, "section": section, "order": order, "languages": languages, "heading": heading,
                  "supports": supports, "protected": protected, "bullets": bullets}
        if extensions:
            record["extensions"] = extensions
        blocks.append((path, record))
    return blocks


def _check_heading_map(reader, value, path):
    return _language_map(reader, value, path, lambda v, p: _check_heading(reader, v, p))


def _check_skills(reader, value, ids, refs):
    items = reader.lst(value, "skills")
    categories = []
    for position, item in enumerate(items or ()):
        path = docvalidate.index("skills", position)
        data, extensions = reader.obj(item, path, required=("id", "title", "items"))
        if data is None:
            continue
        category_id = reader.ident(data["id"], docvalidate.join(path, "id")) if "id" in data else None
        _register(reader, ids["categories"], category_id, docvalidate.join(path, "id"))
        title = _language_map(reader, data["title"], docvalidate.join(path, "title"),
                              lambda v, p: _plain(reader, v, p, HEADING_MAX)) if "title" in data else None
        languages = sorted(title) if title else []
        entries = []
        items_path = docvalidate.join(path, "items")
        raw = reader.lst(data["items"], items_path, empty_ok=False) if "items" in data else None
        for i_position, entry in enumerate(raw or ()):
            entry_path = docvalidate.index(items_path, i_position)
            skill, skill_ext = reader.obj(entry, entry_path, required=("id", "text"),
                                          optional=("supports", "technologies"))
            if skill is None:
                continue
            skill_id = reader.ident(skill["id"], docvalidate.join(entry_path, "id")) if "id" in skill else None
            _register(reader, ids["skills"], skill_id, docvalidate.join(entry_path, "id"))
            text = _language_map(reader, skill["text"], docvalidate.join(entry_path, "text"),
                                 lambda v, p: _inline(reader, v, p)) if "text" in skill else None
            if text is not None and languages and not parity_holds(text, languages):
                reader.error("PARITY_ITEM", docvalidate.join(entry_path, "text"),
                             "a skill must be written in declared languages only, and in en and fr when its category declares both")
            supports = _identifier_list(reader, skill["supports"], docvalidate.join(entry_path, "supports"), True) \
                if "supports" in skill else []
            if not supports and skill_id is not None:
                reader.error("UNSUPPORTED_SKILL", entry_path, "a skill must name the facts that support it")
            technologies = _technologies(reader, skill["technologies"], docvalidate.join(entry_path, "technologies")) \
                if "technologies" in skill else []
            for fact_position, fact_id in enumerate(supports):
                refs.append(Reference(docvalidate.index(docvalidate.join(entry_path, "supports"), fact_position),
                                      fact_id, "skill", entry_path))
            if skill_id is None or text is None:
                continue
            record = {"id": skill_id, "text": text, "supports": supports, "technologies": technologies}
            if skill_ext:
                record["extensions"] = skill_ext
            entries.append(record)
        if category_id is None or title is None:
            continue
        record = {"id": category_id, "title": title, "items": entries}
        if extensions:
            record["extensions"] = extensions
        categories.append(record)
    return categories


def _check_baselines(reader, value):
    items = reader.lst(value, "baselines")
    baselines, seen = [], set()
    for position, item in enumerate(items or ()):
        path = docvalidate.index("baselines", position)
        data, extensions = reader.obj(item, path, required=("family", "language", "items"),
                                      optional=("skills", "focus"))
        if data is None:
            continue
        family = reader.ident(data["family"], docvalidate.join(path, "family")) if "family" in data else None
        language = reader.lang(data["language"], docvalidate.join(path, "language")) if "language" in data else None
        selected = _identifier_list(reader, data["items"], docvalidate.join(path, "items"), False) \
            if "items" in data else None
        skills = _identifier_list(reader, data["skills"], docvalidate.join(path, "skills"), False) \
            if "skills" in data else []
        focus = None
        if data.get("focus") is not None:
            focus = _plain(reader, data["focus"], docvalidate.join(path, "focus"), TEXT_MAX)
        if family and language:
            if (family, language) in seen:
                reader.error("DUPLICATE_BASELINE", path, "this family and language already have a baseline")
            seen.add((family, language))
        if None in (family, language, selected) or ("focus" in data and data["focus"] is not None and focus is None):
            continue
        record = {"family": family, "language": language, "items": selected, "skills": skills, "focus": focus}
        if extensions:
            record["extensions"] = extensions
        baselines.append((path, record))
    return baselines


# --- cross references ---------------------------------------------------------------------------------

def _has_cycle(edges):
    state = {}

    def visit(node):
        state[node] = 1
        for nxt in edges.get(node, ()):
            if state.get(nxt) == 1 or (state.get(nxt) is None and visit(nxt)):
                return True
        state[node] = 2
        return False

    return any(state.get(node) is None and visit(node) for node in list(edges))


def _check_links(reader, blocks):
    """`follows` and `condenses` name another bullet of the same block; neither may loop."""
    follows_edges, condenses_edges = {}, {}
    for block_number, (block_path, block) in enumerate(blocks):
        members = {bullet["id"] for bullet in block["bullets"]}
        for b_position, bullet in enumerate(block["bullets"]):
            path = docvalidate.index(docvalidate.join(block_path, "bullets"), b_position)
            if bullet["follows"] is not None:
                if bullet["follows"] == bullet["id"]:
                    reader.error("INVALID_REFERENCE", docvalidate.join(path, "follows"), "a bullet cannot follow itself")
                elif bullet["follows"] not in members:
                    reader.error("UNKNOWN_BULLET", docvalidate.join(path, "follows"),
                                 "must name another bullet of the same block")
                else:
                    follows_edges[bullet["id"]] = {bullet["follows"]}
            for c_position, target in enumerate(bullet["condenses"]):
                c_path = docvalidate.index(docvalidate.join(path, "condenses"), c_position)
                if target == bullet["id"]:
                    reader.error("INVALID_REFERENCE", c_path, "a bullet cannot condense itself")
                elif target not in members:
                    reader.error("UNKNOWN_BULLET", c_path, "must name another bullet of the same block")
                else:
                    condenses_edges.setdefault(bullet["id"], set()).add(target)
    if _has_cycle(follows_edges):
        reader.error("REFERENCE_CYCLE", "blocks", "`follows` links form a loop")
    if _has_cycle(condenses_edges):
        reader.error("REFERENCE_CYCLE", "blocks", "`condenses` links form a loop")


def _check_parity(reader, sections, blocks, categories):
    """A section title, like a heading, must exist in every language its blocks declare."""
    needed = {}
    for _path, block in blocks:
        needed.setdefault(block["section"], set()).update(block["languages"])
    for position, section in enumerate(sections):
        missing = required_languages(needed.get(section["id"], set())) - set(section["title"])
        if missing:
            reader.error("PARITY_TITLE", docvalidate.join(docvalidate.index("sections", position), "title"),
                         "the title must exist in the languages its blocks require (en and fr when they declare both)")


def _check_baseline_links(reader, baselines, blocks, categories, profile):
    bullets = {bullet["id"]: (block, bullet) for _path, block in blocks for bullet in block["bullets"]}
    skills = {item["id"]: category for category in categories for item in category["items"]}
    for path, baseline in baselines:
        language, chosen = baseline["language"], set(baseline["items"])
        position_of = {bullet_id: number for number, bullet_id in enumerate(baseline["items"])}
        for number, bullet_id in enumerate(baseline["items"]):
            item_path = docvalidate.index(docvalidate.join(path, "items"), number)
            if bullet_id not in bullets:
                reader.error("UNKNOWN_BULLET", item_path, "the baseline names a bullet that does not exist")
                continue
            block, bullet = bullets[bullet_id]
            if bullet["never_publish"]:
                reader.error("BASELINE_NEVER_PUBLISH", item_path, "a never_publish bullet cannot be part of a baseline")
            if language not in bullet["text"]:
                reader.error("BASELINE_LANGUAGE", item_path, "the bullet has no text in the language of the baseline")
            if chosen & set(bullet["condenses"]):
                reader.error("BASELINE_EXCLUSIVE", item_path,
                             "a bullet and a bullet it condenses cannot be selected together")
            if bullet["follows"] is not None and position_of.get(bullet["follows"], number + 1) >= number:
                reader.error("BASELINE_FOLLOWS", item_path, "the bullet it follows must be selected before it")
        for number, skill_id in enumerate(baseline["skills"]):
            item_path = docvalidate.index(docvalidate.join(path, "skills"), number)
            if skill_id not in skills:
                reader.error("UNKNOWN_SKILL", item_path, "the baseline names a skill that does not exist")
            elif language not in skills[skill_id]["title"]:
                reader.error("BASELINE_LANGUAGE", item_path, "the skill has no text in the language of the baseline")
        if profile is not None:
            family = profile.families.get(baseline["family"])
            if family is None:
                reader.error("BASELINE_FAMILY_UNKNOWN", docvalidate.join(path, "family"),
                             "the profile has no such family")
            elif language not in family["languages"]:
                reader.error("BASELINE_FAMILY_LANGUAGE", docvalidate.join(path, "language"),
                             "the family does not use this language")


def _verify_references(reader, refs, factbase, require_date):
    """Check every reference against the fact base. Returns the set of entity paths that cannot be published."""
    by_id = {fact.id: fact for fact in factbase.facts}
    refused = set()
    for ref in refs:
        fact = by_id.get(ref.fact_id)
        if fact is None:
            reader.error("FACT_UNKNOWN", ref.path, "the referenced fact does not exist in the fact base")
            if ref.kind != "unpublished":
                refused.add((ref.kind, ref.entity_path))
        elif ref.kind == "unpublished":
            continue
        elif fact.status != facts.CONFIRMED:
            reader.error("FACT_NOT_CONFIRMED", ref.path, "the referenced fact is not CONFIRMED (status %s)" % fact.status)
            refused.add((ref.kind, ref.entity_path))
        elif require_date and fact.confirmed_on is None:
            reader.error("FACT_DATE_REQUIRED", ref.path, "this workspace requires `confirmed_on` on a CONFIRMED fact")
            refused.add((ref.kind, ref.entity_path))
    unsupported = {"bullet": "UNSUPPORTED_BULLET", "skill": "UNSUPPORTED_SKILL", "heading": "UNSUPPORTED_HEADING"}
    for kind, entity_path in sorted(refused, key=lambda item: (item[1], item[0])):
        reader.error(unsupported[kind], entity_path,
                     "a supporting fact is missing or not CONFIRMED, so this cannot be published")
    return refused


def _technology_warnings(blocks, categories, factbase):
    """A declared technology that no supporting fact lists is flagged, never added or removed by the engine."""
    by_id = {fact.id: fact for fact in factbase.facts}
    warnings = []

    def check(entity, entity_path):
        known = {canonical.fold(tech) for fact_id in entity["supports"] if fact_id in by_id
                 for tech in by_id[fact_id].technologies}
        for position, tech in enumerate(entity["technologies"]):
            if canonical.fold(tech) not in known:
                warnings.append(docvalidate.Problem(
                    PREFIX + "TECHNOLOGY_NOT_IN_SUPPORT",
                    "no supporting fact lists this technology; the engine does not infer it",
                    docvalidate.index(docvalidate.join(entity_path, "technologies"), position)))

    for block_path, block in blocks:
        for b_position, bullet in enumerate(block["bullets"]):
            if not bullet["never_publish"]:
                check(bullet, docvalidate.index(docvalidate.join(block_path, "bullets"), b_position))
    for c_position, category in enumerate(categories):
        for i_position, item in enumerate(category["items"]):
            check(item, docvalidate.index(docvalidate.join(docvalidate.index("skills", c_position), "items"), i_position))
    return warnings


# --- entry points -------------------------------------------------------------------------------------

def _ordered(problems):
    return sorted(problems, key=lambda problem: (problem.path, problem.code))


def check_data(document, source_sha256=None, factbase=None, profile=None):
    """Check an already decoded JSON value. `content` is None when `errors` is not empty.

    With a `factbase`, every reference is verified; without one they stay `UNVERIFIED` and the result says so with the
    warning `CONTENT_FACTS_NOT_CHECKED`. A `profile` (optional) adds the check of baseline families and of
    `policy.require_confirmation_date`."""
    reader = docvalidate.Reader(PREFIX)
    data, extensions = reader.obj(document, "", required=("schema", "sections", "blocks"),
                                  optional=("skills", "baselines"))
    if data is None:
        return CheckResult(None, tuple(reader.problems), (), source_sha256, ())
    if "schema" in data and data["schema"] != SCHEMA:
        reader.error("UNKNOWN_SCHEMA", "schema", "unsupported schema, expected `%s`" % SCHEMA)
        return CheckResult(None, tuple(reader.problems), (), source_sha256, ())

    ids = {name: {} for name in ("sections", "blocks", "bullets", "categories", "skills")}
    refs = []
    sections = _check_sections(reader, data["sections"], ids) if "sections" in data else []
    blocks = _check_blocks(reader, data["blocks"], ids, refs, set(ids["sections"])) if "blocks" in data else []
    categories = _check_skills(reader, data["skills"], ids, refs) if "skills" in data else []
    baselines = _check_baselines(reader, data["baselines"]) if "baselines" in data else []
    if not reader.problems:
        _check_links(reader, blocks)
        _check_parity(reader, sections, blocks, categories)
        _check_baseline_links(reader, baselines, blocks, categories, profile)

    warnings = []
    refused = set()
    if refs and not reader.problems:
        if factbase is not None:
            refused = _verify_references(reader, refs, factbase,
                                         bool(profile is not None and profile.require_confirmation_date))
            if not reader.problems:
                warnings.extend(_technology_warnings(blocks, categories, factbase))
        else:
            warnings.append(docvalidate.Problem(PREFIX + "FACTS_NOT_CHECKED",
                                                "fact references were not checked against a fact base", ""))

    references = []
    for block_path, block in blocks:
        state = UNVERIFIED if factbase is None else (REFUSED if ("heading", block_path) in refused else VERIFIED)
        references.append(("heading", block["id"], state))
        for b_position, bullet in enumerate(block["bullets"]):
            path = docvalidate.index(docvalidate.join(block_path, "bullets"), b_position)
            if bullet["never_publish"]:
                state = NEVER_PUBLISH
            elif factbase is None:
                state = UNVERIFIED
            else:
                state = REFUSED if ("bullet", path) in refused else VERIFIED
            references.append(("bullet", bullet["id"], state))
    for c_position, category in enumerate(categories):
        for i_position, item in enumerate(category["items"]):
            path = docvalidate.index(docvalidate.join(docvalidate.index("skills", c_position), "items"), i_position)
            state = UNVERIFIED if factbase is None else (REFUSED if ("skill", path) in refused else VERIFIED)
            references.append(("skill", item["id"], state))

    if reader.problems:
        return CheckResult(None, tuple(_ordered(reader.problems)), tuple(warnings), source_sha256, tuple(references))

    position_of = {section["id"]: number for number, section in enumerate(sections)}
    ordered_blocks = [block for _path, block in sorted(
        blocks, key=lambda pair: (position_of[pair[1]["section"]], pair[1]["order"], pair[1]["id"]))]
    model = {
        "schema": SCHEMA,
        "sections": sections,
        "blocks": ordered_blocks,
        "skills": categories,
        "baselines": [record for _path, record in sorted(baselines, key=lambda pair: (pair[1]["family"], pair[1]["language"]))],
    }
    if extensions:
        model["extensions"] = extensions
    return CheckResult(ResumeContent(model, source_sha256), (), tuple(warnings), source_sha256, tuple(references))


def check_bytes(data, factbase=None, profile=None):
    """Check the raw bytes of `resume.json`. Never raises on a bad file."""
    source_sha256 = canonical.sha256_text(data)
    try:
        document = docvalidate.load(data, PREFIX)
    except docvalidate.DocumentError as error:
        return CheckResult(None, (docvalidate.Problem(error.code, str(error), ""),), (), source_sha256, ())
    return check_data(document, source_sha256, factbase, profile)


def check_file(path, factbase=None, profile=None):
    """Like `check_bytes` on a file. An unreadable file is `CONTENT_FILE_UNREADABLE`."""
    try:
        with open(str(path), "rb") as handle:
            data = handle.read()
    except OSError as error:
        return CheckResult(None, (docvalidate.Problem(PREFIX + "FILE_UNREADABLE",
                                                      "cannot read the file: %s" % error.strerror, ""),), (), None, ())
    return check_bytes(data, factbase, profile)


def parse_file(path, factbase=None, profile=None):
    """The `ResumeContent` of a file, or `ContentError` carrying every problem."""
    result = check_file(path, factbase, profile)
    if result.errors:
        raise ContentError(result.errors)
    return result.content
