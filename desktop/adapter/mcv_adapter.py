"""Thin structured adapter between ModularCV Desktop and the ModularCV engine.

It is called by the Rust bridge with one JSON request on stdin and answers one JSON
object on stdout. It adds no business rule: every read goes through the engine
(`facts`, `profile`, `content`, `config`) and every write is re-validated by the engine
before and after the atomic replacement. Standard library only; the engine is not changed.

Operations (a closed list, selected by name, never by command line):
  read          read the workspace (facts, profile, resume content) with diagnostics
  save_fact     update or create one fact, editing only that fact's lines in facts.md
  save_profile  update a whitelisted set of Profile-v1 fields

Safety rules shared by the writes:
  * `expected_sha256` (the hash returned by `read`) must still match the file: otherwise
    `CONFLICT`, nothing is written.
  * The candidate file is validated by the engine; any error means `VALIDATION_FAILED`.
  * Untouched facts (fact base) / untouched keys (profile) are proven equal to the originals.
  * Atomic write: temporary file in the same folder, fsync, read-back check, hash re-check,
    then `os.replace`.
  * No fact is ever promoted to CONFIRMED implicitly: it needs `confirm: true` and an explicit
    `confirmed_on` date typed by the user.
  * Nothing is committed to Git and no other file is touched.
"""
import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `python -I` does not add the script folder

from mcv_core import (BOM, Refusal, atomic_replace, clean, clean_list, fail, locate, problems, read_bytes)  # noqa: F401
import mcv_jobs  # noqa: E402
import mcv_packages  # noqa: E402
from modularcv import canonical, content, docvalidate, facts, profile  # noqa: E402

FACT_FIELDS = ("lang", "confirmed_on", "technologies", "capabilities", "source", "supersedes", "note")
SUBSTANTIVE = ("text", "technologies", "capabilities", "source", "supersedes")


def fact_dict(fact):
    return {
        "id": fact.id, "status": fact.status, "text": fact.text, "section": fact.section, "lang": fact.lang,
        "confirmed_on": fact.confirmed_on, "technologies": list(fact.technologies),
        "capabilities": list(fact.capabilities), "source": fact.source, "supersedes": fact.supersedes,
        "note": fact.note, "extensions": dict(fact.extensions), "line": fact.line,
    }


def section_titles(text):
    result = []
    for number, line in enumerate(canonical.normalise_text(text).split("\n"), 1):
        match = facts._SECTION.match(line)
        if match:
            title = match.group("title")
            explicit = match.group("id")
            result.append({"id": explicit if explicit is not None else facts.slugify(title), "title": title, "line": number})
    return result


# --------------------------------------------------------------------------- read

def op_read(request):
    root = request.get("root")
    cfg, files = locate(root)
    out = {"ok": True, "root": str(Path(root)), "files": {k: Path(v).name for k, v in files.items()}}

    raw = read_bytes(files["facts"])
    factbase, require_date = None, False
    if raw is None:
        out["facts"] = {"present": False, "errors": [{"code": "FACT_FILE_MISSING", "message": "the fact file does not exist", "path": None}]}
    else:
        result = facts.check_bytes(raw)
        factbase = result.factbase
        out["facts"] = {
            "present": True, "source_sha256": result.facts_source_sha256, "valid": not result.errors,
            "errors": problems(result.errors), "warnings": problems(result.warnings),
            "sections": [], "facts": [],
        }
        if factbase is not None:
            out["facts"]["facts"] = [fact_dict(f) for f in factbase.facts]
            out["facts"]["counts"] = factbase.counts()
            try:
                out["facts"]["sections"] = section_titles(canonical.decode_text(raw))
            except canonical.CanonicalError:
                pass

    raw_profile = read_bytes(files["profile"])
    loaded_profile = None
    if raw_profile is None:
        out["profile"] = {"present": False, "errors": []}
    else:
        result = profile.check_bytes(raw_profile, factbase)
        loaded_profile = result.profile
        document = None
        try:
            document = docvalidate.load(raw_profile, "PROFILE_")
        except docvalidate.DocumentError:
            pass
        out["profile"] = {
            "present": True, "source_sha256": result.profile_source_sha256, "valid": not result.errors,
            "errors": problems(result.errors), "warnings": problems(result.warnings),
            "data": document if not result.errors else None,
        }
        if loaded_profile is not None:
            require_date = loaded_profile.require_confirmation_date

    raw_content = read_bytes(files["content"])
    if raw_content is None:
        out["content"] = {"present": False, "errors": []}
    else:
        result = content.check_bytes(raw_content, factbase, loaded_profile)
        document = None
        try:
            document = docvalidate.load(raw_content, "CONTENT_")
        except docvalidate.DocumentError:
            pass
        by_id = {f.id: f for f in factbase.facts} if factbase is not None else {}
        skills = []
        if isinstance(document, dict):
            for category in document.get("skills", []) if isinstance(document.get("skills"), list) else []:
                if not isinstance(category, dict):
                    continue
                items = []
                for item in category.get("items", []) if isinstance(category.get("items"), list) else []:
                    if not isinstance(item, dict):
                        continue
                    supports = [s for s in item.get("supports", []) if isinstance(s, str)]
                    items.append({
                        "id": item.get("id"), "text": item.get("text"), "technologies": item.get("technologies", []),
                        "supports": [{"id": s, "status": by_id[s].status if s in by_id else None} for s in supports],
                    })
                skills.append({"id": category.get("id"), "title": category.get("title"), "items": items})
        out["content"] = {
            "present": True, "source_sha256": result.content_source_sha256, "valid": not result.errors,
            "errors": problems(result.errors), "warnings": problems(result.warnings), "skills": skills,
        }
    out["require_confirmation_date"] = require_date
    return out


# --------------------------------------------------------------------------- facts editing

def serialise(record, extensions):
    parts = []
    for key in FACT_FIELDS:
        value = record.get(key)
        if key in ("technologies", "capabilities"):
            if value:
                parts.append("%s: %s" % (key, ", ".join(value)))
        elif value:
            parts.append("%s: %s" % (key, value))
    for key, value in sorted(extensions.items()):
        parts.append("%s: %s" % (key, value))
    line = "- [%s] %s: %s" % (record["id"], record["status"], record["text"])
    return line + (" {%s}" % "; ".join(parts) if parts else "")


def comparable(fact):
    data = fact_dict(fact)
    data.pop("line")
    return data


def split_file(raw):
    """(bom, eol, lines) of a facts file; refuses endings that cannot be preserved."""
    bom = BOM if raw.startswith(BOM) else b""
    try:
        text = (raw[len(bom):]).decode("utf-8")
    except UnicodeDecodeError:
        raise Refusal("FILE_NOT_EDITABLE", "the file is not valid UTF-8")
    crlf, lf = text.count("\r\n"), text.count("\n")
    if text.replace("\r\n", "").count("\r"):
        raise Refusal("FILE_NOT_EDITABLE", "the file uses lone carriage returns; it cannot be edited without altering it")
    if crlf and crlf != lf:
        raise Refusal("FILE_NOT_EDITABLE", "the file mixes CRLF and LF line endings; it cannot be edited without altering it")
    eol = "\r\n" if crlf else "\n"
    return bom, eol, text.replace("\r\n", "\n").split("\n")


def block_end(lines, start):
    """Index after the last continuation line of the fact starting at `start`."""
    end = start + 1
    while end < len(lines) and re.match(r"^ {4}\S", lines[end]):
        end += 1
    return end


def op_save_fact(request):
    cfg, files = locate(request.get("root"))
    raw = read_bytes(files["facts"])
    if raw is None:
        raise Refusal("FILE_UNREADABLE", "the fact file does not exist")
    expected = request.get("expected_sha256")
    if canonical.sha256_text(raw) != expected:
        raise Refusal("CONFLICT", "the file changed since it was read; reload before saving")
    before = facts.check_bytes(raw)
    if before.errors:
        raise Refusal("FILE_NOT_EDITABLE", "the fact file is already invalid; fix it before editing here", problems(before.errors))
    bom, eol, lines = split_file(raw)

    data = request.get("fact")
    if not isinstance(data, dict):
        raise Refusal("VALIDATION_FAILED", "a fact is expected")
    mode = request.get("mode")
    fact_id = clean(data.get("id"))
    existing = before.factbase.get(fact_id) if fact_id else None
    if mode == "update" and existing is None:
        raise Refusal("VALIDATION_FAILED", "the fact to update does not exist")
    if mode == "create" and existing is not None:
        raise Refusal("VALIDATION_FAILED", "a fact with this id already exists")
    if mode not in ("update", "create"):
        raise Refusal("VALIDATION_FAILED", "unknown mode")

    status = clean(data.get("status")) or "NOT_CONFIRMED"
    record = {
        "id": fact_id, "status": status, "text": clean(data.get("text")), "lang": clean(data.get("lang")),
        "confirmed_on": clean(data.get("confirmed_on")), "technologies": clean_list(data.get("technologies")),
        "capabilities": clean_list(data.get("capabilities")), "source": clean(data.get("source")),
        "supersedes": clean(data.get("supersedes")), "note": clean(data.get("note")),
    }
    if not record["text"]:
        raise Refusal("VALIDATION_FAILED", "the fact has no text")
    for key in ("text", "source", "note", "lang", "supersedes"):
        if key != "text" and record[key] and any(c in record[key] for c in "{};"):
            raise Refusal("VALIDATION_FAILED", "`%s` cannot contain braces or semicolons" % key)
    if any(c in item for item in record["technologies"] + record["capabilities"] for c in "{},;"):
        raise Refusal("VALIDATION_FAILED", "technologies and capabilities cannot contain braces, commas or semicolons")
    if "{" in record["text"] or "}" in record["text"]:
        raise Refusal("VALIDATION_FAILED", "the text cannot contain braces (they delimit the attribute block)")

    # Confirmation is an explicit, traceable user decision, never implicit.
    if status == facts.CONFIRMED:
        changed = existing is None or existing.status != facts.CONFIRMED or any(
            comparable(existing)[key] != record[key] for key in SUBSTANTIVE)
        if changed:
            decision = request.get("confirm")
            date = clean(decision.get("confirmed_on")) if isinstance(decision, dict) else None
            if not date:
                raise Refusal("CONFIRMATION_REQUIRED", "confirming a fact (or changing a confirmed one) needs an explicit decision with the date you confirm it (confirmed_on)")
            record["confirmed_on"] = date
    elif request.get("confirm"):
        raise Refusal("VALIDATION_FAILED", "`confirm` only applies to the CONFIRMED status")

    if mode == "update":
        section = existing.section
        extensions = dict(existing.extensions)
    else:
        section = clean(data.get("section"))
        extensions = {}
    titles = section_titles(canonical.decode_text(raw))
    if mode == "create" and section not in {t["id"] for t in titles}:
        raise Refusal("VALIDATION_FAILED", "the section does not exist in the fact file")

    new_line = serialise(record, extensions)
    new_lines = list(lines)
    if mode == "update":
        start = existing.line - 1
        end = block_end(lines, start)
        new_lines[start:end] = [new_line]
    else:
        heading = next(t["line"] for t in titles if t["id"] == section) - 1
        stop = len(lines)
        for index in range(heading + 1, len(lines)):
            if lines[index].startswith("## "):
                stop = index
                break
        last = None
        index = heading + 1
        while index < stop:
            if lines[index].startswith("- ["):
                last = block_end(lines, index) - 1
                index = last + 1
            else:
                index += 1
        if last is None:
            new_lines[heading + 1:heading + 1] = ["", new_line]
        else:
            new_lines.insert(last + 1, new_line)
    candidate = bom + eol.join(new_lines).encode("utf-8")

    def verify(data_bytes):
        after = facts.check_bytes(data_bytes)
        if after.errors:
            raise Refusal("VALIDATION_FAILED", "the engine rejects the edited fact file", problems(after.errors))
        mine = after.factbase.get(record["id"])
        want = {"status": record["status"], "text": record["text"], "lang": record["lang"], "confirmed_on": record["confirmed_on"],
                "technologies": record["technologies"], "capabilities": record["capabilities"], "source": record["source"],
                "supersedes": record["supersedes"], "note": record["note"], "section": section}
        got = comparable(mine)
        if any(got[k] != v for k, v in want.items()):
            raise Refusal("VALIDATION_FAILED", "the saved fact would not read back as entered (check special characters)")
        others_before = [comparable(f) for f in before.factbase.facts if f.id != record["id"]]
        others_after = [comparable(f) for f in after.factbase.facts if f.id != record["id"]]
        if others_before != others_after:
            raise Refusal("VALIDATION_FAILED", "another fact would change; save cancelled")

    if candidate == raw:
        raise Refusal("NO_CHANGE", "nothing changed")
    atomic_replace(files["facts"], candidate, expected, verify)
    return {"ok": True, "message": "saved", "downstream": downstream(request.get("root"), before)}


def downstream(root, before_facts):
    """Engine verdict of profile/content against the fact base as it is now (information, not a gate)."""
    try:
        fresh = op_read({"root": root})
        issues = []
        for name in ("profile", "content"):
            for item in fresh[name].get("errors", []):
                issues.append(dict(item, file=name))
        return issues
    except Refusal:
        return []


# --------------------------------------------------------------------------- profile editing

def op_save_profile(request):
    cfg, files = locate(request.get("root"))
    raw = read_bytes(files["profile"])
    if raw is None:
        raise Refusal("FILE_UNREADABLE", "the profile file does not exist")
    expected = request.get("expected_sha256")
    if canonical.sha256_text(raw) != expected:
        raise Refusal("CONFLICT", "the file changed since it was read; reload before saving")
    fact_raw = read_bytes(files["facts"])
    factbase = facts.check_bytes(fact_raw).factbase if fact_raw is not None else None
    before = profile.check_bytes(raw, factbase)
    if before.errors:
        raise Refusal("FILE_NOT_EDITABLE", "the profile is already invalid; fix it before editing here", problems(before.errors))
    try:
        original = docvalidate.load(raw, "PROFILE_")
    except docvalidate.DocumentError as error:
        raise Refusal("FILE_NOT_EDITABLE", str(error))

    changes = request.get("changes")
    if not isinstance(changes, dict) or set(changes) - {"identity", "default_language", "policy"}:
        raise Refusal("VALIDATION_FAILED", "only identity, default_language and policy can be edited here")
    document = copy.deepcopy(original)

    if "identity" in changes:
        ident = changes["identity"]
        if not isinstance(ident, dict) or set(ident) - set(profile.IDENTITY_FIELDS) - {"links"}:
            raise Refusal("VALIDATION_FAILED", "unknown identity field")
        target = document["identity"]
        for name in profile.IDENTITY_FIELDS:
            if name not in ident:
                continue
            entry = ident[name]
            if entry is None or (isinstance(entry, dict) and not clean(entry.get("value"))):
                if name == "display_name":
                    raise Refusal("VALIDATION_FAILED", "the display name is required")
                target.pop(name, None)
                continue
            if not isinstance(entry, dict) or entry.get("visibility") not in profile.VISIBILITIES:
                raise Refusal("VALIDATION_FAILED", "%s: visibility must be public or private" % name)
            merged = dict(target.get(name, {}))
            merged["value"] = clean(entry["value"])
            merged["visibility"] = entry["visibility"]
            target[name] = merged
        if "links" in ident:
            links = ident["links"]
            if not isinstance(links, list):
                raise Refusal("VALIDATION_FAILED", "links must be a list")
            old = target.get("links", [])
            built = []
            for position, link in enumerate(links):
                if not isinstance(link, dict) or not clean(link.get("value")) or link.get("visibility") not in profile.VISIBILITIES:
                    raise Refusal("VALIDATION_FAILED", "each link needs a value and a visibility")
                merged = dict(old[position]) if position < len(old) and isinstance(old[position], dict) else {}
                merged["value"] = clean(link["value"])
                merged["visibility"] = link["visibility"]
                label = clean(link.get("label"))
                if label:
                    merged["label"] = label
                else:
                    merged.pop("label", None)
                built.append(merged)
            if built:
                target["links"] = built
            else:
                target.pop("links", None)

    if "default_language" in changes:
        lang = changes["default_language"]
        if lang not in document["languages"]:
            raise Refusal("VALIDATION_FAILED", "the default language must be one of the profile languages")
        document["default_language"] = lang

    if "policy" in changes:
        pol = changes["policy"]
        allowed = {"never_publish_terms", "omit_by_default_terms", "forbidden_words", "require_confirmation_date"}
        if not isinstance(pol, dict) or set(pol) - allowed:
            raise Refusal("VALIDATION_FAILED", "unknown policy field")
        target = document.setdefault("policy", {})
        for name in ("never_publish_terms", "omit_by_default_terms"):
            if name in pol:
                target[name] = clean_list(pol[name])
        if "forbidden_words" in pol:
            words = pol["forbidden_words"]
            if not isinstance(words, dict):
                raise Refusal("VALIDATION_FAILED", "forbidden_words must map languages to lists")
            target["forbidden_words"] = {code: clean_list(terms) for code, terms in words.items() if clean_list(terms)}
        if "require_confirmation_date" in pol:
            if not isinstance(pol["require_confirmation_date"], bool):
                raise Refusal("VALIDATION_FAILED", "require_confirmation_date must be true or false")
            target["require_confirmation_date"] = pol["require_confirmation_date"]

    # Untouched top-level keys must be identical to the original.
    touched = set(changes)
    for key in original:
        if key not in touched and document.get(key) != original[key]:
            raise Refusal("VALIDATION_FAILED", "unexpected change to `%s`; save cancelled" % key)
    if set(document) - set(original) - touched:
        raise Refusal("VALIDATION_FAILED", "unexpected new key; save cancelled")

    candidate = (BOM if raw.startswith(BOM) else b"") + (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if document == original:
        raise Refusal("NO_CHANGE", "nothing changed")

    def verify(data_bytes):
        after = profile.check_bytes(data_bytes, factbase)
        if after.errors:
            raise Refusal("VALIDATION_FAILED", "the engine rejects the edited profile", problems(after.errors))
        if docvalidate.load(data_bytes, "PROFILE_") != document:
            raise Refusal("VALIDATION_FAILED", "the saved profile would not read back as entered")

    atomic_replace(files["profile"], candidate, expected, verify)
    return {"ok": True, "message": "saved", "downstream": downstream(request.get("root"), None)}


OPERATIONS = {"read": op_read, "save_fact": op_save_fact, "save_profile": op_save_profile}
OPERATIONS.update(mcv_jobs.OPERATIONS)
OPERATIONS.update(mcv_packages.OPERATIONS)


def main():
    try:
        request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        handler = OPERATIONS.get(request.get("op")) if isinstance(request, dict) else None
        if handler is None:
            result = fail("OPERATION_NOT_ALLOWED", "unknown operation")
        else:
            result = handler(request)
    except Refusal as refusal:
        result = fail(refusal.code, refusal.message, refusal.details)
    except Exception as error:  # fail closed, never a partial success
        result = fail("ADAPTER_ERROR", "unexpected adapter error (%s)" % type(error).__name__)
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
