"""Terminal banners, progress stages, header art and context checks.

The ui layer: terminal text and prompts, with input/output injected.
Imports app and core only (no platform, no root modules).
"""
import os
import sys

from agl.core.context_guard import GREEN_FROM, band

HEADER_FLAG = "ANTIGRAVITY_HEADER_SHOWN"

HEADER_TEXT = """
=============================================================================
    🚀 Google Antigravity Local - Plug & Play Auto-Bootstrap
=============================================================================
"""

_PLAIN = {"on": False}


def set_plain(val: bool) -> None:
    """Set the plain-mode flag for banners."""
    _PLAIN["on"] = bool(val)


def is_plain(plain_flag=None, *, ports=None) -> bool:
    """--plain or NO_COLOR: no art, no emoji, no bar blocks."""
    if plain_flag:
        return True
    if _PLAIN["on"]:
        return True
    env_get = ports.environ_get if (ports and hasattr(ports, "environ_get")) else os.environ.get
    return bool(env_get("NO_COLOR"))


def setup_console() -> None:
    """Windows consoles default to cp1252: make stdout/stderr UTF-8 so emoji and box art print."""
    if sys.platform != "win32":
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def safe_print(text, *, out=None, **kwargs) -> None:
    """print() that never raises on a console that cannot encode the text (cp1252, for example)."""
    fn = out if out is not None else print
    try:
        try:
            fn(text, **kwargs)
        except TypeError:
            fn(text)
    except UnicodeEncodeError:
        try:
            try:
                fn(text.encode("ascii", errors="replace").decode("ascii"), **kwargs)
            except TypeError:
                fn(text.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


def out(*args, **kwargs) -> None:
    """One line of terminal text: several values join with a space, one value prints as-is."""
    text = " ".join(str(x) for x in args) if len(args) > 1 else (args[0] if args else "")
    safe_print(text, out=print, **kwargs)


def stage(n, total, name, next_line, *, plain=None, ports=None, out=None) -> None:
    """One stage banner on one line: 'STAGE 2/4  SERVER  [bar]  what happens next'."""
    ascii_only = is_plain(plain, ports=ports)
    if not ascii_only:
        try:
            "█░".encode(getattr(sys.stdout, "encoding", None) or "ascii")
        except (UnicodeEncodeError, LookupError):
            ascii_only = True
    full, empty = ("#", "-") if ascii_only else ("█", "░")
    filled = round(20 * n / total)
    safe_print("", out=out, flush=True)
    safe_print(f"STAGE {n}/{total}  {name}  [{full * filled}{empty * (20 - filled)}]  {next_line}", out=out, flush=True)


def level_clear(model, agent, ready=None, *, ports=None, out=print) -> None:
    """The short summary at the end of setup: what was picked, where it came from, and the log file."""
    catalog = getattr(ports, "model_wizard", None) if ports else None
    catalog_list = getattr(catalog, "CATALOG", []) if catalog else []
    size = next((s for t, s, _ in catalog_list if t == model), None)
    source = getattr(ports, "_FACTS", {}).get("source", "catalog") if hasattr(ports, "_FACTS") else "catalog"
    project_dir = getattr(ports, "PROJECT_DIR", os.getcwd()) if ports else os.getcwd()
    runlog_mod = getattr(ports, "runlog", None) if ports else None
    logs_dir = ports.path_join(project_dir, "logs") if (ports and hasattr(ports, "path_join")) else os.path.join(project_dir, "logs")
    log_file = runlog_mod.log_path(logs_dir) if runlog_mod and hasattr(runlog_mod, "log_path") else logs_dir

    rows = [
        ("model", model),
        ("size", f"{size:.1f} GB (catalog)" if size else "unknown"),
        ("source", source),
        ("agent", agent),
        ("log", log_file),
    ]
    width = max(len(k) for k, _ in rows)
    bar = "=" * 60
    lines = ["", bar, "  LEVEL CLEAR"] + [f"  {k.ljust(width)}  {v}" for k, v in rows]
    if ready:
        lines.append(f"  {ready}")
    lines.append(bar)
    safe_print("\n".join(lines), out=out)

    env_get = ports.environ_get if (ports and hasattr(ports, "environ_get")) else os.environ.get
    backend = "openai" if env_get("LOCAL_LLM_BACKEND") == "openai" else "ollama"
    coding_apps_mod = getattr(ports, "coding_apps", None) if ports else None
    config_mod = getattr(ports, "config", None) if ports else None
    base_url = config_mod.llm_base_url() if config_mod and hasattr(config_mod, "llm_base_url") else ""
    if coding_apps_mod and hasattr(coding_apps_mod, "lines"):
        safe_print("\n" + "\n".join(coding_apps_mod.lines(model, base_url, backend)), out=out)


_WORD = {"red": "RED", "amber": "AMBER", "green": "GREEN"}
_VERDICT = {"red": "That is too small for coding apps.", "amber": "That is tight for coding apps.",
            "green": "That is enough for coding apps."}
_ADVICE = {"red": "Expect the app to forget parts of your task.",
           "amber": "Keep tasks short and start a new chat often."}
_PI_TOO_SMALL = "pi needs more than about 32,768 tokens. It will not work well here."
_PI_TIGHT = "pi needs more than about 32,768 tokens. It may struggle here."


def _context_lines(tokens, source, told, platform):
    """The context check as plain lines (no prefix). Pure: the caller reads the window and prints."""
    colour = band(tokens)
    lines = []
    if source == "loaded":
        lines.append(f"{_WORD[colour]}: the model can hold {tokens:,} tokens at once. {_VERDICT[colour]}")
        lines.append("Source: Ollama reported this for the loaded model.")
        if colour in _ADVICE:
            lines.append(_ADVICE[colour])
        if tokens <= 16384:
            lines.append(_PI_TOO_SMALL)
        elif tokens <= 32768:
            lines.append(_PI_TIGHT)
    else:
        lines.append("NOT CHECKED: Ollama is not running, or the model is not loaded yet.")
        lines.append(f"{_WORD[colour]} (a guess): {tokens:,} tokens.")
        lines.append("Source: OLLAMA_CONTEXT_LENGTH in this terminal." if source == "env"
                     else "Source: Ollama's usual size for your graphics memory.")
        lines.append("The real size may be different. Run this again once the model is loaded.")
    if told:
        lines.append(f"The coding app we set up is told: {tokens:,}.")
    if colour != "green":
        lines.append("For more room, raise the context length in the Ollama app settings,")
        if platform == "win32":
            lines.append(f"or start the server with: $env:OLLAMA_CONTEXT_LENGTH={GREEN_FROM}; ollama serve")
        else:
            lines.append(f"or start the server with: OLLAMA_CONTEXT_LENGTH={GREEN_FROM} ollama serve")
        lines.append("We do not change your Ollama settings.")
    return lines


def context_check(interactive, ask=None, *, model=None, base_url=None, told=False, ports=None, out=print):
    """Stage 4: read the window Ollama runs now and say how it fits coding agents. Returns (tokens, source),
    or None when the check does not apply (no agent_setup, or the OpenAI-compatible backend)."""
    if ports is not None and hasattr(ports, "agent_setup"):
        agent_setup = ports.agent_setup
    else:
        agent_setup = sys.modules.get("agent_setup")
    live = getattr(agent_setup, "live_window", None) if agent_setup else None
    if live is None:
        return None
    env = ports.environ_copy() if (ports and hasattr(ports, "environ_copy")) else dict(os.environ)
    if env.get("LOCAL_LLM_BACKEND") == "openai":
        return None
    tokens, source = live(model, base_url or "", env)
    plat = getattr(getattr(ports, "sys", None), "platform", None) or sys.platform
    for line in _context_lines(tokens, source, told, plat):
        out(f"       {line}")
    return tokens, source


def print_header(*, ports=None, out=print) -> None:
    """Print the launch banner unless already shown by the parent process."""
    env_get = ports.environ_get if (ports and hasattr(ports, "environ_get")) else os.environ.get
    if env_get(HEADER_FLAG) == "1":
        return
    out(HEADER_TEXT)
