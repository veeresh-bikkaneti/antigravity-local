"""Read and write the JSON files that VS Code Chat and the workspace use. A changed file is backed up first."""

import json
from pathlib import Path

from agl.platform import agent_files


def is_dir(path):
    return Path(path).is_dir()


def apply(path, merge, empty):
    """Merge into the JSON file at path. Returns "written" or "unchanged". A file that is not JSON raises ValueError."""
    path = Path(path)
    exists = path.exists()
    if exists:
        text = path.read_text(encoding="utf-8-sig")
        data = json.loads(text) if text.strip() else empty
    else:
        data = empty
    new = merge(data)
    if exists and new == data:
        return "unchanged"
    if exists:
        agent_files.copy2(path, agent_files.backup_path(path))
    agent_files.atomic_write(path, (json.dumps(new, indent=2) + "\n").encode("utf-8"))
    return "written"
