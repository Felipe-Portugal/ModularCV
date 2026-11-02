"""Workspace configuration.

A workspace is the directory holding *your* data: the fact base, the master CV, the
baselines and the applications. It is resolved from, in order: an explicit argument, the
`MODULARCV_ROOT` environment variable, the current directory. An optional
`modularcv.json` at its root overrides the defaults below.
"""
import json
import os
from pathlib import Path

from . import paths

ROOT_ENV = "MODULARCV_ROOT"
CONFIG_NAME = "modularcv.json"

DEFAULTS = {
    # The single source of professional facts. Nothing may be claimed outside of it.
    "facts": "facts.md",
    # Files a generated document is built from; a generation must match one real commit.
    "provenance_files": [],
    # Registry of packages that were superseded or recalibrated.
    "staleness_registry": "packages/package-staleness.json",
    # Directory holding the secondary index of packages.
    "packages_dir": "packages",
    # Tree that holds the CV metadata of applications; a package may not point outside of it.
    "applications_dir": "applications",
}


class ConfigError(ValueError):
    """`modularcv.json` exists but cannot be used."""


def workspace_root(root=None) -> Path:
    if root is not None:
        return Path(root)
    configured = os.environ.get(ROOT_ENV, "").strip()
    return Path(configured) if configured else Path.cwd()


def load(root=None) -> dict:
    """Defaults merged with `modularcv.json`; unknown keys are refused, not ignored."""
    root = workspace_root(root)
    config = dict(DEFAULTS)
    path = root / CONFIG_NAME
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise ConfigError("%s is not valid JSON: %s" % (path, error))
        if not isinstance(data, dict):
            raise ConfigError("%s must hold a JSON object" % path)
        unknown = sorted(set(data) - set(DEFAULTS))
        if unknown:
            raise ConfigError("Unknown keys in %s: %s" % (path, ", ".join(unknown)))
        config.update(data)
    if not isinstance(config["provenance_files"], list):
        raise ConfigError("provenance_files must be a list of relative paths")
    for key in ("facts", "staleness_registry", "packages_dir", "applications_dir"):
        if not isinstance(config[key], str) or paths.relative_path_problem(config[key]):
            raise ConfigError("%s must be a safe relative path inside the workspace" % key)
    for name in config["provenance_files"]:
        if paths.relative_path_problem(name):
            raise ConfigError("provenance_files holds an unsafe path: %r" % (name,))
    config["root"] = root
    return config


def provenance_files(root=None) -> tuple:
    """Files a generation is built from: the configured ones plus the fact base."""
    config = load(root)
    names = list(config["provenance_files"])
    if config["facts"] not in names:
        names.append(config["facts"])
    return tuple(names)
