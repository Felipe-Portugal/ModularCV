"""Location of an external source of input documents (for example a job-scraper export).

Nothing in this library may assume a machine-specific absolute path. The directory is
read from the `MODULARCV_HANDOFF_DIR` environment variable or passed explicitly. An absent
source is a diagnostic (`HandoffSourceUnavailable`), never an empty result: a missing
dependency must never look like a success.
"""
import os
from pathlib import Path

ENV_VAR = "MODULARCV_HANDOFF_DIR"


class HandoffSourceUnavailable(RuntimeError):
    """The external directory is not configured or does not exist."""


def handoff_root(explicit=None) -> Path:
    configured = str(explicit) if explicit else os.environ.get(ENV_VAR, "").strip()
    if not configured:
        raise HandoffSourceUnavailable(
            "No external input directory configured. Set %s or pass the directory explicitly."
            % ENV_VAR)
    path = Path(configured)
    if not path.is_dir():
        raise HandoffSourceUnavailable(
            "External input directory not found: %s (set via %s)" % (path, ENV_VAR))
    return path


def private_data_available() -> bool:
    try:
        handoff_root()
    except HandoffSourceUnavailable:
        return False
    return True
