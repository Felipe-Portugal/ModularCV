import hashlib
import unicodedata

import pytest

from modularcv import canonical


def test_normalise_text_handles_endings_bom_and_nfc():
    decomposed = "é"  # e + combining acute
    out = canonical.normalise_text("﻿a\r\nb\rc\n" + decomposed)
    assert out == "a\nb\nc\n" + unicodedata.normalize("NFC", decomposed)
    assert out.endswith("é")
    assert "\r" not in out and not out.startswith("﻿")


def test_normalise_text_can_keep_a_bom():
    assert canonical.normalise_text("﻿x", strip_bom=False) == "﻿x"


def test_canonical_bytes_ignores_key_order():
    a = {"b": 1, "a": [1, 2, {"y": 1, "x": 2}]}
    b = {"a": [1, 2, {"x": 2, "y": 1}], "b": 1}
    assert canonical.canonical_bytes(a) == canonical.canonical_bytes(b)
    assert canonical.canonical_json(a) == '{"a":[1,2,{"x":2,"y":1}],"b":1}'


def test_canonical_bytes_ignores_line_endings_and_unicode_form_in_strings():
    lf = {"t": "one\ntwo é"}
    crlf = {"t": "one\r\ntwo é"}
    assert canonical.canonical_bytes(lf) == canonical.canonical_bytes(crlf)
    assert canonical.fingerprint(lf) == canonical.fingerprint(crlf)


def test_canonical_json_keeps_unicode_and_has_no_trailing_newline():
    text = canonical.canonical_json({"k": "café"})
    assert text == '{"k":"café"}'
    assert canonical.canonical_bytes({"k": "café"}).endswith(b'"}')


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_refused(bad):
    with pytest.raises(canonical.CanonicalError) as caught:
        canonical.canonical_bytes({"n": bad})
    assert caught.value.code == "CANONICAL_NON_FINITE"


def test_unsupported_types_and_bad_keys_are_refused():
    with pytest.raises(canonical.CanonicalError) as caught:
        canonical.canonical_bytes({"n": object()})
    assert caught.value.code == "CANONICAL_UNSUPPORTED_TYPE"
    with pytest.raises(canonical.CanonicalError) as caught:
        canonical.canonical_bytes({1: "x"})
    assert caught.value.code == "CANONICAL_BAD_KEY"


def test_keys_equal_once_normalised_are_refused():
    with pytest.raises(canonical.CanonicalError) as caught:
        canonical.canonical_bytes({"é": 1, "é": 2})
    assert caught.value.code == "CANONICAL_DUPLICATE_KEY"


def test_lone_surrogate_is_a_canonical_error_not_a_crash():
    with pytest.raises(canonical.CanonicalError) as caught:
        canonical.canonical_bytes({"s": "\ud800"})
    assert caught.value.code == "CANONICAL_ENCODING"


def test_sha256_text_is_identical_for_lf_and_crlf_copies():
    lf = b"line one\nline two\n"
    crlf = b"line one\r\nline two\r\n"
    cr = b"line one\rline two\r"
    bom = b"\xef\xbb\xbf" + lf
    expected = hashlib.sha256(lf).hexdigest()
    assert canonical.sha256_text(lf) == expected
    assert canonical.sha256_text(crlf) == expected
    assert canonical.sha256_text(cr) == expected
    assert canonical.sha256_text(bom) == expected
    assert canonical.sha256_text(lf.decode("utf-8")) == expected


def test_sha256_text_does_not_apply_nfc_but_fingerprint_does():
    composed = "é\n"
    decomposed = "é\n"
    assert canonical.sha256_text(composed) != canonical.sha256_text(decomposed)
    assert canonical.fingerprint({"t": composed}) == canonical.fingerprint({"t": decomposed})


def test_sha256_text_is_sensitive_to_any_other_edit():
    assert canonical.sha256_text("a\nb\n") != canonical.sha256_text("a\n\nb\n")
    assert canonical.sha256_text("a b\n") != canonical.sha256_text("a  b\n")


def test_sha256_bytes_never_normalises_binary_data():
    data = b"%PDF-1.4\r\nbinary\rdata\xef\xbb\xbf"
    assert canonical.sha256_bytes(data) == hashlib.sha256(data).hexdigest()
    assert canonical.sha256_bytes(data) != canonical.sha256_text(data)


def test_three_hash_kinds_are_distinct_for_the_same_text():
    # A canonical fingerprint hashes the canonical JSON, not the text of a source file.
    model = {"t": "a"}
    as_text = '{"t": "a"}\r\n'
    assert canonical.fingerprint(model) == canonical.sha256_bytes(b'{"t":"a"}')
    assert canonical.sha256_text(as_text) != canonical.sha256_bytes(as_text.encode("utf-8"))
    assert canonical.sha256_text(as_text) != canonical.fingerprint(model)


def test_decode_text_drops_bom_and_rejects_invalid_utf8():
    assert canonical.decode_text(b"\xef\xbb\xbfabc") == "abc"
    with pytest.raises(canonical.CanonicalError) as caught:
        canonical.decode_text(b"\xff\xfe\x00")
    assert caught.value.code == "TEXT_NOT_UTF8"


def test_fingerprint_is_a_64_digit_lowercase_hex_and_deterministic():
    value = canonical.fingerprint({"a": [1, 2, 3]})
    assert len(value) == 64 and value == value.lower()
    assert value == canonical.fingerprint({"a": [1, 2, 3]})
    assert value != canonical.fingerprint({"a": [3, 2, 1]})


def test_module_imports_nothing_from_the_package():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(canonical))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names] + [getattr(node, "module", "") or ""]
            assert not any(name.startswith("modularcv") for name in names)
