"""File and JSON I/O for the agent setup and hand-off scripts (Phase 6c).

The root modules keep their old names as shims that wire these helpers in; every read, write, copy and
temp-file dance lives here. `shutil`/`tempfile` are platform-only imports, so the root files stay clean.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from agl.core.agent_config import AgentSetupError
from agl.core.handoff import BACKUP_SUFFIX, HandoffError, config_dirs, project_dir_name, same


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


def _unknown_tracking(rel, why):
    return (f"Could not check whether git tracks {rel} ({why}), and this folder is inside a git repo. "
            "We did not change anything. Fix: make `git status` work in this folder (for dubious ownership, run "
            "`git config --global --add safe.directory <this folder>`), then run this again.")


def git_tracks(workspace, rel):
    """True when git tracks `rel` in `workspace`, False when it does not. A folder outside any git repo is untracked.
    Inside a repo, when git cannot answer (git missing, dubious ownership, any other error), raise AgentSetupError:
    we cannot tell, so we refuse rather than guess."""
    folder = Path(workspace).resolve()
    if not any((p / ".git").exists() for p in (folder, *folder.parents)):
        return False
    try:
        done = subprocess.run(["git", "ls-files", "--error-unmatch", "--", rel], cwd=str(folder),
                              capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        raise AgentSetupError(_unknown_tracking(rel, f"git did not run: {e}"))
    if done.returncode not in (0, 1):  # 1 means git ran and the file is not in the index
        raise AgentSetupError(_unknown_tracking(rel, f"git exited with code {done.returncode}"))
    return done.returncode == 0


def backup_path(target):
    """A backup name that never overwrites an earlier backup."""
    base = Path(str(target) + BACKUP_SUFFIX)
    n, path = 1, base
    while path.exists():
        n += 1
        path = Path(f"{base}.{n}")
    return path


def read_records(path):
    """Parsed JSON objects, one per line. Blank and broken lines are skipped."""
    records = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                records.append(rec)
    return records


def first_cwd(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for _, line in zip(range(50), f):
                try:
                    cwd = json.loads(line).get("cwd")
                except (ValueError, AttributeError):
                    continue
                if isinstance(cwd, str):
                    return cwd
    except OSError:
        pass
    return None


def find_transcript(session, repo, home, environ):
    """The transcript for this repo: `session` is an id or 'latest'. Newest wins across every config folder."""
    found = []
    for base in config_dirs(home, environ):
        projects = base / "projects"
        if not projects.is_dir():
            continue
        named = projects / project_dir_name(repo)
        folders = [named] if named.is_dir() else []
        folders += [p for p in projects.iterdir() if p.is_dir() and p != named]
        for folder in folders:
            for f in folder.glob("*.jsonl"):
                if session not in (None, "latest") and f.stem != session:
                    continue
                if folder == named or (first_cwd(f) and same(first_cwd(f), repo)):
                    found.append(f)
    if not found:
        raise HandoffError(f"No Claude Code transcript found for {repo}"
                           + ("" if session in (None, "latest") else f" with session id {session}")
                           + ". Pass --transcript PATH.")
    return max(found, key=lambda p: p.stat().st_mtime)
