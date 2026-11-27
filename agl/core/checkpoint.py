"""The shared checkpoint file: render, read back, cap, and merge the pointer block. Pure, no file or git I/O.

The file is `.agl/checkpoint.md` in the user's project. Every coding app reads it first and updates it before it
stops. The layout and wording come from docs/mockups/checkpoint.md. Reads and writes live in agl.app.checkpoint_offer.
"""

MARKER = "<!-- agl-checkpoint v1 -->"
BEGIN = "<!-- agl-checkpoint:begin -->"
END = "<!-- agl-checkpoint:end -->"
SECTIONS = ("Plan", "Done", "Next", "Files", "Notes")
CAP_TOKENS = 1500  # the C3 target from docs/handover/SPECS.md. It is inferred, not measured.
CHARS_PER_TOKEN = 4  # a rough count: about 4 characters per token
ONE_LINE = 160
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


def _one_line(item):
    flat = " ".join(str(item).split())
    return flat if len(flat) <= ONE_LINE else flat[: ONE_LINE - 3] + "..."


def capped(sections, updated):
    """The checkpoint text, trimmed to stay under CAP_TOKENS. Each item becomes one line first. Then the oldest
    Done steps go, with a note saying how many. Plan and Next are never dropped."""
    clean = {name: [_one_line(i) for i in sections.get(name, [])] for name in SECTIONS}
    done, dropped = clean["Done"], 0
    while True:
        note = [f"({dropped} earlier steps trimmed to keep this file small)"] if dropped else []
        text = render(dict(clean, Done=note + done), updated)
        if tokens(text) <= CAP_TOKENS or not done:
            return text
        done, dropped = done[1:], dropped + 1


def next_text(old, now):
    """What the checkpoint file should say now. When it returns `old`, nothing needs writing."""
    if old is None or not is_ours(old):
        return render(TEMPLATE, now)
    if tokens(old) <= CAP_TOKENS:
        return old
    return capped(parse(old)[1], now)


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
