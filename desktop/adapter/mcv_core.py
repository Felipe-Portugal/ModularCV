"""Shared helpers of the Desktop adapter: engine path, refusals, workspace lookup, safe writes.

Nothing here adds a business rule; it only locates files inside the workspace and writes them safely.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ENGINE = os.environ.get("MODULARCV_ENGINE_DIR") or str(Path(__file__).resolve().parents[2])
sys.path.insert(0, ENGINE)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # `python -I` does not add the script folder

from modularcv import canonical, config, paths  # noqa: E402

BOM = b"\xef\xbb\xbf"
LOCK_NAME = ".modularcv-desktop.lock"
LOCK_STALE_SECONDS = 60


class Refusal(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or []


def fail(code, message, details=None):
    return {"ok": False, "code": code, "message": message, "details": details or []}


def locate(root, keys=("facts", "profile", "content")):
    if not isinstance(root, str) or not Path(root).is_dir():
        raise Refusal("WORKSPACE_MISSING", "the workspace folder does not exist")
    try:
        cfg = config.load(root)
    except config.ConfigError as error:
        raise Refusal("CONFIG_ERROR", str(error))
    out = {}
    for key in keys:
        target = paths.resolve_inside(root, cfg[key])
        if target is None:
            raise Refusal("CONFIG_ERROR", "the configured %s path leaves the workspace" % key)
        out[key] = target
    return cfg, out


def read_bytes(path):
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise Refusal("FILE_UNREADABLE", "cannot read %s: %s" % (Path(path).name, error.strerror))


def problems(items):
    out = []
    for item in items:
        if hasattr(item, "line"):
            out.append({"code": item.code, "message": item.message, "path": None if item.line is None else "line %d" % item.line})
        else:
            out.append({"code": item.code, "message": item.message, "path": item.path or None})
    return out


def clean(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise Refusal("VALIDATION_FAILED", "a text value is expected")
    value = " ".join(value.split())
    return value or None


def clean_list(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise Refusal("VALIDATION_FAILED", "a list of text values is expected")
    return [v for v in (" ".join(x.split()) for x in value) if v]


class workspace_lock:
    """Cooperative lock between Desktop writers: an exclusive lock file in the workspace root.

    It serialises the check-then-replace sequence of two Desktop instances (or two quick saves). It cannot
    stop an external editor: that residual window is documented and is covered by the hash re-check.
    """

    def __init__(self, root):
        self.path = Path(root) / LOCK_NAME
        self.held = False

    def __enter__(self):
        for _ in range(2):
            try:
                handle = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(handle)
                self.held = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > LOCK_STALE_SECONDS:
                        os.unlink(str(self.path))
                        continue
                except OSError:
                    pass
                break
            except OSError as error:
                raise Refusal("WRITE_FAILED", "cannot lock the workspace for writing: %s" % error.strerror)
        raise Refusal("BUSY", "another save is in progress in this workspace; try again in a moment")

    def __exit__(self, *exc):
        if self.held:
            try:
                os.unlink(str(self.path))
            except OSError:
                pass
        return False


def atomic_replace(target, new_bytes, expected_sha256, verify, root=None):
    """Replace `target` by `new_bytes` only if it is still the file the user saw."""
    target = Path(target)
    with workspace_lock(root or target.parent):
        current = read_bytes(target)
        if current is None or canonical.sha256_text(current) != expected_sha256:
            raise Refusal("CONFLICT", "the file changed since it was read; reload before saving")
        handle, temp_name = tempfile.mkstemp(prefix="." + target.name + ".mcv-", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(handle, "wb") as temp:
                temp.write(new_bytes)
                temp.flush()
                os.fsync(temp.fileno())
            if Path(temp_name).read_bytes() != new_bytes:
                raise Refusal("WRITE_FAILED", "the temporary file does not match what was prepared; nothing was replaced")
            verify(Path(temp_name).read_bytes())
            again = read_bytes(target)
            if again is None or canonical.sha256_text(again) != expected_sha256:
                raise Refusal("CONFLICT", "the file changed while saving; nothing was replaced")
            try:
                os.replace(temp_name, target)
            except OSError as error:
                raise Refusal("WRITE_FAILED", "cannot replace the file (is it open elsewhere?): %s" % error.strerror)
        finally:
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def create_new(target, data, root=None):
    """Create `target` (exclusive: an existing file is never touched). Returns None or raises Refusal."""
    target = Path(target)
    with workspace_lock(root or target.parent):
        try:
            with open(str(target), "xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            raise Refusal("OUTPUT_EXISTS", "the file already exists; nothing was overwritten")
        except OSError as error:
            raise Refusal("OUTPUT_WRITE_FAILED", "cannot write the file: %s" % error.strerror)
        if target.read_bytes() != data:
            try:
                os.unlink(str(target))
            except OSError:
                pass
            raise Refusal("OUTPUT_WRITE_FAILED", "the written file does not match what was prepared; it was removed")


def ensure_dir(root, name):
    """A direct sub-folder of the workspace root; created once if missing (never a nested or outside path)."""
    if not name or "/" in name or "\\" in name or name in (".", "..") or paths.relative_path_problem(name):
        raise Refusal("PATH_UNSAFE", "unsafe folder name")
    base = Path(root).resolve()
    target = base / name
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise Refusal("PATH_UNSAFE", "the %s entry is not a regular folder" % name)
    if not target.exists():
        try:
            target.mkdir()
        except OSError as error:
            raise Refusal("OUTPUT_WRITE_FAILED", "cannot create the %s folder: %s" % (name, error.strerror))
    if paths.resolve_inside(base, name) is None:
        raise Refusal("PATH_UNSAFE", "the folder leaves the workspace")
    return target


def dumps(document):
    """The JSON form the engine CLI writes (stable, sorted keys)."""
    return (json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
