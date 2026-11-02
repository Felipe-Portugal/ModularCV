"""Command line: `python -m modularcv <command>`.

    provenance            print the verified source commit of the workspace
    check-packages DIR    read-only fail-closed audit of application packages
    facts check [FILE]    validate a FactBase-v1 file (exit 0 valid, 1 invalid, 2 unreadable)
    facts fingerprint [FILE]   print the source and canonical fingerprints of a valid fact base
    privacy ...           scan a tree for personal data before publishing
"""
from argparse import ArgumentParser
import json
import sys

from . import config, facts, privacy, provenance, readiness


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
    try:
        if args.file is None:
            name = config.load(args.root)["facts"]
            path = config.workspace_root(args.root) / name
        else:
            name, path = args.file, args.file
    except config.ConfigError as error:
        print(json.dumps({"status": "CONFIG_ERROR", "detail": str(error)}), file=sys.stderr)
        return 2
    result = facts.check_file(path, args.require_confirmation_date)
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


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "privacy":
        return privacy.main(argv[1:])
    parser = ArgumentParser(prog="modularcv")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("provenance", help="print the verified source commit")
    p.add_argument("--root", default=None)
    c = sub.add_parser("check-packages", help="audit the effective status of packages")
    c.add_argument("directory")
    c.add_argument("--registry", default=None)
    f = sub.add_parser("facts", help="validate and fingerprint a FactBase-v1 file")
    fsub = f.add_subparsers(dest="facts_command", required=True)
    fc = fsub.add_parser("check", help="validate the fact base (exit 1 when invalid)")
    ff = fsub.add_parser("fingerprint", help="print the fingerprints of a valid fact base")
    for p in (fc, ff):
        p.add_argument("file", nargs="?", default=None, help="default: the `facts` file of the workspace")
        p.add_argument("--root", default=None)
        p.add_argument("--require-confirmation-date", action="store_true",
                       help="make `confirmed_on` mandatory on CONFIRMED facts")
    ff.add_argument("--only", choices=("source", "factbase"), default=None,
                    help="print only this hash, alone on one line")
    sub.add_parser("privacy", help="scan for personal data (see: modularcv privacy --help)")
    args = parser.parse_args(argv)
    if args.command == "provenance":
        try:
            print(provenance.resolve_source_commit(args.root))
        except provenance.SourceProvenanceError as error:
            print(json.dumps({"status": error.status, "detail": str(error)}), file=sys.stderr)
            return 2
        return 0
    if args.command == "check-packages":
        report = readiness.audit_directory(args.directory, args.registry)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if report["contradictions"] else 0
    if args.command == "facts":
        return _facts_main(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
