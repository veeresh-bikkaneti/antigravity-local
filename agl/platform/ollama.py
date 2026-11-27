"""The Ollama adapter: every network call outside this process that is about Ollama, in one module.

The local server's own API (/api/tags, /api/show, /v1/chat/completions) plus the public library page
(https://ollama.com/library). The service-check here only asks; starting `ollama serve` stays in run.py
(the shell decides what to run), and the pull stays behind subprocess until Phase 4b.
Bodies moved verbatim from run.py, ollama_models.py, ollama_library.py and probe.py; the old names stay
there as shims until Phase 6.
"""
import json
import urllib.request

from agl.core.menu import _norm
from agl.platform import config, http

LIBRARY_URL = "https://ollama.com/library"
MAX_BYTES = 3_000_000
MAX_SHOW_CALLS = 30
GB = 1e9  # Ollama and Hugging Face print decimal GB


def check_service(base_url=config.OLLAMA_BASE_URL, *, timeout=3):
    """True only when {base_url}/api/tags answers HTTP 200. Anything else (refused, timeout, non-200)
    is False; starting the server is run.py's job, not this adapter's."""
    try:
        with http.open_url(f"{base_url.rstrip('/')}/api/tags", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def installed_models(base_url=config.OLLAMA_BASE_URL, *, timeout=3, get_json=None):
    """The installed model names from /api/tags (Tier 1 of run.get_installed_ollama_models): every name
    lowercased, plus its short form (after the last slash). An empty set when the server does not answer.
    `get_json` defaults to http.get_json, looked up at call time, so a patched helper still applies."""
    if get_json is None:
        get_json = http.get_json
    models = set()
    tags_url = f"{base_url}/api/tags"
    try:
        data = get_json(tags_url, timeout=timeout)
        for m in data.get("models", []):
            name = m.get("name", "").strip().lower()
            if name:
                models.add(name)
                clean_name = name.split("/")[-1]
                models.add(clean_name)
    except Exception:
        pass
    if not models:
        try:
            import shutil
            from agl.platform import process
            if shutil.which("ollama"):
                output = process.check_output(["ollama", "list"], text=True, stderr=process.DEVNULL)
                for line in output.splitlines()[1:]:
                    parts = line.split()
                    if parts:
                        name = parts[0].strip().lower()
                        models.add(name)
                        clean_name = name.split("/")[-1]
                        models.add(clean_name)
        except Exception:
            pass
    return models


def installed_info(base_url=config.OLLAMA_BASE_URL, *, timeout=3):
    """{normalised tag: {"size_gb", "digest"}} from Ollama's /api/tags (size is in bytes). Each model is listed under
    its full name and its short name (after the last slash), the same two names installed_models returns.
    {} when Ollama does not answer: a size we were not told is left out, never guessed."""
    try:
        data = http.get_json(f"{base_url}/api/tags", timeout=timeout)
    except Exception:
        return {}
    out = {}
    for m in data.get("models", []) if isinstance(data, dict) else []:
        name = (m.get("name") or "").strip().lower() if isinstance(m, dict) else ""
        size = m.get("size") if isinstance(m, dict) else None
        if not name:
            continue
        row = {"size_gb": size / 1e9 if isinstance(size, (int, float)) and size > 0 else None,
               "digest": m.get("digest") if isinstance(m.get("digest"), str) else None}
        out[name] = row
        out.setdefault(name.split("/")[-1], row)
    return out


def _get_json(opener, url, timeout, data=None):
    """GET or POST JSON through the platform helper with the JSON content types set (ollama_models._get_json)."""
    if data is None:
        return http.get_json(url, timeout=timeout, headers={"Accept": "application/json"}, opener=opener)
    return http.get_json(url, timeout=timeout, headers={"Content-Type": "application/json", "Accept": "application/json"},
                         data=json.dumps(data).encode("utf-8"), opener=opener)


def _caps(value):
    """Known-type entries only. A non-empty list with nothing usable is unknown (None), not an empty list."""
    if not isinstance(value, list):
        return None
    kept = [c for c in value if isinstance(c, str)]
    return kept if kept or not value else None


def installed_details(base_url=config.OLLAMA_BASE_URL, opener=None, timeout=3):
    """{normalised tag: {"name", "size_gb", "modified_at", "caps"}}. {} when the server does not answer."""
    base = base_url.rstrip("/")
    try:
        tags = _get_json(opener, f"{base}/api/tags", timeout)
    except Exception:
        return {}
    rows = tags.get("models") if isinstance(tags, dict) else None
    details, shows = {}, 0
    for row in rows if isinstance(rows, list) else []:
        name = row.get("name") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name:
            continue
        caps = _caps(row.get("capabilities"))
        if caps is None and shows < MAX_SHOW_CALLS:
            shows += 1
            try:
                shown = _get_json(opener, f"{base}/api/show", timeout, {"model": name})
                caps = _caps(shown.get("capabilities")) if isinstance(shown, dict) else None
            except Exception:
                caps = None
        size = row.get("size")
        details[_norm(name)] = {
            "name": name,
            "size_gb": size / GB if isinstance(size, (int, float)) and not isinstance(size, bool) and size > 0 else None,
            "modified_at": row.get("modified_at") if isinstance(row.get("modified_at"), str) else None,
            "caps": caps,
        }
    return details


def lookup(details, name):
    """The details for a tag: the exact normalised tag first.

    A short name (m:q4) may find an hf.co/ model (hf.co/u/m:q4), because run.py
    lists that short alias. It never finds a model in any other namespace:
    acme/foo:1 does not answer to foo:1.
    """
    if not details or not name:
        return None
    want = _norm(name)
    if want in details:
        return details[want]
    for key, value in details.items():
        if key.startswith("hf.co/") and key.rsplit("/", 1)[-1] == want:
            return value
    return None


def library_page(opener=None, timeout=6):
    """The https://ollama.com/library page HTML, or None when it cannot be read (moved from ollama_library.scan's
    fetch: the same Request headers, the same read(MAX_BYTES), any failure is None)."""
    opener = http._urlopen if opener is None else opener
    try:
        request = urllib.request.Request(LIBRARY_URL, headers={"Accept": "text/html"})
        with opener(request, timeout=timeout) as resp:
            return resp.read(MAX_BYTES).decode("utf-8", errors="replace")
    except Exception:
        return None


def chat_json(url, body, *, opener=None, timeout=60):
    """One POST to a chat-completions endpoint, parsed as JSON (probe._chat's body). `opener` is a
    urlopen-style callable; None resolves to the platform default (http._urlopen) at call time."""
    opener = http._urlopen if opener is None else opener
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
    with opener(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verifier_model(env, *, base_url=None, get_json=None):
    """The local verifier tag, and a note when we fall back. Never pulls a model."""
    named = (env.get("LOCAL_VERIFIER_MODEL") or "").strip()
    main = env.get("LOCAL_LLM_MODEL") or ""
    if not named:
        return main, ""
    if named.lower() in _installed_names(base_url, get_json):
        return named, ""
    used = main or "LOCAL_LLM_MODEL"
    return main, f"The verifier model {named} is not installed. {used} is used."


def _installed_names(base_url, get_json):
    kwargs = {}
    if base_url is not None:
        kwargs["base_url"] = base_url
    if get_json is not None:
        kwargs["get_json"] = get_json
    return installed_models(**kwargs)
