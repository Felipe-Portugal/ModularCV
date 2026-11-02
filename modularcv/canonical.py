"""Canonical text, canonical JSON and the three kinds of hash.

See `docs/design/CONTRACTS.md` sections 0 and 0.1. Three hashes, never mixed:

* canonical fingerprint  - `fingerprint(model)`: SHA-256 of the canonical JSON of a parsed model.
* normalised-source hash - `sha256_text(data)`: SHA-256 of a text file with the BOM removed and the
  line endings turned into LF, nothing else (no Unicode normalisation).
* exact-bytes hash       - `sha256_bytes(data)`: SHA-256 of the raw bytes of a binary file.

Standard library only. This module imports nothing from the rest of the package.
"""
import hashlib
import json
import math
import unicodedata

BOM = "﻿"
BOM_BYTES = b"\xef\xbb\xbf"


class CanonicalError(ValueError):
    """Input that cannot be canonicalised. `code` is a stable machine code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def normalise_newlines(text: str) -> str:
    """CRLF and lone CR become LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalise_text(text: str, strip_bom: bool = True) -> str:
    """The text normalisation of the contracts: optional leading BOM removal, LF, NFC."""
    if strip_bom and text.startswith(BOM):
        text = text[1:]
    return unicodedata.normalize("NFC", normalise_newlines(text))


def fold(text: str) -> str:
    """Matching key for display names: casefolded, accents removed, NFC. Never stored, only compared."""
    stripped = "".join(ch for ch in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", stripped)


def decode_text(data: bytes) -> str:
    """Strict UTF-8 decoding; a leading BOM is dropped. Anything else is `TEXT_NOT_UTF8`."""
    if data.startswith(BOM_BYTES):
        data = data[len(BOM_BYTES):]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CanonicalError("TEXT_NOT_UTF8", "the text is not valid UTF-8 (%s)" % error.reason)


def normalise_source_bytes(data: bytes) -> bytes:
    """Bytes of a text file as hashed by provenance: no BOM, LF endings, no other change."""
    if data.startswith(BOM_BYTES):
        data = data[len(BOM_BYTES):]
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_text(data) -> str:
    """Normalised-source hash of a text file (`bytes`, or `str` encoded as UTF-8)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(normalise_source_bytes(data)).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Exact-bytes hash of a binary file. No normalisation, ever."""
    return hashlib.sha256(data).hexdigest()


def _canonical_value(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalError("CANONICAL_NON_FINITE", "NaN and infinity have no canonical form")
        return value
    if isinstance(value, str):
        return normalise_text(value, strip_bom=False)
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalError("CANONICAL_BAD_KEY", "object keys must be strings")
            key = normalise_text(key, strip_bom=False)
            if key in out:
                raise CanonicalError("CANONICAL_DUPLICATE_KEY", "two keys are equal once normalised")
            out[key] = _canonical_value(item)
        return out
    raise CanonicalError("CANONICAL_UNSUPPORTED_TYPE", "type %s has no canonical form" % type(value).__name__)


def canonical_json(model) -> str:
    """Canonical JSON: sorted keys, `,` and `:` separators, no ASCII escaping, strings in NFC with LF."""
    return json.dumps(
        _canonical_value(model),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(model) -> bytes:
    """UTF-8 bytes of the canonical JSON, without a trailing newline."""
    try:
        return canonical_json(model).encode("utf-8")
    except UnicodeEncodeError:
        raise CanonicalError("CANONICAL_ENCODING", "a string holds a code point that UTF-8 cannot encode")


def fingerprint(model) -> str:
    """Canonical fingerprint of a model: SHA-256 (lowercase hex) of its canonical bytes."""
    return hashlib.sha256(canonical_bytes(model)).hexdigest()
