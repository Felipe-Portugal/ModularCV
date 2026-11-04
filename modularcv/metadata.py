"""Read-only validation of a CV `metadata.json` (schema_version 1 and 2).

Mirrors `schemas/application_metadata.schema.json` without a third-party validator. Historical
compatibility is not a security verdict: a valid v1 or v2 document is only *readable*; readiness
still demands the evidence. `source_commit` is judged by `readiness` (placeholder, unknown, ...),
so it is not checked here. Version 3 is defined in milestone M7; until then it is refused,
like any unknown version, instead of being guessed.
"""
import re

KNOWN_VERSIONS = ("1", "2")  # historical formats: readable, never repaired, never READY on their own
CURRENT_VERSION = "3"
LANGUAGES = ("fr", "en")
JOB_SHA = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = ("schema_version", "job_key", "generated_at", "language", "family", "source_commit",
            "master_resume", "facts_source", "company", "title", "job_sha256", "decision")


def problems(document):
    """List of `(code, message)`; empty when the document is a readable v1/v2 metadata."""
    out = []
    if not isinstance(document, dict):
        return [("METADATA_NOT_OBJECT", "metadata must be a JSON object")]
    version = document.get("schema_version")
    if version == CURRENT_VERSION:
        return _problems_v3(document)
    if version not in KNOWN_VERSIONS:
        return [("METADATA_SCHEMA_VERSION",
                 "unsupported schema_version %r (known: %s)" % (version, ", ".join(KNOWN_VERSIONS + (CURRENT_VERSION,))))]
    for name in REQUIRED:
        if name not in document:
            out.append(("METADATA_FIELD_MISSING", "missing field `%s`" % name))

    for name in ("job_key", "generated_at", "family", "facts_source"):
        value = document.get(name)
        if name in document and (not isinstance(value, str) or not value.strip()):
            out.append(("METADATA_FIELD_TYPE", "`%s` must be a non-empty string" % name))
    for name in ("company", "title"):
        if name in document and not isinstance(document[name], str):
            out.append(("METADATA_FIELD_TYPE", "`%s` must be a string" % name))
    if "language" in document and document["language"] not in LANGUAGES:
        out.append(("METADATA_FIELD_TYPE", "`language` must be one of %s" % ", ".join(LANGUAGES)))
    if "job_sha256" in document and not (isinstance(document["job_sha256"], str)
                                         and JOB_SHA.match(document["job_sha256"])):
        out.append(("METADATA_FIELD_TYPE", "`job_sha256` must be 64 lowercase hex digits"))
    if "master_resume" in document and not (isinstance(document["master_resume"], str)
                                            and document["master_resume"].endswith(".tex")):
        out.append(("METADATA_FIELD_TYPE", "`master_resume` must be a path ending in .tex"))
    base = document.get("base_resume")
    if base is not None and not (isinstance(base, str) and base.endswith(".tex")):
        out.append(("METADATA_FIELD_TYPE", "`base_resume` must be null or a path ending in .tex"))
    pages = document.get("recommended_length_pages")
    if pages is not None and (isinstance(pages, bool) or pages not in (1, 2)):
        out.append(("METADATA_FIELD_TYPE", "`recommended_length_pages` must be 1, 2 or null"))
    if "decision" in document:
        decision = document["decision"]
        if not isinstance(decision, dict):
            out.append(("METADATA_FIELD_TYPE", "`decision` must be an object"))
        else:
            for key in ("selected_content", "excluded_content", "human_validations_required"):
                value = decision.get(key)
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    out.append(("METADATA_FIELD_TYPE", "`decision.%s` must be a list of strings" % key))
    return out


# --- version 3 (M7-B) ------------------------------------------------------------------------------------------
# Defined by CONTRACTS.md 4.2. No `generated_at` (nothing in a CV identity may depend on the clock), no `master_resume`, no
# `base_resume`: a version 3 document names the exact artefacts of one generation by hash instead of by path.
V3_FIELDS = ("schema_version", "tailored_cv_id", "job_key", "language", "family", "source_commit", "facts_source", "taxonomy",
             "company", "title", "job_sha256", "plan_sha256", "assembly_sha256", "tex_sha256", "pdf_sha256", "pdf_pages",
             "page_target", "paper", "template_id", "engine_version", "inputs", "decision", "unsatisfied_required",
             "pending_directives", "warnings")
V3_INPUTS = ("facts_source_sha256", "factbase_sha256", "content_sha256", "profile_sha256", "taxonomy_sha256", "offer_sha256")
V3_PAPERS = ("a4paper", "letterpaper")


def _hex(value):
    return isinstance(value, str) and JOB_SHA.match(value) is not None


def _strings(value):
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _problems_v3(document):
    out = []

    def bad(name, message):
        out.append(("METADATA_FIELD_TYPE", "`%s` %s" % (name, message)))

    missing = [name for name in V3_FIELDS if name not in document]
    extra = sorted(set(document) - set(V3_FIELDS))
    for name in missing:
        out.append(("METADATA_FIELD_MISSING", "missing field `%s`" % name))
    if extra:
        out.append(("METADATA_FIELD_UNKNOWN", "unknown fields: %s" % ", ".join(extra)))
    if missing:
        return out
    for name in ("tailored_cv_id", "job_sha256", "plan_sha256", "assembly_sha256", "tex_sha256"):
        if not _hex(document[name]):
            bad(name, "must be 64 lowercase hex digits")
    if document["pdf_sha256"] is not None and not _hex(document["pdf_sha256"]):
        bad("pdf_sha256", "must be null or 64 lowercase hex digits")
    for name in ("job_key", "family", "facts_source", "taxonomy", "company", "title", "template_id", "engine_version"):
        if not isinstance(document[name], str) or not document[name].strip():
            bad(name, "must be a non-empty string")
    if document["language"] not in LANGUAGES:
        bad("language", "must be one of %s" % ", ".join(LANGUAGES))
    if document["paper"] not in V3_PAPERS:
        bad("paper", "must be one of %s" % ", ".join(V3_PAPERS))
    for name, low, high in (("pdf_pages", 1, 999), ("page_target", 1, 5)):
        value = document[name]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high):
            bad(name, "must be null or an integer between %d and %d" % (low, high))
    if document["pdf_sha256"] is None and document["pdf_pages"] is not None:
        bad("pdf_pages", "must be null when there is no PDF")
    inputs = document["inputs"]
    if not isinstance(inputs, dict) or sorted(inputs) != sorted(V3_INPUTS) or not all(_hex(inputs[k]) for k in inputs):
        bad("inputs", "must hold exactly the six source fingerprints")
    decision = document["decision"]
    if not isinstance(decision, dict) or sorted(decision) != ["excluded_content", "human_validations_required", "selected_content"] \
            or not all(_strings(decision[k]) for k in decision):
        bad("decision", "must hold selected_content, excluded_content and human_validations_required as lists of strings")
    for name in ("unsatisfied_required", "pending_directives", "warnings"):
        if not _strings(document[name]):
            bad(name, "must be a list of non-empty strings")
    return out
