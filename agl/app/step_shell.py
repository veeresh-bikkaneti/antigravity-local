"""Step mode inside the built-in shell (C4 B3): `/steps <task>`, and the resume question at shell start.

The disk, git and test-command work arrives as `ports.step_io` (agl/platform/step_io.py), so this module stays
in the app layer. The test command lives only in memory for one run (agl/app/step_runner.py).
"""
from __future__ import annotations

import datetime
from typing import Any

from agl.app import step_runner
from agl.core import checkpoint, steps
from agl.core.verification_prompts import MAIN_SYSTEM_PROMPT

COMMAND = "/steps"
USAGE = "Usage: /steps <task>"
DEFAULT_WINDOW = 8192  # step mode's floor when stage 4 could not read the window (inferred)


class _Writer:
    """Turns the shell's print-style `out` into the `write` the step runner uses."""

    def __init__(self, out: Any):
        self._out = out

    def write(self, text: str) -> None:
        self._out(text, end="", flush=True)


def window_from(checked: Any) -> int:
    """The window stage 4 read, `(tokens, source)`, or the floor when it read nothing."""
    if isinstance(checked, tuple) and checked and isinstance(checked[0], int) and checked[0] > 0:
        return checked[0]
    return DEFAULT_WINDOW


def is_steps(line: str) -> bool:
    """True for `/steps` and `/steps <task>`, not for `/stepsx`."""
    return line == COMMAND or line.startswith(COMMAND + " ")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _io(ports: Any, workspace: Any) -> Any:
    """The step I/O port, or None when step mode can't run here (no port, or no workspace)."""
    io = getattr(ports, "step_io", None)
    return io if workspace and io is not None else None


def _open_position(io: Any, workspace: Any) -> tuple[int, int] | None:
    text = io.read_checkpoint(workspace)
    return steps.position(text) if isinstance(text, str) else None


async def _run(task: str, *, io: Any, new_agent: Any, workspace: Any, window: int, ports: Any, out: Any,
               input_fn: Any) -> str:
    if io.is_tracked(workspace):
        path = io.checkpoint_path(workspace)
        out(f"Not changed: {path} is already tracked by git, so notes in it would be committed. "
            "Run `git rm --cached .agl/checkpoint.md` (this keeps your file), add .agl/ to .gitignore, "
            "then run this again. Nothing was written.")
        return "tracked"
    out(f"Step mode. Window: {window} tokens. Each step is a fresh chat.")
    if task and _open_position(io, workspace) is None:
        out("Planning. Nothing runs until you type y.")
    elif task:
        out("Open steps are already in the checkpoint. Finishing those first; the new task was not planned.")
    return await step_runner.run_steps(
        task, new_agent=new_agent,
        read_ck=lambda: io.read_checkpoint(workspace),
        write_ck=lambda text: io.write_checkpoint(workspace, text),
        snapshot=lambda: ports.task_report.snapshot(workspace),
        window=window, system_tokens=checkpoint.tokens(MAIN_SYSTEM_PROMPT),
        input_fn=input_fn, out=_Writer(out), now=_now,
        checkpoint_path=str(io.checkpoint_path(workspace)),
        run_test=lambda cmd: io.run_test(cmd, workspace))


async def handle(line: str, *, new_agent: Any, workspace: Any, window: int, ports: Any, out: Any,
                 input_fn: Any) -> str:
    """Run `/steps <task>` typed at the shell. Returns the runner's outcome, or "usage" / "unavailable"."""
    task = line[len(COMMAND):].strip()
    if not task:
        out(USAGE)
        return "usage"
    io = _io(ports, workspace)
    if io is None:
        out("Step mode needs the workspace folder, so it can't run here.")
        return "unavailable"
    return await _run(task, io=io, new_agent=new_agent, workspace=workspace, window=window, ports=ports,
                      out=out, input_fn=input_fn)


async def offer_resume(*, new_agent: Any, workspace: Any, window: int, ports: Any, out: Any,
                       input_fn: Any) -> str:
    """Before the first prompt: when the checkpoint has open steps, ask once. Only y or yes resumes."""
    io = _io(ports, workspace)
    pos = _open_position(io, workspace) if io is not None else None
    if pos is None:
        return "none"
    try:
        answer = input_fn(f"Resume at step {pos[0]} of {pos[1]}? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        return "no"
    if answer.strip().lower() not in ("y", "yes"):
        return "no"
    return await _run("", io=io, new_agent=new_agent, workspace=workspace, window=window, ports=ports,
                      out=out, input_fn=input_fn)
