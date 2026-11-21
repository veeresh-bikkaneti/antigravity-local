"""Homeport's saved settings file: one small JSON object in the app data dir."""

import json
import os

from agl.platform import state

FILE_NAME = "homeport.json"


def _default_path():
    """The data dir is the same folder the ledger uses; reached via agl.platform.state so no root imports."""
    return state.ledger_path().parent / FILE_NAME


def load(path=None) -> dict:
    """The saved settings as a dict; {} when the file is missing, unreadable, invalid JSON,
    or JSON that is not an object."""
    if path is None:
        path = _default_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save(values, path=None) -> None:
    """Write the settings atomically: a temp file in the same directory, then os.replace.
    The parent directory is created on first use."""
    if path is None:
        path = _default_path()
    target = os.fspath(path)
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(values, fh)
    os.replace(tmp, path)
