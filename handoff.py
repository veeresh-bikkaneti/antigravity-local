"""Hand-off: turn a Claude Code transcript into HANDOFF.md so another agent can pick the task up. Standard library only.

`python run.py handoff [--transcript PATH | --session ID|latest] [--install-hook]`

No model call. The transcript format is not a public contract, so every record is read defensively and unknown
record types are skipped. HANDOFF.md can hold command output and secrets from the transcript: we make sure git ignores it, and never overwrite a HANDOFF.md we did not write.

Collaborators (stdin, input, git runner, home, cwd) are passed in and looked up at call time, so tests never touch
the real machine.
"""
import argparse
import copy
import datetime
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

BACKUP_SUFFIX = ".bak-antigravity-local"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}   # on Windows most commands run through the PowerShell tool
MAX_TEXT = 2000
SKIP_PREFIXES = ("<system-reminder>", "<local-command", "<command-name>", "<command-message>", "Caveat:")
RUN_PY = Path(__file__).resolve().parent / "run.py"


class HandoffError(Exception):
    pass


def _clip(text, limit=MAX_TEXT):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " ... (cut)"


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


def _blocks(rec):
    msg = rec.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return []
    # the format is not a contract: a block whose text is not a string (or whose name is not) is kept but harmless
    return [{**b, "text": b["text"] if isinstance(b.get("text"), str) else ""} for b in content
            if isinstance(b, dict)]


def summarize(records):
    """The facts HANDOFF.md needs, from whatever records we recognise."""
    users, todos, files, commands, last_text = [], None, [], [], ""
    tasks = {}   # TaskCreate / TaskUpdate (current Claude Code): ids are 1, 2, 3 ... in creation order
    for rec in records:
        kind = rec.get("type")
        if kind == "user" and not rec.get("isMeta"):
            text = "\n".join(b.get("text", "") for b in _blocks(rec) if b.get("type") == "text").strip()
            if text and not text.startswith(SKIP_PREFIXES):
                users.append(text)
        elif kind == "assistant":
            texts = [b.get("text", "") for b in _blocks(rec) if b.get("type") == "text" and b.get("text", "").strip()]
            if texts:
                last_text = "\n".join(texts).strip()
            for b in _blocks(rec):
                if b.get("type") != "tool_use" or not isinstance(b.get("input"), dict):
                    continue
                name, data = b.get("name"), b["input"]
                if not isinstance(name, str):
                    continue
                if name == "TodoWrite" and isinstance(data.get("todos"), list):  # legacy tool
                    todos, tasks = data["todos"], {}
                elif name == "TaskCreate" and isinstance(data.get("subject"), str):
                    tasks[str(len(tasks) + 1)] = {"content": data["subject"], "status": "pending"}
                    todos = list(tasks.values())
                elif name == "TaskUpdate" and str(data.get("taskId")) in tasks:
                    task = tasks[str(data["taskId"])]
                    if isinstance(data.get("subject"), str):
                        task["content"] = data["subject"]
                    if data.get("status") == "deleted":
                        task["status"] = "deleted"
                    elif isinstance(data.get("status"), str):
                        task["status"] = data["status"]
                    todos = [t for t in tasks.values() if t["status"] != "deleted"]
                elif name in EDIT_TOOLS:
                    path = data.get("file_path") or data.get("notebook_path")
                    if isinstance(path, str) and path not in files:
                        files.append(path)
                elif name in SHELL_TOOLS and isinstance(data.get("command"), str):
                    commands.append(data["command"])
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


def _first_cwd(path):
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


def _same(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def find_transcript(session, repo, home=None, environ=None):
    """The transcript for this repo: `session` is an id or 'latest'. Newest wins across every config folder."""
    home = Path(home) if home else Path.home()
    environ = os.environ if environ is None else environ
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
                if folder == named or (_first_cwd(f) and _same(_first_cwd(f), repo)):
                    found.append(f)
    if not found:
        raise HandoffError(f"No Claude Code transcript found for {repo}"
                           + ("" if session in (None, "latest") else f" with session id {session}")
                           + ". Pass --transcript PATH.")
    return max(found, key=lambda p: p.stat().st_mtime)


# ---------- HANDOFF.md ----------

def _git(args, repo, run=None):
    run = run or subprocess.run
    try:
        r = run(["git"] + args, cwd=str(repo), capture_output=True, text=True, timeout=30)
        return (r.stdout or "").rstrip() or "(none)"  # rstrip only: status columns start with a space
    except Exception as e:
        return f"(git unavailable: {e.__class__.__name__})"


def repo_root(cwd, run=None):
    run = run or subprocess.run
    try:
        r = run(["git", "rev-parse", "--show-toplevel"], cwd=str(cwd), capture_output=True, text=True, timeout=30)
        top = (r.stdout or "").strip()
        if r.returncode == 0 and top:
            return Path(top)
    except Exception:
        pass
    return Path(cwd)


def render(info, transcript, repo, now=None, git_run=None):
    now = now or datetime.datetime.now().astimezone()
    users = info["users"]
    out = ["# Hand-off", "", MARKER, "",
           f"Written {now.isoformat(timespec='seconds')} from a Claude Code transcript, with no model call. "
           "Read it, check `git status`, then continue.", ""]
    out += ["## Original ask", "", _clip(users[0]) if users else "(no user message found)", ""]
    out += ["## Last 3 user messages", ""]
    out += [f"{i}. {_clip(m, 600)}" for i, m in enumerate(users[-3:], 1)] or ["(none)"]
    out += ["", "## Last to-do list", ""]
    todos = info["todos"]
    if todos:
        for t in todos:
            if isinstance(t, dict):
                mark = {"completed": "x", "in_progress": "~"}.get(t.get("status"), " ")
                out.append(f"- [{mark}] {t.get('content') or t.get('subject') or ''}")
    else:
        out.append("(no to-do list was written)")
    out += ["", "## Files edited or created", ""]
    out += [f"- `{p}`" for p in info["files"]] or ["(none)"]
    out += ["", "## Last 10 shell commands", ""]
    out += [f"- `{_clip(c, 300)}`" for c in info["commands"]] or ["(none)"]
    out += ["", "## Last assistant message", "", _clip(info["last_text"]) or "(none)", ""]
    out += ["## git status --short", "", "```", _git(["status", "--short"], repo, git_run), "```", "",
            "## git diff --stat", "", "```", _git(["diff", "--stat"], repo, git_run), "```", "",
            "## Source", "", f"- Transcript: `{transcript}`", f"- Repo: `{repo}`", ""]
    return "\n".join(out)


STDIN_WAIT = 3.0
STDIN_MAX = 1_000_000


def read_hook_stdin(stdin, wait=None):
    """transcript_path and cwd from a hook's JSON on stdin. Nothing if stdin is a terminal, not JSON, or does not
    deliver (and close) within `wait` seconds: a hook always sends its JSON and closes, so a pipe that stays open
    is somebody's pipeline, and we must not hang on it."""
    try:
        if stdin is None or stdin.isatty():
            return {}
    except (ValueError, OSError):
        return {}
    box = {}

    def pull():
        try:
            box["text"] = stdin.read(STDIN_MAX)
        except (ValueError, OSError):
            box["text"] = ""

    t = threading.Thread(target=pull, daemon=True)
    t.start()
    t.join(STDIN_WAIT if wait is None else wait)
    if t.is_alive():
        return {}
    try:
        data = json.loads(box.get("text") or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


MARKER = "<!-- written by antigravity-local handoff -->"


def _backup_path(target):
    """A backup name that never overwrites an earlier backup."""
    base = Path(str(target) + BACKUP_SUFFIX)
    n, path = 1, base
    while path.exists():
        n += 1
        path = Path(f"{base}.{n}")
    return path


def ensure_ignored(repo, git_run=None, out=print):
    """Make sure git will not pick HANDOFF.md up. If the project does not already ignore it, add it to
    .git/info/exclude (a local file that is never committed) and say so. Returns where it is ignored, or None."""
    run = git_run or subprocess.run
    try:
        if run(["git", "check-ignore", "-q", "HANDOFF.md"], cwd=str(repo), capture_output=True, text=True,
               timeout=30).returncode == 0:
            return "your .gitignore"
        raw = (run(["git", "rev-parse", "--git-path", "info/exclude"], cwd=str(repo), capture_output=True,
                   text=True, timeout=30).stdout or "").strip()
        if not raw:
            raise OSError("not a git repository")
        path = Path(raw) if Path(raw).is_absolute() else Path(repo) / raw
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if "/HANDOFF.md*" not in existing.splitlines():
            with open(path, "a", encoding="utf-8", newline="\n") as f:
                f.write(("" if existing.endswith("\n") or not existing else "\n") + "/HANDOFF.md*\n")
        out(f"Added /HANDOFF.md* to {path}, so git ignores it in this project (a local file, never committed).")
        return str(path)
    except Exception as e:
        out(f"WARNING: could not make sure git ignores HANDOFF.md ({e.__class__.__name__}: {e}). It can hold "
            "secrets from the transcript, so add it to this project's .gitignore before you commit.")
        return None


def is_tracked(repo, git_run=None):
    """True when git already tracks HANDOFF.md in this project (`git ls-files --error-unmatch` succeeds).
    If git cannot be run we cannot tell, so say no and let ensure_ignored warn."""
    run = git_run or subprocess.run
    try:
        return run(["git", "ls-files", "--error-unmatch", "HANDOFF.md"], cwd=str(repo), capture_output=True,
                   text=True, timeout=30).returncode == 0
    except Exception:
        return False


def write_handoff(transcript, repo, now=None, git_run=None, out=print):
    """Write HANDOFF.md. Refuses when the project tracks it. A file we did not write is backed up, never overwritten."""
    if is_tracked(repo, git_run):
        raise HandoffError("This project already tracks HANDOFF.md in git, so hand-off notes written there would be "
                           "committed with their command output and any secrets in it. Nothing was written. Run "
                           "`git rm --cached HANDOFF.md` (keeps your file) and add it to .gitignore, or move your "
                           "tracked file elsewhere, then run this again.")
    info = summarize(read_records(transcript))
    target = Path(repo) / "HANDOFF.md"
    if target.exists() and MARKER not in target.read_text(encoding="utf-8", errors="replace"):
        backup = _backup_path(target)
        shutil.copy2(target, backup)
        out(f"An existing HANDOFF.md that we did not write was saved to {backup} first.")
    target.write_text(render(info, transcript, repo, now=now, git_run=git_run), encoding="utf-8")
    return target


# ---------- --install-hook ----------

def hook_command():
    py = "python" if sys.platform == "win32" else "python3"
    return f'{py} "{RUN_PY}" handoff'


def _our_hook(matcher=None):
    entry = {"hooks": [{"type": "command", "command": hook_command()}]}
    if matcher:
        entry["matcher"] = matcher
    return entry


def merge_hooks(settings):
    """settings with our StopFailure (rate_limit) and PreCompact hooks added. Everything else is kept."""
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HandoffError('"hooks" in settings.local.json is not an object. We did not change it.')
    for event, matcher in (("StopFailure", "rate_limit"), ("PreCompact", None)):
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise HandoffError(f'"hooks.{event}" in settings.local.json is not a list. We did not change it.')
        mine = hook_command()
        has = any(isinstance(e, dict) and any(isinstance(h, dict) and h.get("command") == mine
                                              for h in e.get("hooks", []) if isinstance(h, dict)) for e in entries)
        if not has:
            entries.append(_our_hook(matcher))
    return settings


def install_hook(repo, input_fn=None, out=print):
    """Add the hooks to <repo>/.claude/settings.local.json only, after showing the diff and a typed y."""
    input_fn = input_fn or input
    path = Path(repo) / ".claude" / "settings.local.json"
    before_text = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        settings = json.loads(before_text) if before_text.strip() else {}
    except ValueError as e:
        raise HandoffError(f"{path} is not valid JSON ({e}). We did not change it. Fix it and run again.")
    if not isinstance(settings, dict):
        raise HandoffError(f"{path} should hold a JSON object. We did not change it.")
    merged = merge_hooks(copy.deepcopy(settings))
    after_text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    if merged == settings:  # compare what the file means, not how it is indented
        out(f"The hand-off hooks are already in {path}. Nothing to do.")
        return False
    out(f"This changes only {path} (never your user settings):\n")
    out("".join(difflib.unified_diff(before_text.splitlines(True), after_text.splitlines(True),
                                     "before", "after")))
    try:
        answer = input_fn("\nAdd these hooks? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip().lower() not in ("y", "yes"):
        out("Not changed.")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = Path(str(path) + BACKUP_SUFFIX)
    if before_text and not backup.exists():
        shutil.copy2(path, backup)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(after_text)
    os.replace(tmp, path)
    out(f"Added. When a rate limit stops a session, or before a compaction, HANDOFF.md is written in {repo}.")
    return True


def main(argv=None, stdin=None, input_fn=None, home=None, environ=None, cwd=None, git_run=None, out=print):
    ap = argparse.ArgumentParser(prog="run.py handoff",
                                 description="Write HANDOFF.md from a Claude Code transcript (no model call).")
    ap.add_argument("--transcript", metavar="PATH", help="a transcript .jsonl to read")
    ap.add_argument("--session", metavar="ID", help="a session id, or 'latest' (the default)")
    ap.add_argument("--install-hook", action="store_true",
                    help="add rate-limit and pre-compact hooks to this project's .claude/settings.local.json")
    args = ap.parse_args(argv)
    cwd = Path(cwd) if cwd else Path.cwd()
    try:
        repo = repo_root(cwd, git_run)
        if args.install_hook:
            install_hook(repo, input_fn=input_fn, out=out)
            return 0
        payload = {} if (args.transcript or args.session) else read_hook_stdin(stdin if stdin is not None else sys.stdin)
        if payload.get("cwd") and not args.transcript:
            repo = repo_root(payload["cwd"], git_run)
        if args.transcript:
            transcript = Path(args.transcript)
        elif isinstance(payload.get("transcript_path"), str):
            transcript = Path(payload["transcript_path"])
        else:
            transcript = find_transcript(args.session or "latest", repo, home=home, environ=environ)
        if not transcript.is_file():
            raise HandoffError(f"Transcript not found: {transcript}")
        target = write_handoff(transcript, repo, git_run=git_run, out=out)
        out(f"Wrote {target} from {transcript}")
        ensure_ignored(repo, git_run=git_run, out=out)
        out("HANDOFF.md can hold command output and secrets from that transcript. Keep it out of commits.")
        return 0
    except HandoffError as e:
        out(f"[handoff] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
