"""Terminal banners, progress stages, header art and context checks.

The ui layer: terminal text and prompts, with input/output injected.
Imports app and core only (no platform, no root modules).
"""
import os
import sys

from agl.core.window_fit import RUNGS

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


def _article(tokens):
    """'an' for numbers said with a vowel first (8,192, 11,000, 18,000), else 'a'."""
    lead = f"{tokens:,}".split(",")[0]
    return "an" if lead.startswith("8") or lead in ("11", "18") else "a"


def _context_lines(tag, tokens, source, target, trained, told):
    """Stage 4 as plain lines (no prefix), worded as docs/mockups/real-window.md. Pure: the caller reads
    the window, the target (0: nothing fits, None: not read) and the trained max, then prints."""
    tag = tag or "The model"
    if source == "default":
        lines = [f"{tag} runs with Ollama's default {tokens:,} tokens."]
    else:
        lines = [f"{tag} runs with {_article(tokens)} {tokens:,} token window."]
    if target == 0:
        lines.append(f"This GPU cannot fit an {RUNGS[0]:,} window on top of the weights.")
        lines.append("No copy. A long prompt can use /steps.")
    elif target is None:
        lines.append("Free GPU memory or the model's shape was not read, so there is no target.")
    elif trained and tokens >= trained:
        lines.append("That is as high as this model goes. A bigger copy will not help.")
    elif tokens >= target:
        lines.append(f"That covers the {target:,} this GPU can give. No copy needed.")
    else:
        lines.append(f"Coding agents want about {target:,} on this GPU.")
    if told:
        lines.append(f"The coding app we set up is told: {tokens:,}.")
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
    aim = getattr(agent_setup, "window_target", None)
    target, trained = aim(model, base_url or "", env) if aim else (None, None)
    for line in _context_lines(model, tokens, source, target, trained, told):
        out(f"       {line}")
    return tokens, source


def print_header(*, ports=None, out=print) -> None:
    """Print the launch banner unless already shown by the parent process."""
    env_get = ports.environ_get if (ports and hasattr(ports, "environ_get")) else os.environ.get
    if env_get(HEADER_FLAG) == "1":
        return
    out(HEADER_TEXT)
