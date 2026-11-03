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
    privacy ...           scan a tree for personal data before publishing
"""
from argparse import ArgumentParser
import json
import os
import sys
from pathlib import Path

from . import config, docvalidate, facts, legacy, privacy, profile, provenance, readiness, snapshot


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
        print("%s: %s (%s): %s" % (name, problem.code, problem.path or "document", problem.message), file=sys.stderr)


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


def _import_refusal(code, detail):
    print(json.dumps({"status": code, "detail": detail}), file=sys.stderr)
    return 2


def _import_main(args) -> int:
    try:
        root = config.workspace_root(args.root)
        config.load(args.root)
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
        if resolved.exists():
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
