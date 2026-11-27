"""The terminal model menu: rows, the printed list and the search picker. Standard library and agl.core only.

Moved here from model_wizard.py, which re-exports these names. The answer loop follows in a second PR.
"""
from agl.core import capabilities
from agl.core.menu import (
    CATALOG_VERIFIED,
    MEDIA_ROW_TAG,
    MORE_ROW_TAG,
    _is_pick,
    _is_repo_id,
    _norm,
    _visible,
    _word,
)

MAX_PICK_DIGITS = 6


FIT_TEXT = {"gpu": "fits in GPU", "split": "part on CPU", "too big": "too big"}
LEGEND = "Fast = fits in your graphics card · Moderate = part on CPU · Slow = mostly CPU (estimate from size and memory)"


def _row_line(i, m, default_tag, width):
    """One numbered row: number, name, speed, size, one word, then `current` or a short recommendation."""
    current = _norm(m["tag"]) == _norm(default_tag or "")
    star = "*" if current else " "
    if m.get("size_gb") is None:
        size = "size unknown" if not m.get("installed") else ""
    else:
        size = f"~{m['size_gb']:.1f} GB est." if m.get("size_source") == "estimate" else f"{m['size_gb']:.1f} GB"
    note = m.get("note") or ""
    suffix = "  ".join(x for x in ("current" if current else "", note if note.startswith("recommended") else "") if x)
    if m.get("twin"):
        suffix = (suffix + "  " if suffix else "") + m["twin"]
    cols = f"{m.get('speed') or '':<8}  {size:>12}  {_word(m):<9}  {suffix}"
    return f"       {star}{i:>2}. {m['tag']:<{width}}  {cols}".rstrip()


def render(menu, default_tag, backend="ollama"):
    rows = _visible(menu)
    width = min(50, max([len(m["tag"]) for m in rows if _is_pick(m)] or [0]))
    lines = []
    section = None
    for i, m in enumerate(rows, 1):
        if not _is_pick(m):
            if section != "special":
                section = "special"
                lines.append("")
            if m.get("more"):
                n = sum(1 for r in menu if r.get("hidden") and not r.get("media"))
                lines.append(f"        {i:>2}. {MORE_ROW_TAG} ({n} more)")
            elif m.get("media_row"):
                lines.append(f"        {i:>2}. {MEDIA_ROW_TAG} (not for coding)")
            else:
                lines.append(f"        {i:>2}. {m['note']}")
            continue
        want = "installed" if m["installed"] else "download"
        if want != section:
            if section:
                lines.append("")
            section = want
            lines.append("       " + (("Loaded on your server" if backend == "openai" else "On this PC, no download")
                                       if want == "installed" else "Worth downloading"))
        lines.append(_row_line(i, m, default_tag, width))
    if lines:
        lines.append("")
    lines.append(f"       {LEGEND}")
    lines.append(f"       tools = can edit files. Download list checked {CATALOG_VERIFIED}, not yet run through this project's agent loop.")
    keep = (f"Enter keeps {default_tag}" if default_tag
            else "Enter picks 1" if rows else "Enter continues with the automatic pick")
    what = "a model id your server lists" if backend == "openai" else "any Ollama tag"
    lines.append(f"       {keep}. Or type a number, or {what}.")
    return lines


def _search_size_text(r):
    """'  Q4_K_M 2.4 GB download' for a search row that was sized, '' when it was not."""
    if r.get("size_gb") is None:
        return ""
    approx = "~" if r.get("size_source") == "estimate" else ""
    quant = f"{r['quant']} " if r.get("quant") else ""
    tail = " (estimate)" if r.get("size_source") == "estimate" else ""
    return f"  {quant}{approx}{r['size_gb']:.1f} GB download{tail}"


def _search_pick(results, input_fn, out):
    """Show Hugging Face search results with their badges and let the user pick one. Returns hf.co/<repo> or None."""
    shown = [r for r in results if _is_repo_id(r.get("repo"))][:10]  # malformed repos are skipped before numbering
    for i, r in enumerate(shown, 1):
        badge_text = f"  ({capabilities.format_badges(r.get('badges'))})" if r.get("badges") else ""
        downloads = f"  {r['downloads']:,} downloads" if isinstance(r.get("downloads"), int) else ""
        out(f"       {i:>2}. {r['repo']}{badge_text}{downloads}{_search_size_text(r)}")
    out("       (a ? after a badge is a guess from the chat template; run python run.py --probe to check it)")
    try:
        raw = input_fn("       Pick a number, or Enter to go back > ").strip()
    except EOFError:
        return None
    if raw.isascii() and raw.isdigit() and len(raw) <= MAX_PICK_DIGITS and 1 <= int(raw) <= len(shown):
        return "hf.co/" + shown[int(raw) - 1]["repo"].lower()
    return None


def _gave_up(out, fallback, default_tag, default_label=None):
    """One line after three bad tries: which model we use instead, and why we stopped asking.
    `default_label` says what the default is ("current model" or "recommended pick"); the caller knows, we don't."""
    if not fallback:
        out("       No valid pick after 3 tries, using the automatic pick.")
        return
    if fallback == default_tag:
        label = default_label or "current model"
    else:
        label = "first option"
    out(f"       No valid pick after 3 tries, using {fallback} ({label}).")
