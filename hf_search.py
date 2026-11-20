"""Search Hugging Face for GGUF models, politely: a 24 hour cache, a back-off when the Hub says slow down, and
a quiet fallback to what we already have when it cannot be reached.

Anonymous use is limited (the Hub documents 500 calls per 5 minutes per IP), so every answer is cached on disk.
HF_TOKEN is sent only when the caller hands it in, and it is never written to the cache or printed.
"""
import hashlib
import json
import math
import time
import urllib.error
import urllib.parse

import capabilities
from agl.platform import http

SEARCH_URL = "https://huggingface.co/api/models"
CACHE_TTL = 24 * 3600
RETRY_WAITS = (2, 4)      # seconds, used when the Hub does not say how long to wait
MAX_WAIT = 30             # no single wait is longer than this, whatever the Hub asks for
MAX_RETRIES = 2
MAX_BYTES = 3_000_000     # a search reply bigger than this is not trusted, so it is never read whole
EXPAND = ("gguf", "downloads", "lastModified", "pipeline_tag", "tags")  # a list reply only has fields asked for


def cache_path(url, cache_dir):
    return cache_dir / ("hf-" + hashlib.sha1(url.encode("utf-8")).hexdigest() + ".json")


def _read_cache(path, now):
    """(data, age_seconds) or (None, None). A corrupt file, or a stamp from the future, counts as no cache."""
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        age = now - float(blob["fetchedAt"])
        if age < 0 or "data" not in blob:
            return None, None
        return blob["data"], age
    except (OSError, ValueError, KeyError, TypeError):
        return None, None


def _write_cache(path, now, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetchedAt": now, "data": data}), encoding="utf-8")
    except OSError:
        pass  # a cache is a courtesy


def _seconds(value):
    """A header value as a wait in seconds (0 to MAX_WAIT), or None when it is junk, NaN or not a number at all."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return float(MAX_WAIT) if number > 0 else None
    return min(max(number, 0.0), MAX_WAIT)


def _retry_wait(headers, attempt):
    """Seconds to wait after a 429: Retry-After, else the RateLimit header's t=, else 2 s then 4 s. Capped."""
    value = headers.get("Retry-After") if headers else None
    wait = _seconds(value)
    if wait is not None:
        return wait
    ratelimit = headers.get("RateLimit") if headers else None
    if isinstance(ratelimit, str):
        for part in ratelimit.replace(";", ",").split(","):
            part = part.strip()
            if part.startswith("t="):
                wait = _seconds(part[2:])
                if wait is not None:
                    return wait
                break
    return float(RETRY_WAITS[min(attempt, len(RETRY_WAITS) - 1)])


def _read_capped(resp):
    """At most MAX_BYTES + 1 bytes of the reply, so a bigger one can be spotted and refused.
    Real responses are capped with read(MAX_BYTES + 1). Only a reader that takes no argument (TypeError) falls back to
    read() plus a slice, which reads the whole body first."""
    try:
        return resp.read(MAX_BYTES + 1)
    except TypeError:
        return resp.read()[:MAX_BYTES + 1]


class _Capped:
    """A wrapped reply that reads at most MAX_BYTES + 1 bytes and refuses a longer one, so a huge
    reply is never read whole and never trusted. The refusal raises, which fetch_json treats as
    a failed fetch (stale cache, or offline)."""

    def __init__(self, resp):
        self._resp = resp

    def read(self):
        raw = _read_capped(self._resp)
        if len(raw) > MAX_BYTES:
            raise ValueError("reply bigger than MAX_BYTES: not trusted")
        return raw

    def __enter__(self):
        self._resp.__enter__()
        return self

    def __exit__(self, *exc):
        return self._resp.__exit__(*exc)


def _capped(opener):
    """Wrap a urlopen-style opener so every reply it returns is capped."""
    def fetch(request, timeout=None):
        return _Capped(opener(request, timeout=timeout))
    return fetch


def fetch_json(url, *, cache_dir, now=None, opener=None, sleep=None, token=None, ttl=CACHE_TTL, accept=None):
    """(data, source). source: 'cache' (fresh), 'net', 'stale' (expired cache after a failure) or 'offline' (data None)."""
    now = time.time if now is None else now
    opener = http._urlopen if opener is None else opener  # moved, shim until Phase 6: the default urlopen lives in the platform helper
    sleep = time.sleep if sleep is None else sleep
    path = cache_path(url, cache_dir)
    cached, age = _read_cache(path, now())
    if cached is not None and age < ttl and (accept is None or accept(cached)):
        return cached, "cache"
    headers = {"Accept": "application/json"}
    if isinstance(token, str) and token.strip():  # a blank token is no token
        headers["Authorization"] = f"Bearer {token.strip()}"
    for attempt in range(MAX_RETRIES + 1):
        try:
            data = http.get_json(url, timeout=6, headers=headers, opener=_capped(opener))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < MAX_RETRIES:
                sleep(_retry_wait(getattr(e, "headers", None) or {}, attempt))
                continue
            break
        except Exception:
            break
        if accept is not None and not accept(data):
            break  # an error body is not an answer: do not keep it for a day
        _write_cache(path, now(), data)
        return data, "net"
    if cached is not None and (accept is None or accept(cached)):
        return cached, "stale"
    return None, "offline"


def search_url(query=None, pipeline_tag="text-generation", limit=20):
    parts = [("filter", "gguf"), ("pipeline_tag", pipeline_tag), ("sort", "downloads"), ("limit", str(limit))]
    if query:
        if isinstance(query, str):
            query = query.encode("utf-8", "replace").decode("utf-8")  # a lone surrogate becomes "?"
        parts.append(("search", query))
    base = urllib.parse.urlencode(parts)
    return f"{SEARCH_URL}?{base}&" + "&".join(f"expand[]={name}" for name in EXPAND)


def _text(value):
    """The value if it is a string, else None. A list or dict in a text field is junk, not a name."""
    return value if isinstance(value, str) else None


def _count(value):
    """The value if it is a whole number, else None. bool is an int subclass, so True is not a count."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _result(row):
    gguf = row.get("gguf") if isinstance(row.get("gguf"), dict) else {}
    pipeline = _text(row.get("pipeline_tag"))
    return {
        "repo": _text(row.get("id")) or _text(row.get("modelId")) or "",
        "downloads": _count(row.get("downloads")),
        "last_modified": _text(row.get("lastModified")),
        "pipeline_tag": pipeline,
        "badges": capabilities.hf_badges(pipeline, gguf.get("chat_template")),
        "kind": capabilities.kind_from_hf(pipeline),
        "context_length": _count(gguf.get("context_length")),
        "total_file_size": _count(gguf.get("totalFileSize")),
    }


def search_models(cache_dir, query=None, pipeline_tag="text-generation", limit=20, **kw):
    """([result dicts], source). A failure gives ([], 'offline'); a stale cache gives its rows with source 'stale'."""
    data, source = fetch_json(search_url(query, pipeline_tag, limit), cache_dir=cache_dir, accept=lambda d: isinstance(d, list), **kw)
    if not isinstance(data, list):
        return [], ("offline" if data is None else source)
    rows = [_result(r) for r in data if isinstance(r, dict)]
    return [r for r in rows if r["repo"]], source
