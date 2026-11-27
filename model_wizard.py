"""Pick a local model with a short menu instead of silently taking the first one. Standard library only.

Why this exists: run.py used to grab whatever was already installed and call it "most capable".
Models move fast, so we show what is installed plus a short list of newer candidates, say what fits
this machine, and let the human choose. Enter keeps the current pick, so it costs one keypress.

the pure parts (catalog, tag shapes, fit and speed labels, menu building and its row helpers)
live at agl.core.menu, and the terminal menu lives at agl/ui/model_menu.py. This file keeps the HTTP
shims and re-exports the moved names for old imports.
"""
import json
import urllib.error

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
# The terminal menu (render group and answer loop) lives in agl/ui/model_menu.py; these re-exports keep old imports working.
from agl.ui.model_menu import (  # noqa: F401
    FIT_TEXT,
    LEGEND,
    MAX_PICK_DIGITS,
    TAG_RE,
    YES_NO,
    _ask_hf_tag,
    _gave_up,
    _media_loop,
    _media_rows,
    _more_pick,
    _number_answer,
    _pick_row,
    _row_line,
    _search_pick,
    _search_size_text,
    _sub_list,
    _tag_answer,
    choose,
    render,
)


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


def tag_exists(tag, timeout=4):
    """True/False from the public Ollama registry, None when we cannot tell (offline). Sends only the tag."""
    return registry.tag_exists(tag, timeout=timeout)  # moved to agl.platform.registry


def registry_reachable(timeout=3):
    """True when registry.ollama.ai answers at all (any HTTP reply, even a 401), False when we cannot reach it.
    Used by --check-upgrades to say "couldn't check" instead of guessing. Sends no model name."""
    return registry.registry_reachable(timeout=timeout)  # moved to agl.platform.registry

