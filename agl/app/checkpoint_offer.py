"""Offer, once and only on a yes, the shared checkpoint file and its pointer blocks (docs/mockups/checkpoint.md).

Nothing is written without a typed yes, and end of input counts as no. The checkpoint, the pointer files and
.gitignore are planned first and shown. Only then, after the yes, are they written. Every message goes through `out`.
Reads and writes go through the injected `files` module (agl.platform.agent_files), so tests use a temp folder.
"""

import datetime
import os
from collections import namedtuple
from pathlib import Path

from agl.core import checkpoint as ck
from agl.core.agent_config import AgentSetupError

CHECKPOINT = Path(".agl") / "checkpoint.md"
GITIGNORE = Path(".gitignore")
RULES_FILE = Path(".continue") / "rules" / "agl-checkpoint.md"
QUESTION = "       Add the checkpoint file and the pointers? [y/N] "
Change = namedtuple("Change", "path old new kind shown")


def _yes(input_fn, prompt):
    try:
        answer = input_fn(prompt)
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("y", "yes")


def _targets(ws, app):
    """(path, shown name) for each instruction file that gets our pointer block. The chosen app's file is always
    one: CLAUDE.md for Claude Code, AGENTS.md for pi, opencode and codex. The others only when they already exist."""
    name = "CLAUDE.md" if app == "claude" else "AGENTS.md"
    found = [(ws / name, name)]
    copilot = Path(".github") / "copilot-instructions.md"
    if (ws / copilot).is_file():
        found.append((ws / copilot, str(copilot)))
    if (ws / ".continue" / "rules").is_dir():
        shown = str(RULES_FILE) if not (ws / RULES_FILE).is_file() else str(Path(".continue", "rules")) + os.sep
        found.append((ws / RULES_FILE, shown))
    return found


def _status(existed):
    return "found" if existed else "missing, will be created"


def _plan(ws, files, stamp, app):
    """(changes, rows, broken). rows holds (shown, existed) per pointer file. Nothing is written here."""
    changes, rows = [], []
    ck_path = ws / CHECKPOINT
    old = files.read_text_if_exists(ck_path)
    new = ck.next_text(old, stamp)
    if new != old:
        changes.append(Change(ck_path, old, new, "checkpoint", str(CHECKPOINT)))
    for path, shown in _targets(ws, app):
        old = files.read_text_if_exists(path)
        rows.append((shown, old is not None))
        try:
            new = ck.merge_pointer("" if old is None else old)
        except ck.PointerError:
            return [], rows, shown
        if new != old:
            changes.append(Change(path, old, new, "pointer", shown))
    gi = ws / GITIGNORE
    old = files.read_text_if_exists(gi)
    new = ck.with_ignore("" if old is None else old)
    if new != old:
        changes.append(Change(gi, old, new, "ignore", str(GITIGNORE)))
    return changes, rows, None


def _in_place(ck_path, rows, out):
    out("       Checkpoint: already in place. Nothing to do.")
    out(f"       File     : {ck_path} (up to date)")
    out(f"       Pointers : {', '.join(shown for shown, _ in rows)} (all current)")


def _show(ck_path, changes, rows, out):
    out("       Checkpoint: a short file your coding app reads first and updates before it stops.")
    out("       It keeps the plan, what is done, what is next, and the files you touched.")
    out(f"       File     : {ck_path}")
    (first_shown, first_existed), *others = rows
    out(f"       Pointers : {first_shown} ({_status(first_existed)})")
    found = [shown for shown, existed in others if existed]
    if found:
        out(" " * 18 + ", ".join(found) + " (found)")
    for shown, existed in others:
        if not existed:
            out(" " * 18 + f"{shown} ({_status(existed)})")
    if any(c.kind == "pointer" for c in changes):
        out("       Add a pointer block for each. We back up each existing file first.")
    if any(c.kind == "ignore" for c in changes):
        out("       The same yes also adds .agl/ to the project's .gitignore.")


def _write(change, files, out):
    backed_up = change.old is not None
    try:
        if backed_up:
            files.copy2(change.path, files.backup_path(change.path))
        files.write_text_atomic(change.path, change.new)
    except OSError as e:
        out(f"       Not changed: {change.path} ({e}).")
        return
    if change.old is None:
        out(f"       Created: {change.path}")
    elif backed_up:
        out(f"       Updated: {change.path} (an existing file was backed up first).")
    else:
        out(f"       Updated: {change.path}")


def offer(workspace, *, app, files, is_tracked, input_fn, out, now=None):
    """Ask once. A yes writes the checkpoint file, adds our pointer block to the chosen app's file (created if
    missing) and to each other instruction file that already exists, and adds .agl/ to .gitignore. Anything else
    writes nothing. `app` is the agent name: claude, pi, opencode or codex."""
    ws = Path(workspace)
    ck_path = ws / CHECKPOINT
    try:
        tracked = is_tracked(ws, CHECKPOINT.as_posix())
    except AgentSetupError as e:
        out(f"       Not changed: {e}")
        return
    if tracked:
        out(f"       Not changed: {ck_path} is already tracked by git, so notes in it would be committed. "
            f"Run `git rm --cached {CHECKPOINT.as_posix()}` (this keeps your file), add .agl/ to .gitignore, "
            "then run this again. Nothing was written.")
        return
    stamp = now or datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    changes, rows, broken = _plan(ws, files, stamp, app)
    if broken:
        out(f"       Not changed: {broken} has only one of our two marker lines, or more than one. "
            "Fix that by hand, then run this again. Nothing was written.")
        return
    if not changes:
        _in_place(ck_path, rows, out)
        return
    _show(ck_path, changes, rows, out)
    if not _yes(input_fn, QUESTION):
        out("       Not changed. Nothing was written, and .gitignore is untouched. Run this again any time.")
        return
    for change in changes:
        _write(change, files, out)
