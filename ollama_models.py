"""What Ollama knows about the models installed on this machine: size, age and what each can do.

/api/tags lists them (newer servers include `capabilities` right there). Where that field is missing we ask
/api/show once per model. If neither answers, capabilities stay None, which means "unknown", never "none":
an old Ollama must not make every model look tool-less.
"""
import json

import model_wizard
from agl.platform import config, http

MAX_SHOW_CALLS = 30
GB = 1e9  # Ollama and Hugging Face print decimal GB


def _get_json(opener, url, timeout, data=None):
    # moved, shim until Phase 6: the request/parse now lives in agl.platform.http
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
        details[model_wizard._norm(name)] = {
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
    want = model_wizard._norm(name)
    if want in details:
        return details[want]
    for key, value in details.items():
        if key.startswith("hf.co/") and key.rsplit("/", 1)[-1] == want:
            return value
    return None
