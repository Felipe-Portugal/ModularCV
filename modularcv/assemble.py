"""AssembledResume-v1: the CV a verified tailoring plan describes, as structured data independent of LaTeX (M7-A).

Contract: `docs/design/CONTRACTS.md` section 5.2, user guide `docs/RENDER.md`. The plan of M6 is an *input*, not an
authorisation. Before anything is assembled the plan goes through the checks of `verify_plan`, in this order, and the first
failing layer stops the run:

1. `check_shape`        the plan is the object M6 writes (schema, status `PLAN_ONLY`, not reviewed, no `tailored_cv_id`).
2. `check_fingerprint`  `plan_sha256` matches the body: an edited plan is refused.
3. `check_sources`      the fingerprint of every source the plan records is the one of the source loaded now: a plan built
                        from other facts, content, profile, taxonomy or offer is obsolete.
4. `check_reproducible` the plan the engine builds *today* from those sources and the plan's own family and language is
                        byte-for-byte (canonically) the stored plan. This catches an edit whose hash was recomputed. The
                        rebuilt plan is only compared, never used: the stored plan is what is assembled.
5. `check_publishable`  an independent re-validation of everything the plan selects, against the fact base, the content and
                        the profile policy, whatever the earlier layers said.

The assembly then takes the selection from the plan and the words from the content. It writes no sentence, rewrites, shortens,
translates and enriches nothing, and adds nothing the plan does not select. A `soften` directive that would need a different
text stays listed as pending; it is never claimed to be applied. The result is not reviewed and never `READY_TO_SEND`.
"""
import copy
import re

from . import canonical, content as contentmod, docvalidate, facts, matrix as matrixmod, plan as planmod

SCHEMA = "AssembledResume-v1"
PREFIX = "ASSEMBLY_"
HASH = re.compile(r"[0-9a-f]{64}")
INPUT_KEYS = ("offer_sha256", "profile_sha256", "facts_source_sha256", "factbase_sha256", "content_sha256",
              "taxonomy_sha256", "matrix_sha256")
LABELS = {"en": {"skills": "Skills"}, "fr": {"skills": "Compétences"}}  # fixed interface words, never a claim
HEADING_FIELDS = contentmod.HEADING_FIELDS
LIMITS = (
    "The assembly is an intermediate artefact: not reviewed by a human, not a CV approved for sending, never READY_TO_SEND.",
    "A reference check proves that facts exist and are CONFIRMED, not that a text means what its facts say.",
    "French and English texts are paired by identifier; their equivalence is not checked and nothing is translated.",
    "A `soften` directive needs a text nobody approved: it stays pending and is not applied.",
    "The page target is recorded; the real page count exists only after a compilation.",
)


class AssemblyError(ValueError):
    """The plan cannot be assembled. `errors` holds every problem of the failing layer (code, fixed message, path)."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        first = self.errors[0]
        super().__init__("%s (%s): %s" % (first.code, first.path or "plan", first.message))

    @property
    def code(self):
        return self.errors[0].code


def _problem(code, message, path=""):
    return docvalidate.Problem(PREFIX + code, message, path)


# --- reading the plan ----------------------------------------------------------------------------------------

def load_plan(data):
    """The plan object of `data` (bytes): strict JSON, no duplicate key, no NaN. Raises `AssemblyError`."""
    try:
        document = docvalidate.load(data, PREFIX + "PLAN_")
    except docvalidate.DocumentError as error:
        raise AssemblyError([docvalidate.Problem(error.code, str(error), "")])
    return document


# --- layer 1: shape ------------------------------------------------------------------------------------------

def check_shape(plan):
    """Raises unless `plan` is an object of the shape M6 writes. Says nothing about whether it is true."""
    problems = []
    if not isinstance(plan, dict):
        raise AssemblyError([_problem("PLAN_NOT_OBJECT", "the plan must be a JSON object")])
    if plan.get("schema") != planmod.SCHEMA:
        problems.append(_problem("PLAN_SCHEMA", "the plan is not a TailoringPlan-v1", "schema"))
    if plan.get("plan_status") != "PLAN_ONLY" or plan.get("review") != {"status": "NOT_REVIEWED"} \
            or plan.get("tailored_cv_id") is not None:
        problems.append(_problem("PLAN_STATUS", "a plan must be PLAN_ONLY, not reviewed, with no tailored_cv_id", "plan_status"))
    for key in ("family", "language"):
        if not isinstance(plan.get(key), str) or not facts.valid_id(plan[key]):
            problems.append(_problem("PLAN_FIELD", "must be a valid identifier", key))
    inputs = plan.get("inputs")
    if not isinstance(inputs, dict) or sorted(inputs) != sorted(INPUT_KEYS) \
            or not all(isinstance(inputs[k], str) and HASH.fullmatch(inputs[k]) for k in inputs):
        problems.append(_problem("PLAN_FIELD", "must hold the recorded source fingerprints", "inputs"))
    selected = plan.get("selected")
    if not isinstance(selected, dict) or sorted(selected) != ["blocks", "bullets", "skills"] \
            or not all(isinstance(selected[k], list) and all(isinstance(e, dict) for e in selected[k]) for k in selected):
        problems.append(_problem("PLAN_FIELD", "must list the selected blocks, bullets and skills", "selected"))
    if not isinstance(plan.get("plan_sha256"), str) or not HASH.fullmatch(plan["plan_sha256"]):
        problems.append(_problem("PLAN_FIELD", "must be a sha256 fingerprint", "plan_sha256"))
    if problems:
        raise AssemblyError(problems)


# --- layer 2: the plan's own fingerprint ---------------------------------------------------------------------

def check_fingerprint(plan):
    if not planmod.verify_fingerprint(plan):
        raise AssemblyError([_problem("PLAN_FINGERPRINT", "plan_sha256 does not match the plan: it was modified", "plan_sha256")])


# --- layer 3: the sources it was built from ------------------------------------------------------------------

def current_inputs(offer, taxonomy, profile, factbase, content):
    return {"offer_sha256": offer.offer_sha256, "profile_sha256": profile.profile_sha256,
            "facts_source_sha256": factbase.facts_source_sha256, "factbase_sha256": factbase.factbase_sha256,
            "content_sha256": content.content_sha256, "taxonomy_sha256": taxonomy.taxonomy_sha256}


def check_sources(plan, offer, taxonomy, profile, factbase, content):
    now = current_inputs(offer, taxonomy, profile, factbase, content)
    problems = [_problem("SOURCE_MISMATCH", "this source is not the one the plan was built from: build the plan again",
                         "inputs." + key) for key in sorted(now) if plan["inputs"][key] != now[key]]
    if problems:
        raise AssemblyError(problems)


# --- layer 4: the engine would build the very same plan ------------------------------------------------------

def check_reproducible(plan, offer, taxonomy, profile, factbase, content):
    method = plan["offer"].get("language_method") if isinstance(plan.get("offer"), dict) else None
    requested = plan["language"] if method == "requested" else None  # an auto-detected language is detected again
    try:
        rebuilt, _matrix = planmod.build_plan(offer, taxonomy, profile, factbase, content, plan["family"], requested)
    except planmod.PlanError as error:
        raise AssemblyError([_problem("PLAN_REFUSED", "the engine no longer builds a plan from these sources", "plan")]
                            + list(error.errors))
    if canonical.canonical_bytes(plan) != canonical.canonical_bytes(rebuilt):
        differing = [key for key in sorted(rebuilt) if canonical.canonical_bytes(plan.get(key)) != canonical.canonical_bytes(rebuilt[key])]
        extra = sorted(key for key in plan if key not in rebuilt)
        path = (differing + extra + ["plan"])[0]
        raise AssemblyError([_problem("PLAN_NOT_REPRODUCIBLE", "the plan differs from the one the engine builds from these sources",
                                      path if re.fullmatch(r"[a-z_]+", path) else "plan")])


# --- layer 5: independent re-validation of what is selected --------------------------------------------------

def _fold_terms(values):
    return {canonical.fold(value) for value in values}


def _policy_hit(profile, language, texts, declared):
    """Whether a printed text or a declared technology/capability breaks the profile's publication policy."""
    policy = profile.policy
    prohibited = _fold_terms(policy["never_publish_terms"])
    words = prohibited | _fold_terms(policy["forbidden_words"].get(language, []))
    shown = canonical.fold(" ".join(texts))
    return any(matrixmod.contains_term(shown, word) for word in words) or bool(_fold_terms(declared) & prohibited)


def check_publishable(plan, offer, taxonomy, profile, factbase, content):
    """Independent of the planner: every selected block, bullet and skill is proven, written in the language, allowed."""
    language, family_id = plan["language"], plan["family"]
    by_id = {fact.id: fact for fact in factbase.facts}
    model = content.to_model()
    blocks = {block["id"]: block for block in model["blocks"]}
    bullets = {bullet["id"]: (block, bullet) for block in model["blocks"] for bullet in block["bullets"]}
    skills = {item["id"]: (category, item) for category in model["skills"] for item in category["items"]}
    family = profile.families.get(family_id)
    pool = matrixmod.build_pool(content, factbase, profile, taxonomy, family_id, language, offer.job_key)
    allowed = {(item.kind, item.id) for item in pool.items}
    printable = {entry.bullet_id for entry in content.selectable(factbase, language)}
    printable_skills = {item_id for _category, item_id in content.selectable_skills(factbase, language)}
    problems = []

    def proven(fact_ids):
        return bool(fact_ids) and all(f in by_id and by_id[f].status == facts.CONFIRMED for f in fact_ids)

    if family is None:
        raise AssemblyError([_problem("PLAN_FIELD", "the family is not in the profile", "family")])
    seen = set()
    for position, entry in enumerate(plan["selected"]["blocks"]):
        path = "selected.blocks[%d]" % position
        block = blocks.get(entry.get("id"))
        if block is None or entry.get("id") in seen:
            problems.append(_problem("ITEM_UNKNOWN" if block is None else "DUPLICATE_SELECTION",
                                     "the block is unknown or selected twice", path))
            continue
        seen.add(entry["id"])
        heading = block["heading"].get(language)
        if heading is None:
            problems.append(_problem("LANGUAGE_UNAVAILABLE", "the heading does not exist in the plan language", path))
        elif not proven(block["supports"]):
            problems.append(_problem("HEADING_UNPROVEN", "a fact behind the heading is missing or not CONFIRMED", path))
        elif entry.get("heading_supports") != sorted(block["supports"]):
            problems.append(_problem("PLAN_REFERENCE", "the recorded heading support differs from the content", path))
        elif block["id"] in family["excluded_blocks"] or _policy_hit(profile, language, [v for v in heading.values() if v], []):
            problems.append(_problem("ITEM_NOT_PUBLISHABLE", "the profile does not allow this heading", path))
    seen = set()
    selected_blocks = {entry.get("id"): entry for entry in plan["selected"]["blocks"]}
    for position, entry in enumerate(plan["selected"]["bullets"]):
        path = "selected.bullets[%d]" % position
        found = bullets.get(entry.get("id"))
        if found is None or entry["id"] in seen:
            problems.append(_problem("ITEM_UNKNOWN" if found is None else "DUPLICATE_SELECTION",
                                     "the bullet is unknown or selected twice", path))
            continue
        seen.add(entry["id"])
        block, bullet = found
        if entry.get("block") != block["id"] or entry["id"] not in selected_blocks.get(block["id"], {}).get("bullets", ()):
            problems.append(_problem("PLAN_REFERENCE", "the bullet is not listed under its own selected block", path))
        elif bullet["never_publish"]:
            problems.append(_problem("ITEM_NOT_PUBLISHABLE", "the bullet is marked never_publish", path))
        elif language not in bullet["text"]:
            problems.append(_problem("LANGUAGE_UNAVAILABLE", "the bullet does not exist in the plan language", path))
        elif not proven(bullet["supports"]) or not proven(block["supports"]) or entry["id"] not in printable:
            problems.append(_problem("FACT_NOT_CONFIRMED", "a fact behind the bullet or its heading is missing or not CONFIRMED", path))
        elif entry.get("supports") != sorted(bullet["supports"]):
            problems.append(_problem("PLAN_REFERENCE", "the recorded support differs from the content", path))
        elif _policy_hit(profile, language, [bullet["text"][language]], bullet["technologies"]) \
                or ("bullet", entry["id"]) not in allowed:
            problems.append(_problem("ITEM_NOT_PUBLISHABLE", "the profile policy does not allow this bullet", path))
    seen = set()
    for position, entry in enumerate(plan["selected"]["skills"]):
        path = "selected.skills[%d]" % position
        found = skills.get(entry.get("id"))
        if found is None or entry["id"] in seen:
            problems.append(_problem("ITEM_UNKNOWN" if found is None else "DUPLICATE_SELECTION",
                                     "the skill is unknown or selected twice", path))
            continue
        seen.add(entry["id"])
        category, item = found
        if entry.get("category") != category["id"]:
            problems.append(_problem("PLAN_REFERENCE", "the skill is not in the category the plan names", path))
        elif language not in item["text"]:
            problems.append(_problem("LANGUAGE_UNAVAILABLE", "the skill does not exist in the plan language", path))
        elif not proven(item["supports"]) or entry["id"] not in printable_skills:
            problems.append(_problem("FACT_NOT_CONFIRMED", "a fact behind the skill is missing or not CONFIRMED", path))
        elif _policy_hit(profile, language, [item["text"][language]], item["technologies"]) \
                or ("skill", entry["id"]) not in allowed:
            problems.append(_problem("ITEM_NOT_PUBLISHABLE", "the profile policy does not allow this skill", path))
    if problems:
        raise AssemblyError(problems)


LAYERS = (check_shape, check_fingerprint, check_sources, check_reproducible, check_publishable)


def verify_plan(plan, offer, taxonomy, profile, factbase, content):
    """Raises `AssemblyError` unless `plan` is intact, current, reproducible and publishable. Changes nothing."""
    check_shape(plan)
    check_fingerprint(plan)
    check_sources(plan, offer, taxonomy, profile, factbase, content)
    check_reproducible(plan, offer, taxonomy, profile, factbase, content)
    check_publishable(plan, offer, taxonomy, profile, factbase, content)


# --- inline formatting ---------------------------------------------------------------------------------------

def inline_spans(text):
    """`[{"text", "bold", "italic"}]` for a ResumeContent-v1 text, or None when its `**bold**`/`_italic_` markup is invalid.

    The markers follow exactly the rules of `content.inline_markup_problem`; an underscore inside a word is plain text."""
    if contentmod.inline_markup_problem(text):
        return None
    spans, buffer = [], []
    bold = italic = False

    def flush():
        if buffer:
            spans.append({"text": "".join(buffer), "bold": bold, "italic": italic})
            del buffer[:]

    i, size = 0, len(text)
    while i < size:
        if text.startswith("**", i):
            flush()
            bold = not bold
            i += 2
            continue
        if text[i] == "_":
            before = text[i - 1] if i else ""
            after = text[i + 1] if i + 1 < size else ""
            opener = (not before or not before.isalnum()) and bool(after) and not after.isspace() and after != "_"
            closer = bool(before) and not before.isspace() and before != "_" and (not after or not after.isalnum())
            if (italic and closer) or (not italic and opener):
                flush()
                italic = not italic
                i += 1
                continue
        buffer.append(text[i])
        i += 1
    flush()
    if bold or italic:
        return None
    return spans


# --- assembly ------------------------------------------------------------------------------------------------

def assemble(plan, offer, taxonomy, profile, factbase, content):
    """The `AssembledResume-v1` model for a verified `plan`. Raises `AssemblyError`; changes none of its arguments."""
    verify_plan(plan, offer, taxonomy, profile, factbase, content)
    language, family_id = plan["language"], plan["family"]
    model = content.to_model()
    view = profile.public_view()
    identity = view["identity"]
    problems = []
    if "display_name" not in identity:
        raise AssemblyError([_problem("HEADER_NAME_PRIVATE", "the display name is not public: a CV needs a name", "header")])

    header = {"display_name": identity["display_name"]}
    for name in ("location", "email", "phone"):
        if name in identity:
            header[name] = identity[name]
    header["links"] = view["links"]
    warnings = []
    if "headline" in identity:
        warnings.append({"code": "HEADLINE_NOT_PRINTED"})  # a self-description that no fact backs: left to a later decision

    sections_by_id = {section["id"]: section for section in model["sections"]}
    blocks = {block["id"]: block for block in model["blocks"]}
    position = {section["id"]: number for number, section in enumerate(model["sections"])}
    expected_order = sorted((entry["id"] for entry in plan["selected"]["blocks"]),
                            key=lambda block_id: (position[blocks[block_id]["section"]], blocks[block_id]["order"], block_id))
    if [entry["id"] for entry in plan["selected"]["blocks"]] != expected_order:
        raise AssemblyError([_problem("ORDER", "the plan lists the blocks in another order than the content defines", "selected.blocks")])
    bullet_entries = {entry["id"]: entry for entry in plan["selected"]["bullets"]}

    sections = []
    for section in model["sections"]:
        rendered_blocks = []
        for entry in plan["selected"]["blocks"]:
            block = blocks[entry["id"]]
            if block["section"] != section["id"]:
                continue
            content_order = [b["id"] for b in block["bullets"] if b["id"] in entry["bullets"]]
            if content_order != list(entry["bullets"]):
                raise AssemblyError([_problem("ORDER", "the plan lists the bullets in another order than the content defines",
                                              "selected.blocks")])
            heading = {name: block["heading"][language][name] for name in HEADING_FIELDS if block["heading"][language].get(name)}
            rendered_bullets = []
            for bullet in block["bullets"]:
                if bullet["id"] not in bullet_entries:
                    continue
                text = bullet["text"][language]
                spans = inline_spans(text)
                if spans is None:
                    problems.append(_problem("MARKUP", "the emphasis markers of this text are not valid", "bullet:" + bullet["id"]))
                    continue
                rendered_bullets.append({"id": bullet["id"], "text": text, "spans": spans,
                                         "supports": sorted(bullet["supports"])})
            rendered_blocks.append({"id": block["id"], "reason": entry["reason"], "heading": heading,
                                    "heading_supports": sorted(block["supports"]), "bullets": rendered_bullets})
        if rendered_blocks:
            title = section["title"].get(language)
            if title is None:
                raise AssemblyError([_problem("LANGUAGE_UNAVAILABLE", "the section title does not exist in the plan language",
                                              "section:" + section["id"])])
            sections.append({"id": section["id"], "kind": section["kind"], "title": title, "blocks": rendered_blocks})

    categories = []
    chosen = {entry["id"]: entry for entry in plan["selected"]["skills"]}
    for category in model["skills"]:
        items = []
        for item in category["items"]:
            if item["id"] in chosen:
                text = item["text"][language]
                spans = inline_spans(text)
                if spans is None:
                    problems.append(_problem("MARKUP", "the emphasis markers of this text are not valid", "skill:" + item["id"]))
                    continue
                items.append({"id": item["id"], "text": text, "spans": spans, "supports": sorted(item["supports"])})
        if items:
            title = category["title"].get(language)
            if title is None:
                raise AssemblyError([_problem("LANGUAGE_UNAVAILABLE", "the category title does not exist in the plan language",
                                              "category:" + category["id"])])
            categories.append({"id": category["id"], "title": title, "items": items})
    skills = None
    if categories:
        if language not in LABELS:
            raise AssemblyError([_problem("LABEL_UNAVAILABLE", "no fixed interface label exists for this language", "language")])
        skills = {"title": LABELS[language]["skills"], "categories": categories}
    if problems:
        raise AssemblyError(problems)

    used = sorted({fact for section in sections for block in section["blocks"] for fact in
                   list(block["heading_supports"]) + [f for b in block["bullets"] for f in b["supports"]]}
                  | {fact for category in categories for item in category["items"] for fact in item["supports"]})
    pending = sorted(({"type": w["type"], "id": w["id"], "directive": "soften"} for w in plan["warnings"]
                      if w["code"] == "GUIDANCE_SOFTEN_PENDING"), key=lambda p: (p["type"], p["id"]))
    families = profile.families
    assembly = {
        "schema": SCHEMA,
        "status": "ASSEMBLED_NOT_REVIEWED",
        "ready_to_send": False,
        "language": language,
        "family": family_id,
        "job_key": offer.job_key,
        "source": {"plan_sha256": plan["plan_sha256"], **{key: plan["inputs"][key] for key in sorted(plan["inputs"])}},
        "header": header,
        "sections": sections,
        "skills": skills,
        "fact_ids": used,
        "pending_directives": pending,
        "unsatisfied_required": copy.deepcopy(plan["unsatisfied_required"]),
        "warnings": sorted(warnings + [{"code": w["code"]} for w in plan["warnings"]], key=lambda w: w["code"]),
        "layout": {"page_target": families[family_id]["page_target"], "pages": None, "status": "NOT_COMPILED"},
        "limits": list(LIMITS),
    }
    assembly["assembly_sha256"] = canonical.fingerprint(assembly)
    return assembly


def verify_assembly_fingerprint(assembly):
    body = {key: value for key, value in assembly.items() if key != "assembly_sha256"}
    return assembly.get("assembly_sha256") == canonical.fingerprint(body)


def outline(assembly):
    """Identifiers and counts only: never a text, a name or a contact value."""
    return {
        "schema": assembly["schema"], "status": assembly["status"], "language": assembly["language"],
        "family": assembly["family"], "job_key": assembly["job_key"], "assembly_sha256": assembly["assembly_sha256"],
        "source": assembly["source"],
        "header_fields": sorted(key for key in assembly["header"] if assembly["header"][key]),
        "sections": [{"id": s["id"], "blocks": [{"id": b["id"], "reason": b["reason"], "bullets": [x["id"] for x in b["bullets"]]}
                                                for b in s["blocks"]]} for s in assembly["sections"]],
        "skills": None if assembly["skills"] is None else [{"id": c["id"], "items": [i["id"] for i in c["items"]]}
                                                          for c in assembly["skills"]["categories"]],
        "fact_ids": assembly["fact_ids"], "pending_directives": assembly["pending_directives"],
        "unsatisfied_required": [u["id"] for u in assembly["unsatisfied_required"]],
        "warnings": assembly["warnings"], "layout": assembly["layout"],
    }
