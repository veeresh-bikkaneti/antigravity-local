"""File and JSON I/O for the agent setup and hand-off scripts (Phase 6c).

The root modules keep their old names as shims that wire these helpers in; every read, write, copy and
temp-file dance lives here. `shutil`/`tempfile` are platform-only imports, so the root files stay clean.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

from agl.core.agent_config import AgentSetupError


def load(path):
    """(data, existing_text). A missing file is an empty object. Anything we cannot safely merge into is refused."""
    if not path.exists():
        return {}, None
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise AgentSetupError(
            f"{path} is not valid JSON ({e}). We did not change it. Fix the file (or move it aside) and run again.")
    if not isinstance(data, dict):
        raise AgentSetupError(f"{path} should hold a JSON object. We did not change it. Fix it and run again.")
    return data, text


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_text_atomic(path, text):
    """The text-mode twin of atomic_write: newline='\n' is kept verbatim, never translated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def copy2(src, dst):
    shutil.copy2(src, dst)


def copytree(src, dst):
    shutil.copytree(src, dst, dirs_exist_ok=True)


def mkdir(path):
    path.mkdir(parents=True, exist_ok=True)


def read_text_or(path, default=""):
    """The file's text, or `default` when it cannot be read (OSError only, like the callers it replaces)."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return default


def read_text_if_exists(path):
    """The file's text with undecodable bytes replaced, or None when the file does not exist."""
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path, text):
    path.write_text(text, encoding="utf-8")
