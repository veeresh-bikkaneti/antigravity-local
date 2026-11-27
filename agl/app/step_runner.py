"""Step runner: plan a task, run each step in a fresh chat, check it, and save the checkpoint after each step.

Standard library plus agl.core only. The shell owns the terminal; this module writes to `out` and asks through `input_fn`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agl.core import steps, task_report

PLAN_PROMPT = ("Split this task into 2 to 8 short steps, one per line, numbered 1. 2. 3.\n"
               "Reply with the numbered list only.\nTask: {task}\n")
CHECK_PROMPT = ("Answer yes or no only. Is this step done?\n"
                "Step: {step}\nFiles created or changed: {files}\n")
ACCEPT_QUESTION = "Accept this plan? [y/N] "
RETRY_QUESTION = "Retry, skip or stop? [r/s/q] "
PLAN_DROPPED = "Plan dropped. Nothing was written."
TOO_BIG = "This step does not fit the window. It was not sent."
NO_FILES = "(none)"
NO_FILE_CHANGE = "No file was created or changed."
MIN_STEPS, MAX_STEPS = 2, 8
_STEP_LINE = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")


def parse_plan(reply: str) -> list[str]:
    """The step texts from a numbered reply, or [] unless 2 to 8 steps came back."""
    found = [m.group(1) for m in map(_STEP_LINE.match, reply.splitlines()) if m]
    return found if MIN_STEPS <= len(found) <= MAX_STEPS else []


def _file_news(created: list[str], changed: list[str]) -> str:
    """`a.html is new. b.py changed.` for the files a step touched, or "" when there are none."""
    parts = []
    if created:
        parts.append(f"{', '.join(created)} {'is' if len(created) == 1 else 'are'} new.")
    if changed:
        parts.append(f"{', '.join(changed)} changed.")
    return " ".join(parts)


@dataclass
class _Run:
    new_agent: Any
    read_ck: Any
    write_ck: Any
    snapshot: Any
    window: int
    system_tokens: int
    input_fn: Any
    out: Any
    now: Any
    checkpoint_path: str
    number: int = 0
    total: int = 0

    def say(self, line: str) -> None:
        self.out.write(line + "\n")

    def next_line(self, head: str) -> str:
        """`head`, plus where the run goes next when a step is still open."""
        pos = steps.position(self.read_ck())
        return head if pos is None else f"{head} Next is step {pos[0]}."


async def _ask(new_agent: Any, prompt: str, out: Any = None) -> str:
    """Send one prompt in a fresh chat and return the reply. Stream it to `out` when given."""
    parts = []
    if out is not None:
        out.write("Agent > ")
    async with new_agent() as agent:
        async for chunk in await agent.chat(prompt):
            parts.append(chunk)
            if out is not None:
                out.write(chunk)
    if out is not None:
        out.write("\n")
    return "".join(parts)


def _accepted(run: _Run) -> bool:
    try:
        answer = run.input_fn(ACCEPT_QUESTION)
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("y", "yes")


async def _plan(run: _Run, task: str) -> bool:
    """Ask for a plan, show it, and save it only on a yes. False means declined, nothing written."""
    try:
        plan = parse_plan(await _ask(run.new_agent, PLAN_PROMPT.format(task=task)))
    except KeyboardInterrupt:
        plan = []
    if not plan:
        run.say(PLAN_DROPPED)
        return False
    for number, step in enumerate(plan, 1):
        run.say(f"  {number}. {step}")
    if not _accepted(run):
        run.say(PLAN_DROPPED)
        return False
    text = steps.with_plan(run.read_ck(), plan, run.now())
    run.write_ck(text)
    run.say(f"Wrote {run.checkpoint_path} with {len(steps.open_steps(text))} open steps.")
    return True


async def _check(run: _Run, step: str, before: dict, after: dict) -> tuple[bool, list[str], list[str]]:
    """Ask a fresh chat whether the step is done. Returns (passed, created, changed)."""
    created, changed = task_report.summarize(before, after)
    files = ", ".join(created + changed) or NO_FILES
    reply = await _ask(run.new_agent, CHECK_PROMPT.format(step=step, files=files))
    return reply.strip().lower().startswith("yes"), created, changed


async def _attempt(run: _Run, step: str) -> str:
    """Run one step once. Returns "ok", "failed" (check said no) or "too_big"."""
    prompt = steps.step_prompt(run.read_ck(), step, window=run.window,
                               system_tokens=run.system_tokens)
    if prompt is None:
        run.say(TOO_BIG)
        return "too_big"
    before = run.snapshot()
    await _ask(run.new_agent, prompt, run.out)
    after = run.snapshot()
    passed, created, changed = await _check(run, step, before, after)
    if not passed:
        nothing = not (created or changed)
        run.say("Check failed. " + NO_FILE_CHANGE if nothing else "Check failed.")
        return "failed"
    run.say(" ".join(line for line in ("Check passed.", _file_news(created, changed)) if line))
    run.write_ck(steps.mark_done(run.read_ck(), step, run.now()))
    run.say(run.next_line(f"Saved. Step {run.number} is done."))
    return "ok"


def _retry_choice(run: _Run) -> str:
    try:
        return run.input_fn(RETRY_QUESTION).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "q"


async def _run_step(run: _Run, step: str) -> str:
    """Run a step until it passes, is skipped, does not fit, or the user stops. Returns the outcome."""
    while True:
        run.say(f"--- step {run.number} of {run.total} ---")
        run.say(step)
        result = await _attempt(run, step)
        if result != "failed":
            return result
        choice = _retry_choice(run)
        if choice == "r":
            continue
        if choice == "s":
            run.write_ck(steps.mark_done(run.read_ck(), step, run.now(), skipped=True))
            run.say(run.next_line(f"Skipped step {run.number}."))
            return "ok"
        run.say(f"Stopped. Step {run.number} is still open.")
        return "stopped"


async def _drive(run: _Run) -> str:
    """Run open steps in order until none are left or one stops the run."""
    while True:
        pos = steps.position(run.read_ck())
        if pos is None:
            run.say(f"All {run.total} steps are done.")
            return "done"
        run.number, run.total = pos
        result = await _run_step(run, steps.open_steps(run.read_ck())[0])
        if result != "ok":
            return result


def _interrupted(number: int) -> str:
    head = f"Interrupted on step {number}."
    saved = [str(n) for n in range(1, number)]
    if not saved:
        return f"{head} Nothing is saved yet."
    if len(saved) == 1:
        return f"{head} Step 1 is saved."
    return f"{head} Steps {', '.join(saved[:-1])} and {saved[-1]} are saved."


async def run_steps(
    task: str,
    *,
    new_agent: Any,
    read_ck: Any,
    write_ck: Any,
    snapshot: Any,
    window: int,
    system_tokens: int,
    input_fn: Any,
    out: Any,
    now: Any,
    checkpoint_path: str,
) -> str:
    """Plan if nothing is open, then run the open steps.

    Returns "done", "stopped", "declined" or "too_big".
    """
    run = _Run(new_agent, read_ck, write_ck, snapshot, window, system_tokens, input_fn, out, now,
               checkpoint_path)
    try:
        if steps.position(read_ck()) is None and not await _plan(run, task):
            return "declined"
        return await _drive(run)
    except KeyboardInterrupt:
        run.out.write("\n")
        run.say(_interrupted(run.number))
        return "stopped"
