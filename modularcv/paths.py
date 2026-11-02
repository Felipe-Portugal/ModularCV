"""Workspace-relative paths: one portable, strict form used by snapshots and provenance.

A safe path is relative, uses `/` only, has no empty, `.` or `..` segment, no drive letter, no
backslash, no `:` (Windows alternate data streams) and no segment ending in a space or a dot
(Windows silently drops them). The same string is accepted or refused on Windows and Linux.
"""
import re
from pathlib import Path

_DRIVE = re.compile(r"^[A-Za-z]:")


def relative_path_problem(value):
    """Why `value` is not a safe workspace-relative path, or None when it is."""
    if not isinstance(value, str) or not value:
        return "the path is empty or not a string"
    if any(ord(ch) < 32 for ch in value):
        return "the path holds a control character"
    if "\\" in value:
        return "the path uses a backslash; use `/`"
    if value.startswith("/") or _DRIVE.match(value):
        return "the path is absolute"
    for segment in value.split("/"):
        if segment in ("", ".", ".."):
            return "the path has an empty, `.` or `..` segment"
        if ":" in segment:
            return "the path holds a `:`"
        if segment.endswith((" ", ".")):
            return "a path segment ends with a space or a dot"
    return None


def resolve_inside(root, relative):
    """The real path of `relative` under `root`, or None if it escapes (symlink, junction, `..`)."""
    if relative_path_problem(relative):
        return None
    base = Path(root).resolve()
    target = (base / relative).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target
