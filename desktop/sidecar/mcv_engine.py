"""Entry point of the embedded engine (PyInstaller sidecar of ModularCV Desktop).

A closed set of modes, nothing else:

    mcv-engine adapter                      structured operations: JSON request on stdin, JSON answer on stdout
    mcv-engine cli facts check --root DIR   the engine's own `facts check`
    mcv-engine diagnose [--root DIR]        environment diagnostics (read-only)
    mcv-engine version                      engine version

No arbitrary command, module or script can be run through it. The engine (`modularcv`) is bundled unchanged.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for extra in (os.path.join(HERE, "..", "adapter"), os.path.join(HERE, "..", "..")):   # development runs from the repository
    if os.path.isdir(extra):
        sys.path.insert(0, os.path.abspath(extra))


def main(args):
    mode = args[0] if args else ""
    if mode == "adapter" and len(args) == 1:
        from mcv_adapter import main as adapter_main
        return adapter_main()
    if mode == "cli" and args[1:4] == ["facts", "check", "--root"] and len(args) == 5:
        from modularcv.__main__ import main as cli_main
        return cli_main(["facts", "check", "--root", args[4]])
    if mode == "diagnose" and len(args) in (1, 3):
        from mcv_diag import main as diag_main
        return diag_main(args[1:])
    if mode == "version" and len(args) == 1:
        from modularcv import __version__
        sys.stdout.write(json.dumps({"engine": __version__}))
        return 0
    sys.stderr.write(json.dumps({"status": "OPERATION_NOT_ALLOWED", "detail": "unknown mode"}))
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
