"""The Hugging Face Hub adapter: repo facts, the file tree, tag vetting and the cached search, in one module.

Bodies moved verbatim from model_wizard.py and hf_search.py; those files keep the same names as shims
until Phase 6. The 24 h cache and the back-off on 429 live here too, because they are part of how the
network is asked. Standard library, agl.core and platform siblings only.
"""
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse

from agl.core import capabilities
from agl.core.menu import QUANT_RE, parse_hf_tag
from agl.platform import http

_HF_OPENER = http.same_host_opener()  # huggingface.co: a cross-host redirect is not followed
_STATE = {"offline": False}  # set when the Hub cannot be reached; later calls in the run stop asking

SEARCH_URL = "https://huggingface.co/api/models"
CACHE_TTL = 24 * 3600
RETRY_WAITS = (2, 4)      # seconds, used when the Hub does not say how long to wait
MAX_WAIT = 30             # no single wait is longer than this, whatever the Hub asks for
MAX_RETRIES = 2
MAX_BYTES = 3_000_000     # a search reply bigger than this is not trusted, so it is never read whole
EXPAND = ("gguf", "downloads", "lastModified", "pipeline_tag", "tags")  # a list reply only has fields asked for


def _hf_api_model(user, repo, timeout=4, opener=None):
    """The Hub's model record for user/repo, fetched through the same-host opener. Returns (status, data):
    'ok' with a dict, 'missing' (a 404), or 'unknown' (offline, private or gated, odd reply; data None).
    Sends only the repo name. Both hf_check and hf_repo_info read through here."""
    if opener is None:
        opener = _HF_OPENER
    try:
        with opener.open(f"https://huggingface.co/api/models/{user}/{repo}", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return ("missing", None) if e.code == 404 else ("unknown", None)
    except Exception:
        return "unknown", None
    if not isinstance(data, dict):
        return "unknown", None
    return "ok", data


def hf_check(tag, timeout=4, opener=None):
    """Ask the Hugging Face API about an hf.co tag. Returns (status, detail), status one of:
    'ok'       the repo is there (and has a .gguf for the quant, when one was given)
    'missing'  the repo is a 404: refuse it
    'no_quant' the repo exists but no .gguf matches the quant; detail = the quants it does have
    'bad_tag'  not hf.co/user/repo[:quant]
    'unknown'  could not tell (offline, private or gated repo, odd reply): allow it, like the Ollama registry check
    Sends only the repo name."""
    parsed = parse_hf_tag(tag)
    if not parsed:
        return "bad_tag", None
    user, repo, quant = parsed
    status, data = _hf_api_model(user, repo, timeout=timeout, opener=opener)
    if status != "ok":
        return status, None
    if not quant:
        return "ok", None
    files = [s.get("rfilename", "") for s in (data.get("siblings") or []) if s.get("rfilename", "").lower().endswith(".gguf")]
    have = sorted({q.upper() for f in files for q in QUANT_RE.findall(f)})
    if quant.upper() in have:
        return "ok", None
    return "no_quant", have


def hf_repo_info(user, repo, timeout=4, opener=None):
    """{'status': 'ok'|'missing'|'unknown', 'gated': bool, 'license': str|None} for a Hugging Face repo.
    Sends only the repo name. gated can be False, True, 'auto' or 'manual' on the Hub: anything truthy counts."""
    status, data = _hf_api_model(user, repo, timeout=timeout, opener=opener)
    if status != "ok":
        return {"status": status, "gated": False, "license": None}
    card = data.get("cardData") if isinstance(data.get("cardData"), dict) else {}
    lic = card.get("license")
    if not lic:
        lic = next((t[len("license:"):] for t in data.get("tags") or [] if isinstance(t, str) and t.startswith("license:")), None)
    return {"status": "ok", "gated": bool(data.get("gated")), "license": str(lic) if lic else None}


def hf_tree_files(user, repo, timeout=6, max_pages=5, opener=None, state=None):
    """[{'name', 'size'}] for every file in the repo (sizes in bytes, from the LFS size when there is one).
    Follows the Link: rel=next header up to max_pages, on huggingface.co only. Any failure returns [].
    `state` is the offline dict to set on a network failure (model_wizard._STATE today)."""
    if opener is None:
        opener = _HF_OPENER
    if state is None:
        state = _STATE
    url = f"https://huggingface.co/api/models/{user}/{repo}/tree/main?expand=true&recursive=true"
    files = []
    for _ in range(max_pages):
        try:
            with opener.open(url, timeout=timeout) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
                link = resp.headers.get("Link", "") if getattr(resp, "headers", None) else ""
        except urllib.error.HTTPError:
            return []  # the Hub answered with an error: say nothing rather than give a wrong size
        except (urllib.error.URLError, OSError, TimeoutError):
            state["offline"] = True  # no network: stop asking for the rest of the run
            return []
        except Exception:
            return []  # a half-read repo would undercount split quants, so say nothing rather than give a wrong size
        if not isinstance(rows, list):
            return []
        for row in rows:
            if isinstance(row, dict) and row.get("type", "file") == "file":
                size = (row.get("lfs") or {}).get("size") if isinstance(row.get("lfs"), dict) else None
                files.append({"name": row.get("path", ""), "size": size if size else row.get("size")})
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link or "")
        if not nxt:
            break
        url = nxt.group(1)
        if not url.startswith("https://huggingface.co/"):
            return []  # never follow a page link to another host
    else:
        return []  # still more pages after max_pages: a partial list would undercount split quants
    return files


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
    opener = http._urlopen if opener is None else opener
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


def _text_or_none(value):
    """The value if it is a string, else None. A list or dict in a text field is junk, not a name.
    was _text: renamed because model_wizard's _text means a stripped note (now _note_text)."""
    return value if isinstance(value, str) else None


def _count(value):
    """The value if it is a whole number, else None. bool is an int subclass, so True is not a count."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _result(row):
    gguf = row.get("gguf") if isinstance(row.get("gguf"), dict) else {}
    pipeline = _text_or_none(row.get("pipeline_tag"))
    return {
        "repo": _text_or_none(row.get("id")) or _text_or_none(row.get("modelId")) or "",
        "downloads": _count(row.get("downloads")),
        "last_modified": _text_or_none(row.get("lastModified")),
        "pipeline_tag": pipeline,
        "badges": capabilities.hf_badges(pipeline, gguf.get("chat_template")),
        "kind": capabilities.kind_from_hf(pipeline),
        "context_length": _count(gguf.get("context_length")),
        "total_file_size": _count(gguf.get("totalFileSize")),
    }


def search_models(cache_dir, query=None, pipeline_tag="text-generation", limit=20, fetch_json=None, **kw):
    """([result dicts], source). A failure gives ([], 'offline'); a stale cache gives its rows with source 'stale'.
    `fetch_json` is injectable: hf_search's shim passes its own module attribute, so a test that patches it
    there still applies."""
    if fetch_json is None:
        fetch_json = globals()["fetch_json"]
    data, source = fetch_json(search_url(query, pipeline_tag, limit), cache_dir=cache_dir, accept=lambda d: isinstance(d, list), **kw)
    if not isinstance(data, list):
        return [], ("offline" if data is None else source)
    rows = [_result(r) for r in data if isinstance(r, dict)]
    return [r for r in rows if r["repo"]], source
