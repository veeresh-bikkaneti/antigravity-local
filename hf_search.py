"""Search Hugging Face for GGUF models, politely: a 24 hour cache, a back-off when the Hub says slow down, and
a quiet fallback to what we already have when it cannot be reached.

Anonymous use is limited (the Hub documents 500 calls per 5 minutes per IP), so every answer is cached on disk.
HF_TOKEN is sent only when the caller hands it in, and it is never written to the cache or printed.

moved, shim until Phase 6: the fetch machinery (cache, back-off, capped reads, result rows) now lives in
agl/platform/hub; the same names stay here as one-line shims, so old imports and test patches keep working.
"""
from agl.platform import hub

SEARCH_URL = hub.SEARCH_URL  # moved, shim until Phase 6
CACHE_TTL = hub.CACHE_TTL  # moved, shim until Phase 6
RETRY_WAITS = hub.RETRY_WAITS  # moved, shim until Phase 6
MAX_WAIT = hub.MAX_WAIT  # moved, shim until Phase 6
MAX_RETRIES = hub.MAX_RETRIES  # moved, shim until Phase 6
MAX_BYTES = hub.MAX_BYTES  # moved, shim until Phase 6
EXPAND = hub.EXPAND  # moved, shim until Phase 6


def cache_path(url, cache_dir):
    # moved, shim until Phase 6
    return hub.cache_path(url, cache_dir)


def _read_cache(path, now):
    # moved, shim until Phase 6
    return hub._read_cache(path, now)


def _write_cache(path, now, data):
    # moved, shim until Phase 6
    return hub._write_cache(path, now, data)


def _seconds(value):
    # moved, shim until Phase 6
    return hub._seconds(value)


def _retry_wait(headers, attempt):
    # moved, shim until Phase 6
    return hub._retry_wait(headers, attempt)


def _read_capped(resp):
    # moved, shim until Phase 6
    return hub._read_capped(resp)


_Capped = hub._Capped  # moved, shim until Phase 6


def _capped(opener):
    # moved, shim until Phase 6
    return hub._capped(opener)


def fetch_json(url, *, cache_dir, now=None, opener=None, sleep=None, token=None, ttl=CACHE_TTL, accept=None):
    """(data, source). source: 'cache' (fresh), 'net', 'stale' (expired cache after a failure) or 'offline' (data None)."""
    # moved, shim until Phase 6
    return hub.fetch_json(url, cache_dir=cache_dir, now=now, opener=opener, sleep=sleep, token=token, ttl=ttl, accept=accept)


def search_url(query=None, pipeline_tag="text-generation", limit=20):
    # moved, shim until Phase 6
    return hub.search_url(query, pipeline_tag, limit)


def _text_or_none(value):
    """The value if it is a string, else None. A list or dict in a text field is junk, not a name.
    was _text: renamed because model_wizard's _text means a stripped note (now _note_text)."""
    # moved, shim until Phase 6
    return hub._text_or_none(value)


def _count(value):
    """The value if it is a whole number, else None. bool is an int subclass, so True is not a count."""
    # moved, shim until Phase 6
    return hub._count(value)


def _result(row):
    # moved, shim until Phase 6
    return hub._result(row)


def search_models(cache_dir, query=None, pipeline_tag="text-generation", limit=20, **kw):
    """([result dicts], source). A failure gives ([], 'offline'); a stale cache gives its rows with source 'stale'."""
    # moved, shim until Phase 6: this module's fetch_json is passed through, so a test patching it here still applies
    return hub.search_models(cache_dir, fetch_json=fetch_json, query=query, pipeline_tag=pipeline_tag, limit=limit, **kw)
