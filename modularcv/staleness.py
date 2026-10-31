"""Registry of application packages that were superseded or materially recalibrated.

A stale package is never edited, moved or deleted: it is listed in the registry, which
the promotion check (`readiness`) consults. Entries are keyed by package fingerprint and
by tailored-CV identity.
"""
from datetime import datetime, timezone
import json
from pathlib import Path

from . import config

REGISTRY_VERSION = "StalePackageRegistry-v1"


def registry_path(root=None) -> Path:
    cfg = config.load(root)
    return cfg["root"] / cfg["staleness_registry"]


def load(path) -> dict:
    path = Path(path)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"registry_version": REGISTRY_VERSION, "packages": []}


def mark(package: dict, reason: str, superseded_by_tailored_cv_id: str, path) -> dict:
    """Record `package` (a parsed package.json) as stale."""
    registry = load(path)
    entry = {"job_id": package["application"]["job_id"],
             "package_fingerprint": package["package_fingerprint"],
             "tailored_cv_id": package["artifacts"]["cv"]["tailored_cv_id"],
             "superseded_by_tailored_cv_id": superseded_by_tailored_cv_id,
             "reason": reason, "status": "STALE",
             "recorded_at": datetime.now(timezone.utc).isoformat()}
    registry["packages"] = [p for p in registry["packages"]
                            if p["package_fingerprint"] != entry["package_fingerprint"]]
    registry["packages"].append(entry)
    registry["packages"].sort(key=lambda p: (str(p["job_id"]), p["recorded_at"]))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(registry, indent=2, sort_keys=True, ensure_ascii=False),
                          encoding="utf-8")
    return entry
