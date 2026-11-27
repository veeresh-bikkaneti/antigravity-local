"""SearXNG first, then Tavily. Hits keep only url and snippet."""
import json
import urllib.parse


def search(query, *, http, env):
    """{"backend": "searxng"|"tavily"|"none", "hits": [{"url", "snippet"}]}."""
    rows = _searxng_rows(query, http, env)
    if rows is not None:
        return {"backend": "searxng", "hits": _hits(rows)}
    rows = _tavily_rows(query, http, env)
    if rows is not None:
        return {"backend": "tavily", "hits": _hits(rows)}
    return {"backend": "none", "hits": []}


def _setting(env, name):
    value = env.get(name) if env is not None else None
    if value is None:
        return ""
    return str(value).strip()


def _rows(payload):
    """The results list, or None when the payload is not that shape."""
    if not isinstance(payload, dict):
        return None
    rows = payload.get("results")
    if isinstance(rows, list):
        return rows
    return None


def _hit(row):
    """url plus content-as-snippet. Every other key, including html, is dropped."""
    if not isinstance(row, dict):
        return None
    url = row.get("url")
    snippet = row.get("content")
    return {
        "url": url if isinstance(url, str) else "",
        "snippet": snippet if isinstance(snippet, str) else "",
    }


def _hits(rows):
    hits = []
    for row in rows:
        hit = _hit(row)
        if hit is not None:
            hits.append(hit)
    return hits


def _searxng_rows(query, http, env):
    base = _setting(env, "AGL_SEARXNG_URL")
    if not base:
        return None
    url = base.rstrip("/") + "/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
    try:
        payload = http.get_json(url, timeout=10)
    except Exception:
        return None
    return _rows(payload)


def _tavily_rows(query, http, env):
    key = _setting(env, "TAVILY_API_KEY")
    if not key:
        return None
    body = json.dumps({
        "api_key": key,
        "query": query,
        "search_depth": "basic",
        "max_results": 5,
    }).encode("utf-8")
    try:
        payload = http.get_json(
            "https://api.tavily.com/search",
            timeout=10,
            headers={"Content-Type": "application/json"},
            data=body,
        )
    except Exception:
        return None
    return _rows(payload)
