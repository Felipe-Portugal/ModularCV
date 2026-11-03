"""RequirementMatrix-v1: what each requirement of an offer is worth against the candidate's *proven, presentable* content.

Contract: `docs/design/CONTRACTS.md` sections 3.3 and 5. A requirement gets exactly one of four states, decided in this
order (the first rule that applies wins, so a prohibition always beats relevance):

1. `FORBIDDEN_TO_CLAIM` - the profile's `never_publish_terms` name the term (by its name or any declared alias), or a
   `NOT_CONFIRMED` / `WITHDRAWN` fact declares it. Nothing can lift this: not a text match, not a confirmed fact beside it.
2. `DIRECT` - an *eligible* bullet or skill declares the term itself, and a `CONFIRMED` fact that item rests on declares it
   too (corroboration). Eligible means published-safe: proven bullet and heading, written in the target language, not excluded by
   the family, the policy or the job's guidance.
3. `ADJACENT` - no direct proof, but a term the taxonomy declares adjacent (one hop, directed) is itself `DIRECT`. The
   adjacent item is evidence of *that other term*; it never states the required one.
4. `ABSENT` - everything else: no evidence, evidence without corroboration, a fact with no presentable content, or a term
   the taxonomy does not know. Absence of proof is never turned into a match.

A match is always an explicit declaration (a capability id or a technology name, compared after casefolding and accent
removal), never a word the texts happen to share. The matrix proves existence, status and declaration; it does not prove
that a text means what its facts say.
"""
import re
from collections import namedtuple

from . import canonical, facts

SCHEMA = "RequirementMatrix-v1"
DIRECT = "DIRECT"
ADJACENT = "ADJACENT"
ABSENT = "ABSENT"
FORBIDDEN = "FORBIDDEN_TO_CLAIM"
STATES = (DIRECT, ADJACENT, ABSENT, FORBIDDEN)

Item = namedtuple("Item", "kind id container position terms capabilities technologies facts heading_facts condenses "
                          "follows protected text")
Pool = namedtuple("Pool", "items excluded warnings family language job_key baseline_items baseline_skills blocked_blocks")


def contains_term(folded_text, folded_term):
    """True when the folded term occurs in the folded text as a whole word (or phrase)."""
    return bool(folded_term) and re.search(r"(?<!\w)%s(?!\w)" % re.escape(folded_term), folded_text) is not None


def fact_terms(fact, taxonomy):
    """Term ids a fact declares itself: its `capabilities` and the technologies the taxonomy knows."""
    found = {c for c in fact.capabilities if c in taxonomy.capability_ids()}
    for technology in fact.technologies:
        term_id = taxonomy.resolve_declared_technology(technology)
        if term_id:
            found.add(term_id)
    return found


def _declared_terms(capabilities, technologies, taxonomy):
    found = {c for c in capabilities if c in taxonomy.capability_ids()}
    for technology in technologies:
        term_id = taxonomy.resolve_declared_technology(technology)
        if term_id:
            found.add(term_id)
    return found


def _forbidden_spellings(profile):
    return {canonical.fold(term) for term in profile.policy["never_publish_terms"]}


def build_pool(content, factbase, profile, taxonomy, family_id, language, job_key):
    """The items a CV may print for this family, language and job, and the reason each other one is left out."""
    policy = profile.policy
    family = profile.families[family_id]
    forbidden = _forbidden_spellings(profile)
    omit = {canonical.fold(term) for term in policy["omit_by_default_terms"]}
    words = forbidden | {canonical.fold(word) for word in policy["forbidden_words"].get(language, [])}
    omitted_facts, softened = set(), set()
    for entry in profile.internal_preferences()["guidance"]:
        if entry["job_key"] == job_key:
            for rule in entry["rules"]:
                (omitted_facts if rule["action"] == "omit" else softened).add(rule["fact_id"])
    baseline = content.baseline(family_id, language) or {"items": [], "skills": []}
    in_baseline_items, in_baseline_skills = set(baseline["items"]), set(baseline["skills"])
    proven = {entry.bullet_id for entry in content.selectable(factbase, language)}
    proven_skills = set(content.selectable_skills(factbase, language))

    def spellings_of(terms_declared, technologies):
        found = set()
        for term_id in terms_declared:
            found |= taxonomy.spellings(term_id)
        found |= {canonical.fold(t) for t in technologies}
        return found

    blocked_blocks = {}
    for block in content.to_model()["blocks"]:
        heading = block["heading"].get(language)
        if heading:
            shown = canonical.fold(" ".join(str(value) for value in heading.values() if value))
            if any(contains_term(shown, word) for word in words):
                blocked_blocks[block["id"]] = "FORBIDDEN_HEADING"
    items, excluded, warnings = [], [], []
    for entry in content.reservoir():
        terms = _declared_terms(entry.capabilities, entry.technologies, taxonomy)
        reason = None
        text = canonical.fold(entry.text.get(language, ""))
        names = spellings_of(terms, entry.technologies)
        if entry.never_publish:
            reason = "NEVER_PUBLISH"
        elif language not in entry.text:
            reason = "LANGUAGE_UNAVAILABLE"
        elif entry.bullet_id not in proven:
            reason = "NOT_PROVEN"
        elif entry.block_id in family["excluded_blocks"]:
            reason = "FAMILY_EXCLUDED_BLOCK"
        elif entry.block_id in blocked_blocks:
            reason = blocked_blocks[entry.block_id]
        elif names & forbidden:
            reason = "FORBIDDEN_TERM"
        elif any(contains_term(text, word) for word in words):
            reason = "FORBIDDEN_TEXT"
        elif set(entry.supports) & omitted_facts:
            reason = "GUIDANCE_OMIT"
        elif names & omit and entry.bullet_id not in in_baseline_items:
            reason = "OMIT_BY_DEFAULT"
        if reason:
            excluded.append({"type": "bullet", "id": entry.bullet_id, "reason": reason})
            continue
        if set(entry.supports) & softened:
            warnings.append({"code": "GUIDANCE_SOFTEN_PENDING", "type": "bullet", "id": entry.bullet_id})
        items.append(Item("bullet", entry.bullet_id, entry.block_id,
                          (entry.section_position, entry.block_order, entry.position), frozenset(terms),
                          entry.capabilities, entry.technologies, entry.supports, entry.heading_supports,
                          entry.condenses, entry.follows, entry.protected, entry.text.get(language)))
    for category in content.to_model()["skills"]:
        for position, item in enumerate(category["items"]):
            terms = _declared_terms((), item["technologies"], taxonomy)
            names = spellings_of(terms, item["technologies"])
            text = canonical.fold(item["text"].get(language, ""))
            pair = (category["id"], item["id"])
            reason = None
            if language not in item["text"]:
                reason = "LANGUAGE_UNAVAILABLE"
            elif pair not in proven_skills:
                reason = "NOT_PROVEN"
            elif names & forbidden or any(contains_term(text, word) for word in words):
                reason = "FORBIDDEN_TERM"
            elif set(item["supports"]) & omitted_facts:
                reason = "GUIDANCE_OMIT"
            elif names & omit and item["id"] not in in_baseline_skills:
                reason = "OMIT_BY_DEFAULT"
            if reason:
                excluded.append({"type": "skill", "id": item["id"], "reason": reason})
                continue
            items.append(Item("skill", item["id"], category["id"], (position,), frozenset(terms), (),
                              tuple(item["technologies"]), tuple(item["supports"]), (), (), None, False,
                              item["text"].get(language)))
    return Pool(tuple(items), tuple(excluded), tuple(warnings), family_id, language, job_key,
                tuple(baseline["items"]), tuple(baseline["skills"]), blocked_blocks)


def _corroborated(item, term_id, by_id, taxonomy):
    for fact_id in item.facts:
        fact = by_id.get(fact_id)
        if fact is not None and fact.status == facts.CONFIRMED and term_id in fact_terms(fact, taxonomy):
            return True
    return False


def build_matrix(requirements, pool, taxonomy, profile, factbase):
    """The `RequirementMatrix-v1` model for `requirements` (see `joboffer.extract_requirements`) and an item `pool`."""
    by_id = {fact.id: fact for fact in factbase.facts}
    forbidden = _forbidden_spellings(profile)
    fact_declarations = {fact.id: fact_terms(fact, taxonomy) for fact in factbase.facts}

    def profile_forbids(term_id, label):
        if term_id is None:
            return canonical.fold(label or "") in forbidden
        return bool(taxonomy.spellings(term_id) & forbidden)

    def forbidding_facts(term_id, label):
        found = []
        for fact in factbase.facts:
            if fact.status not in (facts.NOT_CONFIRMED, facts.WITHDRAWN):
                continue
            if term_id is not None and term_id in fact_declarations[fact.id]:
                found.append(fact)
            elif term_id is None and canonical.fold(label or "") in {canonical.fold(t) for t in fact.technologies}:
                found.append(fact)
        return found

    def direct_items(term_id):
        return [item for item in pool.items if term_id in item.terms and _corroborated(item, term_id, by_id, taxonomy)]

    rows = []
    for requirement in requirements:
        term_id, label = requirement["term_id"], requirement["label"]
        row = dict(requirement)
        row.update({"state": ABSENT, "reasons": [], "evidence": [], "forbidden_by": [], "unpublished_fact_ids": []})
        blockers = []
        if profile_forbids(term_id, label):
            blockers.append({"kind": "profile_term"})
        for fact in forbidding_facts(term_id, label):
            blockers.append({"kind": "fact", "id": fact.id, "status": fact.status})
        if blockers:
            row["state"] = FORBIDDEN
            row["forbidden_by"] = blockers
            row["reasons"] = sorted({"PROFILE_FORBIDDEN_TERM" if b["kind"] == "profile_term" else
                                     "FACT_" + b["status"] for b in blockers})
        elif term_id is None:
            row["reasons"] = ["UNKNOWN_TERM"]
        else:
            direct = direct_items(term_id)
            declared = [item for item in pool.items if term_id in item.terms]
            if direct:
                row["state"] = DIRECT
                row["evidence"] = [{"type": i.kind, "id": i.id, "relation": DIRECT, "via": None,
                                    "facts": sorted(i.facts)} for i in direct]
            else:
                adjacent = []
                for source in taxonomy.adjacent_sources(term_id):
                    if profile_forbids(source, None) or forbidding_facts(source, None):
                        continue
                    adjacent.extend((source, item) for item in direct_items(source))
                if adjacent:
                    row["state"] = ADJACENT
                    row["reasons"] = ["ADJACENT_ONLY"]
                    row["evidence"] = [{"type": i.kind, "id": i.id, "relation": ADJACENT, "via": source,
                                        "facts": sorted(i.facts)} for source, i in adjacent]
                elif declared:
                    row["reasons"] = ["UNCORROBORATED"]
                else:
                    confirmed_only = sorted(f.id for f in factbase.facts
                                            if f.status == facts.CONFIRMED and term_id in fact_declarations[f.id])
                    row["unpublished_fact_ids"] = confirmed_only
                    row["reasons"] = ["NO_PUBLISHABLE_CONTENT" if confirmed_only else "NO_EVIDENCE"]
        row["evidence"].sort(key=lambda e: (e["relation"] != DIRECT, e["type"], e["id"], e["via"] or ""))
        rows.append(row)
    counts = {state: sum(1 for row in rows if row["state"] == state) for state in STATES}
    return {"schema": SCHEMA, "family": pool.family, "language": pool.language, "job_key": pool.job_key,
            "requirements": rows, "counts": counts}


def matrix_sha256(matrix):
    return canonical.fingerprint(matrix)
