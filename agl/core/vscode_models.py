"""Pure helpers that merge one Ollama model entry into VS Code's chat models file."""

from pathlib import PurePath

GROUP = "Local Ollama (antigravity-local)"
QUESTION = (
    "Make VS Code Chat plan for the real window? "
    "Adds one model entry to your VS Code chat models file. [y/N] "
)
DEFAULT_ENDPOINTS = ("http://localhost:11434", "http://127.0.0.1:11434")

_VENDOR = "customendpoint"
_FOLDERS = (("VS Code", "Code"), ("VS Code Insiders", "Code - Insiders"))


def endpoint(base_url):
    """Return the base URL without a trailing slash or a trailing /v1."""
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        url = url[: -len("/v1")]
    return url.rstrip("/")


def chat_url(base_url):
    return endpoint(base_url) + "/v1/chat/completions"


def is_default_endpoint(base_url):
    return endpoint(base_url).lower() in DEFAULT_ENDPOINTS


def _base_dir(platform, home, environ):
    if platform == "win32":
        appdata = environ.get("APPDATA")
        if appdata:
            return PurePath(appdata)
        return PurePath(home) / "AppData" / "Roaming"
    if platform == "darwin":
        return PurePath(home) / "Library" / "Application Support"
    return PurePath(home) / ".config"


def user_dirs(platform, home, environ):
    """Return (label, User folder path) pairs for VS Code and VS Code Insiders."""
    base = _base_dir(platform, home, environ)
    return [(label, base / folder / "User") for label, folder in _FOLDERS]


def model_entry(model, base_url, tokens, tools):
    return {
        "id": model,
        "name": model,
        "url": chat_url(base_url),
        "toolCalling": bool(tools),
        "contextWindow": tokens,
        "maxOutputTokens": min(4096, tokens // 4),
    }


def _our_index(groups):
    for i, group in enumerate(groups):
        if isinstance(group, dict) and group.get("name") == GROUP and group.get("vendor") == _VENDOR:
            return i
    return None


def _with_model(models, entry):
    if not isinstance(models, list):
        raise ValueError("models must be a list")
    merged = list(models)
    for i, old in enumerate(merged):
        if isinstance(old, dict) and old.get("id") == entry["id"]:
            merged[i] = {**old, **entry}
            return merged
    merged.append(entry)
    return merged


def merge_models(groups, entry):
    """Return a new groups list with entry merged into our group. The input is not changed."""
    if not isinstance(groups, list):
        raise ValueError("groups must be a list")
    out = list(groups)
    idx = _our_index(out)
    if idx is None:
        out.append({"name": GROUP, "vendor": _VENDOR, "apiType": "chat-completions", "models": [entry]})
        return out
    group = out[idx]
    out[idx] = {**group, "models": _with_model(group.get("models", []), entry)}
    return out


def merge_settings(settings, base_url):
    if not isinstance(settings, dict):
        raise ValueError("settings must be a dict")
    return {**settings, "ollama.endpoint": endpoint(base_url)}
