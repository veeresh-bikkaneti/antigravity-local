"""The registry.ollama.ai adapter: does a tag exist, is the registry reachable, how big is a manifest.

Bodies moved verbatim from model_wizard.tag_exists / registry_reachable and
download_size.ollama_registry_size; those files keep the same names as shims until Phase 6. No model
name is sent anywhere except the one tag being asked about.
"""
import urllib.error
import urllib.parse

from agl.core.menu import _norm
from agl.platform import http

_OPENER = http.same_host_opener()  # registry.ollama.ai: a cross-host redirect is not followed
REGISTRY = "https://registry.ollama.ai/v2/"
MANIFEST_ACCEPT = ("application/vnd.docker.distribution.manifest.v2+json, "
                   "application/vnd.oci.image.manifest.v1+json")
_STATE = {"offline": False}  # download_size's offline flag, mimicked here without its time budget
_CACHE = {}          # normalised tag -> bytes or None, kept for this run only


def tag_exists(tag, timeout=4, opener=None):
    """True/False from the public Ollama registry, None when we cannot tell (offline). Sends only the tag."""
    if opener is None:
        opener = _OPENER
    name, _, version = _norm(tag).rpartition(":")
    if "/" in name and "." in name.split("/")[0]:
        return None  # another registry (hf.co/..., host.example/...): ours cannot vouch for it, so do not refuse it
    if "/" not in name:
        name = "library/" + name
    try:
        with http.open_url(f"https://registry.ollama.ai/v2/{name}/manifests/{version}", timeout=timeout,
                           method="HEAD", headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
                           opener=opener):
            return True
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None  # a refused cross-host redirect lands here as a 3xx: unknown
    except Exception:
        return None


def registry_reachable(timeout=3, opener=None):
    """True when registry.ollama.ai answers at all (any HTTP reply, even a 401), False when we cannot reach it.
    Used by --check-upgrades to say "couldn't check" instead of guessing. Sends no model name."""
    if opener is None:
        opener = _OPENER
    try:
        with http.open_url("https://registry.ollama.ai/v2/", timeout=timeout, method="HEAD", opener=opener):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def _fetch(url, headers=None, timeout=3):
    """Parsed JSON, or None; download_size._get_json's offline behaviour without its time budget."""
    if _STATE["offline"]:
        return None
    try:
        return http.get_json(url, timeout=timeout, headers=headers, opener=_OPENER)
    except http.ANSWERED_ERRORS:
        return None  # the server answered (404, redirect refused, a cut-off reply): not an outage
    except http.NETWORK_ERRORS:
        _STATE["offline"] = True
        return None
    except ValueError:
        return None


def ollama_registry_size(tag, *, fetch=None, cache=None):
    """Total bytes of the model layers in the registry manifest, or None (offline, unknown tag, other registry).
    `fetch` and `cache` are injectable so download_size can pass its own (budget and offline flag) versions;
    the defaults are this module's plain `_fetch` and `_CACHE`."""
    if fetch is None:
        fetch = _fetch
    if cache is None:
        cache = _CACHE
    if any(bad in (tag or "") for bad in ("?", "#", " ", "..")):
        return None  # would change the request path; never send it
    key = _norm(tag)
    if key in cache:
        return cache[key]
    name, _, version = key.rpartition(":")
    if "/" in name and "." in name.split("/")[0]:
        return None  # hf.co/... and other registries are not ours to size
    if "/" not in name:
        name = "library/" + name
    data = fetch(f"{REGISTRY}{urllib.parse.quote(name, safe='/')}/manifests/{urllib.parse.quote(version, safe='')}",
                headers={"Accept": MANIFEST_ACCEPT})
    layers = data.get("layers") if isinstance(data, dict) else None
    if not isinstance(layers, list):
        layers = None
    sizes = [l.get("size") for l in layers or [] if isinstance(l, dict) and isinstance(l.get("size"), int)]
    total = sum(sizes) if sizes and len(sizes) == len(layers) else None
    cache[key] = total if total and total > 0 else None
    return cache[key]
