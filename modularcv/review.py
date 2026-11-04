"""CVQualityReview-v1: the human approval of one exact CV.

The file `cv-quality-review.json` sits beside the CV metadata and is written by a person; the
engine only reads it. An approval names the exact `tailored_cv_id` **and** the hash of the CV
document (`document_sha256`, the normalised-source hash of the `cv_tex` recorded in the
snapshot). Editing the document, or regenerating it under a new identity, makes an old approval
useless: it matches nothing.
"""
import json

from . import canonical

FILE_NAME = "cv-quality-review.json"
SCHEMA = "CVQualityReview-v1"
FIELDS = ("schema", "decision", "tailored_cv_id", "document_sha256")
OPTIONAL = ("note", "reviewer")
DECISIONS = ("APPROVED", "REJECTED")


def parse(data):
    """(document, error). `error` is a message when the file cannot be used."""
    try:
        document = canonical.loads(data.decode("utf-8-sig"))
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


# --- CVQualityReview-v2 (M7-B) --------------------------------------------------------------------------------
# The approval of one exact final document (the PDF), not of its source. It also records what the reviewer was shown, so an
# approval given before the warnings changed no longer applies. It is a JSON file with no signature: see docs/PACKAGE.md.
SCHEMA_V2 = "CVQualityReview-v2"
FIELDS_V2 = ("schema", "decision", "tailored_cv_id", "document_role", "document_sha256", "reviewed", "acknowledged", "reviewer")
OPTIONAL_V2 = ("note",)
DOCUMENT_ROLE = "cv_pdf"
REVIEWED_FIELDS = ("plan_sha256", "assembly_sha256", "tex_sha256")
ACKNOWLEDGED_FIELDS = ("unsatisfied_required", "pending_directives", "warnings", "page_verdict")


def _hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def schema_of(data):
    """The schema string of a review file, or None when it is not even a JSON object."""
    try:
        document = canonical.loads(data.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return None
    return document.get("schema") if isinstance(document, dict) else None


def parse_v2(data):
    """(document, error) for a `CVQualityReview-v2` file."""
    try:
        document = canonical.loads(data.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as error:
        return None, "not valid JSON: %s" % error
    if not isinstance(document, dict) or document.get("schema") != SCHEMA_V2:
        return None, "schema must be `%s`" % SCHEMA_V2
    missing = [name for name in FIELDS_V2 if name not in document]
    extra = sorted(set(document) - set(FIELDS_V2) - set(OPTIONAL_V2))
    if missing or extra:
        return None, "missing fields %s, unknown fields %s" % (missing, extra)
    if document["decision"] not in DECISIONS:
        return None, "decision must be one of %s" % ", ".join(DECISIONS)
    if document["document_role"] != DOCUMENT_ROLE:
        return None, "document_role must be `%s`: only the final PDF can be approved" % DOCUMENT_ROLE
    if not _hex64(document["tailored_cv_id"]) or not _hex64(document["document_sha256"]):
        return None, "tailored_cv_id and document_sha256 must be 64 lowercase hex digits"
    reviewed = document["reviewed"]
    if not isinstance(reviewed, dict) or sorted(reviewed) != sorted(REVIEWED_FIELDS) or not all(_hex64(v) for v in reviewed.values()):
        return None, "`reviewed` must hold %s as sha256 values" % ", ".join(REVIEWED_FIELDS)
    acknowledged = document["acknowledged"]
    if not isinstance(acknowledged, dict) or sorted(acknowledged) != sorted(ACKNOWLEDGED_FIELDS):
        return None, "`acknowledged` must hold %s" % ", ".join(ACKNOWLEDGED_FIELDS)
    for name in ("unsatisfied_required", "pending_directives", "warnings"):
        if not isinstance(acknowledged[name], list) or not all(isinstance(item, str) for item in acknowledged[name]):
            return None, "`acknowledged.%s` must be a list of strings" % name
    if not isinstance(acknowledged["page_verdict"], str):
        return None, "`acknowledged.page_verdict` must be a string"
    if not isinstance(document["reviewer"], str) or not document["reviewer"].strip():
        return None, "`reviewer` must be a non-empty string"
    if "note" in document and not isinstance(document["note"], str):
        return None, "`note` must be a string"
    return document, None


def judge_v2(document, tailored_cv_id, document_sha256, reviewed, acknowledged):
    """None when the review approves exactly this PDF of this CV as it is presented now, else the readiness reason.

    `document_sha256` is the hash of the PDF bytes **read now**, never the one recorded in the snapshot."""
    if document["decision"] == "REJECTED":
        return "HUMAN_REVIEW_REJECTED"
    if document["tailored_cv_id"] != tailored_cv_id or document["document_sha256"] != document_sha256 \
            or document["reviewed"] != reviewed or document["acknowledged"] != acknowledged:
        return "HUMAN_REVIEW_MISMATCH"
    return None
