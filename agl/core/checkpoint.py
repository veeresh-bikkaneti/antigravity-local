"""The shared checkpoint file: render, read back, cap, and merge the pointer block. Pure, no file or git I/O.

The file is `.agl/checkpoint.md` in the user's project. Every coding app reads it first and updates it before it
stops. The layout and wording come from docs/mockups/checkpoint.md. Reads and writes live in agl.app.checkpoint_offer.
"""

import re

MARKER = "<!-- agl-checkpoint v1 -->"
BEGIN = "<!-- agl-checkpoint:begin -->"
END = "<!-- agl-checkpoint:end -->"
SECTIONS = ("Plan", "Done", "Next", "Files", "Notes")
CAP_TOKENS = 1500  # the C3 target from docs/handover/SPECS.md. It is inferred, not measured.
CHARS_PER_TOKEN = 4  # a rough count: about 4 characters per token
TRIM_NOTE = re.compile(r"^- \((\d+) earlier steps trimmed to keep this file small\)$")
IGNORE_LINE = ".agl/"
IGNORE_FORMS = (".agl", ".agl/", "/.agl", "/.agl/")

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


def capped(text, updated):
    """`text` (a checkpoint file) with the oldest Done steps removed until it fits CAP_TOKENS. Every other line stays
    as it was: unknown sections, free text, Plan, Next, Files and Notes. The `updated:` line becomes `updated`.
    A note under Done counts the steps dropped so far. If no Done step is left to drop, `text` comes back unchanged."""
    lines = [f"updated: {updated}" if line.startswith("updated: ") else line for line in text.splitlines()]
    dropped, start = 0, _done_header(lines)
    if start is not None:  # fold an earlier note into the running count
        i = start + 1
        while i < _done_end(lines, start):
            m = TRIM_NOTE.match(lines[i])
            if m:
                dropped += int(m.group(1))
                del lines[i]
            else:
                i += 1

    def build(count):
        body = list(lines)
        if count and start is not None:
            body.insert(start + 1, f"- ({count} earlier steps trimmed to keep this file small)")
        return "\n".join(body) + ("\n" if text.endswith("\n") else "")

    trimmed = 0
    while start is not None and tokens(build(dropped + trimmed)) > CAP_TOKENS:
        step = next((j for j in range(start + 1, _done_end(lines, start)) if lines[j].startswith("- ")), None)
        if step is None:
            break
        del lines[step]
        trimmed += 1
    if not trimmed:
        return text
    return build(dropped + trimmed)


def next_text(old, now):
    """What the checkpoint file should say now. When it returns `old`, nothing needs writing."""
    if old is None or not is_ours(old):
        return render(TEMPLATE, now)
    if tokens(old) <= CAP_TOKENS:
        return old
    return capped(old, now)


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
