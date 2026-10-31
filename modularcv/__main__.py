"""Command line: `python -m modularcv <command>`.

    provenance            print the verified source commit of the workspace
    check-packages DIR    read-only fail-closed audit of application packages
    privacy ...           scan a tree for personal data before publishing
"""
from argparse import ArgumentParser
import json
import sys

from . import config, privacy, provenance, readiness


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
