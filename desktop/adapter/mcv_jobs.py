"""Job offers, requirement matrix, tailoring plan and CV generation for ModularCV Desktop.

Thin layer over the engine: offers are checked with `joboffer`, the matrix and the plan come from
`plan.build_plan`, the structured CV from `assemble.assemble`, the `.tex` from `latex.render` and the PDF
from `pdf.compile_tex`. No ranking, selection or provenance rule is implemented here. Offers are
untrusted data: nothing in them is ever executed or sent anywhere, and nothing is fetched from the network.

Writes are confined to the workspace: offers in the configured offers folder, plans in `plans/`, outputs in
`out/`. New files are created exclusively (an existing file is never overwritten); an offer edit uses the same
hash check and atomic replacement as the other editors.
"""
import copy
import json
import os
import re
from pathlib import Path

from mcv_core import (BOM, Refusal, atomic_replace, clean, create_new, dumps, ensure_dir, locate, problems, read_bytes,
                      workspace_lock)
from modularcv import (assemble, canonical, content, docvalidate, facts, joboffer, latex, paths, pdf,
                       plan as planmod, profile, provenance, taxonomy)

OFFER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}\.json$")
BASE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
FILE_LIMIT = 1024 * 1024
LIST_LIMIT = 300
PLANS_DIR = "plans"
OUT_DIR = "out"
OFFER_LINE_FIELDS = ("location", "workplace_type", "source_system", "source_ref", "source_url", "posted_on")
OFFER_FORM_FIELDS = ("job_key", "title", "company", "description", "language", "employment_type",
                     *OFFER_LINE_FIELDS, "requirements")


# --------------------------------------------------------------------------- locations

def offers_folder(root, cfg):
    folder = paths.resolve_inside(root, cfg["offers_dir"])
    if folder is None:
        raise Refusal("CONFIG_ERROR", "the configured offers folder leaves the workspace")
    return folder


def offer_path(root, cfg, name):
    if not isinstance(name, str) or not OFFER_NAME.match(name):
        raise Refusal("PATH_UNSAFE", "unsafe offer file name")
    folder = offers_folder(root, cfg)
    target = folder / name
    if target.is_symlink():
        raise Refusal("PATH_UNSAFE", "an offer file cannot be a link")
    if paths.resolve_inside(root, str(Path(cfg["offers_dir"]) / name).replace("\\", "/")) is None:
        raise Refusal("PATH_UNSAFE", "the offer file leaves the workspace")
    return target


def relative_posix(root, path):
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def workspace_file(root, relative, folder):
    """A file named by the UI inside the fixed `folder` of the workspace (plans or out)."""
    if not isinstance(relative, str) or "/" in relative or "\\" in relative or not BASE_NAME.match(relative.rsplit(".", 1)[0] or "") \
            or paths.relative_path_problem(relative):
        raise Refusal("PATH_UNSAFE", "unsafe file name")
    target = Path(root) / folder / relative
    if target.is_symlink() or paths.resolve_inside(root, folder + "/" + relative) is None:
        raise Refusal("PATH_UNSAFE", "the file leaves the workspace")
    return target


# --------------------------------------------------------------------------- offers

def _summary(name, raw):
    result = joboffer.check_bytes(raw)
    entry = {"file": name, "sha256": canonical.sha256_text(raw), "valid": not result.errors, "errors": problems(result.errors)}
    try:
        document = docvalidate.load(raw, "OFFER_")
    except docvalidate.DocumentError:
        document = None
    if isinstance(document, dict):
        for key in ("job_key", "title", "company", "language", "employment_type", "location", "workplace_type", "source_url", "posted_on"):
            value = document.get(key)
            entry[key] = value if isinstance(value, str) else None
        description = document.get("description")
        entry["description_chars"] = len(description) if isinstance(description, str) else 0
        requirements = document.get("requirements")
        entry["requirements"] = len(requirements) if isinstance(requirements, list) else 0
    return entry


def op_offers_list(request):
    cfg, _ = locate(request.get("root"), ())
    root = request["root"]
    folder = offers_folder(root, cfg)
    out = {"ok": True, "folder": cfg["offers_dir"], "offers": [], "truncated": False}
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.json")):
        if not OFFER_NAME.match(path.name) or path.is_symlink() or not path.is_file():
            continue
        if len(out["offers"]) >= LIST_LIMIT:
            out["truncated"] = True
            break
        if path.stat().st_size > FILE_LIMIT:
            out["offers"].append({"file": path.name, "sha256": None, "valid": False,
                                  "errors": [{"code": "OFFER_FILE_TOO_LARGE", "message": "the file is larger than 1 MB", "path": None}]})
            continue
        out["offers"].append(_summary(path.name, read_bytes(path)))
    return out


def op_offer_read(request):
    cfg, _ = locate(request.get("root"), ())
    path = offer_path(request["root"], cfg, request.get("file"))
    raw = read_bytes(path)
    if raw is None:
        raise Refusal("FILE_UNREADABLE", "the offer does not exist")
    if len(raw) > FILE_LIMIT:
        raise Refusal("FILE_NOT_EDITABLE", "the offer is larger than 1 MB")
    result = joboffer.check_bytes(raw)
    try:
        document = docvalidate.load(raw, "OFFER_")
    except docvalidate.DocumentError:
        document = None
    return {"ok": True, "file": path.name, "sha256": canonical.sha256_text(raw), "valid": not result.errors,
            "errors": problems(result.errors), "warnings": problems(result.warnings), "document": document,
            "offer_sha256": result.offer.offer_sha256 if result.offer else None}


def _multiline(value):
    if not isinstance(value, str):
        raise Refusal("VALIDATION_FAILED", "the description must be text")
    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()


def build_offer_document(form, base=None):
    """The offer document for a form. Required fields must come from the user; nothing is filled in."""
    if not isinstance(form, dict) or set(form) - set(OFFER_FORM_FIELDS):
        raise Refusal("VALIDATION_FAILED", "unknown offer field")
    document = copy.deepcopy(base) if base else {"schema": joboffer.SCHEMA}
    for key in ("job_key", "title", "company"):
        if key in form:
            value = clean(form[key])
            if not value:
                raise Refusal("VALIDATION_FAILED", "%s is required" % key)
            document[key] = value
    if "description" in form:
        value = _multiline(form["description"])
        if not value:
            raise Refusal("VALIDATION_FAILED", "description is required")
        if value != document.get("description"):
            document["description"] = value
            document.pop("description_sha256", None)  # re-derived by the engine below when it was present
    if base is None:
        for key in ("job_key", "title", "company", "description"):
            if key not in document:
                raise Refusal("VALIDATION_FAILED", "%s is required and must be entered by you" % key)
    for key in ("language", "employment_type"):
        if key in form:
            value = clean(form[key])
            if value:
                document[key] = value
            else:
                document.pop(key, None)
    for key in OFFER_LINE_FIELDS:
        if key in form:
            value = clean(form[key])
            if value:
                document[key] = value
            else:
                document.pop(key, None)
    if "requirements" in form:
        rows = form["requirements"]
        if not isinstance(rows, list):
            raise Refusal("VALIDATION_FAILED", "requirements must be a list")
        built = []
        for row in rows:
            if not isinstance(row, dict):
                raise Refusal("VALIDATION_FAILED", "a requirement needs an id, a term and a priority")
            built.append({"id": clean(row.get("id")), "term": clean(row.get("term")), "priority": clean(row.get("priority"))})
        if built:
            document["requirements"] = built
        else:
            document.pop("requirements", None)
    if base is not None and "description_sha256" in base and "description_sha256" not in document:
        # The description changed: ask the engine for the hash it expects, instead of computing one here.
        probe = joboffer.check_data({k: v for k, v in document.items() if k != "description_sha256"})
        if probe.offer is not None:
            document["description_sha256"] = probe.offer.description_sha256
    return document


def _offer_bytes(document, bom=False):
    return (BOM if bom else b"") + (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _check_document_bytes(data):
    result = joboffer.check_bytes(data)
    if result.errors:
        raise Refusal("VALIDATION_FAILED", "the engine refuses this offer", problems(result.errors))
    return result


def op_offer_save(request):
    root = request.get("root")
    cfg, _ = locate(root, ())
    mode = request.get("mode")
    form = request.get("offer")
    if mode == "create":
        document = build_offer_document(form)
        data = _offer_bytes(document)
        _check_document_bytes(data)  # the engine judges the content (including the job key) first
        name = document["job_key"] + ".json"
        target = offer_path(root, cfg, name)
        folder = offers_folder(root, cfg)
        if not folder.is_dir():
            if len(Path(cfg["offers_dir"]).parts) != 1:
                raise Refusal("PATH_UNSAFE", "the offers folder does not exist")
            ensure_dir(root, cfg["offers_dir"])
        try:
            create_new(target, data, root)
        except Refusal as refusal:
            if refusal.code == "OUTPUT_EXISTS":
                raise Refusal("OFFER_EXISTS", "an offer with this job key already exists; nothing was overwritten")
            raise
        return {"ok": True, "message": "saved", "file": name, "sha256": canonical.sha256_text(data)}
    if mode != "update":
        raise Refusal("VALIDATION_FAILED", "unknown mode")
    target = offer_path(root, cfg, request.get("file"))
    raw = read_bytes(target)
    if raw is None:
        raise Refusal("FILE_UNREADABLE", "the offer does not exist")
    expected = request.get("expected_sha256")
    if canonical.sha256_text(raw) != expected:
        raise Refusal("CONFLICT", "the file changed since it was read; reload before saving")
    if len(raw) > FILE_LIMIT:
        raise Refusal("FILE_NOT_EDITABLE", "the offer is larger than 1 MB")
    before = joboffer.check_bytes(raw)
    if before.errors:
        raise Refusal("FILE_NOT_EDITABLE", "the offer is already invalid; fix it before editing here", problems(before.errors))
    original = docvalidate.load(raw, "OFFER_")
    if isinstance(form, dict) and "job_key" in form and clean(form["job_key"]) != original.get("job_key"):
        raise Refusal("VALIDATION_FAILED", "the job key identifies the offer and cannot be changed")
    document = build_offer_document(form, original)
    if document == original:
        raise Refusal("NO_CHANGE", "nothing changed")
    data = _offer_bytes(document, raw.startswith(BOM))
    touched = set(form)

    def verify(candidate):
        _check_document_bytes(candidate)
        saved = docvalidate.load(candidate, "OFFER_")
        for key in original:
            if key not in touched and key != "description_sha256" and saved.get(key) != original[key]:
                raise Refusal("VALIDATION_FAILED", "unexpected change to `%s`; save cancelled" % key)

    atomic_replace(target, data, expected, verify, root)
    return {"ok": True, "message": "saved", "file": target.name, "sha256": canonical.sha256_text(data)}


def op_offer_delete(request):
    root = request.get("root")
    cfg, _ = locate(root, ())
    target = offer_path(root, cfg, request.get("file"))
    with workspace_lock(root):
        raw = read_bytes(target)
        if raw is None:
            raise Refusal("FILE_UNREADABLE", "the offer does not exist")
        if canonical.sha256_text(raw) != request.get("expected_sha256"):
            raise Refusal("CONFLICT", "the file changed since it was read; reload before deleting")
        if request.get("confirm") != target.name[:-5]:
            raise Refusal("CONFIRMATION_REQUIRED", "type the offer file name to confirm the deletion")
        try:
            os.unlink(str(target))
        except OSError as error:
            raise Refusal("WRITE_FAILED", "cannot delete the file: %s" % error.strerror)
    return {"ok": True, "message": "deleted", "file": target.name}


def op_offer_import(request):
    """Read a file chosen by the user (read-only). JobOffer-v1 JSON is copied into the offers folder; text is returned."""
    root = request.get("root")
    cfg, _ = locate(root, ())
    source = request.get("source")
    if not isinstance(source, str) or not Path(source).is_file():
        raise Refusal("FILE_UNREADABLE", "the chosen file does not exist")
    suffix = Path(source).suffix.lower()
    if suffix not in (".json", ".txt", ".md"):
        raise Refusal("UNSUPPORTED_FILE", "only JobOffer-v1 .json files and .txt or .md descriptions can be imported")
    if Path(source).stat().st_size > FILE_LIMIT:
        raise Refusal("UNSUPPORTED_FILE", "the file is larger than 1 MB")
    raw = Path(source).read_bytes()
    if suffix != ".json":
        try:
            text = canonical.decode_text(raw)
        except canonical.CanonicalError:
            raise Refusal("UNSUPPORTED_FILE", "the text file is not valid UTF-8")
        return {"ok": True, "kind": "text", "text": canonical.normalise_text(text)}
    result = _check_document_bytes(raw)
    name = result.offer.job_key + ".json"
    target = offer_path(root, cfg, name)
    folder = offers_folder(root, cfg)
    if not folder.is_dir():
        ensure_dir(root, cfg["offers_dir"])
    try:
        create_new(target, raw, root)
    except Refusal as refusal:
        if refusal.code == "OUTPUT_EXISTS":
            raise Refusal("OFFER_EXISTS", "an offer with this job key already exists; nothing was overwritten")
        raise
    return {"ok": True, "kind": "offer", "file": name, "sha256": canonical.sha256_text(raw)}


# --------------------------------------------------------------------------- engine inputs

def _stage(stage, items):
    details = [dict(p, file=stage) for p in problems(items)]
    unreadable = any(p["code"].endswith("FILE_UNREADABLE") for p in details)
    raise Refusal("INPUT_UNREADABLE" if unreadable else "INPUT_INVALID",
                  "the %s of the workspace is not usable: the engine stops at the first invalid stage" % stage, details)


def load_inputs(root):
    cfg, files = locate(root, ("facts", "profile", "content"))
    loaded_facts = facts.check_file(files["facts"])
    if loaded_facts.errors:
        _stage("facts", loaded_facts.errors)
    loaded_profile = profile.check_file(files["profile"], loaded_facts.factbase)
    if loaded_profile.errors:
        _stage("profile", loaded_profile.errors)
    found_profile = loaded_profile.profile
    loaded_taxonomy = taxonomy.load(found_profile.internal_preferences()["taxonomy"], Path(root))
    if loaded_taxonomy.errors:
        _stage("taxonomy", loaded_taxonomy.errors)
    loaded_content = content.check_file(files["content"], loaded_facts.factbase, found_profile)
    if loaded_content.errors:
        _stage("content", loaded_content.errors)
    return {"cfg": cfg, "files": files, "factbase": loaded_facts.factbase, "profile": found_profile,
            "taxonomy": loaded_taxonomy.taxonomy, "content": loaded_content.content}


def load_offer(root, cfg, name):
    path = offer_path(root, cfg, name)
    raw = read_bytes(path)
    if raw is None:
        raise Refusal("FILE_UNREADABLE", "the offer does not exist")
    result = joboffer.check_bytes(raw)
    if result.errors:
        _stage("offer", result.errors)
    return result.offer, path


def _texts(model, language):
    """Display texts of the user's own, already-written lines, keyed like the plan keys them."""
    texts = {}
    for block in model.get("blocks", []):
        heading = block.get("heading", {}).get(language) or {}
        texts["block:" + block["id"]] = heading.get("title")
        for bullet in block.get("bullets", []):
            texts["bullet:" + bullet["id"]] = (bullet.get("text") or {}).get(language)
    for category in model.get("skills", []):
        for item in category.get("items", []):
            texts["skill:" + item["id"]] = (item.get("text") or {}).get(language)
    return texts


def op_adapt_options(request):
    root = request.get("root")
    inputs = load_inputs(root)
    offer, _ = load_offer(root, inputs["cfg"], request.get("file")) if request.get("file") else (None, None)
    content_languages = set(inputs["content"].languages)
    families = []
    for family_id, family in sorted(inputs["profile"].families.items()):
        families.append({"id": family_id, "label": family.get("label"),
                         "languages": [l for l in family["languages"] if l in content_languages and l in inputs["profile"].languages],
                         "page_target": family.get("page_target")})
    out = {"ok": True, "families": families, "default_language": inputs["profile"].default_language}
    if offer is not None:
        language, method = offer.resolve_language(inputs["profile"].default_language)
        out["offer_language"] = {"language": language, "method": method, "declared": offer.declared_language}
    return out


def _build(root, request):
    inputs = load_inputs(root)
    offer, offer_file = load_offer(root, inputs["cfg"], request.get("offer_file"))
    try:
        result, matrix = planmod.build_plan(offer, inputs["taxonomy"], inputs["profile"], inputs["factbase"],
                                            inputs["content"], request.get("family") or None, request.get("language") or None)
    except planmod.PlanError as error:
        raise Refusal("PLAN_REFUSED", "the engine refuses to build this plan", problems(error.errors))
    return inputs, offer, offer_file, result, matrix


def op_matrix(request):
    inputs, offer, _, result, matrix = _build(request.get("root"), request)
    language = matrix["language"]
    return {"ok": True, "matrix": matrix, "matrix_sha256": result["inputs"]["matrix_sha256"],
            "texts": _texts(inputs["content"].to_model(), language), "job": {"title": offer.to_model()["title"], "company": offer.to_model()["company"]}}


def _free_name(folder, base, suffixes, on_exists):
    def taken(candidate):
        return any(os.path.lexists(str(folder / (candidate + s))) for s in suffixes)

    if not taken(base):
        return base
    if on_exists != "new_name":
        raise Refusal("OUTPUT_EXISTS", "a file with this name already exists; nothing was overwritten",
                      [{"code": "SUGGESTED_NAME", "message": _free_candidate(folder, base, suffixes), "path": None}])
    return _free_candidate(folder, base, suffixes)


def _free_candidate(folder, base, suffixes):
    for n in range(2, 1000):
        candidate = "%s-%d" % (base, n)
        if not any(os.path.lexists(str(folder / (candidate + s))) for s in suffixes):
            return candidate
    raise Refusal("OUTPUT_EXISTS", "no free output name could be found")


def _base_name(request, default):
    name = request.get("name")
    if name in (None, ""):
        name = default
    name = str(name)
    for suffix in (".json", ".tex", ".pdf"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    if not BASE_NAME.match(name):
        raise Refusal("VALIDATION_FAILED", "the name may only use letters, digits, dots, dashes and underscores")
    return name


def op_plan(request):
    root = request.get("root")
    inputs, offer, offer_file, result, matrix = _build(root, request)
    language = result["language"]
    out = {"ok": True, "plan": result, "matrix": matrix, "texts": _texts(inputs["content"].to_model(), language),
           "provenance": provenance_info(root, inputs, offer_file), "written": None}
    if request.get("write") is True:
        folder = ensure_dir(root, PLANS_DIR)
        base = _base_name(request, "%s.%s.%s" % (offer.job_key, result["family"], language))
        base = _free_name(folder, base, (".json",), request.get("on_exists"))
        data = dumps(result)
        create_new(folder / (base + ".json"), data, root)
        out["written"] = {"file": base + ".json", "sha256": canonical.sha256_text(data)}
    return out


def op_plans_list(request):
    cfg, _ = locate(request.get("root"), ())
    folder = Path(request["root"]) / PLANS_DIR
    out = {"ok": True, "plans": []}
    if not folder.is_dir() or folder.is_symlink():
        return out
    for path in sorted(folder.glob("*.json"))[:LIST_LIMIT]:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            continue
        entry = {"file": path.name, "valid": False}
        try:
            document = assemble.load_plan(path.read_bytes())
            assemble.check_shape(document)
            assemble.check_fingerprint(document)
            entry.update(valid=True, family=document["family"], language=document["language"],
                         job_key=(document.get("offer") or {}).get("job_key"), plan_sha256=document["plan_sha256"])
        except assemble.AssemblyError as error:
            entry["errors"] = problems(error.errors)
        out["plans"].append(entry)
    return out


def op_plan_read(request):
    root = request.get("root")
    locate(root, ())
    path = workspace_file(root, request.get("file"), PLANS_DIR)
    raw = read_bytes(path)
    if raw is None:
        raise Refusal("FILE_UNREADABLE", "the plan does not exist")
    try:
        document = assemble.load_plan(raw)
        assemble.check_shape(document)
        assemble.check_fingerprint(document)
    except assemble.AssemblyError as error:
        raise Refusal("PLAN_INVALID", "this file is not a valid tailoring plan", problems(error.errors))
    return {"ok": True, "plan": document, "file": path.name}


# --------------------------------------------------------------------------- provenance (information only)

def provenance_info(root, inputs, offer_file):
    """Whether the sources match a verifiable commit of the workspace repository.

    Plans, assemblies and `.tex` files do not need it. A package (a later step) does: this is why it is shown. Nothing is
    ever committed here."""
    names = [relative_posix(root, p) for p in inputs["files"].values()] + [relative_posix(root, offer_file)]
    try:
        commit = provenance.resolve_source_commit(root, names)
        return {"status": "VERIFIED", "commit": commit}
    except provenance.SourceProvenanceError as error:
        return {"status": "UNVERIFIED", "code": error.status, "reason": error.reason, "path": error.path, "message": str(error)[:300]}


def op_provenance(request):
    root = request.get("root")
    inputs = load_inputs(root)
    offer, offer_file = load_offer(root, inputs["cfg"], request.get("offer_file"))
    return {"ok": True, "provenance": provenance_info(root, inputs, offer_file)}


# --------------------------------------------------------------------------- assemble / render

def _assembly(root, request):
    inputs = load_inputs(root)
    offer, offer_file = load_offer(root, inputs["cfg"], request.get("offer_file"))
    plan_path = workspace_file(root, request.get("plan_file"), PLANS_DIR)
    raw = read_bytes(plan_path)
    if raw is None:
        raise Refusal("FILE_UNREADABLE", "the plan does not exist")
    try:
        document = assemble.load_plan(raw)
        assembly = assemble.assemble(document, offer, inputs["taxonomy"], inputs["profile"], inputs["factbase"], inputs["content"])
    except assemble.AssemblyError as error:
        raise Refusal("ASSEMBLY_REFUSED", "the engine refuses to assemble this plan against the current sources", problems(error.errors))
    return inputs, offer, offer_file, assembly


def op_assemble(request):
    _, _, _, assembly = _assembly(request.get("root"), request)
    return {"ok": True, "assembly": assembly, "outline": assemble.outline(assembly)}


def op_latex_status(request):
    return dict(pdf.environment(), ok=True, optional_dependency=True)


def op_render(request):
    root = request.get("root")
    inputs, offer, offer_file, assembly = _assembly(root, request)
    paper = request.get("paper") or latex.DEFAULT_PAPER
    try:
        text = latex.render(assembly, paper)
    except latex.RenderError as error:
        raise Refusal("RENDER_REFUSED", "the engine refuses to render this assembly", problems(error.errors))
    data = latex.tex_bytes(text)
    folder = ensure_dir(root, OUT_DIR)
    compile_pdf = request.get("compile") is True
    default = "%s.%s.%s" % (offer.job_key, assembly["family"], assembly["language"])
    base = _base_name(request, default)
    suffixes = (".tex", ".pdf") if compile_pdf else (".tex",)
    base = _free_name(folder, base, suffixes, request.get("on_exists"))
    create_new(folder / (base + ".tex"), data, root)
    report = {
        "ok": True, "ready_to_send": False, "review": "NOT_REVIEWED", "template": latex.TEMPLATE_ID, "paper": paper,
        "plan_sha256": assembly["source"]["plan_sha256"], "assembly_sha256": assembly["assembly_sha256"],
        "tex": {"file": OUT_DIR + "/" + base + ".tex", "bytes": len(data), "sha256": latex.tex_sha256(data)},
        "pdf": {"status": "NOT_REQUESTED"},
        "layout": {"page_target": assembly["layout"]["page_target"], "pages": None,
                   "page_verdict": pdf.page_verdict(assembly["layout"]["page_target"], None)},
        "pending_directives": len(assembly["pending_directives"]), "warnings": [w["code"] for w in assembly["warnings"]],
    }
    if compile_pdf:
        timeout = request.get("timeout", 60)
        try:
            result = pdf.compile_tex(data, timeout if isinstance(timeout, int) and not isinstance(timeout, bool) else 60)
        except pdf.PdfError as error:
            unavailable = error.code == "PDF_UNAVAILABLE"
            report["pdf"] = {"status": "UNAVAILABLE" if unavailable else "FAILED", "code": error.code, "details": error.details,
                             "message": error.errors[0].message}
        else:
            create_new(folder / (base + ".pdf"), result.pdf, root)
            report["pdf"] = {"status": "COMPILED", "file": OUT_DIR + "/" + base + ".pdf", "bytes": len(result.pdf),
                             "pages": result.pages, "sha256": result.pdf_sha256}
            report["layout"]["pages"] = result.pages
            report["layout"]["page_verdict"] = pdf.page_verdict(assembly["layout"]["page_target"], result.pages)
    return report


def op_outputs_list(request):
    locate(request.get("root"), ())
    folder = Path(request["root"]) / OUT_DIR
    out = {"ok": True, "files": []}
    if not folder.is_dir() or folder.is_symlink():
        return out
    for path in sorted(folder.iterdir())[:LIST_LIMIT]:
        if path.suffix in (".tex", ".pdf") and path.is_file() and not path.is_symlink():
            out["files"].append({"file": OUT_DIR + "/" + path.name, "bytes": path.stat().st_size, "kind": path.suffix[1:]})
    return out


OPERATIONS = {
    "offers_list": op_offers_list,
    "offer_read": op_offer_read,
    "offer_save": op_offer_save,
    "offer_delete": op_offer_delete,
    "offer_import": op_offer_import,
    "adapt_options": op_adapt_options,
    "matrix": op_matrix,
    "plan": op_plan,
    "plans_list": op_plans_list,
    "plan_read": op_plan_read,
    "provenance": op_provenance,
    "assemble": op_assemble,
    "latex_status": op_latex_status,
    "render": op_render,
    "outputs_list": op_outputs_list,
}
