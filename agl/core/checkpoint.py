"""The shared checkpoint file: render, read back, cap, and merge the pointer block. Pure, no file or git I/O.

The file is `.agl/checkpoint.md` in the user's project. Every coding app reads it first and updates it before it
stops. The layout and wording come from docs/mockups/checkpoint.md. Reads and writes live in agl.app.checkpoint_offer.
"""

import re
from collections import namedtuple

MARKER ="<!-- agl-checkpoint v1 -->"
BEGIN = "<!-- agl-checkpoint:begin -->"
END = "<!-- agl-checkpoint:end -->"
SECTIONS = ("Plan", "Done", "Next", "Files", "Notes")
CAP_TOKENS = 1500  # the C3 target from docs/handover/SPECS.md. It is inferred, not measured.
CHARS_PER_TOKEN = 4  # a rough count: about 4 characters per token
TRIM_NOTE = re.compile(r"^- \((\d+) earlier steps trimmed to keep this file small\)$")
IGNORE_LINE = ".agl/"
IGNORE_FORMS = (".agl", ".agl/", "/.agl", "/.agl/")
NONE_YET = "- (none yet)"  # what render() writes for an empty section. It is a placeholder, not a step.
Fit = namedtuple("Fit", "text trimmed marker over_limit")

TEMPLATE = {
    "Plan": ["The goal in one or two lines, in the user's own words.",
             "The steps, in order, as short checkboxes."],
    "Done": ["[x] Step that is finished, with the commit or file that proves it."],
    "Next": ["[ ] The one step to start with when the app wakes up."],
    "Files": ["`path/to/file.py`: what changed and why, in one line."],
    "Notes": ["Open questions for the user.", "Gotchas the next session must not repeat."],
}

POINTER = "\n".join([
    BEGIN,
    "Before you start, read `.agl/checkpoint.md`. It holds the plan, what is done, and what is next.",
    "Before you stop, update it: plan, done, next, files, notes, and the `updated:` line.",
    "Keep it under about 1,500 tokens. If `HANDOFF.md` exists, read it too for extra context.",
    "Do not merge HANDOFF.md into the checkpoint and do not rename it.",
    END,
])


class PointerError(ValueError):
    """A pointer file has only one of our two marker lines, or more than one block. We never guess, so we stop."""


def tokens(text):
    return len(text) // CHARS_PER_TOKEN


def is_ours(text):
    return MARKER in text


def render(sections, updated):
    lines = ["# Checkpoint", "", MARKER, f"updated: {updated}", ""]
    for name in SECTIONS:
        lines += [f"## {name}", ""]
        lines += [f"- {item}" for item in sections.get(name) or ["(none yet)"]]
        lines.append("")
    return "\n".join(lines)


def parse(text):
    """(updated, sections) read back from a checkpoint. Lines we do not know are skipped."""
    updated, sections, current = "", {name: [] for name in SECTIONS}, None
    for line in text.splitlines():
        if line.startswith("updated: "):
            updated = line[len("updated: "):]
        elif line.startswith("## "):
            title = line[3:].strip()
            current = title if title in sections else None
        elif line.startswith("- ") and current:
            sections[current].append(line[2:])
    return updated, sections


def _done_header(lines):
    return next((i for i, line in enumerate(lines) if line.strip() == "## Done"), None)


def _done_end(lines, start):
    return next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))


def _cap(text, updated):
    """(new text, Done steps trimmed this run). The oldest Done steps go until the text fits CAP_TOKENS. Every other line
    stays as it was. The `updated:` line becomes `updated`, and a note under Done counts the steps dropped so far.
    (None, 0) when dropping Done steps cannot make it fit. Then nothing is removed."""
    lines = [f"updated: {updated}" if line.startswith("updated: ") else line for line in text.splitlines()]
    dropped, start = 0, _done_header(lines)
    if start is None:
        return None, 0
    i = start + 1  # fold an earlier note into the running count
    while i < _done_end(lines, start):
        m = TRIM_NOTE.match(lines[i])
        if m:
            dropped += int(m.group(1))
            del lines[i]
        else:
            i += 1

    def build(body, count):
        out = list(body)
        if count:
            out.insert(start + 1, f"- ({count} earlier steps trimmed to keep this file small)")
        return "\n".join(out) + ("\n" if text.endswith("\n") else "")

    body, trimmed = list(lines), 0
    while True:
        result = build(body, dropped + trimmed)
        if tokens(result) <= CAP_TOKENS:
            return result, trimmed
        step = next((j for j in range(start + 1, _done_end(body, start))
                     if body[j].startswith("- ") and body[j] != NONE_YET), None)
        if step is None:
            return None, 0
        del body[step]
        trimmed += 1


def capped(text, updated):
    """`text` (a checkpoint file) with the oldest Done steps removed until it fits CAP_TOKENS. If it cannot fit that way,
    or no Done step is left to drop, `text` comes back unchanged."""
    new, _ = _cap(text, updated)
    return text if new is None else new


def fit(old, now):
    """The plan for the checkpoint file (`old` is None when there is no file yet), as a Fit. `text` is what to write and
    equals `old` when nothing changes. `marker` is True when our marker line is added. A file that needs the marker and
    is over CAP_TOKENS gets both in one run, so `marker` can come with `trimmed`. `trimmed` counts the Done steps this
    run removes. `over_limit` is True when the file cannot fit by trimming Done. Then `text` is `old`, and nothing is
    removed or added."""
    if old is None or not old.strip():
        return Fit(render(TEMPLATE, now), 0, False, False)
    if not is_ours(old):
        marked = MARKER + "\n" + old
        if tokens(marked) <= CAP_TOKENS:
            return Fit(marked, 0, True, False)
        new, trimmed = _cap(marked, now)
        if new is None:
            return Fit(old, 0, False, True)
        return Fit(new, trimmed, True, False)
    if tokens(old) <= CAP_TOKENS:
        return Fit(old, 0, False, False)
    new, trimmed = _cap(old, now)
    if new is None:
        return Fit(old, 0, False, True)
    return Fit(new, trimmed, False, False)


def next_text(old, now):
    """What the checkpoint file should say now. When it returns `old`, nothing needs writing."""
    return fit(old, now).text


def merge_pointer(text):
    """`text` with our pointer block added, or replaced in place if it is already there. Other lines stay as they are."""
    begins, ends = text.count(BEGIN), text.count(END)
    if begins == 0 and ends == 0:
        head = text.rstrip("\n")
        return (head + "\n\n" if head else "") + POINTER + "\n"
    if begins != 1 or ends != 1 or text.index(END) < text.index(BEGIN):
        raise PointerError("only part of the pointer block is there")
    start = text.index(BEGIN)
    return text[:start] + POINTER + text[text.index(END) + len(END):]


def with_ignore(text):
    """`text` with `.agl/` added to a .gitignore, unless a line already ignores it."""
    if any(line.strip() in IGNORE_FORMS for line in text.splitlines()):
        return text
    return (text if not text or text.endswith("\n") else text + "\n") + IGNORE_LINE + "\n"
