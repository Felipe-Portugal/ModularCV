"""CVQualityReview-v1: the human approval of one exact CV.

The file `cv-quality-review.json` sits beside the CV metadata and is written by a person; the
engine only reads it. An approval names the exact `tailored_cv_id` **and** the hash of the CV
document (`document_sha256`, the normalised-source hash of the `cv_tex` recorded in the
snapshot). Editing the document, or regenerating it under a new identity, makes an old approval
useless: it matches nothing.
"""
import json

FILE_NAME = "cv-quality-review.json"
SCHEMA = "CVQualityReview-v1"
FIELDS = ("schema", "decision", "tailored_cv_id", "document_sha256")
OPTIONAL = ("note", "reviewer")
DECISIONS = ("APPROVED", "REJECTED")


def parse(data):
    """(document, error). `error` is a message when the file cannot be used."""
    try:
        document = json.loads(data.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as error:
        return None, "not valid JSON: %s" % error
    if not isinstance(document, dict):
        return None, "not a JSON object"
    if document.get("schema") != SCHEMA:
        return None, "schema must be `%s`" % SCHEMA
    missing = [name for name in FIELDS if name not in document]
    extra = sorted(set(document) - set(FIELDS) - set(OPTIONAL))
    if missing or extra:
        return None, "missing fields %s, unknown fields %s" % (missing, extra)
    if document["decision"] not in DECISIONS:
        return None, "decision must be one of %s" % ", ".join(DECISIONS)
    for name in ("tailored_cv_id", "document_sha256"):
        if not isinstance(document[name], str) or not document[name]:
            return None, "`%s` must be a non-empty string" % name
    for name in OPTIONAL:
        if name in document and not isinstance(document[name], str):
            return None, "`%s` must be a string" % name
    return document, None


def judge(document, tailored_cv_id, document_sha256):
    """None when the review approves exactly this CV, else the readiness reason."""
    if document["decision"] == "REJECTED":
        return "HUMAN_REVIEW_REJECTED"
    if document["tailored_cv_id"] != tailored_cv_id or document["document_sha256"] != document_sha256:
        return "HUMAN_REVIEW_MISMATCH"
    return None
