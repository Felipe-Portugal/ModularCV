"""The chain of evidence of a CV package: sources, plan, assembly, `.tex`, PDF, metadata (M7-B).

Dependency graph of the fingerprints (an arrow means "is a function of"; there is no cycle, which is why a document never has
to contain the hash of something that contains its own hash):

    facts, profile, content, taxonomy, offer           (workspace sources, committed in the workspace repository)
        -> plan            plan_sha256, with the canonical fingerprints of the sources in `inputs`
        -> assembly        assembly_sha256 (a function of the plan and the sources)
        -> .tex            tex_sha256, exact bytes (a function of the assembly and the paper size)
        -> .pdf            pdf_sha256, exact bytes (an artefact compiled from the .tex; not reproducible)
        -> metadata v3     names all of the above and the workspace commit
        -> snapshot        path, role, hash and size of the files above (it never contains the package or the review)
        -> package.json    names the snapshot fingerprint and the paths (it never contains the review)
        -> review          written last, by a person: names the identity and the exact PDF bytes (outside the snapshot)
    tailored_cv_id         a function of the plan and the engine version only, recomputable from the plan file.

`verify` re-derives every link from the files of the workspace and reports each break; it never trusts a field because it is
present, and never writes. Readiness (`readiness.py`) calls it for version 3 packages.
"""
from collections import namedtuple

from . import (__version__, assemble as assemblemod, canonical, config, content as contentmod, docvalidate, facts,
               joboffer, latex, paths, pdf, plan as planmod, profile as profilemod, snapshot, taxonomy as taxonomymod)

IDENTITY_SCHEMA = "TailoredCvIdentity-v1"
Problem = namedtuple("Problem", "reason code message")
Sources = namedtuple("Sources", "factbase profile taxonomy content offer")
IDENTITY_INPUTS = ("facts_source_sha256", "factbase_sha256", "content_sha256", "profile_sha256", "taxonomy_sha256", "offer_sha256")
METADATA_INPUTS = IDENTITY_INPUTS


class ChainError(ValueError):
    """A source cannot be loaded. `stage` names it; `errors` are the value-free problems of that stage."""

    def __init__(self, stage, errors):
        self.stage, self.errors = stage, tuple(errors)
        first = self.errors[0]
        super().__init__("%s: %s (%s)" % (stage, first.code, getattr(first, "path", "") or "document"))


def tailored_cv_id(plan, engine_version=__version__, template_id=latex.TEMPLATE_ID):
    """The stable identity of the CV a plan describes. No timestamp, no personal value: only fingerprints and versions."""
    body = {"schema": IDENTITY_SCHEMA, "engine_version": engine_version, "template_id": template_id,
            "language": plan["language"], "plan_sha256": plan["plan_sha256"]}
    body.update({key: plan["inputs"][key] for key in IDENTITY_INPUTS})
    return canonical.fingerprint(body)


def load_sources(root, settings, offer_relative):
    """Load and strictly validate every source from the workspace. Raises `ChainError` naming the failing stage."""
    def read(relative):
        target = paths.resolve_inside(root, relative)
        return target

    loaded_facts = facts.check_file(root / settings["facts"])
    if loaded_facts.errors:
        raise ChainError("facts", loaded_facts.errors)
    loaded_profile = profilemod.check_file(root / settings["profile"], loaded_facts.factbase)
    if loaded_profile.errors:
        raise ChainError("profile", loaded_profile.errors)
    found_profile = loaded_profile.profile
    loaded_taxonomy = taxonomymod.load(found_profile.internal_preferences()["taxonomy"], root)
    if loaded_taxonomy.errors:
        raise ChainError("taxonomy", loaded_taxonomy.errors)
    loaded_content = contentmod.check_file(root / settings["content"], loaded_facts.factbase, found_profile)
    if loaded_content.errors:
        raise ChainError("content", loaded_content.errors)
    target = read(offer_relative)
    if target is None:
        raise ChainError("offer", [docvalidate.Problem("OFFER_FILE_UNREADABLE", "the offer is not a safe path inside the workspace", "")])
    loaded_offer = joboffer.check_file(target)
    if loaded_offer.errors:
        raise ChainError("offer", loaded_offer.errors)
    return Sources(loaded_facts.factbase, found_profile, loaded_taxonomy.taxonomy, loaded_content.content, loaded_offer.offer)


def source_paths(settings, sources):
    """`{role: relative path}` of the workspace files the sources come from (a built-in taxonomy has no file)."""
    found = {"facts": settings["facts"], "profile": settings["profile"], "resume_content": settings["content"]}
    reference = sources.profile.internal_preferences()["taxonomy"]
    if reference.endswith(".json") and not reference.startswith("builtin:"):
        found["taxonomy"] = reference
    return found


def selected_content(plan):
    return sorted(["block:" + b["id"] for b in plan["selected"]["blocks"]] + ["bullet:" + b["id"] for b in plan["selected"]["bullets"]]
                  + ["skill:" + s["id"] for s in plan["selected"]["skills"]])


def build_metadata(plan, assembly, sources, tex, pdf_bytes, paper, source_commit, facts_path,
                   engine_version=__version__):
    """The `schema_version` 3 metadata of a CV, derived only from verified objects. `pdf_bytes` may be None."""
    offer = sources.offer.to_model()
    return {
        "schema_version": "3",
        "tailored_cv_id": tailored_cv_id(plan, engine_version),
        "job_key": sources.offer.job_key,
        "language": plan["language"],
        "family": plan["family"],
        "source_commit": source_commit,
        "facts_source": facts_path,
        "taxonomy": sources.profile.internal_preferences()["taxonomy"],
        "company": offer["company"],
        "title": offer["title"],
        "job_sha256": plan["inputs"]["offer_sha256"],
        "plan_sha256": plan["plan_sha256"],
        "assembly_sha256": assembly["assembly_sha256"],
        "tex_sha256": canonical.sha256_bytes(tex),
        "pdf_sha256": None if pdf_bytes is None else canonical.sha256_bytes(pdf_bytes),
        "pdf_pages": None if pdf_bytes is None else pdf.count_pages(pdf_bytes),
        "page_target": assembly["layout"]["page_target"],
        "paper": paper,
        "template_id": latex.TEMPLATE_ID,
        "engine_version": engine_version,
        "inputs": {key: plan["inputs"][key] for key in METADATA_INPUTS},
        "decision": {"selected_content": selected_content(plan),
                     "excluded_content": sorted("%s:%s:%s" % (o["type"], o["id"], o["reason"]) for o in plan["omitted"]),
                     "human_validations_required": []},
        "unsatisfied_required": sorted(u["id"] for u in plan["unsatisfied_required"]),
        "pending_directives": sorted("%s:%s" % (p["type"], p["id"]) for p in assembly["pending_directives"]),
        "warnings": sorted({w["code"] for w in assembly["warnings"]}),
    }


def acknowledgement(cv_metadata):
    """What a reviewer must have seen to approve this package: derived from the metadata, never typed by hand."""
    return {"unsatisfied_required": list(cv_metadata["unsatisfied_required"]),
            "pending_directives": list(cv_metadata["pending_directives"]),
            "warnings": list(cv_metadata["warnings"]),
            "page_verdict": pdf.page_verdict(cv_metadata["page_target"], cv_metadata["pdf_pages"])}


def _entry(document, role):
    found = snapshot.entries_for(document, role)
    return found[0] if found else None


def _read(root, entry):
    target = paths.resolve_inside(root, entry["path"])
    try:
        return target.read_bytes() if target is not None and target.is_file() else None
    except OSError:
        return None


def verify(root, document, cv_metadata, settings):
    """Re-derive the chain from the workspace files named by the snapshot `document`. Returns `(problems, identity)`.

    `identity` is the recomputed `tailored_cv_id` (None when the plan cannot be read). Each problem has a readiness
    `reason`, a finer `code` and a fixed `message`; none repeats a value of a document."""
    problems = []

    def add(reason, code, message):
        problems.append(Problem(reason, code, message))

    plan_entry, assembly_entry = _entry(document, "tailoring_plan"), _entry(document, "assembly")
    tex_entry, pdf_entry, offer_entry = _entry(document, "cv_tex"), _entry(document, "cv_pdf"), _entry(document, "offer")
    for role, entry in (("assembly", assembly_entry), ("offer", offer_entry)):
        if entry is None:
            add("SNAPSHOT_INVALID", "SNAPSHOT_ROLE_MISSING", "a version 3 package must snapshot the role `%s`" % role)
    if assembly_entry is None or offer_entry is None:
        return problems, None
    plan_bytes, assembly_bytes, tex_bytes = _read(root, plan_entry), _read(root, assembly_entry), _read(root, tex_entry)
    pdf_bytes = _read(root, pdf_entry) if pdf_entry is not None else None
    if None in (plan_bytes, assembly_bytes, tex_bytes):
        add("CHAIN_INVALID", "CHAIN_FILE_UNREADABLE", "the plan, the assembly or the .tex cannot be read")
        return problems, None
    try:
        plan = assemblemod.load_plan(plan_bytes)
        assemblemod.check_shape(plan)
        assemblemod.check_fingerprint(plan)
    except assemblemod.AssemblyError as error:
        add("CHAIN_INVALID", error.code, "the tailoring plan in the package is not an intact plan")
        return problems, None
    identity = tailored_cv_id(plan, cv_metadata["engine_version"])

    for role, relative in (("facts", settings["facts"]), ("profile", settings["profile"]), ("resume_content", settings["content"])):
        entry = _entry(document, role)
        if entry is None or entry["path"] != relative:
            add("CV_REFERENCE_MISMATCH", "SNAPSHOT_PATH_DIFFERS_FROM_CONFIGURATION",
                "the snapshot does not name the configured file for the role `%s`" % role)
            return problems, identity
    try:
        sources = load_sources(root, settings, offer_entry["path"])
    except ChainError as error:
        add("CHAIN_INVALID", "CHAIN_SOURCE_INVALID", "the source `%s` no longer validates (%s)" % (error.stage, error.errors[0].code))
        return problems, identity
    try:
        fresh = assemblemod.assemble(plan, sources.offer, sources.taxonomy, sources.profile, sources.factbase, sources.content)
    except assemblemod.AssemblyError as error:
        add("CHAIN_INVALID", error.code, "the plan no longer verifies against the sources (%s)" % error.code)
        return problems, identity
    try:
        stored = docvalidate.load(assembly_bytes, "ASSEMBLY_FILE_")
    except docvalidate.DocumentError:
        stored = None
    if stored is None or canonical.canonical_bytes(stored) != canonical.canonical_bytes(fresh):
        add("CHAIN_INVALID", "CHAIN_ASSEMBLY_MISMATCH", "the assembly file is not the assembly of this plan and these sources")
        return problems, identity
    paper = cv_metadata.get("paper")
    try:
        if paper not in latex.PAPERS or latex.tex_bytes(latex.render(fresh, paper)) != tex_bytes:
            raise latex.RenderError([docvalidate.Problem("RENDER_MISMATCH", "", "")])
    except latex.RenderError:
        add("CHAIN_INVALID", "CHAIN_TEX_MISMATCH", "the .tex is not the rendering of the assembly")
        return problems, identity
    if pdf_bytes is not None:
        if not pdf.looks_like_pdf(pdf_bytes):
            add("CHAIN_INVALID", "CHAIN_PDF_MALFORMED", "the PDF is not a complete PDF file")
    expected = build_metadata(plan, fresh, sources, tex_bytes, pdf_bytes, paper, cv_metadata.get("source_commit"),
                              settings["facts"], cv_metadata["engine_version"])
    if canonical.canonical_bytes(expected) != canonical.canonical_bytes(cv_metadata):
        differing = sorted(key for key in expected if canonical.canonical_bytes(expected[key]) != canonical.canonical_bytes(cv_metadata.get(key)))
        add("CV_REFERENCE_MISMATCH", "METADATA_DIFFERS_FROM_CHAIN",
            "the metadata differs from what the chain implies (fields: %s)" % ", ".join(differing or ["unknown"]))
    return problems, identity
