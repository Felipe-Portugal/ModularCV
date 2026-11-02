"""Read-only validation of a CV `metadata.json` (schema_version 1 and 2).

Mirrors `schemas/application_metadata.schema.json` without a third-party validator. Historical
compatibility is not a security verdict: a valid v1 or v2 document is only *readable*; readiness
still demands the evidence. `source_commit` is judged by `readiness` (placeholder, unknown, ...),
so it is not checked here. Version 3 is defined in milestone M7; until then it is refused,
like any unknown version, instead of being guessed.
"""
import re

KNOWN_VERSIONS = ("1", "2")
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
    if version not in KNOWN_VERSIONS:
        return [("METADATA_SCHEMA_VERSION",
                 "unsupported schema_version %r (known: %s)" % (version, ", ".join(KNOWN_VERSIONS)))]
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
