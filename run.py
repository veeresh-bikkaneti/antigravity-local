#!/usr/bin/env python3
"""Google Antigravity Local - 1-Command Plug & Play Bootstrap. write_to_file(TargetFile, CodeContent)"""
import argparse, os, re, shutil, sys, time; time = time

import download_size, hf_search, ledger, model_wizard, ollama_library, runlog
import probe as root_probe; probe = root_probe
from agl.app import agent, bootstrap, pick, probe as probe_app, server
from agl.core import capabilities, ranking
from agl.platform import config, hardware, http, ollama, process, state
from agl.ui import banner, pick_menu

if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace"); sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

PROJECT_DIR, IS_WIN = os.path.dirname(os.path.abspath(__file__)), sys.platform == "win32"
VENV_DIR, _PLAIN = os.path.join(PROJECT_DIR, "venv"), {"on": False}; VENV_PYTHON = os.path.join(VENV_DIR, "Scripts" if IS_WIN else "bin", "python.exe" if IS_WIN else "python")
MAX_SHELL_FAILURES, _SETUP_ONLY, UPGRADE_STATE_FILE = 3, False, os.path.join(PROJECT_DIR, ".antigravity_upgrade_state.json")
HEADER_FLAG, _WARNED, LOOPBACK_OLLAMA_HOST, DEFAULT_OLLAMA_HOSTS = banner.HEADER_FLAG, pick_menu._WARNED, "127.0.0.1:11434", (config.OLLAMA_BASE_URL, "http://127.0.0.1:11434")

FAMILIES = [
    (("embed", "rerank"), 5.0), (("qwen3", "devstral-small-2", "gpt-oss", "laguna"), 97.0), (("nanbeige",), 92.0), (("deepseek",), 90.0), (("qwen2.5",), 88.0),
    (("command-r",), 86.0), (("codestral",), 84.0), (("glm4", "glm-4"), 82.0), (("mistral-large", "devstral"), 80.0), (("gemma2",), 76.0),
    (("llama3.3", "llama3.1", "llama3.2", "llama3"), 74.0), (("phi4", "phi3"), 68.0), (("mistral",), 65.0),
]


def _raw_capability_score(model_name: str) -> float:
    name = str(model_name).lower().strip()
    score = next((sc for keys, sc in FAMILIES if any(k in name for k in keys)), 45.0)
    m = re.search(r"(\d+)(?:\.\d+)?b", name)
    score += min(float(m.group(1)), 72.0) * 0.3 if m else 4.0
    if "coder" in name or "code" in name: score += 8.0
    if any(k in name for k in ("agent", "tool", "search")): score += 8.0
    if "instruct" in name or "chat" in name: score += 4.0
    return score


def get_model_capability_score(name: str) -> float: return min(_raw_capability_score(name), 100.0)
def capability_rank_key(name: str) -> float: return _raw_capability_score(name)
def hardware_tier_model(vram: float, ram: float) -> str: return "qwen2.5-coder:14b" if (vram >= 15.0 or (vram >= 8.0 and ram >= 32.0)) else ("qwen2.5-coder:7b" if (vram >= 8.0 or ram >= 16.0) else "llama3.2:3b")
model_wizard.hardware_tier_model, model_wizard.get_model_capability_score, model_wizard.capability_rank_key = hardware_tier_model, get_model_capability_score, capability_rank_key


def _out(*a, **k): banner.safe_print(" ".join(str(x) for x in a) if len(a) > 1 else (a[0] if a else ""), out=getattr(__import__("builtins"), "print"), **k)

_FACTS, _safe_print = getattr(banner, "_FACTS", {"model": "unknown", "size": "unknown", "source": "catalog"}), banner.safe_print
_remember_upgrade_stay = getattr(pick, "_remember_upgrade_stay", lambda current, now=None: state.remember_upgrade_stay(current, now=now, path=UPGRADE_STATE_FILE))

def update_env_model(model_name: str):
    exc = state.update_env_model(model_name, env_file=os.path.join(PROJECT_DIR, ".env"))
    if exc is not None: _out(f"Couldn't update .env: {exc}")


class _PickPorts:
    def __init__(self): self._FACTS, self.download_size, self.ranking, self.shutil = _FACTS, download_size, ranking, shutil

    def _load_env(self): state.load_env(os.path.join(PROJECT_DIR, ".env"))
    def check_or_update_memory(self, *a, **k):
        try: return check_or_update_memory(*a, **k)
        except TypeError: return check_or_update_memory()

    def __getattr__(self, name):
        if name in globals(): return globals()[name]
        try: return __import__(name)
        except ImportError: raise AttributeError(name)

    def agent_sdk(self): return sys.modules.get("google.antigravity") or getattr(__import__("google.antigravity"), "antigravity", None)
    def index_memory(self):
        import memory
        from agl.platform import embeddings, memory_store
        return memory.MemoryIndexer(getattr(memory, "MemoryDatabase", memory_store.MemoryDatabase)(getattr(memory, "DB_PATH", None)), getattr(memory, "EmbeddingProvider", embeddings.EmbeddingProvider)(getattr(memory, "OLLAMA_API_BASE", None))).index_all(force=False)


def select_and_pull_model(base_url=None, requested_model=None, interactive=False, scan_library=False, **kwargs):
    return pick.select_and_pull_model(base_url or config.OLLAMA_BASE_URL, requested_model=requested_model, interactive=interactive, scan_library=scan_library, ports=_PickPorts(), out=_out, ask=lambda *a, **k: pick_menu.ask_which_model(*a, ports=_PickPorts(), out=_out, **k), stage=banner.stage)

def select_openai_model(base_url, requested_model=None, interactive=False, **kwargs): return pick_menu.select_openai_model(base_url, requested_model, interactive=interactive, ports=_PickPorts(), out=_out)

async def run_agent(model, base=config.LLM_BASE_URL, *a, **k):
    return await agent.run_agent(model, base, ports=k.get("ports") or _PickPorts(), out=k.get("out") or _out, input_fn=k.get("input_fn") or input)

def _pull_with_gate(*a, **k):
    return pick._pull_with_gate(*a, ports=k.pop("ports", None) or _PickPorts(), out=k.pop("out", None) or _out, **k)

is_model_installed, _free_for_fit, _plan_download = pick.is_model_installed, pick._free_for_fit, pick._plan_download
get_media_rows, get_library_rows = (lambda *a, **k: pick.get_media_rows(*a, ports=k.pop("ports", None) or _PickPorts(), out=k.pop("out", None) or _out, **k)), (lambda *a, **k: pick.get_library_rows(*a, ports=k.pop("ports", None) or _PickPorts(), out=k.pop("out", None) or _out, **k))
hf_menu_search, hf_menu_search_sized = (lambda *a, **k: pick.hf_menu_search(*a, ports=k.pop("ports", None) or _PickPorts(), out=k.pop("out", None) or _out, **k)), (lambda *a, **k: pick.hf_menu_search_sized(*a, ports=k.pop("ports", None) or _PickPorts(), out=k.pop("out", None) or _out, **k))
_installed_candidates, _find_candidate, _is_hf_short_alias, _printable_tag, _best_installed, _with_tag = pick._installed_candidates, pick._find_candidate, pick._is_hf_short_alias, pick._printable_tag, pick._best_installed, pick._with_tag
get_hardware_profile, get_system_ram_gb, get_free_resources = hardware.get_hardware_profile, hardware.get_system_ram_gb, hardware.free_resources
detect_backend, is_default_ollama_url, list_openai_models, check_ollama_service = lambda url: server.detect_backend(url, ports=_PickPorts()), lambda url: server.is_default_ollama_url(url, ports=_PickPorts()), lambda url: server.list_openai_models(url, ports=_PickPorts()), lambda host: server.check_ollama_service(host, ports=_PickPorts(), out=_out)
offer_upgrade, run_check_upgrades, check_or_update_memory, run_probe_command = lambda *a, **k: pick.offer_upgrade(*a, ports=k.pop("ports", None) or _PickPorts(), **k), lambda: pick.run_check_upgrades(ports=_PickPorts(), out=_out), lambda: probe_app.check_or_update_memory(ports=_PickPorts(), out=_out), lambda a: probe_app.run_probe_command(a, ports=_PickPorts(), out=_out)
get_installed_ollama_models, get_installed_details, get_installed_info, get_ledger_entries = ollama.installed_models, ollama.installed_details, ollama.installed_info, ledger.read
is_in_venv = lambda: bootstrap.is_in_venv()
bootstrap_venv = lambda *a, **k: bootstrap.bootstrap_venv(*a, ports=k.pop("ports", _PickPorts()), out=k.pop("out", _out), **k)
stage, context_check, level_clear, print_header, _refuse_non_chat, _ledger_warning, _hf_tag_ok = banner.stage, banner.context_check, banner.level_clear, banner.print_header, pick_menu.refuse_non_chat, pick_menu.ledger_warning, pick_menu.hf_tag_ok
path_join, makedirs, environ_get, environ_set, environ_pop, environ_copy = os.path.join, os.makedirs, os.environ.get, os.environ.__setitem__, os.environ.pop, lambda: dict(os.environ)
_load_env, _upgrade_candidates = lambda: state.load_env(os.path.join(PROJECT_DIR, ".env")), lambda *a, **k: pick._upgrade_candidates(*a, ports=_PickPorts(), **k)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Plug-and-play bootstrap for Antigravity with a local Ollama model.")
    add = ap.add_argument
    add("model", nargs="?", help="Ollama model to use (pulled if missing)"); add("--model", dest="model_flag", metavar="TAG", help="same as the positional model"); add("--serve", action="store_true", help="start the web UI + API (needs no Ollama)"); add("--host", help="with --serve: bind address"); add("--port", type=int, help="with --serve: port (default: a free one)")
    add("--check-upgrades", action="store_true", help="list catalog models that beat your best installed one and fit this PC; report only, never pulls"); add("--probe", action="store_true", help="run one live tool call against the model and record pass or fail in the local ledger, then exit"); add("--scan-library", action="store_true", help="also list models read off ollama.com/library (reads HTML, so it can break; the curated list stays)"); add("-y", "--yes", action="store_true", help="skip the menu and every question: use the best installed model, or exit 1 and print the ollama pull command. Never downloads")
    add("--sync-memory", action="store_true", help="re-index the memory fabric and exit"); add("--plain", action="store_true", help="no colour, no art, ASCII only (NO_COLOR does the same)")
    add("--agent", choices=["shell", "pi", "opencode", "codex", "claude"], default="shell", help="coding agent to land in: shell (default, Antigravity SDK), or pi / opencode / codex / claude pre-configured for your local model"); add("--agent-config-only", action="store_true", help="with --agent: write the agent's config, print how to start it, and exit")
    add("--workspace", metavar="PATH", help="with --agent: the project folder the agent works in (default: the folder you ran this from, or this repo's workspace/ folder when you run it from here)"); add("--continue-local", action="store_true", help="with --agent: start with the prompt that makes the agent read HANDOFF.md and carry on")
    add("--coding-apps", action="store_true", help="print how to connect VS Code, Continue, terminal agents, Antigravity and Gemini CLI to your model, then exit"); add("--doctor", action="store_true", help="with --agent claude: read-only check for settings that send normal Claude Code sessions to a local model")
    add("--copy-user-settings", action="store_true", help="with --agent claude: copy (once) a safe slice of ~/.claude into ~/.claude-local"); add("--resume-from", metavar="ID|latest", help="with --agent claude: EXPERIMENTAL, fork a Claude Code session into the local model")
    args = ap.parse_args(argv)
    if args.model and args.model_flag and args.model != args.model_flag: ap.error("give the model once: python run.py <tag> or --model <tag>")
    args.model = args.model_flag or args.model
    for flag, on in (("--workspace", args.workspace), ("--agent-config-only", args.agent_config_only), ("--continue-local", args.continue_local)):
        if on and args.agent == "shell": ap.error(f"{flag} needs --agent pi, opencode, codex or claude")
    for flag, on in (("--doctor", args.doctor), ("--copy-user-settings", args.copy_user_settings), ("--resume-from", args.resume_from)):
        if on and args.agent != "claude": ap.error(f"{flag} needs --agent claude")
    if args.resume_from and args.continue_local: ap.error("--resume-from and --continue-local do different things; pick one")
    return args


def _dispatch_simple(args, ports):
    if args.coding_apps:
        backend = "openai" if ports.environ_get("LOCAL_LLM_BACKEND") == "openai" else "ollama"
        banner.safe_print("\n".join(__import__("coding_apps").lines(args.model or ports.environ_get("LOCAL_LLM_MODEL") or "<your-model>", config.llm_base_url(), backend)), out=_out)
        return True
    if args.doctor: return __import__("agent_setup").claude_doctor() or True
    if args.probe: sys.exit(probe_app.run_probe_command(args, ports=ports, out=_out))
    if args.check_upgrades: sys.exit(pick.run_check_upgrades(ports=ports, out=_out))
    if args.sync_memory:
        try: __import__("memory").cmd_sync(__import__("types").SimpleNamespace())
        except Exception as e: _out(f"Error syncing memory: {e}")
        return True
    return False


def _run_serve(args):
    return False if not args.serve else (__import__("serve").main((["--host", args.host] if args.host else []) + (["--port", str(args.port)] if args.port is not None else [])) or True)


def _setup_backend(args, ports):
    base_api = config.llm_base_url()
    host = base_api.replace("/v1", "").rstrip("/")
    backend = detect_backend(base_api)
    try: interactive = bool(sys.stdin.isatty() and sys.stdout.isatty()) and not getattr(args, "yes", False)
    except Exception: interactive = False
    global _SETUP_ONLY
    _SETUP_ONLY = not interactive
    if backend == "openai":
        banner.stage(2, 5, "SERVER", "use the OpenAI-compatible server you already run", plain=banner.is_plain(_PLAIN["on"], ports=ports), ports=ports, out=_out)
        banner.safe_print(f"       Found an OpenAI-compatible server at {base_api} (not Ollama). Nothing will be downloaded.", out=_out)
        os.environ["LOCAL_LLM_BACKEND"] = "openai"
    else:
        os.environ.pop("LOCAL_LLM_BACKEND", None)
        if backend is None and not is_default_ollama_url(base_api):
            banner.safe_print(f"\n❌ Nothing answered at {base_api}: no Ollama (/api/tags) and no OpenAI-compatible /models. Start your server, or fix LOCAL_LLM_BASE_URL in .env.", out=_out)
            sys.exit(1)
        chk = globals().get("check_ollama_service")
        try: res = chk(host) if chk else True
        except TypeError: res = chk(host, ports=ports, out=_out)
        if not res: sys.exit(1)
    return base_api, host, backend, interactive


def _run_shell(model, base_api):
    import asyncio
    try:
        res = run_agent(model, base_api)
        if asyncio.iscoroutine(res): asyncio.run(res)
    except KeyboardInterrupt: _out("\n\n👋 Goodbye!\n"); sys.exit(0)


def _main(argv=None):
    raw = sys.argv[1:] if argv is None else list(argv)
    if raw and raw[0] == "handoff": sys.exit(__import__("handoff").main(raw[1:]))
    args, ports = parse_args(argv), _PickPorts()
    if _dispatch_simple(args, ports): return
    ports.print_header()
    if not globals()["is_in_venv"](): bootstrap.bootstrap_venv(ports=ports, out=_out); return
    if _run_serve(args): return
    base_api, host, backend, interactive = _setup_backend(args, ports)
    try:
        model = select_openai_model(base_api, args.model, interactive=interactive) if backend == "openai" else select_and_pull_model(host, args.model, interactive=interactive, scan_library=args.scan_library)
    except KeyboardInterrupt:
        _out("\nStopped with Ctrl+C. Nothing was saved. Run python run.py to start again."); sys.exit(130)
    if not model: sys.exit(1)
    agent.handle_agent(args, model, base_api, interactive, ports=ports, out=_out)
    probe_app.check_or_update_memory(ports=ports, out=_out)
    _run_shell(model, base_api)


def main(argv=None):
    state.load_env(os.path.join(PROJECT_DIR, ".env"))
    if os.environ.get("ANTIGRAVITY_NO_RUN_LOG"): return _main(argv)
    with runlog.tee(os.path.join(PROJECT_DIR, "logs")): return _main(argv)


if __name__ == "__main__":
    main()
