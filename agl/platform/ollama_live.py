"""Live-model adapter for Homeport: what Ollama has loaded right now, from /api/ps.

Ollama's /api/ps lists each loaded model with its size, the part resident in VRAM, the
context length and the expiry time (https://github.com/ollama/ollama/blob/main/docs/api.md).
"""

from agl.platform import config, http


def loaded_models(base_url=config.OLLAMA_BASE_URL, *, timeout=3, get_json=None) -> list:
    """Rows of /api/ps as dicts with exactly the keys name, size, size_vram, context_length,
    expires_at (values passed through from each row). Any error, a non-dict body or a
    non-list "models" gives [].

    `get_json` defaults to http.get_json, looked up at call time, so a patched helper still applies.
    """
    if get_json is None:
        get_json = http.get_json
    try:
        data = get_json(f"{base_url.rstrip('/')}/api/ps", timeout=timeout)
        rows = data.get("models") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []
        return [
            {
                "name": row.get("name"),
                "size": row.get("size"),
                "size_vram": row.get("size_vram"),
                "context_length": row.get("context_length"),
                "expires_at": row.get("expires_at"),
            }
            for row in rows
        ]
    except Exception:
        return []
