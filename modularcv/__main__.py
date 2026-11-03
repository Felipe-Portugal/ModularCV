"""Command line: `python -m modularcv <command>`.

    provenance            print the verified source commit of the workspace
    provenance --verify SHA [--recorded]   check one commit against the provenance policy
    check-packages DIR    read-only fail-closed audit of application packages
                          (exit 0 clean, 1 contradiction, 2 incomplete audit or bad configuration)
    snapshot verify FILE  read-only check of a SourceSnapshot-v1 (exit 0 consistent, 1 problems, 2 unreadable)
    facts check [FILE]    validate a FactBase-v1 file (exit 0 valid, 1 invalid, 2 unreadable)
    facts fingerprint [FILE]   print the source and canonical fingerprints of a valid fact base
    facts import --mapping MAP --in LEGACY [--out F --report R] [--dry-run] [--allow-partial]
                          controlled import of a historical document (exit 0 complete, 1 incomplete, 2 refused)
    profile check [FILE]  validate a Profile-v1 and its fact references (exit 0 valid and verified, 1 invalid,
                          2 unreadable, 3 structurally valid but fact references left UNVERIFIED)
    profile fingerprint [FILE]   print the source and canonical fingerprints of a valid profile
    content check [FILE]  validate a ResumeContent-v1 and verify its fact references (exit 0 valid and verified,
                          1 invalid, 2 unreadable, 3 structurally valid but fact references left UNVERIFIED)
    content fingerprint [FILE]   print the source and canonical fingerprints of a valid content file
    offer check|fingerprint FILE   validate a JobOffer-v1 and list the requirements found in it (exit 0, 1 invalid, 2 unreadable)
    taxonomy check|fingerprint [SPEC]   validate a Taxonomy-v1 (default builtin:generic-v1)
    matrix --offer FILE [--family F] [--language L] [--out F]   the RequirementMatrix-v1 of an offer (exit 0, 1 refused, 2 unreadable)
    plan --offer FILE [--family F] [--language L] [--out F]     the TailoringPlan-v1 (a plan, never a ready CV)
    assemble --plan P --offer FILE [--outline] [--out F.json]   verify the plan, then the structured CV it describes
    render --plan P --offer FILE [--out F.tex [--pdf F.pdf [--log F.log]]] [--paper P] [--timeout S]
                          generic LaTeX of the verified plan; exit 0 done, 1 refused, 2 unreadable or output refused,
                          4 .tex written but pdflatex absent, 5 .tex written but the compilation failed
    latex check           is the optional pdflatex available (exit 0 found, 1 absent)
    privacy ...           scan a tree for personal data before publishing
"""
from argparse import ArgumentParser
import json
import os
import sys
from pathlib import Path

from . import (assemble, config, content, docvalidate, facts, joboffer, latex, legacy, pdf, plan, privacy, profile, provenance,
               readiness, snapshot, taxonomy)


def _facts_report(name, result):
    """Machine-readable result of `facts check`. Never contains the text of a fact."""
    base = result.factbase
    return {
        "status": "OK" if not result.errors else "INVALID",
        "file": name,
        "fact_count": len(base.facts) if base else None,
        "counts": base.counts() if base else None,
        "publishable": len(base.publishable()) if base else None,
        "facts_source_sha256": result.facts_source_sha256,
        "factbase_sha256": base.factbase_sha256 if base else None,
        "errors": [error.as_dict() for error in result.errors],
        "warnings": [warning.as_dict() for warning in result.warnings],
    }


def _facts_main(args) -> int:
    if args.facts_command == "import":
        return _import_main(args)
    try:
        if args.file is None:
            name = config.load(args.root)["facts"]
            path = config.workspace_root(args.root) / name
        else:
            name, path = args.file, args.file
    except config.ConfigError as error:
        print(json.dumps({"status": "CONFIG_ERROR", "detail": str(error)}), file=sys.stderr)
        return 2
    require_date = args.require_confirmation_date
    if getattr(args, "use_profile", False):
        try:
            profile_path = config.workspace_root(args.root) / config.load(args.root)["profile"]
        except config.ConfigError as error:
            print(json.dumps({"status": "CONFIG_ERROR", "detail": str(error)}), file=sys.stderr)
            return 2
        loaded = profile.check_file(profile_path)
        if loaded.errors:
            _print_problems("profile", loaded.errors)
            return 2
        require_date = require_date or loaded.profile.require_confirmation_date
    result = facts.check_file(path, require_date)
    report = _facts_report(name, result)
    for error in result.errors:
        where = name if error.line is None else "%s:%d" % (name, error.line)
        print("%s: %s: %s" % (where, error.code, error.message), file=sys.stderr)
    if any(error.code == "FACT_FILE_UNREADABLE" for error in result.errors):
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    only = getattr(args, "only", None)
    if args.facts_command == "fingerprint" and not result.errors and only:
        key = "facts_source_sha256" if only == "source" else "factbase_sha256"
        print(report[key])
        return 0
    if args.facts_command == "fingerprint" and not result.errors:
        report = {key: report[key] for key in ("status", "file", "fact_count", "facts_source_sha256", "factbase_sha256")}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if result.errors else 0


def _print_problems(name, problems):
    for problem in problems:
        where = getattr(problem, "path", None)
        if where is None and getattr(problem, "line", None) is not None:
            where = "line %d" % problem.line
        print("%s: %s (%s): %s" % (name, problem.code, where or "document", problem.message), file=sys.stderr)


PROFILE_UNVERIFIED_EXIT = 3


def _profile_unverified(result):
    """True when the profile is structurally valid but some fact reference was not checked against a fact base."""
    return not result.errors and any(w.code == "PROFILE_FACTS_NOT_CHECKED" for w in result.warnings)


def _profile_report(name, result, no_facts):
    """Machine-readable result of `profile check`. Holds field names and counts, never a value.

    `status` is `OK` only when nothing is left unchecked; a structure-only success is `UNVERIFIED`."""
    found = result.profile
    model = found.to_model() if found else None
    unchecked = any(w.code == "PROFILE_FACTS_NOT_CHECKED" for w in result.warnings)
    return {
        "status": "INVALID" if result.errors else ("UNVERIFIED" if unchecked else "OK"),
        "file": name,
        "profile_source_sha256": result.profile_source_sha256,
        "profile_sha256": found.profile_sha256 if found else None,
        "languages": list(found.languages) if found else None,
        "default_language": found.default_language if found else None,
        "identity_visibility": found.identity_visibility() if found else None,
        "counts": {key: len(model[key]) for key in ("families", "availability", "precedence_rules", "guidance")}
        if model else None,
        "facts_checked": not no_facts and not unchecked,
        "availability": [{"id": entry_id, "state": state} for entry_id, state in result.availability],
        "errors": [error.as_dict() for error in result.errors],
        "warnings": [warning.as_dict() for warning in result.warnings],
    }


def _profile_main(args) -> int:
    try:
        settings = config.load(args.root)
        root = config.workspace_root(args.root)
        name = args.file if args.file is not None else settings["profile"]
        path = args.file if args.file is not None else root / settings["profile"]
        facts_path = getattr(args, "facts", None) or root / settings["facts"]
    except config.ConfigError as error:
        print(json.dumps({"status": "CONFIG_ERROR", "detail": str(error)}), file=sys.stderr)
        return 2
    result = profile.check_file(path)
    no_facts = getattr(args, "no_facts", False)
    needs_facts = any(w.code == "PROFILE_FACTS_NOT_CHECKED" for w in result.warnings)
    if not result.errors and needs_facts and not no_facts and args.profile_command == "check":
        loaded = facts.check_file(facts_path)
        if any(e.code == "FACT_FILE_UNREADABLE" for e in loaded.errors):
            print(json.dumps({"status": "FACTS_UNREADABLE", "detail": "the fact base cannot be read"}), file=sys.stderr)
            return 2
        if loaded.errors:
            result = result._replace(profile=None, errors=(docvalidate.Problem(
                "PROFILE_FACTS_INVALID", "the fact base is invalid, so fact references cannot be verified", ""),))
        else:
            result = profile.check_file(path, loaded.factbase)
    _print_problems(str(name), result.errors)
    if any(e.code == "PROFILE_FILE_UNREADABLE" for e in result.errors):
        return 2
    if args.profile_command == "fingerprint":
        if result.errors:
            return 1
        if args.only:
            print(result.profile_source_sha256 if args.only == "source" else result.profile.profile_sha256)
        else:
            print(json.dumps({"status": "OK", "file": str(name),
                              "profile_source_sha256": result.profile_source_sha256,
                              "profile_sha256": result.profile.profile_sha256}, indent=2, ensure_ascii=False))
        return 0
    print(json.dumps(_profile_report(str(name), result, no_facts), indent=2, ensure_ascii=False))
    if result.errors:
        return 1
    if _profile_unverified(result):
        _print_problems(str(name), result.warnings)
    return PROFILE_UNVERIFIED_EXIT if _profile_unverified(result) else 0


CONTENT_UNVERIFIED_EXIT = 3


def _content_unverified(result):
    """True when the content is structurally valid but its fact references were not checked against a fact base."""
    return not result.errors and any(w.code == "CONTENT_FACTS_NOT_CHECKED" for w in result.warnings)


def _content_outline(found, states):
    """Structure without any text: identifiers, languages, order and the state of each reference."""
    model = found.to_model()
    blocks = [{"id": block["id"], "section": block["section"], "order": block["order"],
               "languages": block["languages"], "protected": block["protected"],
               "heading_state": states.get(("heading", block["id"])),
               "bullets": [{"id": bullet["id"], "state": states.get(("bullet", bullet["id"]))}
                           for bullet in block["bullets"]]} for block in model["blocks"]]
    skills = [{"id": category["id"], "languages": sorted(category["title"]),
               "items": [{"id": item["id"], "state": states.get(("skill", item["id"]))} for item in category["items"]]}
              for category in model["skills"]]
    return {"sections": [section["id"] for section in model["sections"]], "blocks": blocks, "skills": skills,
            "baselines": [{"family": b["family"], "language": b["language"], "items": len(b["items"])}
                          for b in model["baselines"]]}


def _content_report(name, result, no_facts, profile_checked, outline):
    """Machine-readable result of `content check`. Holds identifiers and counts, never a text.

    `status` is `OK` only when nothing is left unchecked; a structure-only success is `UNVERIFIED`. Two things are
    never checked and are stated as such: the meaning of a text against its facts, and the FR/EN equivalence."""
    found = result.content
    unchecked = any(w.code == "CONTENT_FACTS_NOT_CHECKED" for w in result.warnings)
    states = {(kind, entity_id): state for kind, entity_id, state in result.references}
    tally = {"headings": {}, "bullets": {}, "skills": {}}
    for kind, _entity_id, state in result.references:
        bucket = tally[{"heading": "headings", "bullet": "bullets", "skill": "skills"}[kind]]
        bucket[state] = bucket.get(state, 0) + 1
    report = {
        "status": "INVALID" if result.errors else ("UNVERIFIED" if unchecked else "OK"),
        "file": name,
        "content_source_sha256": result.content_source_sha256,
        "content_sha256": found.content_sha256 if found else None,
        "languages": list(found.languages) if found else None,
        "counts": found.counts() if found else None,
        "facts_checked": not no_facts and not unchecked,
        "profile_checked": profile_checked,
        "references": tally if found else None,
        "parity": "by entity id, structure only",
        "semantic_equivalence_checked": False,
        "errors": [error.as_dict() for error in result.errors],
        "warnings": [warning.as_dict() for warning in result.warnings],
    }
    if outline and found:
        report["outline"] = _content_outline(found, states)
    return report


def _content_main(args) -> int:
    try:
        settings = config.load(args.root)
        root = config.workspace_root(args.root)
        name = args.file if args.file is not None else settings["content"]
        path = args.file if args.file is not None else root / settings["content"]
        facts_path = getattr(args, "facts", None) or root / settings["facts"]
    except config.ConfigError as error:
        print(json.dumps({"status": "CONFIG_ERROR", "detail": str(error)}), file=sys.stderr)
        return 2
    chosen_profile = None
    if getattr(args, "profile", None):
        loaded_profile = profile.check_file(args.profile)
        if loaded_profile.errors:
            _print_problems("profile", loaded_profile.errors)
            return 2
        chosen_profile = loaded_profile.profile
    no_facts = getattr(args, "no_facts", False)
    result = content.check_file(path, None, chosen_profile)
    if any(e.code == "CONTENT_FILE_UNREADABLE" for e in result.errors):
        _print_problems(str(name), result.errors)
        return 2
    if (not result.errors and args.content_command == "check" and not no_facts
            and any(w.code == "CONTENT_FACTS_NOT_CHECKED" for w in result.warnings)):
        loaded = facts.check_file(facts_path)
        if any(e.code == "FACT_FILE_UNREADABLE" for e in loaded.errors):
            print(json.dumps({"status": "FACTS_UNREADABLE", "detail": "the fact base cannot be read"}), file=sys.stderr)
            return 2
        if loaded.errors:
            result = result._replace(content=None, errors=(docvalidate.Problem(
                "CONTENT_FACTS_INVALID", "the fact base is invalid, so fact references cannot be verified", ""),))
        else:
            result = content.check_file(path, loaded.factbase, chosen_profile)
    _print_problems(str(name), result.errors)
    if args.content_command == "fingerprint":
        if result.errors:
            return 1
        if args.only:
            print(result.content_source_sha256 if args.only == "source" else result.content.content_sha256)
        else:
            print(json.dumps({"status": "OK", "file": str(name),
                              "content_source_sha256": result.content_source_sha256,
                              "content_sha256": result.content.content_sha256}, indent=2, ensure_ascii=False))
        return 0
    print(json.dumps(_content_report(str(name), result, no_facts, chosen_profile is not None, args.outline),
                     indent=2, ensure_ascii=False))
    if result.errors:
        return 1
    if _content_unverified(result):
        _print_problems(str(name), result.warnings)
        return CONTENT_UNVERIFIED_EXIT
    return 0


def _stage_failed(stage, problems):
    _print_problems(stage, problems)
    unreadable = any(p.code.endswith("FILE_UNREADABLE") or p.code == "FACT_FILE_UNREADABLE" for p in problems)
    return 2 if unreadable else 1


def _load_engine_inputs(args):
    """Load and strictly validate every input of the engine. Returns a dict, or an exit code (1 invalid, 2 unreadable).

    Nothing is trusted: the fact base is validated, the profile's fact references are verified against it, the content is
    checked against both, the taxonomy is the one the profile names. An invalid stage stops the run and is named."""
    try:
        settings = config.load(args.root)
        root = config.workspace_root(args.root)
    except config.ConfigError as error:
        print(json.dumps({"status": "CONFIG_ERROR", "detail": str(error)}), file=sys.stderr)
        return 2
    loaded_facts = facts.check_file(root / settings["facts"])
    if loaded_facts.errors:
        return _stage_failed("facts", loaded_facts.errors)
    loaded_profile = profile.check_file(root / settings["profile"], loaded_facts.factbase)
    if loaded_profile.errors:
        return _stage_failed("profile", loaded_profile.errors)
    found_profile = loaded_profile.profile
    loaded_taxonomy = taxonomy.load(found_profile.internal_preferences()["taxonomy"], root)
    if loaded_taxonomy.errors:
        return _stage_failed("taxonomy", loaded_taxonomy.errors)
    loaded_content = content.check_file(root / settings["content"], loaded_facts.factbase, found_profile)
    if loaded_content.errors:
        return _stage_failed("content", loaded_content.errors)
    loaded_offer = joboffer.check_file(args.offer)
    if loaded_offer.errors:
        return _stage_failed("offer", loaded_offer.errors)
    return {"root": root, "settings": settings, "factbase": loaded_facts.factbase, "profile": found_profile,
            "taxonomy": loaded_taxonomy.taxonomy, "content": loaded_content.content, "offer": loaded_offer.offer,
            "inputs": [root / settings[key] for key in ("facts", "profile", "content")] + [Path(args.offer)]}


def _write_new_output(root, value, protected):
    """Create `value` (inside the workspace, never over an existing file or one of the inputs). Returns the path or an exit code."""
    resolved, inside = _inside(root, value)
    if not inside or ".git" in resolved.relative_to(root.resolve()).parts:
        return _import_refusal("OUTPUT_OUTSIDE_WORKSPACE", "--out must be inside the workspace (and not in .git)")
    if any(_reaches_target(resolved, Path(item).resolve()) for item in protected):
        return _import_refusal("OUTPUT_IS_AN_INPUT", "--out designates one of the inputs of the engine")
    if os.path.lexists(str(resolved)):
        return _import_refusal("OUTPUT_EXISTS", "--out already exists; the engine never overwrites a file")
    return resolved


def _engine_main(args) -> int:
    loaded = _load_engine_inputs(args)
    if isinstance(loaded, int):
        return loaded
    try:
        result, matrix = plan.build_plan(loaded["offer"], loaded["taxonomy"], loaded["profile"], loaded["factbase"],
                                         loaded["content"], args.family, args.language)
    except plan.PlanError as error:
        _print_problems("plan", error.errors)
        return 1
    if args.command == "matrix":
        document = {"matrix": matrix, "matrix_sha256": result["inputs"]["matrix_sha256"]}
    else:
        document = result
    rendered = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out is None:
        print(rendered)
        return 0
    target = _write_new_output(loaded["root"], args.out, loaded["inputs"])
    if isinstance(target, int):
        return target
    try:
        with open(str(target), "xb") as handle:
            handle.write((rendered + "\n").encode("utf-8"))
    except OSError as error:
        return _import_refusal("OUTPUT_WRITE_FAILED", "cannot write the output: %s" % error.strerror)
    print(json.dumps({"status": "WRITTEN", "out": args.out,
                      "sha256_key": "matrix_sha256" if args.command == "matrix" else "plan_sha256",
                      "sha256": document.get("matrix_sha256") or document["plan_sha256"]}, indent=2))
    return 0


PDF_UNAVAILABLE_EXIT = 4
PDF_FAILED_EXIT = 5
PLAN_FILE_LIMIT = 8 * 1024 * 1024


def _read_plan_file(path):
    """The plan object, or an exit code (1 not a plan, 2 unreadable)."""
    try:
        with open(str(path), "rb") as handle:
            data = handle.read(PLAN_FILE_LIMIT + 1)
    except OSError:
        print("plan: ASSEMBLY_PLAN_FILE_UNREADABLE (document): the plan file cannot be read", file=sys.stderr)
        return 2
    if len(data) > PLAN_FILE_LIMIT:
        print("plan: ASSEMBLY_PLAN_TOO_LARGE (document): the plan file is too large", file=sys.stderr)
        return 1
    try:
        return assemble.load_plan(data)
    except assemble.AssemblyError as error:
        return _stage_failed("plan", error.errors)


def _output_targets(args, loaded, protected):
    """Validate every requested output path before anything is written: `{name: Path}`, or an exit code."""
    wanted = [("tex", args.out, ".tex"), ("pdf", args.pdf, ".pdf"), ("log", args.log, ".log")]
    targets = {}
    for name, value, suffix in wanted:
        if value is None:
            continue
        if not value.endswith(suffix):
            return _import_refusal("OUTPUT_BAD_EXTENSION", "--%s must end with %s" % ("out" if name == "tex" else name, suffix))
        target = _write_new_output(loaded["root"], value, protected)
        if isinstance(target, int):
            return target
        targets[name] = target
    paths = list(targets.values())
    if any(_same_target(paths[i], paths[j]) for i in range(len(paths)) for j in range(i + 1, len(paths))):
        return _import_refusal("OUTPUT_DUPLICATE", "the output files must be different files")
    return targets


def _write_bytes(path, data):
    try:
        with open(str(path), "xb") as handle:
            handle.write(data)
    except OSError as error:
        return _import_refusal("OUTPUT_WRITE_FAILED", "cannot write the output: %s" % error.strerror)
    return None


def _render_main(args) -> int:
    rendering = args.command == "render"
    if rendering and (args.pdf or args.log) and not args.out:
        return _import_refusal("OUTPUT_REQUIRED", "--pdf and --log need --out: the .tex file is the artefact a PDF comes from")
    if rendering and args.log and not args.pdf:
        return _import_refusal("OUTPUT_REQUIRED", "--log is the compiler log: it needs --pdf")
    loaded = _load_engine_inputs(args)
    if isinstance(loaded, int):
        return loaded
    plan_document = _read_plan_file(args.plan)
    if isinstance(plan_document, int):
        return plan_document
    try:
        assembly = assemble.assemble(plan_document, loaded["offer"], loaded["taxonomy"], loaded["profile"],
                                     loaded["factbase"], loaded["content"])
    except assemble.AssemblyError as error:
        _print_problems("assemble", error.errors)
        return 1
    protected = loaded["inputs"] + [Path(args.plan)]
    if not rendering:
        document = assemble.outline(assembly) if args.outline else assembly
        rendered = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True)
        if args.out is None:
            print(rendered)
            return 0
        if not args.out.endswith(".json"):
            return _import_refusal("OUTPUT_BAD_EXTENSION", "--out must end with .json")
        target = _write_new_output(loaded["root"], args.out, protected)
        if isinstance(target, int):
            return target
        failed = _write_bytes(target, (rendered + "\n").encode("utf-8"))
        if failed is not None:
            return failed
        print(json.dumps({"status": "WRITTEN", "out": args.out, "assembly_sha256": assembly["assembly_sha256"]}, indent=2))
        return 0
    try:
        text = latex.render(assembly, args.paper)
    except latex.RenderError as error:
        _print_problems("render", error.errors)
        return 1
    data = latex.tex_bytes(text)
    if args.out is None:
        sys.stdout.write(text)
        return 0
    targets = _output_targets(args, loaded, protected)
    if isinstance(targets, int):
        return targets
    failed = _write_bytes(targets["tex"], data)
    if failed is not None:
        return failed
    report = {
        "status": "WRITTEN", "ready_to_send": False, "review": "NOT_REVIEWED", "template": latex.TEMPLATE_ID, "paper": args.paper,
        "plan_sha256": assembly["source"]["plan_sha256"], "assembly_sha256": assembly["assembly_sha256"],
        "tex": {"out": args.out, "bytes": len(data), "sha256": latex.tex_sha256(data)},
        "pdf": {"status": "NOT_REQUESTED"},
        "layout": {"page_target": assembly["layout"]["page_target"], "pages": None,
                   "page_verdict": pdf.page_verdict(assembly["layout"]["page_target"], None)},
        "pending_directives": len(assembly["pending_directives"]), "warnings": [w["code"] for w in assembly["warnings"]],
    }
    exit_code = 0
    if args.pdf:
        report["pdf"] = {"status": "PENDING", "out": args.pdf}
        log_text = None
        try:
            result = pdf.compile_tex(data, args.timeout)
            log_text = result.log
        except pdf.PdfError as error:
            unavailable = error.code == "PDF_UNAVAILABLE"
            report["pdf"].update({"status": "UNAVAILABLE" if unavailable else "FAILED", "code": error.code,
                                  "details": error.details})
            report["pdf_compilation_validated"] = False
            _print_problems("pdf", error.errors)
            exit_code = PDF_UNAVAILABLE_EXIT if unavailable else PDF_FAILED_EXIT
            result = None
            log_text = error.log
        if result is not None:
            failed = _write_bytes(targets["pdf"], result.pdf)
            if failed is not None:
                return failed
            report["pdf"].update({"status": "COMPILED", "bytes": len(result.pdf), "pages": result.pages,
                                  "sha256": result.pdf_sha256, "byte_reproducible": False})
            report["layout"]["pages"] = result.pages
            report["layout"]["page_verdict"] = pdf.page_verdict(assembly["layout"]["page_target"], result.pages)
            report["pdf_compilation_validated"] = True
        if "log" in targets and log_text:
            failed = _write_bytes(targets["log"], log_text.encode("utf-8"))
            if failed is not None:
                return failed
            report["pdf"]["log"] = {"out": args.log, "may_contain_resume_text": True}
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


def _latex_main(args) -> int:
    environment = pdf.environment()
    print(json.dumps(dict(environment, optional_dependency=True, note="pdflatex is never installed by modularcv"), indent=2))
    return 0 if environment["pdflatex"] == "FOUND" else 1


def _offer_main(args) -> int:
    result = joboffer.check_file(args.file)
    if result.errors:
        return _stage_failed(str(args.file), result.errors)
    found = result.offer
    if args.offer_command == "fingerprint":
        if args.only:
            print(result.offer_source_sha256 if args.only == "source" else found.offer_sha256)
        else:
            print(json.dumps({"status": "OK", "offer_source_sha256": result.offer_source_sha256,
                              "offer_sha256": found.offer_sha256, "description_sha256": found.description_sha256},
                             indent=2))
        return 0
    try:
        root = config.workspace_root(args.root)
    except config.ConfigError as error:
        print(json.dumps({"status": "CONFIG_ERROR", "detail": str(error)}), file=sys.stderr)
        return 2
    loaded_taxonomy = taxonomy.load(args.taxonomy, root)
    if loaded_taxonomy.errors:
        return _stage_failed("taxonomy", loaded_taxonomy.errors)
    language, method = found.resolve_language(None)
    detected = []
    problems = []
    if language is not None:
        detected, problems = joboffer.extract_requirements(found, loaded_taxonomy.taxonomy, language)
    if problems:
        return _stage_failed("offer", problems)
    report = {
        "status": "OK" if language is not None else "LANGUAGE_UNDECIDED",
        "offer_source_sha256": result.offer_source_sha256, "offer_sha256": found.offer_sha256,
        "description_sha256": found.description_sha256, "job_key": found.job_key,
        "declared_language": found.declared_language, "language": language, "language_method": method,
        "employment_type": found.employment_type, "explicit_requirements": len(found.explicit_requirements),
        "requirements": [{"id": r["id"], "term_id": r["term_id"], "priority": r["priority"], "weight": r["weight"],
                          "sources": r["sources"]} for r in detected],
        "unknown_terms": sum(1 for r in detected if r["term_id"] is None),
        "taxonomy_sha256": loaded_taxonomy.taxonomy.taxonomy_sha256,
        "semantic_understanding": False,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if language is not None else 1


def _taxonomy_main(args) -> int:
    try:
        root = config.workspace_root(args.root)
    except config.ConfigError as error:
        print(json.dumps({"status": "CONFIG_ERROR", "detail": str(error)}), file=sys.stderr)
        return 2
    if args.spec.endswith(".json") and not args.spec.startswith("builtin:"):
        result = taxonomy.check_file(args.spec)
    else:
        result = taxonomy.load(args.spec, root)
    if result.errors:
        return _stage_failed("taxonomy", result.errors)
    found = result.taxonomy
    model = found.to_model()
    if args.taxonomy_command == "fingerprint":
        if args.only:
            print(found.taxonomy_sha256)
        else:
            print(json.dumps({"status": "OK", "id": found.id, "taxonomy_sha256": found.taxonomy_sha256}, indent=2))
        return 0
    print(json.dumps({
        "status": "OK", "id": found.id, "taxonomy_sha256": found.taxonomy_sha256,
        "taxonomy_source_sha256": result.taxonomy_source_sha256,
        "counts": {"capabilities": len(found.terms("capability")), "technologies": len(found.terms("technology")),
                   "zones": len(model["zones"]), "adjacencies": len(model["adjacencies"])},
    }, indent=2))
    return 0


def _inside(root, value):
    """The resolved path of `value` (relative to `root` when relative) and whether it lies inside `root`."""
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return resolved, False
    return resolved, True


def _same_target(path, other):
    """Whether two resolved paths name the same file, existing or not (case, short names, links in the parents)."""
    if os.path.normcase(str(path)) == os.path.normcase(str(other)):
        return True
    try:
        if path.exists() and other.exists() and os.path.samefile(str(path), str(other)):
            return True
        return (os.path.normcase(path.name) == os.path.normcase(other.name)
                and os.path.samefile(str(path.parent), str(other.parent)))
    except OSError:
        return False


def _reaches_target(path, other):
    """`_same_target`, also following a symbolic link at the end of `path` (resolve() leaves a dangling one alone on Windows)."""
    for _ in range(40):
        if _same_target(path, other):
            return True
        if not os.path.islink(str(path)):
            return False
        try:
            path = Path(os.path.join(os.path.dirname(str(path)), os.readlink(str(path)))).resolve()
        except (OSError, RuntimeError):
            return False
    return False


def _import_refusal(code, detail):
    print(json.dumps({"status": code, "detail": detail}), file=sys.stderr)
    return 2


def _import_main(args) -> int:
    try:
        root = config.workspace_root(args.root)
        fact_base = (root / config.load(args.root)["facts"]).resolve()
    except config.ConfigError as error:
        return _import_refusal("CONFIG_ERROR", str(error))
    if not args.dry_run and (args.out is None or args.report is None):
        return _import_refusal("IMPORT_OUTPUT_REQUIRED", "--out and --report are both required unless --dry-run is given")
    mapping_path, mapping_ok = _inside(root, args.mapping)
    if not mapping_ok:
        return _import_refusal("IMPORT_MAPPING_OUTSIDE_WORKSPACE", "the mapping file must live inside the workspace")
    legacy_path = _inside(root, args.legacy)[0]
    targets = {}
    for which, value in (("out", args.out), ("report", args.report)):
        if value is None:
            continue
        resolved, inside = _inside(root, value)
        if not inside or ".git" in resolved.relative_to(root.resolve()).parts:
            return _import_refusal("IMPORT_OUTPUT_OUTSIDE_WORKSPACE",
                                   "--%s must be inside the workspace (and not in .git)" % which)
        if _reaches_target(resolved, fact_base):
            return _import_refusal("IMPORT_OUTPUT_IS_FACT_BASE",
                                   "--%s designates the workspace's active fact base; write the proposal to a separate "
                                   "file and review it before it replaces the fact base" % which)
        if os.path.lexists(str(resolved)):  # a dangling symbolic link counts: writing would go through it
            return _import_refusal("IMPORT_OUTPUT_EXISTS",
                                   "--%s already exists; the import never overwrites a file" % which)
        targets[which] = resolved
    taken = [legacy_path, mapping_path] + list(targets.values())
    if len({os.path.normcase(str(item)) for item in taken}) != len(taken):
        return _import_refusal("IMPORT_PATH_CONFLICT",
                               "the legacy document, mapping, output and report must be different files")

    checked = legacy.check_mapping_file(mapping_path)
    if checked.errors:
        _print_problems("mapping", checked.errors)
        return _import_refusal("MAPPING_INVALID", "the mapping file is not a valid LegacyFactMap-v1")
    try:
        with open(str(legacy_path), "rb") as handle:
            data = handle.read()
    except OSError as error:
        return _import_refusal("LEGACY_FILE_UNREADABLE", "cannot read the legacy document: %s" % error.strerror)
    try:
        result = legacy.run(checked.mapping, data)
    except legacy.LegacyInputError as error:
        return _import_refusal(error.code, str(error))

    report = result.report
    exit_code = 0 if result.complete else 1
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.dry_run:
        print(rendered)
        return exit_code

    write_facts = result.facts_text is not None and (result.complete or args.allow_partial)
    created = []
    try:
        if write_facts:
            with open(str(targets["out"]), "xb") as handle:
                created.append(targets["out"])
                handle.write(result.facts_text.encode("utf-8"))
        with open(str(targets["report"]), "xb") as handle:
            created.append(targets["report"])
            handle.write((rendered + "\n").encode("utf-8"))
    except OSError as error:
        for leftover in created:
            try:
                os.remove(str(leftover))
            except OSError:
                pass
        return _import_refusal("IMPORT_WRITE_FAILED", "cannot write the outputs: %s" % error.strerror)
    summary = {
        "status": "COMPLETE" if result.complete else ("NOTHING_IMPORTED" if result.facts_text is None else "INCOMPLETE"),
        "facts_written": write_facts,
        "out": args.out if write_facts else None,
        "report": args.report,
        "counts": report["counts"],
        "problems": [{"line": e["line"], "code": e["code"], "decision": e["decision"]}
                     for e in report["lines"] if e["kind"] != "HEADING" and e["decision"] in legacy.PROBLEM_DECISIONS],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return exit_code



def _snapshot_main(args) -> int:
    try:
        document = json.loads(open(args.file, "rb").read().decode("utf-8-sig"))
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "SNAPSHOT_UNREADABLE", "detail": str(error)}), file=sys.stderr)
        return 2
    problems = snapshot.verify(document, config.workspace_root(args.root))
    report = {"status": "OK" if not problems else "INVALID",
              "problems": [dict(problem._asdict()) for problem in problems]}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if problems else 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "privacy":
        return privacy.main(argv[1:])
    parser = ArgumentParser(prog="modularcv")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("provenance", help="print the verified source commit")
    p.add_argument("--root", default=None)
    p.add_argument("--verify", metavar="SHA", default=None,
                   help="verify this commit instead of resolving HEAD")
    p.add_argument("--recorded", action="store_true",
                   help="with --verify: a document that already exists (working tree not compared)")
    c = sub.add_parser("check-packages", help="audit the effective status of packages")
    c.add_argument("directory")
    c.add_argument("--registry", default=None)
    c.add_argument("--root", default=None, help="the workspace (default: MODULARCV_ROOT or the current directory)")
    sn = sub.add_parser("snapshot", help="check a source snapshot")
    snsub = sn.add_subparsers(dest="snapshot_command", required=True)
    sv = snsub.add_parser("verify", help="verify a SourceSnapshot-v1 against the workspace")
    sv.add_argument("file")
    sv.add_argument("--root", default=None)
    f = sub.add_parser("facts", help="validate and fingerprint a FactBase-v1 file")
    fsub = f.add_subparsers(dest="facts_command", required=True)
    fc = fsub.add_parser("check", help="validate the fact base (exit 1 when invalid)")
    ff = fsub.add_parser("fingerprint", help="print the fingerprints of a valid fact base")
    for p in (fc, ff):
        p.add_argument("file", nargs="?", default=None, help="default: the `facts` file of the workspace")
        p.add_argument("--root", default=None)
        p.add_argument("--require-confirmation-date", action="store_true",
                       help="make `confirmed_on` mandatory on CONFIRMED facts")
        p.add_argument("--use-profile", action="store_true",
                       help="also apply `policy.require_confirmation_date` of the workspace profile")
    fi = fsub.add_parser("import", help="propose a FactBase-v1 from a historical document (see docs/IMPORT.md)")
    fi.add_argument("--mapping", required=True, help="LegacyFactMap-v1 file, inside the workspace")
    fi.add_argument("--in", dest="legacy", required=True, help="the historical document (only read)")
    fi.add_argument("--out", default=None, help="the proposed fact base to create (never overwritten)")
    fi.add_argument("--report", default=None, help="the line-by-line audit report to create (never overwritten)")
    fi.add_argument("--dry-run", action="store_true", help="classify and print the report; write nothing")
    fi.add_argument("--allow-partial", action="store_true",
                    help="write the accepted facts even if some lines are unclassified, ambiguous or rejected")
    fi.add_argument("--root", default=None)
    ff.add_argument("--only", choices=("source", "factbase"), default=None,
                    help="print only this hash, alone on one line")
    pr = sub.add_parser("profile", help="validate and fingerprint a Profile-v1 file")
    prsub = pr.add_subparsers(dest="profile_command", required=True)
    pc = prsub.add_parser("check", help="validate the profile and verify its fact references (exit 1 when invalid)")
    pf = prsub.add_parser("fingerprint", help="print the fingerprints of a valid profile")
    for p in (pc, pf):
        p.add_argument("file", nargs="?", default=None, help="default: the `profile` file of the workspace")
        p.add_argument("--root", default=None)
    pc.add_argument("--facts", default=None, help="fact base used to verify references (default: the workspace one)")
    pc.add_argument("--no-facts", action="store_true",
                    help="structure only: fact references are not verified, reported UNVERIFIED, exit 3")
    pf.add_argument("--only", choices=("source", "profile"), default=None, help="print only this hash")
    ct = sub.add_parser("content", help="validate and fingerprint a ResumeContent-v1 file")
    ctsub = ct.add_subparsers(dest="content_command", required=True)
    cc = ctsub.add_parser("check", help="validate the content and verify its fact references (exit 1 when invalid)")
    cf = ctsub.add_parser("fingerprint", help="print the fingerprints of a valid content file")
    for p in (cc, cf):
        p.add_argument("file", nargs="?", default=None, help="default: the `content` file of the workspace")
        p.add_argument("--root", default=None)
    cc.add_argument("--facts", default=None, help="fact base used to verify references (default: the workspace one)")
    cc.add_argument("--no-facts", action="store_true",
                    help="structure only: fact references are not verified, reported UNVERIFIED, exit 3")
    cc.add_argument("--profile", default=None, help="also check baseline families and the confirmation-date policy")
    cc.add_argument("--outline", action="store_true", help="add the structure (identifiers and states, no text)")
    cf.add_argument("--only", choices=("source", "content"), default=None, help="print only this hash")
    of = sub.add_parser("offer", help="validate and fingerprint a JobOffer-v1 file")
    ofsub = of.add_subparsers(dest="offer_command", required=True)
    oc = ofsub.add_parser("check", help="validate the offer and list the requirements found in it")
    ofp = ofsub.add_parser("fingerprint", help="print the fingerprints of a valid offer")
    for p in (oc, ofp):
        p.add_argument("file")
        p.add_argument("--root", default=None)
    oc.add_argument("--taxonomy", default=taxonomy.BUILTIN, help="taxonomy used to find requirements (default: builtin)")
    ofp.add_argument("--only", choices=("source", "offer"), default=None, help="print only this hash")
    tx = sub.add_parser("taxonomy", help="validate and fingerprint a Taxonomy-v1")
    txsub = tx.add_subparsers(dest="taxonomy_command", required=True)
    tc = txsub.add_parser("check", help="validate a taxonomy")
    tf = txsub.add_parser("fingerprint", help="print the fingerprint of a valid taxonomy")
    for p in (tc, tf):
        p.add_argument("spec", nargs="?", default=taxonomy.BUILTIN, help="builtin:generic-v1 or a .json file")
        p.add_argument("--root", default=None)
    tf.add_argument("--only", action="store_true", help="print the hash alone")
    for name, text in (("matrix", "build the requirement matrix of an offer"), ("plan", "build the tailoring plan of an offer")):
        e = sub.add_parser(name, help=text)
        e.add_argument("--offer", required=True, help="the JobOffer-v1 file")
        e.add_argument("--family", default=None, help="the profile family (required when the profile has several)")
        e.add_argument("--language", default=None, choices=("fr", "en"), help="override the language of the offer")
        e.add_argument("--out", default=None, help="write the result to a new file inside the workspace (never overwritten)")
        e.add_argument("--root", default=None)
    for name, text in (("assemble", "assemble the CV a verified tailoring plan describes (structured, no LaTeX)"),
                       ("render", "render a verified plan as a generic LaTeX file, optionally compiled to PDF")):
        e = sub.add_parser(name, help=text)
        e.add_argument("--plan", required=True, help="the TailoringPlan-v1 file written by `plan --out`")
        e.add_argument("--offer", required=True, help="the JobOffer-v1 file the plan was built for")
        e.add_argument("--out", default=None, help="write to a new file inside the workspace (never overwritten)")
        e.add_argument("--root", default=None)
        if name == "assemble":
            e.add_argument("--outline", action="store_true", help="identifiers and counts only, no text")
        else:
            e.add_argument("--pdf", default=None, help="also compile the .tex to this new .pdf (needs pdflatex)")
            e.add_argument("--log", default=None, help="keep the compiler log in this new .log file (it can quote the CV)")
            e.add_argument("--paper", choices=latex.PAPERS, default=latex.DEFAULT_PAPER)
            e.add_argument("--timeout", type=int, default=pdf.DEFAULT_TIMEOUT, help="compiler time limit in seconds")
    lt = sub.add_parser("latex", help="report whether the optional pdflatex dependency is available")
    ltsub = lt.add_subparsers(dest="latex_command", required=True)
    ltsub.add_parser("check", help="exit 0 when pdflatex is found, 1 when absent")
    sub.add_parser("privacy", help="scan for personal data (see: modularcv privacy --help)")
    args = parser.parse_args(argv)
    if args.command == "provenance":
        try:
            if args.verify is None:
                print(provenance.resolve_source_commit(args.root))
            elif args.recorded:
                print(provenance.verify_recorded_commit(args.verify, args.root))
            else:
                print(provenance.verify_source_commit(args.verify, args.root))
        except (provenance.SourceProvenanceError, config.ConfigError) as error:
            status = getattr(error, "status", "CONFIG_ERROR")
            print(json.dumps({"status": status, "detail": str(error)}), file=sys.stderr)
            return 2
        return 0
    if args.command == "check-packages":
        try:
            report = readiness.audit_directory(args.directory, args.registry, args.root)
        except (readiness.AuditError, config.ConfigError) as error:
            print(json.dumps({"status": getattr(error, "code", "CONFIG_ERROR"), "detail": str(error)}),
                  file=sys.stderr)
            return 2
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if report["contradictions"] else 0
    if args.command == "snapshot":
        return _snapshot_main(args)
    if args.command == "facts":
        return _facts_main(args)
    if args.command == "profile":
        return _profile_main(args)
    if args.command == "content":
        return _content_main(args)
    if args.command == "offer":
        return _offer_main(args)
    if args.command == "taxonomy":
        return _taxonomy_main(args)
    if args.command in ("matrix", "plan"):
        return _engine_main(args)
    if args.command in ("assemble", "render"):
        return _render_main(args)
    if args.command == "latex":
        return _latex_main(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
