"""Stage 4's copy offer (docs/mockups/real-window.md): one question, and on a yes a copy of the model with a
bigger num_ctx. The copy reuses the weights; nothing is pulled.

Only `y` or `yes` goes on. Anything else, end of input included, keeps the model and writes nothing.
`create(tag, new_tag, num_ctx)` is injected: it returns None on success or the error text. Every message
goes through `out`.
"""

from agl.core import window_fit

INDENT = "       "
FALLBACK_REASON = "the create command failed"


def _yes(input_fn, prompt):
    try:
        answer = input_fn(prompt)
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("y", "yes")


def _reason(error):
    """The error cut to one short line, or the fallback when it is empty."""
    lines = [ln.strip() for ln in str(error or "").splitlines() if ln.strip()]
    text = lines[-1] if lines else FALLBACK_REASON
    text = text.rstrip(".")
    return text if len(text) <= 55 else text[:52].rstrip() + "..."


def offer(tag, target, *, create, input_fn, out):
    """Ask once. Returns the new tag after a copy is made, else None."""
    new_tag = window_fit.copy_name(tag, target)
    question = f"{INDENT}Make {window_fit.article(target)} {target // 1000}K copy now? It reuses your weights. No download. [y/N] "
    if not _yes(input_fn, question):
        out(f"{INDENT}Keeping {tag}. I'll offer the copy again next start.")
        return None
    error = create(tag, new_tag, target)
    if error is not None:
        out(f"{INDENT}Could not make {new_tag}. Keeping {tag}.")
        out(f"{INDENT}Reason: {_reason(error)}. Nothing was downloaded.")
        return None
    out(f"{INDENT}Made {new_tag}. It uses the weights you already have.")
    out(f"{INDENT}This run will use {new_tag}, with {window_fit.article(target)} {target:,} token window.")
    return new_tag
