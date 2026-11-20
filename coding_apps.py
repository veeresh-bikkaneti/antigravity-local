"""The "connect your coding app" block printed at the end of setup and by `python run.py --coding-apps`.

Pure text: no network, no files. Facts and sources live in docs/coding-apps.md (checked 2026-11-18).
"""

from agl.platform import config

DOCS_PATH = "docs/coding-apps.md"


def _roots(base_url, backend):
    """(server root, OpenAI-style base). Ollama: root is http://host:11434 and the OpenAI base adds /v1.
    An OpenAI-compatible server gives its own base, so both are that URL."""
    base = (base_url or config.LLM_BASE_URL).rstrip("/")
    if backend == "openai":
        return base, base
    root = base[:-3] if base.endswith("/v1") else base
    return root, root + "/v1"


def lines(model, base_url=config.LLM_BASE_URL, backend="ollama"):
    """The block, one string per printed line. `backend="openai"` drops the rows that only work with Ollama."""
    root, openai_base = _roots(base_url, backend)
    rows = []
    if backend != "openai":
        rows.append(("VS Code", f"Ollama extension (Ollama.ollama), pick {model} under Ollama in Chat"))
        rows.append(("Continue", f"provider ollama, model {model}, apiBase {root}"))
    rows.append(("Terminal", "python run.py --agent pi   (or opencode, codex, claude)"))
    rows.append(("Antigravity", "no documented local-model setting in the app; run the Terminal line in its terminal"))
    rows.append(("Gemini CLI", "no local models; only via a LiteLLM proxy (experimental)"))
    rows.append(("Your code", f"base_url {openai_base}, model {model}"))
    width = max(len(name) for name, _ in rows)
    out = [f"       Use {model} in a coding app   (all steps: {DOCS_PATH})"]
    out += [f"         {name.ljust(width)}  {what}" for name, what in rows]
    return out
