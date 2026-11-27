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

CHECKPOINT = Path(".agl") / "checkpoint.md"
GITIGNORE = Path(".gitignore")
QUESTION = "       Add the checkpoint file and the pointers? [y/N] "
Change = namedtuple("Change", "path old new kind shown")


def _yes(input_fn, prompt):
    try:
        answer = input_fn(prompt)
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("y", "yes")


def _targets(ws):
    """(path, shown name) for each instruction file that gets our pointer block. AGENTS.md is always one."""
    found = [(ws / "AGENTS.md", "AGENTS.md")]
    for name in ("CLAUDE.md", Path(".github") / "copilot-instructions.md"):
        if (ws / name).is_file():
            found.append((ws / name, str(name)))
    rules = ws / ".continue" / "rules"
    if rules.is_dir():
        found.append((rules / "agl-checkpoint.md", str(Path(".continue", "rules")) + os.sep))
    return found


def _plan(ws, files, stamp):
    """(changes, rows, broken). rows holds (shown, existed) per pointer file. Nothing is written here."""
    changes, rows = [], []
    ck_path = ws / CHECKPOINT
    old = files.read_text_if_exists(ck_path)
    new = ck.next_text(old, stamp)
    if new != old:
        changes.append(Change(ck_path, old, new, "checkpoint", str(CHECKPOINT)))
    for path, shown in _targets(ws):
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
    out(f"       Pointers : {first_shown} ({'found' if first_existed else 'missing, will be created'})")
    found = [shown for shown, existed in others if existed]
    if found:
        out(" " * 18 + ", ".join(found) + " (found)")
    if any(c.kind == "pointer" for c in changes):
        out("       Add a pointer block for each. We back up each existing file first.")
    if any(c.kind == "ignore" for c in changes):
        out("       The same yes also adds .agl/ to the project's .gitignore.")


def _write(change, files, out):
    backed_up = change.old is not None and (change.kind != "checkpoint" or not ck.is_ours(change.old))
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


def offer(workspace, *, files, is_tracked, input_fn, out, now=None):
    """Ask once. A yes writes the checkpoint file, adds our pointer block to each instruction file that applies,
    and adds .agl/ to .gitignore. Anything else writes nothing."""
    ws = Path(workspace)
    ck_path = ws / CHECKPOINT
    if is_tracked(ws, CHECKPOINT.as_posix()):
        out(f"       Not changed: {ck_path} is already tracked by git, so notes in it would be committed. "
            f"Run `git rm --cached {CHECKPOINT.as_posix()}` (this keeps your file), add .agl/ to .gitignore, "
            "then run this again. Nothing was written.")
        return
    stamp = now or datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    changes, rows, broken = _plan(ws, files, stamp)
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
