"""TailoringPlan-v1: a deterministic, traceable selection of the content a CV for one offer may print.

Contract: `docs/design/CONTRACTS.md` sections 3.3 and 5, algorithm of `docs/design/ENGINE.md` section 2.3. The plan is an
*input for the renderer* (M7). It is not a CV, not a reviewed CV and not a `READY_TO_SEND` package: it only names, by id,
which proven bullets, headings and skills to print, in print order, with the reason for each choice. It writes no sentence,
reads no unproven content and changes no source.

Selection (greedy, marginal coverage):

* Only **eligible** items are considered: proven bullets under a proven heading and proven skills, written in the target
  language, not excluded by the family, the policy (`never_publish_terms`, `forbidden_words`, `omit_by_default_terms`) or
  the job's `guidance`. A baseline or a core skill can never bring an excluded item back.
* Each requirement covered by an item (`DIRECT` evidence, or `ADJACENT` evidence scaled by `inferred_factor`) gives
  `weight / (1 + n)` where `n` items already cover it (saturation). A technology requirement first covered directly gets
  `named_bonus`. An item of the family baseline gets `baseline_prior`. An item declaring capabilities outside the family's
  `clusters` loses `off_target_penalty` per capability, capped at `off_target_penalty_cap`.
* The item with the largest gain is taken while that gain is at least `minimum_gain`. Ties are broken by print position
  (section, block order, bullet order) and then by id, so the same canonical inputs always give the same plan.
* `follows` pulls its predecessor in first; a bullet and a bullet it `condenses` are never selected together; a profile
  precedence rule drops the `over` block when the `keep` block directly proves the requirement; a protected block keeps its
  proven heading even when no bullet is selected.

A required requirement that nothing proves stays listed as unsatisfied. Nothing is invented to fill a page.
"""
import copy

from . import canonical, docvalidate, facts, joboffer, matrix as matrixmod, taxonomy as taxonomymod

SCHEMA = "TailoringPlan-v1"
PREFIX = "PLAN_"
GAIN_PRECISION = 9

LIMITS = (
    "Requirements come from explicit offer entries and exact taxonomy spellings in the posting; no semantic reading of the text.",
    "A reference check proves that facts exist and are CONFIRMED, not that a text means what its facts say.",
    "French and English texts are paired by identifier; their equivalence is not checked.",
    "ADJACENT means a declared neighbouring capability is proven; it never states the required one.",
    "The plan is not a CV, not reviewed by a human and not a READY_TO_SEND package.",
    "The page target of the family is recorded, not enforced.",
)


class PlanError(ValueError):
    """The plan cannot be built. `errors` holds every problem found (code, fixed message, path)."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        first = self.errors[0]
        super().__init__("%s (%s): %s" % (first.code, first.path or "inputs", first.message))

    @property
    def code(self):
        return self.errors[0].code


def _problem(code, message, path=""):
    return docvalidate.Problem(PREFIX + code, message, path)


def _proven(by_id, fact_ids):
    return bool(fact_ids) and all(f in by_id and by_id[f].status == facts.CONFIRMED for f in fact_ids)


def _rounded(value):
    return round(value, GAIN_PRECISION)


def _resolve_inputs(offer, taxonomy, profile, factbase, content, family_id, language):
    errors = []
    if factbase is None:
        raise PlanError([_problem("FACTBASE_REQUIRED", "a validated fact base is required: without it nothing is proven")])
    families = profile.families
    if family_id is None:
        if len(families) == 1:
            family_id = next(iter(families))
        else:
            errors.append(_problem("FAMILY_REQUIRED", "the profile has several families: name one"))
    elif family_id not in families:
        errors.append(_problem("FAMILY_UNKNOWN", "the profile has no such family"))
    chosen, method = language, "requested"
    if chosen is None:
        chosen, method = offer.resolve_language(profile.default_language)
    if chosen is None:
        errors.append(_problem("LANGUAGE_UNDECIDED", "the offer language is `auto` and could not be decided: name the language"))
    if errors:
        raise PlanError(errors)
    family = families[family_id]
    if chosen not in profile.languages or chosen not in family["languages"] or chosen not in content.languages:
        raise PlanError([_problem("LANGUAGE_UNAVAILABLE",
                                  "the language is not available in the profile, the family and the content")])
    problems = [_problem("CAPABILITY_UNKNOWN", message, path)
                for path, message in taxonomymod.vocabulary_problems(taxonomy, content, factbase)]
    capability_ids = taxonomy.capability_ids()
    for position, cluster in enumerate(family["clusters"]):
        if cluster not in capability_ids:
            problems.append(_problem("CLUSTER_UNKNOWN", "the family cluster is not a capability of the taxonomy",
                                     "families.%s.clusters[%d]" % (family_id, position)))
    if problems:
        raise PlanError(problems)
    return family_id, family, chosen, method


def build_plan(offer, taxonomy, profile, factbase, content, family_id=None, language=None):
    """The `TailoringPlan-v1` model, or `PlanError`. Pure: reads its arguments, changes none of them."""
    family_id, family, language, method = _resolve_inputs(offer, taxonomy, profile, factbase, content, family_id, language)
    selection = profile.selection
    by_id = {fact.id: fact for fact in factbase.facts}

    requirements, problems = joboffer.extract_requirements(offer, taxonomy, language)
    if problems:
        raise PlanError(problems)
    pool = matrixmod.build_pool(content, factbase, profile, taxonomy, family_id, language, offer.job_key)
    matrix = matrixmod.build_matrix(requirements, pool, taxonomy, profile, factbase)
    rows = {row["id"]: row for row in matrix["requirements"]}

    covers = {}
    for row in matrix["requirements"]:
        for evidence in row["evidence"]:
            covers.setdefault((evidence["type"], evidence["id"]), []).append((row, evidence["relation"]))

    excluded = list(pool.excluded)
    bullets = {item.id: item for item in pool.items if item.kind == "bullet"}
    skills = [item for item in pool.items if item.kind == "skill"]

    # --- precedence: when the keep block directly proves the requirement, the over block is dropped ---------------
    precedence = []
    for rule in profile.internal_preferences()["precedence_rules"]:
        for row in matrix["requirements"]:
            if row["state"] != matrixmod.DIRECT or rule["when_direct"] not in (row["id"], row["term_id"]):
                continue
            proof = [e for e in row["evidence"] if e["type"] == "bullet" and bullets[e["id"]].container == rule["keep"]]
            if not proof:
                continue
            dropped = sorted(i for i, item in bullets.items() if item.container == rule["over"])
            for bullet_id in dropped:
                del bullets[bullet_id]
                excluded.append({"type": "bullet", "id": bullet_id, "reason": "PRECEDENCE"})
            precedence.append({"requirement": row["id"], "keep": rule["keep"], "over": rule["over"], "dropped": dropped})

    baseline_items = set(pool.baseline_items)
    clusters = set(family["clusters"])
    counts = {row["id"]: 0 for row in matrix["requirements"]}

    def contributions(item, running):
        found, named = [], 0.0
        for row, relation in covers.get((item.kind, item.id), ()):
            factor = 1.0 if relation == matrixmod.DIRECT else selection["inferred_factor"]
            found.append({"requirement": row["id"], "relation": relation,
                          "value": _rounded(row["weight"] * factor / (1 + running[row["id"]]))})
            if relation == matrixmod.DIRECT and row["kind"] == "technology" and running[row["id"]] == 0:
                named += selection["named_bonus"]
        prior = selection["baseline_prior"] if item.id in baseline_items else 0.0
        outside = len([c for c in item.capabilities if c not in clusters]) if clusters else 0
        penalty = min(selection["off_target_penalty"] * outside, selection["off_target_penalty_cap"])
        total = _rounded(sum(c["value"] for c in found) + named + prior - penalty)
        return {"contributions": found, "named_bonus": _rounded(named), "baseline_prior": prior,
                "off_target_penalty": _rounded(penalty), "gain": total}

    def commit_counts(item, running):
        for row, _relation in covers.get((item.kind, item.id), ()):
            running[row["id"]] += 1

    def unit_for(item, chosen):
        chain, current = [], item
        while current.follows is not None:
            predecessor = bullets.get(current.follows)
            if predecessor is None:
                return None
            if predecessor.id in chosen:
                break
            chain.insert(0, predecessor)
            current = predecessor
        return chain + [item]

    def blocked(item, chosen):
        return bool(set(item.condenses) & chosen) or any(item.id in bullets[c].condenses for c in chosen)

    selected, chosen_ids, rank = [], set(), 0
    while True:
        best = None
        for item in sorted(bullets.values(), key=lambda i: (i.position, i.id)):
            if item.id in chosen_ids or blocked(item, chosen_ids):
                continue
            unit = unit_for(item, chosen_ids)
            if unit is None or any(blocked(member, chosen_ids) or member.id in chosen_ids and member is not item
                                   for member in unit[:-1]):
                continue
            running, total, details = dict(counts), 0.0, []
            for member in unit:
                detail = contributions(member, running)
                commit_counts(member, running)
                total += detail["gain"]
                details.append((member, detail))
            total = _rounded(total)
            if total < selection["minimum_gain"]:
                continue
            key = (-total, item.position, item.id)
            if best is None or key < best[0]:
                best = (key, details)
        if best is None:
            break
        for member, detail in best[1]:
            rank += 1
            commit_counts(member, counts)
            chosen_ids.add(member.id)
            selected.append({"id": member.id, "block": member.container, "rank": rank,
                             "reason": "RANKED" if member is best[1][-1][0] else "FOLLOWS_REQUIRED",
                             "gain": detail["gain"], "contributions": detail["contributions"],
                             "named_bonus": detail["named_bonus"], "baseline_prior": detail["baseline_prior"],
                             "off_target_penalty": detail["off_target_penalty"], "supports": sorted(member.facts),
                             "heading_supports": sorted(member.heading_facts)})

    for item in sorted(bullets.values(), key=lambda i: (i.position, i.id)):
        if item.id in chosen_ids:
            continue
        if blocked(item, chosen_ids):
            reason = "EXCLUSIVE_WITH_SELECTED"
        elif unit_for(item, chosen_ids) is None:
            reason = "FOLLOWS_UNAVAILABLE"
        else:
            reason = "BELOW_MINIMUM_GAIN"
        excluded.append({"type": "bullet", "id": item.id, "reason": reason,
                         "gain": contributions(item, counts)["gain"] if reason == "BELOW_MINIMUM_GAIN" else None})

    # --- skills ------------------------------------------------------------------------------------------------
    core = {canonical.fold(name): position for position, name in enumerate(family["core_skills"])}
    selected_skills, matched_core = [], set()
    for item in sorted(skills, key=lambda i: (i.container, i.position)):
        names = {canonical.fold(t) for t in item.technologies} | {canonical.fold(item.text or "")}
        hits = sorted(core[name] for name in names if name in core)
        matched_core.update(hits)
        covered = [row["id"] for row, relation in covers.get(("skill", item.id), ()) if relation == matrixmod.DIRECT]
        reason = "REQUIREMENT" if covered else "CORE_SKILL" if hits else "BASELINE" if item.id in pool.baseline_skills else None
        if reason is None:
            excluded.append({"type": "skill", "id": item.id, "reason": "NOT_RELEVANT", "gain": None})
            continue
        selected_skills.append({"category": item.container, "id": item.id, "reason": reason, "requirements": sorted(covered),
                                "supports": sorted(item.facts)})
    selected_skills = sorted(selected_skills, key=lambda s: _skill_position(content, s))

    # --- blocks ------------------------------------------------------------------------------------------------
    models = {block["id"]: block for block in content.to_model()["blocks"]}
    section_position = {section["id"]: n for n, section in enumerate(content.to_model()["sections"])}
    per_block = {}
    for entry in selected:
        per_block.setdefault(entry["block"], []).append(entry["id"])
    blocks, warnings = [], list(pool.warnings)
    precedence_over = {p["over"] for p in precedence}
    for block_id, block in sorted(models.items(), key=lambda kv: (section_position[kv[1]["section"]], kv[1]["order"], kv[0])):
        ids = per_block.get(block_id, [])
        printable = language in block["heading"] and _proven(by_id, block["supports"])
        if ids:
            blocks.append({"id": block_id, "reason": "SELECTED", "heading_supports": sorted(block["supports"]),
                           "bullets": sorted(ids, key=lambda b: bullets[b].position)})
        elif block["protected"] and block_id not in family["excluded_blocks"] and block_id not in precedence_over \
                and block_id not in pool.blocked_blocks and printable:
            blocks.append({"id": block_id, "reason": "PROTECTED", "heading_supports": sorted(block["supports"]),
                           "bullets": []})
        elif block["protected"]:
            warnings.append({"code": "PROTECTED_BLOCK_NOT_KEPT", "block": block_id})

    for position, name in enumerate(family["core_skills"]):
        if position not in matched_core:
            warnings.append({"code": "CORE_SKILL_UNAVAILABLE", "path": "families.%s.core_skills[%d]" % (family_id, position)})
    known_ids = {item.id for item in pool.items}
    reasons = {(r["type"], r["id"]): r["reason"] for r in excluded}
    for bullet_id in pool.baseline_items:
        if bullet_id not in known_ids or ("bullet", bullet_id) in reasons and bullet_id not in chosen_ids and \
                reasons[("bullet", bullet_id)] in _SAFETY_REASONS:
            warnings.append({"code": "BASELINE_ITEM_EXCLUDED", "type": "bullet", "id": bullet_id,
                             "reason": reasons.get(("bullet", bullet_id), "UNKNOWN")})
    for skill_id in pool.baseline_skills:
        if ("skill", skill_id) in reasons and reasons[("skill", skill_id)] in _SAFETY_REASONS:
            warnings.append({"code": "BASELINE_ITEM_EXCLUDED", "type": "skill", "id": skill_id,
                             "reason": reasons[("skill", skill_id)]})

    # --- coverage ---------------------------------------------------------------------------------------------
    chosen_skill_ids = {s["id"] for s in selected_skills}
    coverage, unsatisfied = [], []
    for row in matrix["requirements"]:
        by = sorted([("bullet", i) for i in chosen_ids] + [("skill", i) for i in chosen_skill_ids])
        evidence = [e for e in row["evidence"] if (e["type"], e["id"]) in set(by)]
        direct = [e for e in evidence if e["relation"] == matrixmod.DIRECT]
        if row["state"] == matrixmod.DIRECT:
            status = "SATISFIED" if direct else "EVIDENCE_NOT_SELECTED"
        elif row["state"] == matrixmod.ADJACENT:
            status = "ADJACENT_ONLY" if evidence else "EVIDENCE_NOT_SELECTED"
        elif row["state"] == matrixmod.FORBIDDEN:
            status = "FORBIDDEN"
        else:
            status = "UNSATISFIED"
        covered_by = sorted({"%s:%s" % (e["type"], e["id"]) for e in evidence})
        coverage.append({"id": row["id"], "state": row["state"], "priority": row["priority"], "weight": row["weight"],
                         "status": status, "covered_by": covered_by})
        if row["priority"] == "REQUIRED" and status != "SATISFIED":
            unsatisfied.append({"id": row["id"], "state": row["state"], "status": status, "reasons": row["reasons"]})
    if unsatisfied:
        warnings.append({"code": "UNSATISFIED_REQUIRED", "count": len(unsatisfied)})
    if not chosen_ids and not selected_skills:
        warnings.append({"code": "NO_RELEVANT_CONTENT"})
    if any(c["status"] == "ADJACENT_ONLY" for c in coverage):
        warnings.append({"code": "ADJACENT_ONLY_PRESENT"})
    if family["page_target"] is not None:
        warnings.append({"code": "PAGE_TARGET_NOT_ENFORCED", "page_target": family["page_target"]})

    availability = {"employment_type": offer.employment_type, "confirmed_availability": []}
    if offer.employment_type != "UNSPECIFIED":
        availability["confirmed_availability"] = sorted(
            entry["id"] for entry in profile.confirmed_availability(factbase) if offer.employment_type in entry["applies_to"])

    plan = {
        "schema": SCHEMA,
        "plan_status": "PLAN_ONLY",
        "review": {"status": "NOT_REVIEWED"},
        "tailored_cv_id": None,
        "offer": {"job_key": offer.job_key, "language": language, "language_method": method,
                  "declared_language": offer.declared_language},
        "family": family_id,
        "language": language,
        "inputs": {
            "offer_sha256": offer.offer_sha256, "profile_sha256": profile.profile_sha256,
            "facts_source_sha256": factbase.facts_source_sha256, "factbase_sha256": factbase.factbase_sha256,
            "content_sha256": content.content_sha256, "taxonomy_sha256": taxonomy.taxonomy_sha256,
            "matrix_sha256": matrixmod.matrix_sha256(matrix),
        },
        "selection_config": {key: selection[key] for key in sorted(selection)},
        "requirements": coverage,
        "selected": {"blocks": blocks, "bullets": selected, "skills": selected_skills},
        "omitted": sorted(excluded, key=lambda r: (r["type"], r["id"], r["reason"])),
        "precedence_applied": precedence,
        "unsatisfied_required": unsatisfied,
        "availability": availability,
        "warnings": sorted(warnings, key=lambda w: (w["code"], str(w.get("id", w.get("path", w.get("block", "")))))),
        "limits": list(LIMITS),
    }
    plan["plan_sha256"] = canonical.fingerprint(plan)
    return plan, matrix


_SAFETY_REASONS = frozenset(("NEVER_PUBLISH", "LANGUAGE_UNAVAILABLE", "NOT_PROVEN", "FAMILY_EXCLUDED_BLOCK",
                             "FORBIDDEN_TERM", "FORBIDDEN_TEXT", "FORBIDDEN_HEADING", "GUIDANCE_OMIT", "OMIT_BY_DEFAULT",
                             "PRECEDENCE"))


def _skill_position(content, entry):
    for c_position, category in enumerate(content.to_model()["skills"]):
        if category["id"] == entry["category"]:
            for i_position, item in enumerate(category["items"]):
                if item["id"] == entry["id"]:
                    return (c_position, i_position)
    return (len(content.to_model()["skills"]), 0)


def verify_fingerprint(plan):
    """True when `plan_sha256` matches the body: detects an edited plan."""
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    return plan.get("plan_sha256") == canonical.fingerprint(body)
