"""Hand-off: turn a Claude Code transcript into HANDOFF.md so another agent can pick the task up. Standard library only.

`python run.py handoff [--transcript PATH | --session ID|latest] [--install-hook]`

No model call. The transcript format is not a public contract, so every record is read defensively and unknown
record types are skipped. HANDOFF.md can hold command output and secrets from the transcript: we make sure git ignores it, and never overwrite a HANDOFF.md we did not write.

Collaborators (stdin, input, git runner, home, cwd) are passed in and looked up at call time, so tests never touch
the real machine.

The file/JSON/git/registry I/O lives in agl/platform (agent_files.py, agent_proc.py), the pure decisions in
agl/core/handoff.py, and the orchestration (write_handoff, install_hook) in agl/app/agent_session.py. What is
left here is this module's own shell: its constants, plus main() and read_hook_stdin(), the hook's shell.
"""

import argparse
import json
import os
import sys
import threading
from pathlib import Path

from agl.app import agent_session
from agl.core import handoff as core_handoff
from agl.core.handoff import BACKUP_SUFFIX, MARKER, MAX_TEXT, HandoffError
from agl.platform import agent_files, agent_proc

RUN_PY = Path(__file__).resolve().parent / "run.py"


def read_records(path):  # I/O in agl.platform.agent_files
    """Parsed JSON objects, one per line. Blank and broken lines are skipped."""
    return agent_files.read_records(path)


summarize = core_handoff.summarize_transcript  # old name stays for callers and tests


# ---------- finding the transcript ----------

def project_dir_name(path):  # pure logic in agl.core.handoff
    """Claude Code names a project's transcript folder after its path with every non-alphanumeric turned into '-'."""
    return core_handoff.project_dir_name(path)


def config_dirs(home, environ):  # pure logic in agl.core.handoff
    """Where transcripts may live: the configured folder, ~/.claude, and ~/.claude-local (local-model sessions)."""
    return core_handoff.config_dirs(home, environ)


def find_transcript(session, repo, home=None, environ=None):  # I/O in agl.platform.agent_files
    """The transcript for this repo: `session` is an id or 'latest'. Newest wins across every config folder."""
    home = Path(home) if home else Path.home()
    environ = os.environ if environ is None else environ
    return agent_files.find_transcript(session, repo, home, environ)


# ---------- HANDOFF.md ----------

def repo_root(cwd, run=None):  # I/O in agl.platform.agent_proc
    return agent_proc.repo_root(cwd, run)


def render(info, transcript, repo, now=None, git_run=None):  # pure logic in agl.core.handoff
    return core_handoff.render(info, transcript, repo, now=now,
                               git_text=lambda args, r: agent_proc.git(args, r, git_run))


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


def ensure_ignored(repo, git_run=None, out=print):  # stays here: this module's own shell
    """Make sure git will not pick HANDOFF.md up. If the project does not already ignore it, add it to
    .git/info/exclude (a local file that is never committed) and say so. Returns where it is ignored, or None."""
    run = git_run or agent_proc.run
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


def is_tracked(repo, git_run=None):  # I/O in agl.platform.agent_proc
    """True when git already tracks HANDOFF.md in this project (`git ls-files --error-unmatch` succeeds).
    If git cannot be run we cannot tell, so say no and let ensure_ignored warn."""
    return agent_proc.is_tracked(repo, git_run)


def write_handoff(transcript, repo, now=None, git_run=None, out=print):  # orchestration in agl.app.agent_session
    """Write HANDOFF.md. Refuses when the project tracks it. A file we did not write is backed up, never overwritten."""
    return agent_session.write_handoff(
        transcript, repo, now=now, git_run=git_run, out=out, is_tracked=agent_proc.is_tracked,
        read_records=agent_files.read_records, summarize=core_handoff.summarize_transcript,
        render=lambda info, tr, rp, now=None: core_handoff.render(
            info, tr, rp, now=now, git_text=lambda args, r: agent_proc.git(args, r, git_run)),
        backup_path=agent_files.backup_path, copy2=agent_files.copy2,
        read_existing=agent_files.read_text_if_exists, write_file=agent_files.write_text, marker=MARKER)


# ---------- --install-hook ----------

def hook_command():
    py = "python" if sys.platform == "win32" else "python3"
    return f'{py} "{RUN_PY}" handoff'


def merge_hooks(settings):  # pure logic in agl.core.handoff
    """settings with our StopFailure (rate_limit) and PreCompact hooks added. Everything else is kept."""
    return core_handoff.merge_hooks(settings, hook_command())


def install_hook(repo, input_fn=None, out=print):  # orchestration in agl.app.agent_session
    """Add the hooks to <repo>/.claude/settings.local.json only, after showing the diff and a typed y."""
    return agent_session.install_hook(
        repo, input_fn=input_fn, out=out, hook_cmd=hook_command, merge=core_handoff.merge_hooks,
        read_text=agent_files.read_text_or, atomic_text_write=agent_files.write_text_atomic,
        copy2=agent_files.copy2, mkdir=agent_files.mkdir, backup_suffix=BACKUP_SUFFIX)


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
