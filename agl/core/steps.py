"""Step core: read and mark the checkpoint one step at a time, and build the prompt for each step. Pure, no file or git I/O."""

from agl.core import checkpoint

SKIPPED = "(skipped) "
STEP_PROMPT = (
    "You are doing one step of a larger task. Do only this step.\n"
    "Checkpoint so far:\n{checkpoint}\n\nThis step: {step}\n"
)
EMPTY = "(none yet)"
OPEN, DONE = "[ ] ", "[x] "
_EXAMPLE_DONE = checkpoint.TEMPLATE["Done"][0]  # the template's sample line, not a real step


def _items(text, section):
    """The items of one section, without the "(none yet)" placeholder."""
    return [item for item in checkpoint.parse(text)[1][section] if item != EMPTY]


def _real_done(items):
    """Done items without the two placeholders: "(none yet)" and the template's sample line."""
    return [item for item in items if item not in (EMPTY, _EXAMPLE_DONE)]


def _open(plan):
    return [item[len(OPEN):] for item in plan if item.startswith(OPEN)]


def open_steps(text):
    """The Plan steps that are not done yet, in order."""
    return _open(_items(text, "Plan"))


def done_steps(text):
    """The finished steps, oldest first. A skipped step keeps its "(skipped) " prefix."""
    return [item[len(DONE):] for item in _real_done(_items(text, "Done")) if item.startswith(DONE)]


def _trimmed(text):
    """How many Done steps earlier runs dropped, from the note the cap leaves behind."""
    notes = (checkpoint.TRIM_NOTE.match("- " + item) for item in _items(text, "Done"))
    return sum(int(m.group(1)) for m in notes if m)


def position(text):
    """(number of the next open step, total steps), done and open both counted. None when nothing is open."""
    opened = open_steps(text)
    if not opened:
        return None
    finished = len(done_steps(text)) + _trimmed(text)
    return finished + 1, finished + len(opened)


def with_plan(text, steps, now):
    """`text` with `steps` as the open Plan and Next on the first one. The goal and other Plan lines stay."""
    _, sections = checkpoint.parse(text)
    kept = [item for item in sections["Plan"] if item != EMPTY and not item.startswith((OPEN, DONE))]
    sections["Plan"] = kept + [OPEN + step for step in steps]
    sections["Next"] = [OPEN + steps[0]] if steps else []
    sections["Done"] = _real_done(sections["Done"])  # gone before the cap can trim it and count it as a step
    return checkpoint.capped(checkpoint.render(sections, now), now)


def mark_done(text, step, now, *, skipped=False):
    """`text` with `step` moved from Plan to Done, and Next on the next open step (or cleared)."""
    _, sections = checkpoint.parse(text)
    if OPEN + step not in sections["Plan"]:
        return text  # not an open step (unknown or already done): nothing to tick
    sections["Plan"].remove(OPEN + step)  # one box per call, so twin steps each get their turn
    finished = DONE + (SKIPPED if skipped else "") + step
    sections["Done"] = _real_done(sections["Done"]) + [finished]
    opened = _open(sections["Plan"])
    sections["Next"] = [OPEN + opened[0]] if opened else []
    return checkpoint.capped(checkpoint.render(sections, now), now)


def step_prompt(text, step, *, window, system_tokens, reply_reserve=1024):
    """The prompt for one step, or None when it would not fit in `window`. Nothing is trimmed to make it fit."""
    prompt = STEP_PROMPT.format(checkpoint=text, step=step)
    if system_tokens + checkpoint.tokens(prompt) + reply_reserve > window:
        return None
    return prompt
