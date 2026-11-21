"""Search Hugging Face for GGUF models, politely: a 24 hour cache, a back-off when the Hub says slow down, and
a quiet fallback to what we already have when it cannot be reached.

Anonymous use is limited (the Hub documents 500 calls per 5 minutes per IP), so every answer is cached on disk.
HF_TOKEN is sent only when the caller hands it in, and it is never written to the cache or printed.

the fetch machinery (cache, back-off, capped reads, result rows) lives in agl/platform/hub;
the same names stay here as one-line wrappers for old imports and test patches.
"""
from agl.platform import hub

CACHE_TTL = hub.CACHE_TTL  # moved to agl.platform.hub
MAX_WAIT = hub.MAX_WAIT  # moved to agl.platform.hub
EXPAND = hub.EXPAND  # moved to agl.platform.hub


def cache_path(url, cache_dir):
    # moved to agl.platform.hub
    return hub.cache_path(url, cache_dir)


def _read_cache(path, now):
    # moved to agl.platform.hub
    return hub._read_cache(path, now)


def _write_cache(path, now, data):
    # moved to agl.platform.hub
    return hub._write_cache(path, now, data)


def _seconds(value):
    # moved to agl.platform.hub
    return hub._seconds(value)


def _retry_wait(headers, attempt):
    # moved to agl.platform.hub
    return hub._retry_wait(headers, attempt)


def _read_capped(resp):
    # moved to agl.platform.hub
    return hub._read_capped(resp)


def _capped(opener):
    # moved to agl.platform.hub
    return hub._capped(opener)


def fetch_json(url, *, cache_dir, now=None, opener=None, sleep=None, token=None, ttl=CACHE_TTL, accept=None):
    """(data, source). source: 'cache' (fresh), 'net', 'stale' (expired cache after a failure) or 'offline' (data None)."""
    # moved to agl.platform.hub
    return hub.fetch_json(url, cache_dir=cache_dir, now=now, opener=opener, sleep=sleep, token=token, ttl=ttl, accept=accept)


def search_url(query=None, pipeline_tag="text-generation", limit=20):
    # moved to agl.platform.hub
    return hub.search_url(query, pipeline_tag, limit)


def _text_or_none(value):
    """The value if it is a string, else None. A list or dict in a text field is junk, not a name.
    was _text: renamed because model_wizard's _text means a stripped note (now _note_text)."""
    # moved to agl.platform.hub
    return hub._text_or_none(value)


def _count(value):
    """The value if it is a whole number, else None. bool is an int subclass, so True is not a count."""
    # moved to agl.platform.hub
    return hub._count(value)


def _result(row):
    # moved to agl.platform.hub
    return hub._result(row)


def search_models(cache_dir, query=None, pipeline_tag="text-generation", limit=20, **kw):
    """([result dicts], source). A failure gives ([], 'offline'); a stale cache gives its rows with source 'stale'."""
    # moved to agl.platform.hub: this module's fetch_json is passed through, so a test patching it here still applies
    return hub.search_models(cache_dir, fetch_json=fetch_json, query=query, pipeline_tag=pipeline_tag, limit=limit, **kw)
