#!/usr/bin/env python3
"""
=============================================================================
 Google Antigravity Local - 1-Command Plug & Play Bootstrap
=============================================================================
One command to rule them all:
- Auto-detects OS and system hardware (RAM/VRAM)
- Auto-creates virtual environment & installs dependencies
- Auto-detects / starts Ollama local server in background
- Auto-evaluates local models and picks the MOST CAPABLE model available
  (Nanbeige, Qwen 2.5, DeepSeek, Codestral, LLaMA 3.x, Gemma 2)
- Pre-checks inventory before downloading (zero redundant pulls)
- Runs autonomous workspace agent and starts an interactive agent shell!
=============================================================================
"""

import sys
import os
import re
import platform
import shutil
import time
import json
import argparse

import capabilities
import coding_apps
import download_size
import hardware
import hf_search
import ledger
import model_wizard
import ollama_library
import ollama_models
import probe
import pull_gate
import quant_pick
import ranking
import runlog
import task_report
import userdata
from agl.platform import config, http, ollama, process, state
from agl.app import pick
import agl.app.server, agl.app.agent, agl.app.probe
from agl.ui import banner, pick_menu

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(PROJECT_DIR, "venv")


def _load_env():
    """Load PROJECT_DIR/.env into os.environ when python-dotenv is installed. Without it, .env is simply skipped."""
    state.load_env(os.path.join(PROJECT_DIR, ".env"))  # moved, shim until Phase 6
IS_WIN = sys.platform == "win32"
VENV_PYTHON = os.path.join(VENV_DIR, "Scripts" if IS_WIN else "bin", "python.exe" if IS_WIN else "python")

MAX_SHELL_FAILURES = 3
_SETUP_ONLY = False  # set by main() when there is no terminal (--yes, piped, CI): stop after setup

_FACTS = {"source": "installed"}  # set to "pulled" when this run downloads the model


_PLAIN = {"on": False}  # set by _main() from --plain


def _plain():
    """--plain or NO_COLOR: no art, no emoji, no bar blocks."""
    # moved, shim until Phase 6
    return banner.is_plain(_PLAIN["on"], ports=_PickPorts())


def _safe_print(text):
    """print() that never raises on a console that cannot encode the text (cp1252, for example)."""
    # moved, shim until Phase 6
    return banner.safe_print(text, out=_out)


def stage(n, total, name, next_line):
    """One stage banner on one line: 'STAGE 2/4  SERVER  [bar]  what happens next'."""
    # moved, shim until Phase 6
    return banner.stage(n, total, name, next_line, plain=_plain(), ports=_PickPorts(), out=_out)


def level_clear(model, agent, ready=None):
    """The short summary at the end of setup: what was picked, where it came from, and the log file."""
    # moved, shim until Phase 6
    return banner.level_clear(model, agent, ready=ready, ports=_PickPorts(), out=_out)


def context_check(interactive, ask=None, out=None):
    """Stage 4: say once if the server's context window is too small for coding agents. Never changes Ollama."""
    # moved, shim until Phase 6
    return banner.context_check(interactive, ask=ask, ports=_PickPorts(), out=out if out is not None else _out)


HEADER_FLAG = banner.HEADER_FLAG


def print_header():
    # moved, shim until Phase 6
    return banner.print_header(ports=_PickPorts(), out=_out)

def is_in_venv():
    return sys.prefix != sys.base_prefix

def get_system_ram_gb():
    """Total RAM in GB (0.0 = unknown). The work lives in hardware.py; this name stays for old callers."""
    return hardware.get_system_ram_gb()

def get_hardware_profile():
    """System RAM, GPU name and total VRAM. The work lives in hardware.py; this name stays for old callers."""
    return hardware.get_hardware_profile()

def get_free_resources():
    """Free VRAM, free RAM and free disk right now (hardware.free_resources)."""
    return hardware.free_resources()

def _free_for_fit(hw, res):
    """(free_vram, free_ram) to fit models against. An unknown GPU counts as 0 VRAM (fit on RAM only);
    unknown free RAM falls back to total RAM so we never fit against zero by accident."""
    vram = res["free_vram_gb"] if res.get("gpu_known") else 0.0
    ram = res.get("free_ram_gb") or hw.get("ram_gb") or 0.0
    return vram, ram

def bootstrap_venv():
    """Create virtual environment and install requirements if not inside one."""
    stage(1, 5, "ENVIRONMENT", "check the Python environment, then find Ollama")
    healthy = True  # a healthy run prints one line; anything we have to create or install prints its own
    if not os.path.exists(VENV_DIR) or not os.path.exists(VENV_PYTHON):
        healthy = False
        print(f"       Creating virtual environment at: {VENV_DIR}")
        process.check_call([sys.executable, "-m", "venv", VENV_DIR])

    # Copy .env.example to .env if missing
    env_file = os.path.join(PROJECT_DIR, ".env")
    env_example = os.path.join(PROJECT_DIR, ".env.example")
    if not os.path.exists(env_file) and os.path.exists(env_example):
        healthy = False
        print("       Generating default .env from .env.example...")
        shutil.copyfile(env_example, env_file)

    # Check if google-antigravity is installed in venv
    try:
        process.check_call([VENV_PYTHON, "-c", "import google.antigravity"], stdout=process.DEVNULL, stderr=process.DEVNULL)
        print("       Python environment ready (google-antigravity installed)" if healthy
              else "       Dependencies verified: 'google-antigravity' is ready.")
    except process.CalledProcessError:
        healthy = False
        print("       Installing dependencies from requirements.txt (first run only)...")
        req_file = os.path.join(PROJECT_DIR, "requirements.txt")
        process.check_call([VENV_PYTHON, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])  # not pip.exe: Windows cannot self-replace it
        process.check_call([VENV_PYTHON, "-m", "pip", "install", "-r", req_file, "--quiet"])
        print("       Dependencies successfully installed.")

    # Relaunch script using the venv python
    if not healthy:
        print("       Switching execution to managed environment...")
    sys.stdout.flush()  # the venv child writes next; our buffered lines must reach the log and screen first
    sys.stderr.flush()
    script_path = os.path.abspath(__file__)
    os.environ[HEADER_FLAG] = "1"  # inherited by both relaunch paths below (execv and the Windows child process)
    if IS_WIN:
        try:
            sys.exit(process.call([VENV_PYTHON, script_path] + sys.argv[1:]))
        except KeyboardInterrupt:
            sys.exit(0)
    else:
        os.execv(VENV_PYTHON, [VENV_PYTHON, script_path] + sys.argv[1:])

def _is_tty(stream):
    """True for a real terminal. A missing or closed stream (pythonw, a closed pipe) is just not a terminal."""
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


LOOPBACK_OLLAMA_HOST = "127.0.0.1:11434"

def check_ollama_service(base_url=config.OLLAMA_BASE_URL):
    """Check if Ollama is running; if not, attempt to start it."""
    # moved to agl.app.server, shim until Phase 6
    return agl.app.server.check_ollama_service(base_url, ports=_PickPorts(), out=_out)

DEFAULT_BASE_URL = config.LLM_BASE_URL  # moved, shim until Phase 6: the one default lives in agl.platform.config
DEFAULT_OLLAMA_HOSTS = (config.OLLAMA_BASE_URL, "http://127.0.0.1:11434")


def _http_get(url, timeout=3):
    """Body text of a 200 reply, or None for anything else (refused, timeout, non-200).
    moved, shim until Phase 6: the urlopen call now lives in agl.platform.http"""
    return http.get_text(url, timeout=timeout)  # moved, shim until Phase 6


def _server_urls(base_url):
    """(ollama root, [candidate /models URLs]) for a LOCAL_LLM_BASE_URL such as http://localhost:1234/v1."""
    base = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if base.endswith("/v1"):
        return base[:-3].rstrip("/"), [base + "/models"]
    return base, [base + "/v1/models", base + "/models"]


def list_openai_models(base_url):
    """Model ids from an OpenAI-compatible GET /models (the `data[].id` list). [] when it does not answer in that shape."""
    for url in _server_urls(base_url)[1]:
        body = _http_get(url)
        if body is None:
            continue
        try:
            data = json.loads(body).get("data")
        except Exception:
            continue
        if isinstance(data, list):
            return [m["id"] for m in data if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"].strip()]
    return []


def _openai_answers(base_url):
    for url in _server_urls(base_url)[1]:
        body = _http_get(url)
        if body is None:
            continue
        try:
            if isinstance(json.loads(body).get("data"), list):
                return True
        except Exception:
            continue
    return False


def detect_backend(base_url):
    """Which server answers at LOCAL_LLM_BASE_URL: "ollama" (its own /api/tags), "openai" (an OpenAI-compatible
    GET /models with a `data` list, e.g. LM Studio, llama.cpp, vLLM), or None when neither answers."""
    host = _server_urls(base_url)[0]
    if _http_get(f"{host}/api/tags") is not None:
        return "ollama"
    if _openai_answers(base_url):
        return "openai"
    return None


def is_default_ollama_url(base_url):
    return _server_urls(base_url)[0].lower() in DEFAULT_OLLAMA_HOSTS


def get_installed_ollama_models(base_url=config.OLLAMA_BASE_URL):
    """
    Rigorously detect already pulled models using dual-tier checks:
    Tier 1: Ollama HTTP API (/api/tags)
    Tier 2: Ollama CLI (`ollama list`) fallback
    Returns a set of normalized model identifiers.
    """
    models = ollama.installed_models(base_url)  # moved, shim until Phase 6: the Tier-1 REST read lives in agl.platform.ollama

    # Tier 2: CLI fallback if API was empty or unreachable
    if not models and shutil.which("ollama"):
        try:
            output = process.check_output(["ollama", "list"], text=True, stderr=process.DEVNULL)
            for line in output.splitlines()[1:]:
                parts = line.split()
                if parts:
                    name = parts[0].strip().lower()
                    models.add(name)
                    clean_name = name.split("/")[-1]
                    models.add(clean_name)
        except Exception:
            pass

    return models

def get_installed_info(base_url=config.OLLAMA_BASE_URL):
    """{normalised tag: {"size_gb", "digest"}} from Ollama's /api/tags (size is in bytes). Each model is listed under
    its full name and its short name (after the last slash), the same two names get_installed_ollama_models returns.
    {} when Ollama does not answer: a size we were not told is left out, never guessed."""
    # moved, shim until Phase 6: the REST read lives in agl.platform.ollama
    return ollama.installed_info(base_url)


def _raw_capability_score(model_name: str) -> float:
    """
    Computes an agentic capability score to automatically select the MOST CAPABLE model:
    - Nanbeige: Top-tier multi-step agentic reasoning and sequential tool calling (Nanbeige 4.1/4.2/4.3, Nanbeige 2-16B)
    - DeepSeek Coder / R1: World-class programming, fill-in-the-middle, and competitive reasoning
    - Qwen 2.5 Coder / Qwen 2.5: Proven flagship open coding & native OpenAI function calling
    - Command R / R+: Enterprise multi-step tool execution and structured citations
    - Codestral: Dedicated 32k context coding model
    - GLM-4: Advanced multilingual agentic tool use and function calling
    - Mistral Large / Devstral: High software architecture capability
    - Gemma 2: High general reasoning (streaming/text)
    - LLaMA 3.3 / 3.1: Strong general foundation
    - Scale weighting: 70B > 35B > 33B > 32B > 27B > 22B > 16B > 14B > 9B > 8B > 7B > 3B
    """
    name = model_name.lower().strip()
    score = 0.0

    # 1. Family weighting for agentic / tool-calling / reasoning capabilities
    if "embed" in name or "rerank" in name:
        score += 5.0    # embedding / reranker tags cannot chat or call tools; checked first so "qwen3-embedding" is not a qwen3
    elif "qwen3" in name or "devstral-small-2" in name or "gpt-oss" in name or "laguna" in name:
        score += 97.0   # 2026 agentic families (see model_wizard.CATALOG); must out-score qwen2.5-coder:14b (raw 100.2)
    elif "nanbeige" in name:
        score += 92.0   # Nanbeige (4.1/4.2/4.3, 2-16B) - top agentic tool caller & deep search
    elif "deepseek" in name:
        score += 90.0   # DeepSeek Coder V2 / R1 / V2.5 - world-class code synthesis
    elif "qwen2.5" in name:
        score += 88.0   # Qwen 2.5 Coder / Qwen 2.5 - native OpenAI tool calling benchmark leader
    elif "command-r" in name:
        score += 86.0   # Cohere Command R / Command R+ - enterprise tool calling
    elif "codestral" in name:
        score += 84.0   # Mistral Codestral 22B
    elif "glm4" in name or "glm-4" in name:
        score += 82.0   # Zhipu GLM-4
    elif "mistral-large" in name or "devstral" in name:
        score += 80.0   # Mistral Large / Devstral
    elif "gemma2" in name:
        score += 76.0   # Gemma 2
    elif "llama3.3" in name or "llama3.1" in name or "llama3.2" in name or "llama3" in name:
        score += 74.0   # Meta LLaMA 3.x
    elif "phi4" in name or "phi3" in name:
        score += 68.0   # Microsoft Phi
    elif "mistral" in name:
        score += 65.0
    else:
        score += 45.0

    # 2. Parameter scale weighting
    size_match = re.search(r"(\d+)(?:\.\d+)?b", name)
    if size_match:
        size = float(size_match.group(1))
        score += min(size, 72.0) * 0.3
    else:
        score += 4.0

    # 3. Task optimization keywords
    if "coder" in name or "code" in name:
        score += 8.0
    if "agent" in name or "tool" in name or "search" in name:
        score += 8.0
    if "instruct" in name or "chat" in name:
        score += 4.0

    return score


def get_model_capability_score(model_name: str) -> float:
    """Score for display, capped at 100. Never rank with this: ties at the cap break alphabetically."""
    return min(_raw_capability_score(model_name), 100.0)


def capability_rank_key(model_name: str) -> float:
    """The one key every ranking uses (menu default and automatic pick), uncapped so capable models never tie."""
    return _raw_capability_score(model_name)


def hardware_tier_model(vram_gb: float, ram_gb: float) -> str:
    """The model to download on a machine with none, by hardware. One owner: the menu and the automatic path both use it."""
    if vram_gb >= 15.0 or (vram_gb >= 8.0 and ram_gb >= 32.0):
        return "qwen2.5-coder:14b"
    if vram_gb >= 8.0 or ram_gb >= 16.0:
        return "qwen2.5-coder:7b"
    return "llama3.2:3b"

UPGRADE_STATE_FILE = os.path.join(PROJECT_DIR, ".antigravity_upgrade_state.json")
UPGRADE_STAY_SECONDS = 7 * 24 * 3600  # a "stay" answer quiets that one model for a week


def _best_installed(installed):
    """Highest-scoring installed chat-style tag (embedding and namespaced junk ignored), or None."""
    names = [m for m in installed if ":" in m or "/" in m]
    return max(names, key=get_model_capability_score, default=None)


class _PickPorts:
    """run.py's own globals, looked up at call time, so every test patch on a run.X name still lands."""
    def __getattr__(self, name):
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(name)

    def environ_get(self, key, default=None):
        import os
        return os.environ.get(key, default)

    def environ_copy(self):
        import os
        return dict(os.environ)

    def path_join(self, *parts):
        import os
        return os.path.join(*parts)

    def makedirs(self, path, exist_ok=True):
        import os
        return os.makedirs(path, exist_ok=exist_ok)

    def agent_sdk(self):
        import sys
        if "google.antigravity" in sys.modules:
            return sys.modules["google.antigravity"]
        import google.antigravity
        return sys.modules.get("google.antigravity", getattr(google, "antigravity", None))

    def index_memory(self):
        from memory import MemoryDatabase, EmbeddingProvider, MemoryIndexer
        db = MemoryDatabase()
        embedder = EmbeddingProvider()
        indexer = MemoryIndexer(db, embedder)
        return indexer.index_all(force=False)


def _out(*a, **k):
    print(*a, **k)  # looked up at call time: a patched builtins.print is used


def _upgrade_candidates(installed, hw, free_vram, free_ram):
    """Catalog picks plus the hardware tier pick that beat the best installed model and fit this PC right now.
    Each row: {'tag', 'gb', 'label' (where the size came from), 'note', 'fit'}. Report only: nothing is pulled."""
    # moved, shim until Phase 6
    return pick._upgrade_candidates(installed, hw, free_vram, free_ram, ports=_PickPorts())


def run_check_upgrades(base_url=None):
    """`python run.py --check-upgrades`: one line per better model that fits this PC. Never pulls. Always returns 0."""
    # moved, shim until Phase 6
    return pick.run_check_upgrades(base_url, ports=_PickPorts(), out=_out)


def _read_upgrade_state():
    return state.read_upgrade_state(UPGRADE_STATE_FILE)  # moved, shim until Phase 6


def offer_upgrade(installed, hw, free_vram, free_ram, now=None):
    """Interactive runs only. Returns the best fitting upgrade as a menu row ({"tag", "gb", "label", "fit"}) plus
    "current" (the installed model it would replace), or None. It never prompts: the model menu shows the row as
    "recommended upgrade", so there is one list and one question. Enter on that menu is a stay, remembered by
    _remember_upgrade_stay for UPGRADE_STAY_SECONDS per model."""
    current = _best_installed(installed)
    if not current:
        return None  # nothing installed yet: the normal path already offers the hardware pick
    now = time.time() if now is None else now
    stays = _read_upgrade_state().get("stay_until")
    stay_until = stays.get(current) if isinstance(stays, dict) else None  # old bare-number files mean no stay
    if isinstance(stay_until, (int, float)) and stay_until > now:
        return None  # a recent "stay" on this model: no upgrade row for the rest of the week
    rows = _upgrade_candidates(installed, hw, free_vram, free_ram)
    if not rows:
        return None
    return dict(rows[0], current=current)


def _remember_upgrade_stay(current, now=None):
    """Enter on the model menu while the upgrade row was shown: that model's upgrade stays quiet for a week."""
    state.remember_upgrade_stay(current, now=now, path=UPGRADE_STATE_FILE)  # moved, shim until Phase 6


def _with_tag(name):
    """'qwen2.5-coder' -> 'qwen2.5-coder:latest' (Ollama's implicit tag). '' stays ''."""
    name = name.strip().lower()
    return name if not name or ":" in name.split("/")[-1] else name + ":latest"

def is_model_installed(target_model, installed_models):
    """Exact match (an implicit ':latest' tag counts). No substring or bare-family matching."""
    target = _with_tag(target_model or "")
    if not target:
        return False
    installed = {_with_tag(m) for m in installed_models}
    return target in installed or target.split("/")[-1] in installed

def update_env_model(model_name: str):
    """Keep .env synchronized with the active local model."""
    exc = state.update_env_model(model_name, env_file=os.path.join(PROJECT_DIR, ".env"))  # moved, shim until Phase 6
    if exc is not None:
        print(f"Couldn't update .env: {exc}")  # the model still runs; only the saved default is lost

_WARNED = pick_menu._WARNED


# moved, shim until Phase 6
def _warn_once(key, text, *, out=None):
    return pick_menu._warn_once(key, text, out=out or _out)


def get_installed_details(base_url=config.OLLAMA_BASE_URL):
    """Size, age and capabilities of the installed models (ollama_models.installed_details)."""
    return ollama_models.installed_details(base_url)


def get_ledger_entries():
    """What past probes said about each model on this PC (ledger.read)."""
    return ledger.read()


def hf_menu_search(words=None, pipeline_tag="text-generation", limit=20):
    """Hugging Face GGUF search for the menu. Cached 24 h; offline gives [] and one warning line for the whole run."""
    rows, source = hf_search.search_models(userdata.data_dir() / "cache", query=words, pipeline_tag=pipeline_tag,
                                           limit=limit, token=(os.environ.get("HF_TOKEN") or "").strip() or None)
    if source == "offline":
        _warn_once("hf", "Could not reach Hugging Face. Showing installed and curated models only.")
    elif source == "stale":
        _warn_once("hf", "Could not reach Hugging Face. Showing results saved earlier.")
    return rows


def hf_menu_search_sized(words, free_vram, free_ram, limit=10):
    """hf_menu_search, plus the size of the quant each of the first rows would pull (one Hub tree read per repo)."""
    download_size.new_lookup_window()
    rows = hf_menu_search(words)
    sized = 0
    for r in rows:
        if sized >= limit:
            break
        if not model_wizard._is_repo_id(r.get("repo")):
            continue
        sized += 1
        user, repo = r["repo"].split("/", 1)
        info = download_size.hf_quant_size(user, repo, free_vram, free_ram)
        if info:
            r.update(size_gb=info["gb"], quant=info["quant"], size_source=info["source"])
    return rows


def get_media_rows(backend="ollama"):
    """Picture, video and sound models for their own menu section. Listed, never picked for an agent."""
    if backend != "ollama":
        return []
    if sys.platform == "darwin":
        return [{"tag": tag, "badges": (badge,), "note": note,
                 "hint": f'Run it yourself with: ollama run {tag} "your prompt"' + (" (the 9B Klein is non-commercial)" if nc else "")}
                for tag, badge, note, nc in capabilities.MEDIA_MODELS]
    rows = []
    for pipeline in ("text-to-image", "text-to-video"):
        for r in hf_menu_search(None, pipeline, 3)[:3]:
            rows.append({"tag": "huggingface.co/" + r["repo"], "badges": r["badges"], "note": pipeline.replace("-", " "),
                         "hint": f"Needs a separate runtime (for example ComfyUI or diffusers); this tool does not run it. "
                                 f"https://huggingface.co/{r['repo']}"})
    return rows


def get_library_rows(scan=False):
    """Extra models read off the Ollama library page. Only with --scan-library, because that page is read as HTML."""
    if not scan:
        return []
    rows = ollama_library.scan()
    if not rows:
        _warn_once("library", "Could not read the Ollama library page (--scan-library is fragile). Using the curated list.")
    return [{"tag": r["name"], "badges": r["badges"],
             "note": ("sizes " + ", ".join(r["sizes"]) + ": " if r["sizes"] else "") + r["note"]}
            for r in rows[:25]]


def _find_candidate(name, pool):
    """The candidate for a tag. A short name also finds an hf.co model (run.py lists that short alias),
    but never a model from any other namespace."""
    want = model_wizard._norm(name or "")
    for c in pool:
        have = model_wizard._norm(c["tag"])
        if have == want or (have.startswith("hf.co/") and have.rsplit("/", 1)[-1] == want):
            return c
    return None


def _is_hf_short_alias(name, names, details):
    """True when `name` is only the short alias of a longer hf.co name (u/m:q4 for hf.co/u/m:q4). With details, a name
    the details know by its own key is kept, so two namespaces that share a short name are both candidates."""
    if details:
        return name not in details and any(k.endswith("/" + name) for k in details)
    return any(o != name and o.endswith("/" + name) for o in names)


_SAFE_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@+-]*$")


def _printable_tag(tag):
    """A model name as it may be printed. A safe name is quoted as-is. Anything else is escaped (repr, cut to 60
    characters) and marked unsafe, so a newline cannot forge a printed line and a shell character cannot sit in a
    copy-paste command."""
    text = str(tag)
    if _SAFE_TAG_RE.fullmatch(text):
        return f"'{text}'"
    return f"{repr(text)[:60]} (unsafe name, shown escaped)"


def _installed_candidates(names, details, hw, entries):
    """One ranking candidate per installed model. Fit uses this PC's TOTAL memory, because a model that is loaded
    right now is already holding some of the free memory and must not look too big to itself."""
    names = [n for n in names if not _is_hf_short_alias(n, names, details)]  # drop hf.co short aliases
    vram, ram = hw.get("vram_gb") or 0.0, hw.get("ram_gb") or 0.0
    pool = []
    for name in names:
        d = ollama_models.lookup(details, name)
        caps = d["caps"] if d else None
        status = ledger.status(name, entries)
        badges = capabilities.ollama_badges(caps)
        if status == "pass":
            badges = capabilities.confirm_tools(badges)
        size = d["size_gb"] if d else None
        pool.append({
            "tag": name, "kind": capabilities.kind_from_ollama(caps),
            "fit": model_wizard.fit_label(size, vram, ram, headroom=model_wizard.FIT_HEADROOM) if size and (vram or ram) else None,
            "badges": badges, "installed": True, "ledger": status,
            "last_modified": d["modified_at"] if d else None, "downloads": None, "size_gb": size,
            "name_score": capability_rank_key(name),
        })
    return pool


def _ledger_warning(tag, entries):
    """Warns, never refuses: a model that failed the probe can still be picked."""
    # moved, shim until Phase 6
    return pick_menu.ledger_warning(tag, entries, ports=_PickPorts(), out=_out)


def _refuse_non_chat(tag, pool):
    """True (after saying why) when a model cannot drive a coding agent: an embedding or media model."""
    # moved, shim until Phase 6
    return pick_menu.refuse_non_chat(tag, pool, ports=_PickPorts(), out=_out)


def _typed_tag_problem(tag, installed_models):
    """None when a tag can be pulled or used, else the line that says why not."""
    # moved, shim until Phase 6
    return pick_menu.typed_tag_problem(tag, installed_models, ports=_PickPorts(), out=_out)


def _ask_which_model(display_names, installed_models, vram_gb, ram_gb, free_vram=None, free_ram=None, pool=None,
                     scan_library=False, upgrade=None, installed_info=None):
    """Run the wizard. Returns the chosen tag, or None to keep the installed model."""
    # moved, shim until Phase 6
    return pick_menu.ask_which_model(display_names, installed_models, vram_gb, ram_gb,
                                     free_vram=free_vram, free_ram=free_ram, pool=pool,
                                     scan_library=scan_library, upgrade=upgrade,
                                     installed_info=installed_info, ports=_PickPorts(), out=_out)


def _hf_tag_problem(tag):
    """The reason a typed hf.co tag is clearly wrong, or None."""
    # moved, shim until Phase 6
    return pick_menu.hf_tag_problem(tag, ports=_PickPorts(), out=_out)


def _hf_tag_ok(tag):
    """Vet a typed hf.co tag against the Hugging Face API."""
    # moved, shim until Phase 6
    return pick_menu.hf_tag_ok(tag, ports=_PickPorts(), out=_out)


def select_openai_model(base_url, requested_model=None, interactive=False):
    """Pick a model from an OpenAI-compatible server (LM Studio, llama.cpp, vLLM)."""
    # moved, shim until Phase 6
    return pick_menu.select_openai_model(base_url, requested_model=requested_model, interactive=interactive,
                                         ports=_PickPorts(), out=_out)


def _catalog_size(tag):
    """Download size in GB for a curated tag, or None."""
    want = model_wizard._norm(tag)
    return next((size for t, size, _ in model_wizard.CATALOG if model_wizard._norm(t) == want), None)


def _plan_download(tag, hw, res):
    """Work out what pulling `tag` really means: final tag (with the quant we picked for a typed Hugging Face repo),
    size, licence, gated or not, disk numbers. Returns the plan for pull_gate.ask_pull, or None (with a reason printed)
    when it cannot fit or the quant the user typed does not exist."""
    # moved, shim until Phase 6
    return pick._plan_download(tag, hw, res, ports=_PickPorts(), out=_out)


def _pull_with_gate(tag, interactive, hw, res):
    """The only way a model gets downloaded. Asks first, every time, whatever the size. Only a typed y pulls.
    --yes, piped input and CI never download: they print the exact command and return None."""
    # moved, shim until Phase 6
    return pick._pull_with_gate(tag, interactive, hw, res, ports=_PickPorts(), out=_out)


def select_and_pull_model(base_url=config.OLLAMA_BASE_URL, requested_model=None, interactive=False, scan_library=False):
    """
    Engineering Best Practice:
    1. NEVER download if compatible models are already present on the machine!
    2. Check local Ollama inventory FIRST across all modern open-source models:
       (Nanbeige, DeepSeek, Qwen 2.5 Coder, Command-R, Codestral, GLM-4, LLaMA, Gemma).
    3. If multiple models exist locally, automatically rank and select the MOST CAPABLE one.
    4. Only if the machine has ZERO models installed, evaluate the PC build (RAM, GPU, VRAM)
       and recommend/pull the optimal cutting-edge model tailored to the hardware.
    """
    # moved, shim until Phase 6
    return pick.select_and_pull_model(base_url, requested_model=requested_model, interactive=interactive,
                                      scan_library=scan_library, ports=_PickPorts(), out=_out, ask=_ask_which_model,
                                      stage=stage)

def _is_harness_error(exc):
    """True for the SDK's execution error. Matched by class name, so an SDK module move cannot break the CLI."""
    # moved to agl.app.agent, shim until Phase 6
    return agl.app.agent._is_harness_error(exc)

async def run_agent(model, base_url=config.LLM_BASE_URL):
    """Run the demo and the shell. Leaving (exit word or Ctrl+C) ends quietly; the SDK's close-time error is not shown."""
    # moved to agl.app.agent, shim until Phase 6
    return await agl.app.agent.run_agent(model, base_url, ports=_PickPorts(), out=_out, input_fn=input)

async def _run_agent_session(model, base_url, leave):
    """Run autonomous demonstration and interactive shell."""
    # Prompt contract: write_to_file(TargetFile, CodeContent, Overwrite=True)
    # moved to agl.app.agent, shim until Phase 6
    return await agl.app.agent._run_agent_session(model, base_url, leave, ports=_PickPorts(), out=_out, input_fn=input)

def check_or_update_memory():
    """Ensure the 3-Tier Memory Fabric (.memory/index.sqlite) is indexed and up to date."""
    # moved to agl.app.probe, shim until Phase 6
    agl.app.probe.check_or_update_memory(ports=_PickPorts(), out=_out)


def run_probe_command(args):
    """`python run.py --probe [model]`: one live tool call, recorded in the local ledger. Returns the exit code.
    It runs before the venv step and never starts or pulls anything: it only talks to a server that is already up."""
    # moved to agl.app.probe, shim until Phase 6
    return agl.app.probe.run_probe_command(args, ports=_PickPorts(), out=_out)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Plug-and-play bootstrap for Antigravity with a local Ollama model.")
    ap.add_argument("model", nargs="?", help="Ollama model to use (pulled if missing)")
    ap.add_argument("--model", dest="model_flag", metavar="TAG", help="same as the positional model")
    ap.add_argument("--serve", action="store_true", help="start the web UI + API (needs no Ollama)")
    ap.add_argument("--host", help="with --serve: bind address")
    ap.add_argument("--port", type=int, help="with --serve: port (default: a free one)")
    ap.add_argument("--check-upgrades", action="store_true",
                    help="list catalog models that beat your best installed one and fit this PC; report only, never pulls")
    ap.add_argument("--probe", action="store_true",
                    help="run one live tool call against the model and record pass or fail in the local ledger, then exit")
    ap.add_argument("--scan-library", action="store_true",
                    help="also list models read off ollama.com/library (reads HTML, so it can break; the curated list stays)")
    ap.add_argument("-y", "--yes", action="store_true", help="skip the menu and every question: use the best installed model, or exit 1 and print the ollama pull command. Never downloads")
    ap.add_argument("--sync-memory", action="store_true", help="re-index the memory fabric and exit")
    ap.add_argument("--plain", action="store_true", help="no colour, no art, ASCII only (NO_COLOR does the same)")
    ap.add_argument("--agent", choices=["shell", "pi", "opencode", "codex", "claude"], default="shell",
                    help="coding agent to land in: shell (default, Antigravity SDK), or pi / opencode / codex / "
                         "claude pre-configured for your local model")
    ap.add_argument("--agent-config-only", action="store_true",
                    help="with --agent: write the agent's config, print how to start it, and exit")
    ap.add_argument("--workspace", metavar="PATH",
                    help="with --agent: the project folder the agent works in (default: the folder you ran this "
                         "from, or this repo's workspace/ folder when you run it from here)")
    ap.add_argument("--continue-local", action="store_true",
                    help="with --agent: start with the prompt that makes the agent read HANDOFF.md and carry on")
    ap.add_argument("--coding-apps", action="store_true",
                    help="print how to connect VS Code, Continue, terminal agents, Antigravity and Gemini CLI to your model, then exit")
    ap.add_argument("--doctor", action="store_true",
                    help="with --agent claude: read-only check for settings that send normal Claude Code sessions "
                         "to a local model")
    ap.add_argument("--copy-user-settings", action="store_true",
                    help="with --agent claude: copy (once) a safe slice of ~/.claude into ~/.claude-local")
    ap.add_argument("--resume-from", metavar="ID|latest",
                    help="with --agent claude: EXPERIMENTAL, fork a Claude Code session into the local model")
    args = ap.parse_args(argv)
    if args.model and args.model_flag and args.model != args.model_flag:
        ap.error("give the model once: python run.py <tag> or --model <tag>")
    args.model = args.model_flag or args.model
    for flag, on in (("--workspace", args.workspace), ("--agent-config-only", args.agent_config_only),
                     ("--continue-local", args.continue_local)):
        if on and args.agent == "shell":
            ap.error(f"{flag} needs --agent pi, opencode, codex or claude")
    for flag, on in (("--doctor", args.doctor), ("--copy-user-settings", args.copy_user_settings),
                     ("--resume-from", args.resume_from)):
        if on and args.agent != "claude":
            ap.error(f"{flag} needs --agent claude")
    if args.resume_from and args.continue_local:
        ap.error("--resume-from and --continue-local do different things; pick one")
    return args


def main(argv=None):
    """Run everything, copying each printed line into logs/run-<date>.log (set ANTIGRAVITY_NO_RUN_LOG=1 to skip)."""
    if os.environ.get("ANTIGRAVITY_NO_RUN_LOG"):
        return _main(argv)
    with runlog.tee(os.path.join(PROJECT_DIR, "logs")):
        return _main(argv)


def _dispatch_simple(args):
    """Handle modes that run early or text-only commands without starting the LLM."""
    if args.coding_apps:
        backend = "openai" if os.environ.get("LOCAL_LLM_BACKEND") == "openai" else "ollama"
        _safe_print("\n".join(coding_apps.lines(args.model or os.environ.get("LOCAL_LLM_MODEL") or "<your-model>",
                                                config.llm_base_url(), backend)))
        return True
    if args.doctor:
        import agent_setup
        agent_setup.claude_doctor()
        return True
    if args.probe:
        sys.exit(run_probe_command(args))
    if args.check_upgrades:
        sys.exit(run_check_upgrades())
    if args.sync_memory:
        try:
            from memory import cmd_sync
            import types
            cmd_sync(types.SimpleNamespace())
        except Exception as e:
            print(f"Error syncing memory: {e}")
        return True
    return False


def _run_serve(args):
    """--serve: web UI + API on a free port."""
    if not args.serve:
        return False
    import serve
    serve_argv = []
    if args.host:
        serve_argv += ["--host", args.host]
    if args.port is not None:
        serve_argv += ["--port", str(args.port)]
    serve.main(serve_argv)
    return True


def _setup_backend(args):
    """Ensure Ollama or OpenAI-compatible server is answering."""
    base_api = config.llm_base_url()
    ollama_host = base_api.replace("/v1", "").rstrip("/")
    backend = detect_backend(base_api)
    interactive = _is_tty(sys.stdin) and _is_tty(sys.stdout) and not args.yes
    global _SETUP_ONLY
    _SETUP_ONLY = not interactive
    if backend == "openai":
        stage(2, 5, "SERVER", "use the OpenAI-compatible server you already run")
        print(f"       Found an OpenAI-compatible server at {base_api} (not Ollama). Nothing will be downloaded.")
        os.environ["LOCAL_LLM_BACKEND"] = "openai"
    else:
        os.environ.pop("LOCAL_LLM_BACKEND", None)
        if backend is None and not is_default_ollama_url(base_api):
            print(f"\n❌ Nothing answered at {base_api}: no Ollama (/api/tags) and no OpenAI-compatible /models. "
                  "Start your server, or fix LOCAL_LLM_BASE_URL in .env.")
            sys.exit(1)
        if not check_ollama_service(ollama_host):
            sys.exit(1)
    return base_api, ollama_host, backend, interactive


def _pick_model(args, base_api, ollama_host, backend, interactive):
    """Check local inventory & auto-select or pull most capable model."""
    try:
        if backend == "openai":
            model = select_openai_model(base_api, args.model, interactive=interactive)
        else:
            model = select_and_pull_model(ollama_host, args.model, interactive=interactive, scan_library=args.scan_library)
    except KeyboardInterrupt:
        print("\nStopped with Ctrl+C. Nothing was saved. Run python run.py to start again.")
        sys.exit(130)
    if not model:
        sys.exit(1)
    return model


def _handle_agent(args, model, base_api, interactive):
    """Configure external coding agent (--agent pi/opencode/codex/claude) and hand over."""
    if args.agent == "shell":
        return
    check_or_update_memory()
    import agent_setup
    try:
        workspace = agent_setup.resolve_workspace(args.workspace, os.getcwd(), PROJECT_DIR)
    except agent_setup.AgentSetupError as e:
        print(f"\n[agent setup] {e}")
        sys.exit(e.code)
    finder = None
    if args.resume_from:
        import handoff

        def finder(ident):
            try:
                return handoff.find_transcript(ident, handoff.repo_root(workspace))
            except handoff.HandoffError as e:
                raise agent_setup.AgentSetupError(str(e))
    stage(4, 5, "CONTEXT", "check the context window the coding agent needs")
    context_check(interactive=interactive)
    level_clear(model, args.agent)
    sys.exit(agent_setup.run(args.agent, model, base_api, workspace, config_only=args.agent_config_only,
                             continue_local=args.continue_local, resume_from=args.resume_from,
                             copy_settings=args.copy_user_settings, find_transcript=finder))


def _main(argv=None):
    raw = sys.argv[1:] if argv is None else list(argv)
    if raw and raw[0] == "handoff":  # `python run.py handoff ...`: stdlib only, no venv, no Ollama
        import handoff
        sys.exit(handoff.main(raw[1:]))
    args = parse_args(argv)  # before bootstrap_venv: --help / bad flags must not touch pip
    _PLAIN["on"] = bool(args.plain)
    if _dispatch_simple(args):
        return
    print_header()

    # Step 1: Self-bootstrap inside venv if running in system Python
    if not is_in_venv():
        bootstrap_venv()
        return

    # --serve: web UI + API on a free port. Needs no Ollama (memory falls back to pure Python).
    if _run_serve(args):
        return

    # Step 2: Ensure Ollama is running
    base_api, ollama_host, backend, interactive = _setup_backend(args)

    # Step 3: Check local inventory & auto-select most capable model
    model = _pick_model(args, base_api, ollama_host, backend, interactive)

    # Step 3.2: --agent pi/opencode/codex/claude: configure that agent for this model and hand over
    _handle_agent(args, model, base_api, interactive)

    # Step 3.5: Auto-index memory fabric
    check_or_update_memory()

    # Step 4: Run agent via asyncio
    _run_shell(model, base_api)


def _run_shell(model, base_api):
    """Run the agent. On Python 3.11+ asyncio.run turns the first Ctrl+C into a task cancel and re-raises
    KeyboardInterrupt once the task ends, outside run_agent, so it is caught here: Goodbye and exit 0."""
    import asyncio
    try:
        asyncio.run(run_agent(model, base_api))
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
