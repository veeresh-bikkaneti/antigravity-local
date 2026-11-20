"""Terminal banners, progress stages, header art and context checks.

The ui layer: terminal text and prompts, with input/output injected.
Imports app and core only (no platform, no root modules).
"""
import os
import sys

HEADER_FLAG = "ANTIGRAVITY_HEADER_SHOWN"

HEADER_TEXT = """
=============================================================================
    🚀 Google Antigravity Local - Plug & Play Auto-Bootstrap
=============================================================================
"""

_PLAIN = {"on": False}
_WARNED = set()


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


def safe_print(text, *, out=print) -> None:
    """print() that never raises on a console that cannot encode the text (cp1252, for example)."""
    try:
        try:
            out(text, flush=True)
        except TypeError:
            out(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        encoded = text.encode(enc, "replace").decode(enc, "replace")
        try:
            out(encoded, flush=True)
        except TypeError:
            out(encoded)


def stage(n, total, name, next_line, *, plain=None, ports=None, out=print) -> None:
    """One stage banner on one line: 'STAGE 2/4  SERVER  [bar]  what happens next'."""
    ascii_only = is_plain(plain, ports=ports)
    if not ascii_only:
        try:
            "█░".encode(getattr(sys.stdout, "encoding", None) or "ascii")
        except (UnicodeEncodeError, LookupError):
            ascii_only = True
    full, empty = ("#", "-") if ascii_only else ("█", "░")
    filled = round(20 * n / total)
    safe_print("", out=out)
    safe_print(f"STAGE {n}/{total}  {name}  [{full * filled}{empty * (20 - filled)}]  {next_line}", out=out)


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


def context_check(interactive, ask=None, *, ports=None, out=print) -> None:
    """Stage 4: say once if the server's context window is too small for coding agents."""
    agent_setup = getattr(ports, "agent_setup", None) if ports else None
    if agent_setup is None:
        agent_setup = sys.modules.get("agent_setup")
    check = getattr(agent_setup, "claude_context", None) if agent_setup else None
    if check is None:
        return
    env = ports.environ_copy() if (ports and hasattr(ports, "environ_copy")) else dict(os.environ)
    if env.get("LOCAL_LLM_BACKEND") == "openai":
        return
    warning = check(env)[1]
    if warning is None:
        return
    warning = warning.replace("Claude Code", "the coding agent")
    out(f"       {warning}")
    plat = getattr(getattr(ports, "sys", None), "platform", None) or sys.platform
    if plat == "win32":
        out("       $env:OLLAMA_CONTEXT_LENGTH=65536; ollama serve")
    else:
        out("       OLLAMA_CONTEXT_LENGTH=65536 ollama serve")


def print_header(*, ports=None, out=print) -> None:
    """Print the launch banner unless already shown by the parent process."""
    env_get = ports.environ_get if (ports and hasattr(ports, "environ_get")) else os.environ.get
    if env_get(HEADER_FLAG) == "1":
        return
    out(HEADER_TEXT)


def warn_once(key, text, *, out=print) -> None:
    """Print a warning line at most once per run."""
    if key not in _WARNED:
        _WARNED.add(key)
        out(f"       Warning: {text}")
