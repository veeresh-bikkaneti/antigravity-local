"""How big is a download, before you say yes. Standard library only.

Order for an Ollama tag: the registry manifest (the real layer sizes), then our own curated list, then an estimate
from the parameter count in the tag. An estimate is always labelled "(estimate)". Nothing here downloads a
model; it reads a small JSON manifest, and only from registry.ollama.ai.
"""
import re
import time
import urllib.parse

import model_wizard
import quant_pick
from agl.platform import http, registry

REGISTRY = "https://registry.ollama.ai/v2/"
MANIFEST_ACCEPT = ("application/vnd.docker.distribution.manifest.v2+json, "
                   "application/vnd.oci.image.manifest.v1+json")
DEFAULT_BPW = 4.5  # Ollama's default tags are mostly Q4_K_M, about 4.5 bits per weight
PARAMS_RE = re.compile(r"(?<![a-z\d.])(\d+(?:\.\d+)?)b(?![a-z])", re.IGNORECASE)  # "e2b" is not 2B

_CACHE = {}          # normalised tag -> bytes or None, kept for this run only
SIZE_BUDGET_S = 8  # one budget for every size lookup in a run; slow-but-answering networks cannot stall the menu
_STATE = {"offline": False, "started": None}


def reset_cache():
    """Forget every answer. Tests and a fresh run start from nothing."""
    _CACHE.clear()
    _STATE["offline"] = False
    _STATE["started"] = None
    model_wizard._STATE["offline"] = False


def new_lookup_window():
    """Start a fresh time budget and forget an earlier outage, but keep every size already found.
    Called when the user opens a menu or searches, so one slow lookup does not blind the next one."""
    _STATE["started"] = None
    _STATE["offline"] = False
    model_wizard._STATE["offline"] = False


_SameHostOnly = model_wizard._SameHostOnly  # kept here so older callers and tests keep working


def _budget_spent():
    """True once the run has used its SIZE_BUDGET_S. The clock starts at the first lookup."""
    now = time.monotonic()
    if _STATE["started"] is None:
        _STATE["started"] = now
    return now - _STATE["started"] > SIZE_BUDGET_S


def _get_json(url, headers=None, timeout=3):
    """Parsed JSON, or None. Sets the offline flag on a network failure so the rest of the run stops asking."""
    if _STATE["offline"] or _budget_spent():
        return None
    try:
        return http.get_json(url, timeout=timeout, headers=headers, opener=registry._OPENER)
    except http.ANSWERED_ERRORS:  # the request/parse lives in agl.platform.http
        return None  # the server answered (404, redirect refused, a cut-off reply): not an outage
    except http.NETWORK_ERRORS:
        _STATE["offline"] = True
        return None
    except ValueError:
        return None


def ollama_registry_size(tag):
    """Total bytes of the model layers in the registry manifest, or None (offline, unknown tag, other registry)."""
    # the manifest read lives in agl.platform.registry; our own budget,
    # offline flag and cache are passed through as the fetch and the cache.
    return registry.ollama_registry_size(tag, fetch=_get_json, cache=_CACHE)


def estimate_gb(tag):
    """Size estimate from the parameter count in the tag (27b at 4.5 bits is about 15 GB). None when the tag has none."""
    version = (tag or "").rpartition(":")[2]
    m = PARAMS_RE.search(version)
    if not m:
        return None
    return float(m.group(1)) * DEFAULT_BPW / 8


def resolve(tag, list_gb=None):
    """{"gb": float, "source": "registry" | "list" | "estimate"} for an Ollama tag, or None when nothing is known."""
    if model_wizard.is_hf_tag(tag):
        return {"gb": list_gb, "source": "list"} if list_gb else None
    total = ollama_registry_size(tag)
    if total:
        return {"gb": total / 1e9, "source": "registry"}
    if list_gb:
        return {"gb": list_gb, "source": "list"}
    est = estimate_gb(tag)
    return {"gb": est, "source": "estimate"} if est else None


def hf_quant_size(user, repo, free_vram, free_ram):
    """Size of the quant that would be pulled for a Hugging Face repo, judged against the memory free right now.
    {"gb", "quant", "source": "hugging face" | "estimate"} or None."""
    if model_wizard._STATE["offline"] or _budget_spent():
        return None
    files = model_wizard.hf_tree_files(user, repo)
    if not files:
        return None
    pick = quant_pick.pick_quant(files, free_vram, free_ram)
    if pick is None:
        return None
    return {"gb": pick["size_gb"], "quant": pick["quant"],
            "source": "estimate" if pick["estimated"] else "hugging face"}
