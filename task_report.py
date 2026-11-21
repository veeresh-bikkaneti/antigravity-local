"""Describe what a --task run changed in the workspace. Standard library only.

the pure report functions (summarize, deleted, render) live at
agl.core.task_report and are resolved on first use (not at import) -- a lone copy of this file beside
a side script (code_agent.py and friends get one in their folder) keeps importing with the standard
library only, and touches no package. The disk-touching parts below stay at the root.
"""
import hashlib
import os

HASH_CAP = 64 * 1024 * 1024  # ponytail: bigger files fall back to (size, mtime); fine for agent-written text

_MOVED_TO_CORE = ("summarize", "deleted", "render")


def __getattr__(name):
    """Re-export the pure functions from agl.core.task_report on first attribute access."""
    if name in _MOVED_TO_CORE:
        from agl.core import task_report as _core
        return getattr(_core, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def snapshot(workspace_dir):
    """Map each file's relative path to a fingerprint: (size, sha256). Touch-only edits don't change it."""
    files = {}
    for root, _, names in os.walk(workspace_dir):
        for name in names:
            path = os.path.join(root, name)
            try:
                stat = os.stat(path)
                if stat.st_size <= HASH_CAP:
                    with open(path, "rb") as f:
                        fp = (stat.st_size, hashlib.sha256(f.read()).hexdigest())
                else:
                    fp = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                continue  # vanished or unreadable mid-walk
            files[os.path.relpath(path, workspace_dir)] = fp
    return files


def set_aside(path):
    """Move a leftover demo file to <path>.prev so the SDK can create it fresh (it refuses to create over a file)."""
    if os.path.isfile(path):
        os.replace(path, path + ".prev")


def demo_page_ok(path):
    """True when the demo file exists and really holds a dark-mode toggle, not just 'some change'."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "dark" in f.read().lower()
    except OSError:
        return False
