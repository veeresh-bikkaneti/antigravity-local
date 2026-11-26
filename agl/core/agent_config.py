"""Pure agent-setup decisions (Phase 6c): tag validation, the Node check, config merges, argv building.

No I/O, no env reads, no subprocess: every value a decision needs arrives as an argument, so the root
agent_setup.py shim can pass its own constants at call time. Standard library only.
"""

import json
import os
import re


class AgentSetupError(Exception):
    """Something the user has to fix. `code` is the process exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def validate_model_tag(model, pattern):
    """An error message for a tag we refuse, or None when the tag is safe. The shim raises AgentSetupError."""
    if not isinstance(model, str) or not model.strip():
        return "No model name to configure."
    if not pattern.match(model):
        return (f"'{model}' is not a model tag. Use letters, digits and . _ / - with an optional "
                ":tag, and no leading '-'. Example: qwen3.6:27b")
    return None


def node_ok(version, pi_min):
    """True for Node >= pi_min (what pi needs). Accepts 'v26.13.0'."""
    m = re.match(r"v?(\d+)\.(\d+)", (version or "").strip())
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= pi_min


def obj(parent, key, path):
    """parent[key] as a dict, created if missing. A non-object there means a config we should not guess about."""
    child = parent.setdefault(key, {})
    if not isinstance(child, dict):
        raise AgentSetupError(f"{path}: '{key}' should be a JSON object. We did not change the file.")
    return child


# assumed only when the window cannot be read (OpenAI-compatible servers)
UNKNOWN_CONTEXT_WINDOW = 65536


def pi_models(data, model, base_url, path, context_window):
    prov = obj(obj(data, "providers", path), "ollama", path)
    prov["baseUrl"] = base_url
    prov["api"] = "openai-completions"
    prov["apiKey"] = "ollama"
    compat = obj(prov, "compat", path)
    compat["supportsDeveloperRole"] = False
    compat["supportsReasoningEffort"] = False
    models = prov.setdefault("models", [])
    if not isinstance(models, list):
        raise AgentSetupError(f"{path}: 'models' should be a JSON list. We did not change the file.")
    entry = next((m for m in models if isinstance(m, dict) and m.get("id") == model), None)
    if entry is None:
        models.append({"id": model, "contextWindow": context_window or UNKNOWN_CONTEXT_WINDOW})
    elif context_window is not None:
        entry["contextWindow"] = context_window


def opencode(data, model, base_url, path, schema, context_window=None):
    data.setdefault("$schema", schema)
    prov = obj(obj(data, "provider", path), "ollama", path)
    prov["npm"] = "@ai-sdk/openai-compatible"
    prov.setdefault("name", "Ollama (local)")
    obj(prov, "options", path)["baseURL"] = base_url
    models = obj(prov, "models", path)
    models.setdefault(model, {"name": model})
    if context_window is not None:
        limit = obj(obj(models, model, path), "limit", path)
        limit["context"] = context_window
        # opencode's schema requires output whenever limit exists
        limit.setdefault("output", min(4096, context_window // 4))


def targets(name, home, context_window, schema):
    """(path, merge function) per file we own a block in. Codex has none."""
    if name == "pi":
        agent = home / ".pi" / "agent"
        # never settings.json: pi's own default is the user's
        return [(agent / "models.json",
                 lambda data, model, base_url, path: pi_models(data, model, base_url, path, context_window))]
    if name == "opencode":
        return [(home / ".config" / "opencode" / "opencode.json",
                 lambda data, model, base_url, path: opencode(data, model, base_url, path, schema, context_window))]
    return []


def render_json(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def agent_command(name, model, exe=None, prompt=None):
    """The one argv for each agent, used by the printed hint, write_config's result and launch.
    `prompt` is the agent's first message (--continue-local); every agent takes it on its command line."""
    exe = exe or name
    argv = {"pi": [exe, "--provider", "ollama", "--model", model],
            "opencode": [exe, "--model", f"ollama/{model}"],
            "codex": [exe, "--oss", "-m", model],
            "claude": [exe, "--model", model]}[name]
    if prompt:
        argv += ["--prompt", prompt] if name == "opencode" else [prompt]
    return argv


def context_hint():
    return ("Heads up: coding agents want a 64k+ token context. Ollama's default is smaller on most PCs "
            "(4k below 24 GB of VRAM). Raise it in the Ollama app's settings, or start the server with "
            "OLLAMA_CONTEXT_LENGTH=65536. We do not change your Ollama settings.")


def same_folder(a, b):
    """True when two paths are the same folder: resolved, and case-insensitive where the OS is (Windows)."""
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def claude_base_url(base_url, default):
    """LOCAL_LLM_BASE_URL minus a trailing slash and /v1: Claude Code wants the server root."""
    url = (base_url or default).strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url.rstrip("/") or default


def claude_context(environ, context_window):
    """(tokens, warning or None). The window Ollama really runs with is what Claude Code must plan for."""
    raw = (environ.get("OLLAMA_CONTEXT_LENGTH") or "").strip()
    if raw.isdigit() and int(raw) > 0:
        n = int(raw)
        return n, (None if n >= context_window else
                   f"OLLAMA_CONTEXT_LENGTH is {n}, below the 64k (65536) coding agents want.")
    return context_window, ("OLLAMA_CONTEXT_LENGTH is not set in this terminal. Ollama's default window is 4096, "
                            "so start the Ollama server with OLLAMA_CONTEXT_LENGTH=65536 (we assume 65536 here; if "
                            "the server runs smaller, Claude Code will overrun it).")


def is_claude_key(name):
    return (name.startswith("ANTHROPIC_") or name.startswith("CLAUDE_CODE_USE_")
            or name in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR"))
