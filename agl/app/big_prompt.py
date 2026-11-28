"""The shell's big-prompt question (docs/mockups/real-window.md section 5).

A typed prompt over the running window is never cut and never refused. The shell asks once whether to
send it. Empty Enter, `y` or `yes` sends it unchanged. `n`, `no` or end of input holds it, because a closed
pipe is not a typed Enter. `/steps` hands the prompt to step mode as its task. The model is not changed on
any path. Every message goes through `out`.
"""

from agl.core import checkpoint

INDENT = "       "
SEND, HOLD, STEPS = "send", "hold", "steps"


def known_window(checked):
    """The window stage 4 read, `(tokens, source, ...)`, or None when it read nothing."""
    if isinstance(checked, tuple) and checked and isinstance(checked[0], int) and checked[0] > 0:
        return checked[0]
    return None


def ask(text, window, *, input_fn, out):
    """SEND, HOLD or STEPS for one typed prompt. Asks only when the prompt is over a known window."""
    if not window or checkpoint.tokens(text) <= window:
        return SEND
    out(f"{INDENT}Over the {window:,} window, so the model may forget the start.")
    try:
        answer = input_fn(f"{INDENT}Send anyway? [Y/n] (or type /steps) ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = None
    if answer in ("", "y", "yes"):
        return SEND
    if answer == "/steps":
        return STEPS
    out(f"{INDENT}Not sent. Nothing was cut, and the model was not changed.")
    return HOLD
