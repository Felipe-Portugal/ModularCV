"""Shared reader for the JSON documents of the workspace (Profile-v1, LegacyFactMap-v1).

Every problem is a stable machine code (`<PREFIX><SUFFIX>`), a message and a JSON path such as
`families.software.languages[1]`. **A message never repeats a value of the document**: the file is
private, and so are the reports built from these problems. Only a path made of safe key names is echoed.

Rules of the contracts applied here (CONTRACTS.md section 0): unknown fields are refused, `x-` fields are
kept and ignored by the engine, strings are NFC-normalised with collapsed whitespace, a duplicate JSON
key is an error (never "last one wins"), and `NaN`/`Infinity` are refused.
"""
import json
import re
import unicodedata
from collections import namedtuple

from . import canonical, facts

MISSING = object()
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


class Problem(namedtuple("Problem", "code message path")):
    def as_dict(self):
        return {"code": self.code, "message": self.message, "path": self.path}


class DocumentError(ValueError):
    """The bytes are not a usable JSON document. `code` is a stable machine code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def label(key):
    """A key name safe to show in a path: short and made of harmless characters, else `<key>`."""
    return key if isinstance(key, str) and _SAFE_LABEL.match(key) else "<key>"


def join(path, key):
    return label(key) if not path else "%s.%s" % (path, label(key))


def join_key(path, key):
    """Like `join` for a key the user chose (a family id, a block id, a language code): echoed only when it is
    a valid identifier, so an invalid key - which may well be a personal value - is masked as `<key>`."""
    shown = key if isinstance(key, str) and facts.valid_id(key) else "<key>"
    return shown if not path else "%s.%s" % (path, shown)


def index(path, position):
    return "%s[%d]" % (path, position)


def load(data, prefix):
    """The JSON value of `data` (bytes). Raises `DocumentError` with `<prefix>NOT_UTF8|NOT_JSON|DUPLICATE_KEY`."""
    try:
        text = canonical.decode_text(data)
    except canonical.CanonicalError:
        raise DocumentError(prefix + "NOT_UTF8", "the file is not valid UTF-8")

    def pairs(items):
        seen = set()
        for key, _ in items:
            if key in seen:
                raise DocumentError(prefix + "DUPLICATE_KEY", "an object holds the same key twice")
            seen.add(key)
        return dict(items)

    def constant(_name):
        raise DocumentError(prefix + "NOT_JSON", "NaN and infinity are not valid JSON")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except DocumentError:
        raise
    except (ValueError, RecursionError):
        raise DocumentError(prefix + "NOT_JSON", "the file is not valid JSON")


class Reader:
    """Collects problems while a document is checked; the check functions return None on a bad value."""

    def __init__(self, prefix):
        self.prefix = prefix
        self.problems = []

    def error(self, suffix, path, message):
        self.problems.append(Problem(self.prefix + suffix, message, path))

    # --- structure ---------------------------------------------------------------------------------

    def obj(self, value, path, required=(), optional=()):
        """(dict or None, extensions). Unknown fields are refused, `x-` fields are returned apart."""
        if not isinstance(value, dict):
            self.error("BAD_TYPE", path, "must be a JSON object")
            return None, {}
        known = set(required) | set(optional)
        extensions = {}
        for key in value:
            if key in known:
                continue
            if isinstance(key, str) and key.startswith("x-"):
                if not facts.EXTENSION_PATTERN.fullmatch(key):
                    self.error("BAD_EXTENSION", join(path, key), "an extension name must read `x-` then a lowercase identifier")
                    continue
                try:
                    extensions[key] = json.loads(canonical.canonical_json(value[key]))
                except canonical.CanonicalError:
                    self.error("BAD_EXTENSION", join(path, key), "the extension value has no canonical form")
            else:
                self.error("UNKNOWN_FIELD", join(path, key), "unknown field")
        for key in required:
            if key not in value:
                self.error("MISSING_FIELD", join(path, key), "required field is missing")
        return value, extensions

    def lst(self, value, path, empty_ok=True):
        if not isinstance(value, list):
            self.error("BAD_TYPE", path, "must be a JSON array")
            return None
        if not value and not empty_ok:
            self.error("EMPTY_VALUE", path, "must not be empty")
            return None
        return value

    # --- scalars -----------------------------------------------------------------------------------

    def text(self, value, path):
        """A single-line string: NFC, whitespace collapsed, never empty."""
        if not isinstance(value, str):
            self.error("BAD_TYPE", path, "must be a string")
            return None
        if any(unicodedata.category(ch) in ("Cc", "Zl", "Zp") for ch in value):
            self.error("CONTROL_CHARACTER", path, "the value holds a control or separator character")
            return None
        cleaned = " ".join(unicodedata.normalize("NFC", value).split())
        if not cleaned:
            self.error("EMPTY_VALUE", path, "must not be empty")
            return None
        return cleaned

    def ident(self, value, path):
        if not isinstance(value, str) or not facts.valid_id(value):
            self.error("INVALID_ID", path, "must be a lowercase identifier of 1 to %d characters" % facts.ID_MAX)
            return None
        return value

    def lang(self, value, path):
        if not isinstance(value, str) or not facts.LANG_PATTERN.fullmatch(value):
            self.error("INVALID_LANGUAGE", path, "must be a two-letter lowercase language code")
            return None
        return value

    def boolean(self, value, path):
        if not isinstance(value, bool):
            self.error("BAD_TYPE", path, "must be true or false")
            return None
        return value

    def integer(self, value, path, low, high):
        if isinstance(value, bool) or not isinstance(value, int):
            self.error("BAD_TYPE", path, "must be an integer")
            return None
        if not low <= value <= high:
            self.error("OUT_OF_RANGE", path, "must be between %d and %d" % (low, high))
            return None
        return value

    def choice(self, value, path, allowed):
        if not isinstance(value, str) or value not in allowed:
            self.error("INVALID_VALUE", path, "must be one of: %s" % ", ".join(allowed))
            return None
        return value

    # --- collections -------------------------------------------------------------------------------

    def unique(self, items, path, key=lambda item: item):
        """Report every item whose key was already seen. Returns the items that are first occurrences."""
        seen, kept = set(), []
        for position, item in enumerate(items):
            marker = key(item)
            if marker in seen:
                self.error("DUPLICATE_VALUE", index(path, position), "duplicates an earlier entry")
                continue
            seen.add(marker)
            kept.append(item)
        return kept

    def ok(self):
        return not self.problems
