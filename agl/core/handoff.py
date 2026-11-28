"""Pure hand-off decisions (Phase 6c): transcript summary, folder naming, hook merging, HANDOFF.md rendering.

No I/O and no subprocess: the git text arrives through the injected `git_text` callable, the clock through
`now`. Standard library only, so the root handoff.py shim passes its own constants at call time.
"""

import datetime
import os
import re
from pathlib import Path

BACKUP_SUFFIX = ".bak-antigravity-local"
MARKER = "<!-- written by antigravity-local handoff -->"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}   # on Windows most commands run through the PowerShell tool
MAX_TEXT = 2000
SKIP_PREFIXES = ("<system-reminder>", "<local-command", "<command-name>", "<command-message>", "Caveat:")


class HandoffError(Exception):
    pass


def clip(text, limit=MAX_TEXT):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " ... (cut)"


def blocks(rec):
    msg = rec.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return []
    # the format is not a contract: a block whose text is not a string (or whose name is not) is kept but harmless
    return [{**b, "text": b["text"] if isinstance(b.get("text"), str) else ""} for b in content
            if isinstance(b, dict)]


def _user_messages(records):
    users = []
    for rec in records:
        if rec.get("type") == "user" and not rec.get("isMeta"):
            text = "\n".join(b.get("text", "") for b in blocks(rec) if b.get("type") == "text").strip()
            if text and not text.startswith(SKIP_PREFIXES):
                users.append(text)
    return users


def _live(tasks):
    return [t for t in tasks.values() if t["status"] != "deleted"]


def _apply_tool(name, data, tasks):
    """(todo_list, file, command) effects of one tool use; each is None when the tool does not set it."""
    if name == "TodoWrite" and isinstance(data.get("todos"), list):  # legacy tool
        tasks.clear()
        return data["todos"], None, None
    if name == "TaskCreate" and isinstance(data.get("subject"), str):
        tasks[str(len(tasks) + 1)] = {"content": data["subject"], "status": "pending"}
        return _live(tasks), None, None
    if name == "TaskUpdate" and str(data.get("taskId")) in tasks:
        task = tasks[str(data["taskId"])]
        if isinstance(data.get("subject"), str):
            task["content"] = data["subject"]
        if task["status"] != "deleted" and isinstance(data.get("status"), str):
            # deleted stays deleted: a late update must not bring it back
            task["status"] = data["status"]
        return _live(tasks), None, None
    if name in EDIT_TOOLS:
        path = data.get("file_path") or data.get("notebook_path")
        return None, path if isinstance(path, str) else None, None
    if name in SHELL_TOOLS and isinstance(data.get("command"), str):
        return None, None, data["command"]
    return None, None, None


def _tool_effects(b, tasks):
    if b.get("type") != "tool_use" or not isinstance(b.get("input"), dict):
        return None, None, None
    name, data = b.get("name"), b["input"]
    if not isinstance(name, str):
        return None, None, None
    return _apply_tool(name, data, tasks)


def _assistant_facts(records):
    """(last_text, todos, files, commands) over the assistant records."""
    last_text, todos, tasks = "", None, {}
    files, commands = [], []
    for rec in records:
        if rec.get("type") != "assistant":
            continue
        texts = [b.get("text", "") for b in blocks(rec) if b.get("type") == "text" and b.get("text", "").strip()]
        if texts:
            last_text = "\n".join(texts).strip()
        for b in blocks(rec):
            new_todos, file, command = _tool_effects(b, tasks)
            if new_todos is not None:
                todos = new_todos
            if file is not None and file not in files:
                files.append(file)
            if command is not None:
                commands.append(command)
    return last_text, todos, files, commands


def summarize_transcript(records):
    """The facts HANDOFF.md needs, from whatever records we recognise.
    was summarize: renamed because task_report.summarize means the workspace before/after diff."""
    users = _user_messages(records)
    last_text, todos, files, commands = _assistant_facts(records)
    return {"users": users, "todos": todos, "files": files, "commands": commands[-10:], "last_text": last_text}


# ---------- finding the transcript ----------

def project_dir_name(path):
    """Claude Code names a project's transcript folder after its path with every non-alphanumeric turned into '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def config_dirs(home, environ):
    """Where transcripts may live: the configured folder, ~/.claude, and ~/.claude-local (local-model sessions)."""
    dirs = []
    if environ.get("CLAUDE_CONFIG_DIR"):
        dirs.append(Path(environ["CLAUDE_CONFIG_DIR"]))
    dirs += [Path(home) / ".claude", Path(home) / ".claude-local"]
    seen, out = set(), []
    for d in dirs:
        if str(d) not in seen:
            seen.add(str(d))
            out.append(d)
    return out


def same(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


# ---------- HANDOFF.md ----------

def _no_git(args, repo):
    return "(git unavailable: no runner)"


def _todos_section(todos):
    if not todos:
        return ["(no to-do list was written)"]
    lines = []
    for t in todos:
        if isinstance(t, dict):
            status = t.get("status")
            mark = {"completed": "x", "in_progress": "~"}.get(status if isinstance(status, str) else "", " ")
            lines.append(f"- [{mark}] {t.get('content') or t.get('subject') or ''}")
    return lines


def _bullets(items, fmt, empty):
    return [fmt(i) for i in items] or [empty]


def render(info, transcript, repo, now=None, git_text=None):
    gt = git_text or _no_git
    now = now or datetime.datetime.now().astimezone()
    users = info["users"]
    out = ["# Hand-off", "", MARKER, "",
           f"Written {now.isoformat(timespec='seconds')} from a Claude Code transcript, with no model call. "
           "Read it, check `git status`, then continue.", "",
           "## Original ask", "", clip(users[0]) if users else "(no user message found)", "",
           "## Last 3 user messages", ""]
    out += [f"{i}. {clip(m, 600)}" for i, m in enumerate(users[-3:], 1)] or ["(none)"]
    out += ["", "## Last to-do list", ""] + _todos_section(info["todos"])
    out += ["", "## Files edited or created", ""] + _bullets(info["files"], lambda p: f"- `{p}`", "(none)")
    out += ["", "## Last 10 shell commands", ""] + _bullets(info["commands"], lambda c: f"- `{clip(c, 300)}`", "(none)")
    out += ["", "## Last assistant message", "", clip(info["last_text"]) or "(none)", "",
            "## git status --short", "", "```", gt(["status", "--short"], repo), "```", "",
            "## git diff --stat", "", "```", gt(["diff", "--stat"], repo), "```", "",
            "## Source", "", f"- Transcript: `{transcript}`", f"- Repo: `{repo}`", ""]
    return "\n".join(out)


def render_checkpoint(checkpoint, source, repo, now=None, git_text=None):
    """HANDOFF.md built from the shared `.agl/checkpoint.md`, so a hand-off works for every coding app, not only
    Claude Code. The checkpoint text is copied as it is; git status and diff stat are added for the next model."""
    gt = git_text or _no_git
    now = now or datetime.datetime.now().astimezone()
    body = (checkpoint or "").strip() or "(the checkpoint is empty)"
    out = ["# Hand-off", "", MARKER, "",
           f"Written {now.isoformat(timespec='seconds')} from `.agl/checkpoint.md`, with no model call. "
           "Read it, check `git status`, then continue from Next.", "",
           "## Checkpoint", "", body, "",
           "## git status --short", "", "```", gt(["status", "--short"], repo), "```", "",
           "## git diff --stat", "", "```", gt(["diff", "--stat"], repo), "```", "",
           "## Source", "", f"- Checkpoint: `{source}`", f"- Repo: `{repo}`", ""]
    return "\n".join(out)


# ---------- --install-hook ----------

def our_hook(hook_cmd, matcher=None):
    entry = {"hooks": [{"type": "command", "command": hook_cmd}]}
    if matcher:
        entry["matcher"] = matcher
    return entry


def merge_hooks(settings, hook_cmd):
    """settings with our StopFailure (rate_limit) and PreCompact hooks added. Everything else is kept."""
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HandoffError('"hooks" in settings.local.json is not an object. We did not change it.')
    for event, matcher in (("StopFailure", "rate_limit"), ("PreCompact", None)):
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise HandoffError(f'"hooks.{event}" in settings.local.json is not a list. We did not change it.')
        has = any(isinstance(e, dict) and any(isinstance(h, dict) and h.get("command") == hook_cmd
                                              for h in e.get("hooks", []) if isinstance(h, dict)) for e in entries)
        if not has:
            entries.append(our_hook(hook_cmd, matcher))
    return settings
