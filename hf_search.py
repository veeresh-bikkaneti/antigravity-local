"""Search Hugging Face for GGUF models, politely: a 24 hour cache, a back-off when the Hub says slow down, and
a quiet fallback to what we already have when it cannot be reached.

Anonymous use is limited (the Hub documents 500 calls per 5 minutes per IP), so every answer is cached on disk.
HF_TOKEN is sent only when the caller hands it in, and it is never written to the cache or printed.
"""
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import capabilities

SEARCH_URL = "https://huggingface.co/api/models"
CACHE_TTL = 24 * 3600
RETRY_WAITS = (2, 4)      # seconds, used when the Hub does not say how long to wait
MAX_WAIT = 30             # no single wait is longer than this, whatever the Hub asks for
MAX_RETRIES = 2
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


def _retry_wait(headers, attempt):
    """Seconds to wait after a 429: Retry-After, else the RateLimit header's t=, else 2 s then 4 s. Capped."""
    for name in ("Retry-After",):
        value = (headers.get(name) if headers else None)
        try:
            if value is not None:
                return min(max(float(value), 0.0), MAX_WAIT)
        except (TypeError, ValueError):
            pass
    ratelimit = headers.get("RateLimit") if headers else None
    if isinstance(ratelimit, str):
        for part in ratelimit.replace(";", ",").split(","):
            part = part.strip()
            if part.startswith("t="):
                try:
                    return min(max(float(part[2:]), 0.0), MAX_WAIT)
                except ValueError:
                    break
    return float(RETRY_WAITS[min(attempt, len(RETRY_WAITS) - 1)])


def fetch_json(url, *, cache_dir, now=None, opener=None, sleep=None, token=None, ttl=CACHE_TTL):
    """(data, source). source: 'cache' (fresh), 'net', 'stale' (expired cache after a failure) or 'offline' (data None)."""
    now = time.time if now is None else now
    opener = urllib.request.urlopen if opener is None else opener
    sleep = time.sleep if sleep is None else sleep
    path = cache_path(url, cache_dir)
    cached, age = _read_cache(path, now())
    if cached is not None and age < ttl:
        return cached, "cache"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(MAX_RETRIES + 1):
        try:
            with opener(urllib.request.Request(url, headers=headers), timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < MAX_RETRIES:
                sleep(_retry_wait(getattr(e, "headers", None) or {}, attempt))
                continue
            break
        except Exception:
            break
        _write_cache(path, now(), data)
        return data, "net"
    return (cached, "stale") if cached is not None else (None, "offline")


def search_url(query=None, pipeline_tag="text-generation", limit=20):
    parts = [("filter", "gguf"), ("pipeline_tag", pipeline_tag), ("sort", "downloads"), ("limit", str(limit))]
    if query:
        parts.append(("search", query))
    base = urllib.parse.urlencode(parts)
    return f"{SEARCH_URL}?{base}&" + "&".join(f"expand[]={name}" for name in EXPAND)


def _result(row):
    gguf = row.get("gguf") if isinstance(row.get("gguf"), dict) else {}
    pipeline = row.get("pipeline_tag")
    return {
        "repo": row.get("id") or row.get("modelId") or "",
        "downloads": row.get("downloads") if isinstance(row.get("downloads"), int) else None,
        "last_modified": row.get("lastModified") if isinstance(row.get("lastModified"), str) else None,
        "pipeline_tag": pipeline,
        "badges": capabilities.hf_badges(pipeline, gguf.get("chat_template")),
        "kind": capabilities.kind_from_hf(pipeline),
        "context_length": gguf.get("context_length") if isinstance(gguf.get("context_length"), int) else None,
        "total_file_size": gguf.get("totalFileSize") if isinstance(gguf.get("totalFileSize"), int) else None,
    }


def search_models(cache_dir, query=None, pipeline_tag="text-generation", limit=20, **kw):
    """([result dicts], source). A failure gives ([], 'offline'); a stale cache gives its rows with source 'stale'."""
    data, source = fetch_json(search_url(query, pipeline_tag, limit), cache_dir=cache_dir, **kw)
    if not isinstance(data, list):
        return [], ("offline" if data is None else source)
    rows = [_result(r) for r in data if isinstance(r, dict)]
    return [r for r in rows if r["repo"]], source
