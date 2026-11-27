"""Pick a local model with a short menu instead of silently taking the first one. Standard library only.

Why this exists: run.py used to grab whatever was already installed and call it "most capable".
Models move fast, so we show what is installed plus a short list of newer candidates, say what fits
this machine, and let the human choose. Enter keeps the current pick, so it costs one keypress.

the pure parts (catalog, tag shapes, fit and speed labels, menu building and its row helpers)
live at agl.core.menu; this file keeps the HTTP functions and the interactive chooser and re-exports
the moved names for old imports.
"""
import json
import re
import urllib.error

from agl.core import capabilities
from agl.core.menu import (  # noqa: F401
    CATALOG,
    CATALOG_VERIFIED,
    FIT_HEADROOM,
    HF_PREFIXES,
    HF_ROW_TAG,
    LEGACY_HEADROOM,
    MEDIA_ROW_TAG,
    MORE_ROW_TAG,
    QUANT_RE,
    REPO_RE,
    SPLIT_RAM_SHARE,
    TOP_DOWNLOADS,
    _badges,
    _badge_list,
    _has_tools,
    _has_twin,
    _is_pick,
    _is_repo_id,
    _media_row,
    _norm,
    _note_text,
    _one_row_per_file,
    _sized,
    _visible,
    _word,
    build_menu,
    fit_label,
    is_hf_tag,
    parse_hf_tag,
    speed_label,
)
from agl.platform import http, hub, registry
# The menu render group lives in agl/ui/model_menu.py; these re-exports keep old imports working.
from agl.ui.model_menu import (  # noqa: F401
    FIT_TEXT,
    LEGEND,
    MAX_PICK_DIGITS,
    _gave_up,
    _row_line,
    _search_pick,
    _search_size_text,
    render,
)

TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*(:[a-z0-9._-]+)?$")


def _hf_api_model(user, repo, timeout=4):
    """The Hub's model record for user/repo, fetched through the same-host opener. Returns (status, data):
    'ok' with a dict, 'missing' (a 404), or 'unknown' (offline, private or gated, odd reply; data None).
    Sends only the repo name. Both hf_check and hf_repo_info read through here."""
    return hub._hf_api_model(user, repo, timeout=timeout)  # moved to agl.platform.hub


def hf_check(tag, timeout=4):
    """Ask the Hugging Face API about an hf.co tag. Returns (status, detail), status one of:
    'ok'       the repo is there (and has a .gguf for the quant, when one was given)
    'missing'  the repo is a 404: refuse it
    'no_quant' the repo exists but no .gguf matches the quant; detail = the quants it does have
    'bad_tag'  not hf.co/user/repo[:quant]
    'unknown'  could not tell (offline, private or gated repo, odd reply): allow it, like the Ollama registry check
    Sends only the repo name."""
    return hub.hf_check(tag, timeout=timeout)  # moved to agl.platform.hub


def hf_repo_info(user, repo, timeout=4):
    """{'status': 'ok'|'missing'|'unknown', 'gated': bool, 'license': str|None} for a Hugging Face repo.
    Sends only the repo name. gated can be False, True, 'auto' or 'manual' on the Hub: anything truthy counts."""
    return hub.hf_repo_info(user, repo, timeout=timeout)  # moved to agl.platform.hub


_SameHostOnly = http._SameHostOnly  # moved to agl.platform.http
_STATE = {"offline": False}  # set when the Hub cannot be reached; later calls in the run stop asking


def hf_tree_files(user, repo, timeout=6, max_pages=5):
    """[{'name', 'size'}] for every file in the repo (sizes in bytes, from the LFS size when there is one).
    Follows the Link: rel=next header up to max_pages, on huggingface.co only. Any failure returns []."""
    return hub.hf_tree_files(user, repo, timeout=timeout, max_pages=max_pages,
                              state=_STATE)  # moved to agl.platform.hub


def _ask_hf_tag(input_fn, out, fallback, search_fn=None, validate_fn=None, default_tag=None, default_label=None):
    """The Hugging Face row was picked: ask for a tag, or for words to search for. Blank returns the fallback.
    A tag that validate_fn rejects prints why and asks again. Three bad tries print one line and give the fallback."""
    prompt = "       hf.co tag (hf.co/user/repo:quant)" + (", or words to search for > " if search_fn else " > ")
    for _ in range(3):
        try:
            raw = input_fn(prompt).strip().lower()
        except EOFError:
            return fallback
        if not raw:
            return fallback
        if is_hf_tag(raw) and TAG_RE.match(raw):
            problem = validate_fn(raw) if validate_fn else None
            if problem is None:
                return raw
            out(problem)
            continue
        if search_fn and not is_hf_tag(raw) and raw not in YES_NO:
            results = search_fn(raw)
            if not results:
                out("       No GGUF models found (or Hugging Face could not be reached). Try other words.")
                continue
            picked = _search_pick(results, input_fn, out)
            if picked:
                problem = validate_fn(picked) if validate_fn else None
                if problem is None:
                    return picked
                out(problem)
            continue
        out("       That is not a Hugging Face tag. Use the form hf.co/user/repo:quant.")
    _gave_up(out, fallback, default_tag, default_label)
    return fallback


YES_NO = {"y", "yes", "n", "no"}


def _sub_list(rows, out):
    """Print a numbered side list (more downloads, or media). The numbers restart at 1 inside it."""
    width = min(50, max([len(m["tag"]) for m in rows] or [0]))
    for i, m in enumerate(rows, 1):
        if m.get("media"):
            b = capabilities.format_badges(m.get("badges"))
            out(f"       {i:>2}. {m['tag']:<{width}}  {b + '  ' if b else ''}{m.get('note') or ''}".rstrip())
        else:
            out(_row_line(i, m, None, width))


def _more_pick(menu, input_fn, out, validate_fn):
    """The 'More downloads' side list. Returns a tag, or None for 'go back to the main list'."""
    rows = [m for m in menu if m.get("hidden") and not m.get("media")]
    _sub_list(rows, out)
    for _ in range(3):
        try:
            raw = input_fn("       Pick a number, or Enter to go back > ").strip()
        except EOFError:
            return None
        if not raw:
            return None
        if raw.isascii() and raw.isdigit() and len(raw) <= MAX_PICK_DIGITS and 1 <= int(raw) <= len(rows):
            problem = validate_fn(rows[int(raw) - 1]["tag"]) if validate_fn else None
            if problem is None:
                return rows[int(raw) - 1]["tag"]
            out(problem)
            continue
        out(f"       Pick 1 to {len(rows)}, or press Enter to go back.")
    return None


def _media_rows(row, menu):
    """Media rows for the side list: the ones already in the menu plus whatever the lazy loader finds now."""
    rows = [m for m in menu if m.get("media")]
    if row.get("loader"):
        known = set(row.get("known") or ())
        try:
            found = row["loader"]() or []
        except Exception:  # noqa: BLE001 - a failed lookup is an empty list, never a crash
            found = []
        for r in found:
            if isinstance(r, dict) and r.get("tag") and _norm(r["tag"]) not in known:
                known.add(_norm(r["tag"]))
                rows.append(_media_row(r))
    return rows


def _media_loop(row, menu, input_fn, out):
    """The 'Image and video models' side list. A number prints how to run that model and stays here.
    Enter goes back to the main list. None of this is a bad try."""
    rows = _media_rows(row, menu)
    if not rows:
        out("       No image or video models found (or Hugging Face could not be reached).")
        return
    out("       Image and video models. This tool does not run them, so none of these can be picked.")
    _sub_list(rows, out)
    wrong = 0
    while wrong < 3:
        try:
            raw = input_fn("       Type a number to see how to run it, or Enter to go back > ").strip()
        except EOFError:
            return
        if not raw:
            return
        if raw.isascii() and raw.isdigit() and len(raw) <= MAX_PICK_DIGITS and 1 <= int(raw) <= len(rows):
            out(f"       {rows[int(raw) - 1].get('hint') or 'Media models are not used by coding agents.'}")
            continue
        wrong += 1
        out(f"       Pick 1 to {len(rows)}, or press Enter to go back.")


def _pick_row(menu, row, input_fn, out, fallback, search_fn, validate_fn, default_tag, default_label):
    """Act on a numbered menu row. Returns ("return", tag), ("redraw", None) or ("try", None when it cost a try)."""
    if row.get("hf"):
        return "return", _ask_hf_tag(input_fn, out, fallback, search_fn, validate_fn, default_tag, default_label)
    if row.get("more"):
        picked = _more_pick(menu, input_fn, out, validate_fn)
        return ("return", picked) if picked else ("redraw", None)
    if row.get("media_row"):
        _media_loop(row, menu, input_fn, out)
        return "redraw", None
    problem = validate_fn(row["tag"]) if validate_fn else None
    if problem is None:
        return "return", row["tag"]
    out(problem)
    return "try", None


def _number_answer(menu, raw, input_fn, out, fallback, search_fn, validate_fn, default_tag, default_label):
    """A typed number. Same returns as _pick_row; a number out of range prints why and costs one try."""
    rows = _visible(menu)
    n = int(raw) if len(raw) <= MAX_PICK_DIGITS else 0  # int() refuses 4300+ digits; no menu is that long
    if 1 <= n <= len(rows):
        return _pick_row(menu, rows[n - 1], input_fn, out, fallback, search_fn, validate_fn, default_tag, default_label)
    out(f"       Pick 1 to {len(rows)}, or type a tag.")
    return "try", None


def _tag_answer(raw, out, validate_fn):
    """A typed tag that validate_fn must accept. Same returns as _pick_row; a refusal costs one try."""
    problem = validate_fn(raw) if validate_fn else None
    if problem is None:
        return "return", raw
    out(problem)
    return "try", None


def choose(menu, default_tag, input_fn=None, out=print, backend="ollama", search_fn=None, validate_fn=None,
           default_label=None, result=None):
    """Return the chosen tag. Bad input re-asks, up to 3 tries. After 3 bad tries the default is used and one line
    says so, naming it with `default_label`. `validate_fn(tag)` vets a typed tag or a numbered pick: None when it is
    fine, else the line to print that says why not (for example "not on the registry"). Without it every tag passes.
    The main list shows only the rows not marked hidden. "More downloads" and "Image and video models" open side
    lists; looking at those is never a bad try, and Enter in them goes back to the main list.
    Pass a dict as `result` to learn how it ended: result["how"] is "enter", "pick", "gave_up" or "eof"."""
    input_fn = input_fn or input  # looked up now, not at import, so a terminal or a test can swap it
    how = result if isinstance(result, dict) else {}
    how["how"] = "pick"
    fallback = default_tag or next((m["tag"] for m in menu if _is_pick(m) and not m.get("hidden")), None)
    tries = 0
    show = True
    while tries < 3:
        if show:
            for line in render(menu, default_tag, backend):
                out(line)
            show = False
        try:
            raw = input_fn("       > ").strip()
        except EOFError:  # input closed (piped, CI): same as Enter. Ctrl+C is NOT caught: the caller must stop.
            how["how"] = "eof"
            return fallback
        if not raw:
            how["how"] = "enter"
            return fallback
        if raw.lower() in YES_NO:  # "y" is a valid-looking tag, but nobody means it as one
            out(f"       That looks like a yes/no answer. Type a number, a model tag, or press Enter for {fallback}.")
            tries += 1
            continue
        if raw.isascii() and raw.isdigit():
            kind, tag = _number_answer(menu, raw, input_fn, out, fallback, search_fn, validate_fn,
                                       default_tag, default_label)
            if kind == "return":
                return tag
            if kind == "redraw":
                show = True
                continue
            tries += 1
            continue
        if TAG_RE.match(raw.lower()):
            kind, tag = _tag_answer(raw.lower(), out, validate_fn)
            if kind == "return":
                return tag
            tries += 1
            continue
        out("       That is not a tag. Use a number, or something like qwen3.6:27b.")
        tries += 1
    _gave_up(out, fallback, default_tag, default_label)
    how["how"] = "gave_up"
    return fallback


def tag_exists(tag, timeout=4):
    """True/False from the public Ollama registry, None when we cannot tell (offline). Sends only the tag."""
    return registry.tag_exists(tag, timeout=timeout)  # moved to agl.platform.registry


def registry_reachable(timeout=3):
    """True when registry.ollama.ai answers at all (any HTTP reply, even a 401), False when we cannot reach it.
    Used by --check-upgrades to say "couldn't check" instead of guessing. Sends no model name."""
    return registry.registry_reachable(timeout=timeout)  # moved to agl.platform.registry

