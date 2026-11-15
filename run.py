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
import subprocess
import platform
import shutil
import time
import json
import urllib.request
import urllib.error
import argparse

import capabilities
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

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(PROJECT_DIR, "venv")
IS_WIN = sys.platform == "win32"
VENV_PYTHON = os.path.join(VENV_DIR, "Scripts" if IS_WIN else "bin", "python.exe" if IS_WIN else "python")

MAX_SHELL_FAILURES = 3

def print_header():
    print("""
=============================================================================
    🚀 Google Antigravity Local - Plug & Play Auto-Bootstrap
=============================================================================
""")

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
    print("📦 [1/4] Checking Python Virtual Environment...")
    if not os.path.exists(VENV_DIR) or not os.path.exists(VENV_PYTHON):
        print(f"       Creating virtual environment at: {VENV_DIR}")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    else:
        print("       Existing virtual environment verified.")

    # Copy .env.example to .env if missing
    env_file = os.path.join(PROJECT_DIR, ".env")
    env_example = os.path.join(PROJECT_DIR, ".env.example")
    if not os.path.exists(env_file) and os.path.exists(env_example):
        print("       Generating default .env from .env.example...")
        shutil.copyfile(env_example, env_file)

    # Check if google-antigravity is installed in venv
    try:
        subprocess.check_call([VENV_PYTHON, "-c", "import google.antigravity"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("       Dependencies verified: 'google-antigravity' is ready.")
    except subprocess.CalledProcessError:
        print("       Installing dependencies from requirements.txt (first run only)...")
        req_file = os.path.join(PROJECT_DIR, "requirements.txt")
        subprocess.check_call([VENV_PYTHON, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])  # not pip.exe: Windows cannot self-replace it
        subprocess.check_call([VENV_PYTHON, "-m", "pip", "install", "-r", req_file, "--quiet"])
        print("       Dependencies successfully installed.")

    # Relaunch script using the venv python
    print("       Switching execution to managed environment...\n")
    script_path = os.path.abspath(__file__)
    if IS_WIN:
        try:
            sys.exit(subprocess.call([VENV_PYTHON, script_path] + sys.argv[1:]))
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

def check_ollama_service(base_url="http://localhost:11434"):
    """Check if Ollama is running; if not, attempt to start it."""
    print("🤖 [2/4] Verifying Ollama Local LLM Server...")
    tags_url = f"{base_url}/api/tags"
    
    # 1. Test if already responsive
    try:
        with urllib.request.urlopen(tags_url, timeout=3) as resp:
            if resp.status == 200:
                print(f"       Connected to Ollama service at: {base_url}")
                return True
    except Exception:
        pass

    # 2. Ollama is not responding, check if ollama binary exists to auto-start
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        print("\n❌ [ERROR] Ollama is not installed or not in your system PATH.")
        print("   Please install Ollama (free, open-source local LLM engine):")
        if IS_WIN:
            print("   👉 Windows: Download from https://ollama.com/download or run: winget install Ollama.Ollama")
        elif sys.platform == "darwin":
            print("   👉 macOS: Download from https://ollama.com/download or run: brew install ollama")
        else:
            print("   👉 Linux: Run: curl -fsSL https://ollama.com/install.sh | sh")
        print("\n   Once installed, run this command again!\n")
        sys.exit(1)

    print("       Ollama service is not running. Launching 'ollama serve' in background (this PC only)...")
    child_env = dict(os.environ, OLLAMA_HOST=LOOPBACK_OLLAMA_HOST)  # child only: our own environment stays as it was
    if os.environ.get("OLLAMA_HOST") and os.environ["OLLAMA_HOST"] != LOOPBACK_OLLAMA_HOST:
        print(f"       (Your OLLAMA_HOST is set; the server we start listens on {LOOPBACK_OLLAMA_HOST} only.)")
    try:
        if IS_WIN:
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=child_env
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=child_env
            )
        
        # Wait up to 12 seconds for Ollama to spin up
        for _ in range(12):
            time.sleep(1)
            try:
                with urllib.request.urlopen(tags_url, timeout=1) as resp:
                    if resp.status == 200:
                        print("       Ollama service successfully started.")
                        return True
            except Exception:
                continue
    except Exception as exc:
        print(f"       Warning: Auto-start attempted but got: {exc}")

    print(f"\n⚠️  Please ensure Ollama is running (`ollama serve`) at {base_url} and re-run.\n")
    return False

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_HOSTS = ("http://localhost:11434", "http://127.0.0.1:11434")


def _http_get(url, timeout=3):
    """Body text of a 200 reply, or None for anything else (refused, timeout, non-200)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8")
    except Exception:
        pass
    return None


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


def get_installed_ollama_models(base_url="http://localhost:11434"):
    """
    Rigorously detect already pulled models using dual-tier checks:
    Tier 1: Ollama HTTP API (/api/tags)
    Tier 2: Ollama CLI (`ollama list`) fallback
    Returns a set of normalized model identifiers.
    """
    models = set()
    
    # Tier 1: Query Ollama REST API
    tags_url = f"{base_url}/api/tags"
    try:
        with urllib.request.urlopen(tags_url, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for m in data.get("models", []):
                name = m.get("name", "").strip().lower()
                if name:
                    models.add(name)
                    clean_name = name.split("/")[-1]
                    models.add(clean_name)
    except Exception:
        pass

    # Tier 2: CLI fallback if API was empty or unreachable
    if not models and shutil.which("ollama"):
        try:
            output = subprocess.check_output(["ollama", "list"], text=True, stderr=subprocess.DEVNULL)
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
    env_file = os.path.join(PROJECT_DIR, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                content = f.read()
            if "LOCAL_LLM_MODEL=" in content:
                content = re.sub(r"LOCAL_LLM_MODEL=.*", f"LOCAL_LLM_MODEL={model_name}", content)
            else:
                content += f"\nLOCAL_LLM_MODEL={model_name}\n"
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

_WARNED = set()


def _warn_once(key, text):
    """Print a warning line at most once per run, so a flaky connection does not spam the screen."""
    if key not in _WARNED:
        _WARNED.add(key)
        print(f"       Warning: {text}")


def get_installed_details(base_url="http://localhost:11434"):
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
    if ledger.status(tag, entries) == "fail":
        hint = f" Check again with: python run.py --probe {tag}" if _SAFE_TAG_RE.fullmatch(str(tag)) else ""
        print(f"       Warning: {_printable_tag(tag)} failed a tool-call probe on this PC, so it may not work as a coding agent."
              f"{hint}")


def _refuse_non_chat(tag, pool):
    """True (after saying why) when a model cannot drive a coding agent: an embedding or media model."""
    cand = _find_candidate(tag, pool)
    if cand and capabilities.resolve_kind(cand["kind"], cand["tag"]) in ("embedding", "media"):
        print(f"       {_printable_tag(tag)} is an embedding or media model, so a coding agent cannot use it. Pick a chat model.")
        return True
    return False


def _ask_which_model(display_names, installed_models, vram_gb, ram_gb, free_vram=None, free_ram=None, pool=None, scan_library=False):
    """Run the wizard. Returns the chosen tag, or None to continue with the automatic pick."""
    configured = os.environ.get("LOCAL_LLM_MODEL")
    if pool is None:
        pool = _installed_candidates(display_names, {}, {"vram_gb": vram_gb, "ram_gb": ram_gb}, [])
    usable = ranking.agent_candidates(pool)
    best = ranking.best_for_agent(pool)
    if configured and is_model_installed(configured, installed_models) and _find_candidate(configured, usable):
        default = configured
    elif best:
        default = best["tag"]
    else:
        default = None
    tier = hardware_tier_model(vram_gb, ram_gb)
    download_size.new_lookup_window()
    menu = model_wizard.build_menu(display_names, vram_gb if free_vram is None else free_vram,
                                   ram_gb if free_ram is None else free_ram,
                                   recommended=None if best else tier,
                                   badges={model_wizard._norm(c["tag"]): c["badges"] for c in pool},
                                   library=get_library_rows(scan_library), media=get_media_rows(),
                                   size_of=download_size.resolve)
    if not default:
        default = tier  # no usable model installed: Enter means exactly what the automatic path would offer
    fv = vram_gb if free_vram is None else free_vram
    fr = ram_gb if free_ram is None else free_ram
    chosen = model_wizard.choose(menu, default, search_fn=lambda words: hf_menu_search_sized(words, fv, fr))
    if not chosen or model_wizard._norm(chosen) == model_wizard._norm(default or ""):
        # Kept the default: for an installed model the automatic path handles it; otherwise pull it.
        return None if chosen and is_model_installed(chosen, installed_models) else chosen
    if not is_model_installed(chosen, installed_models):
        if model_wizard.is_hf_tag(chosen):
            if not _hf_tag_ok(chosen):
                print("       Continuing with the automatic pick.")
                return None
        elif model_wizard.tag_exists(chosen) is False:
            print(f"       '{chosen}' is not on the Ollama registry. Continuing with the automatic pick.")
            return None
    return chosen


def _hf_tag_ok(tag):
    """Vet a typed hf.co tag against the Hugging Face API. False (with a reason) only when it is clearly wrong:
    not a repo, or not the hf.co/user/repo[:quant] shape. A quant with no matching .gguf is a warning, because
    Ollama is the final judge. Offline or private repos are allowed, same rule as the Ollama registry check."""
    status, detail = model_wizard.hf_check(tag)
    if status == "bad_tag":
        print(f"       '{tag}' is not a Hugging Face tag. Use hf.co/{{username}}/{{repository}}:{{quantization}}.")
        return False
    if status == "missing":
        print(f"       '{tag}' was not found on Hugging Face (404). Check the user and repo name.")
        return False
    if status == "no_quant":
        have = ", ".join(detail) if detail else "none (no .gguf files in that repo)"
        print(f"       Warning: no .gguf file in that repo matches the quant in '{tag}'. Quants it has: {have}.")
    return True


def select_openai_model(base_url, requested_model=None, interactive=False):
    """Pick a model from an OpenAI-compatible server (LM Studio, llama.cpp, vLLM). We never download here:
    the server owns its models. Order: --model, then LOCAL_LLM_MODEL if the server lists it, then the menu
    (real terminal) or the top-ranked loaded model (--yes, piped, CI). Returns the id, or None."""
    print("🧠 [3/4] Checking which models your server has loaded...")
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJECT_DIR, ".env"))
    except ImportError:
        pass
    ids = list_openai_models(base_url)
    if not ids:
        print("       The server answered but lists no models. Load a model in your server, then re-run.")
        return None
    print(f"       Found {len(ids)} model(s) on the server: {', '.join(ids)}")
    by_name = {m.lower(): m for m in ids}
    if requested_model:
        chosen = by_name.get(requested_model.strip().lower())
        if not chosen:
            print(f"       '{requested_model}' is not loaded on this server. Load it there, or pick one it lists.")
            return None
    else:
        configured = (os.environ.get("LOCAL_LLM_MODEL") or "").strip().lower()
        default = by_name.get(configured) or max(ids, key=capability_rank_key)
        chosen = default
        if interactive:
            menu = model_wizard.build_menu(ids, 0.0, 0.0, backend="openai")
            picked = model_wizard.choose(menu, default, backend="openai")
            chosen = by_name.get((picked or "").lower())
            if not chosen:
                print(f"       '{picked}' is not loaded on this server. Keeping '{default}'.")
                chosen = default
    print(f"       ✅ Using '{chosen}' from your server. Nothing to download.")
    update_env_model(chosen)
    return chosen


def _catalog_size(tag):
    """Download size in GB for a curated tag, or None."""
    want = model_wizard._norm(tag)
    return next((size for t, size, _ in model_wizard.CATALOG if model_wizard._norm(t) == want), None)


def _plan_download(tag, hw, res):
    """Work out what pulling `tag` really means: final tag (with the quant we picked for a typed Hugging Face repo),
    size, licence, gated or not, disk numbers. Returns the plan for pull_gate.ask_pull, or None (with a reason printed)
    when it cannot fit or the quant the user typed does not exist."""
    text = tag or ""
    # ASCII only (the Kelvin sign lowercases to a plain k), no "..", and the usual tag shape.
    if not text.isascii() or ".." in text or not model_wizard.TAG_RE.fullmatch(text.lower()):
        print(f"       {tag!r} is not a model tag (ASCII letters, digits, . _ - / : only, and it cannot start with a dash).")
        return None
    free_vram, free_ram = _free_for_fit(hw, res)
    plan = {"tag": tag, "quant": None, "size_gb": None, "size_source": None, "license": None, "gated": False,
            "free_disk_gb": res["free_disk_gb"], "disk_total_gb": res["disk_total_gb"]}
    parsed = model_wizard.parse_hf_tag(tag) if model_wizard.is_hf_tag(tag) else None
    if not parsed:
        info = download_size.resolve(tag, _catalog_size(tag))
        if info:
            plan.update(size_gb=info["gb"], size_source=info["source"])
        return plan
    user, repo, typed_quant = parsed
    if model_wizard._STATE["offline"]:
        info = {"status": "unknown", "gated": False, "license": None}  # the Hub is down this run: do not ask again
    else:
        info = model_wizard.hf_repo_info(user, repo)
    if info["status"] == "missing":
        print(f"       '{user}/{repo}' was not found on Hugging Face (404). Check the user and repo name.")
        return None
    plan["license"], plan["gated"] = info["license"], info["gated"]
    if plan["gated"]:
        return plan
    files = [] if model_wizard._STATE["offline"] else model_wizard.hf_tree_files(user, repo)
    if not files:
        print("       Could not read the file sizes from Hugging Face. Asking you with the tag as typed.")
        return plan
    pick = quant_pick.pick_quant(files, free_vram, free_ram, wanted=typed_quant)
    if pick is None:
        if typed_quant:
            have = sorted({q for q in (quant_pick.quant_of(f["name"]) for f in files) if q})
            print(f"       No {typed_quant.upper()} file in that repo. Quants it has: {', '.join(have) or 'none'}.")
        else:
            print(f"       No quant in {user}/{repo} fits {free_vram:.1f} GB free VRAM + {free_ram:.1f} GB free RAM. Try a smaller model.")
        return None
    if pick["fit"] == "too big":
        print(f"       {typed_quant.upper()} does not fit: {pick['why']}.")
        return None
    est = " (estimate)" if pick["estimated"] else ""
    print(f"       Quant picked: {pick['quant']}, {pick['size_gb']:.1f} GB{est}. {pick['why']}.")
    plan.update(tag=f"hf.co/{user}/{repo}:{pick['quant']}", quant=pick["quant"], size_gb=pick["size_gb"],
                size_source="estimate" if pick["estimated"] else "hugging face")
    return plan


def _pull_with_gate(tag, interactive, hw, res):
    """The only way a model gets downloaded. Asks first, every time, whatever the size. Only a typed y pulls.
    --yes, piped input and CI never download: they print the exact command and return None."""
    plan = _plan_download(tag, hw, res)
    if plan is None:
        return None
    decision = pull_gate.ask_pull(plan, interactive)
    if decision == "non_interactive":
        print(f"\n🛑 '{plan['tag']}' is not installed, and this run cannot ask you. Nothing was downloaded.")
        print(f"   To get it yourself: ollama pull {plan['tag']}\n")
        return None
    if decision == "yes":
        print(f"\n📥 Downloading '{plan['tag']}' via Ollama...")
        try:
            subprocess.check_call(["ollama", "pull", plan["tag"]])
        except Exception as exc:
            print(f"\n❌ Failed to pull model: {exc}")
            print(f"   You can manually pull it via: ollama pull {plan['tag']}\n")
            return None
        print(f"✅ Model '{plan['tag']}' successfully pulled!\n")
        update_env_model(plan["tag"])  # so the next run's menu default and --yes start from this pick
        return plan["tag"]
    if decision == "no":
        print("       Nothing downloaded.")
    return None


def select_and_pull_model(base_url="http://localhost:11434", requested_model=None, interactive=False, scan_library=False):
    """
    Engineering Best Practice:
    1. NEVER download if compatible models are already present on the machine!
    2. Check local Ollama inventory FIRST across all modern open-source models:
       (Nanbeige, DeepSeek, Qwen 2.5 Coder, Command-R, Codestral, GLM-4, LLaMA, Gemma).
    3. If multiple models exist locally, automatically rank and select the MOST CAPABLE one.
    4. Only if the machine has ZERO models installed, evaluate the PC build (RAM, GPU, VRAM)
       and recommend/pull the optimal cutting-edge model tailored to the hardware.
    """
    print("🧠 [3/4] Evaluating Hardware & Model Inventory for Highest Capability...")
    
    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJECT_DIR, ".env"))
    except ImportError:
        pass

    # Inspect hardware profile
    hw = get_hardware_profile()
    res = get_free_resources()
    ram_gb = hw["ram_gb"]
    vram_gb = hw["vram_gb"]
    gpu_name = hw["gpu_name"]
    free_vram, free_ram = _free_for_fit(hw, res)
    ram_txt = f"{ram_gb:.1f} GB RAM" if ram_gb else "RAM unknown"
    print(f"       Detected PC Build: {gpu_name} ({vram_gb:.1f} GB VRAM) | {ram_txt}")
    gpu_txt = f"{free_vram:.1f} GB VRAM free" if res.get("gpu_known") else "GPU unknown (fitting on RAM only)"
    print(f"       Free right now: {gpu_txt} | {free_ram:.1f} GB RAM free | {res['free_disk_gb']:.0f} GB disk free")

    # Check existing models locally FIRST
    installed_models = get_installed_ollama_models(base_url)
    display_names = sorted(list(set(m for m in installed_models if ":" in m or "/" in m)))
    if display_names:
        print(f"       Found {len(display_names)} local model(s) in machine inventory: {', '.join(display_names)}")
    else:
        print("       No local models found in machine inventory.")
    details = get_installed_details(base_url)
    entries = get_ledger_entries()
    pool = _installed_candidates(display_names, details, hw, entries)
    best = ranking.best_for_agent(pool)  # None when nothing installed can drive a coding agent

    # 1. Did the user explicitly pass a model via CLI command-line?
    cli_requested_model = requested_model

    # 1b. On a real terminal, offer a short menu (installed + newer candidates) instead of silently auto-picking.
    #     Enter keeps the current pick. Piped runs, CI and --yes skip this, and they never download.
    from_menu = False
    if interactive and not cli_requested_model:
        cli_requested_model = _ask_which_model(display_names, installed_models, vram_gb, ram_gb, free_vram, free_ram,
                                               pool=pool, scan_library=scan_library)
        from_menu = True  # the menu already vetted a typed tag

    if cli_requested_model:
        if is_model_installed(cli_requested_model, installed_models):
            if _refuse_non_chat(cli_requested_model, pool):
                return None
            _ledger_warning(cli_requested_model, entries)
            print(f"       ✅ Using explicitly requested model: '{cli_requested_model}' (Found locally. Skipping download!)")
            update_env_model(cli_requested_model)
            return cli_requested_model
        else:
            print(f"       User explicitly requested model '{cli_requested_model}' which is not in local inventory.")
            if not from_menu and model_wizard.is_hf_tag(cli_requested_model) and not _hf_tag_ok(cli_requested_model):
                return None
            target_to_pull = cli_requested_model

    # 2. ZERO-DOWNLOAD BEST PRACTICE: If models are already installed on this machine, REUSE THEM!
    elif best:
        # Check if .env model is installed (and can drive a coding agent: an embedding model never can)
        configured_env_model = os.environ.get("LOCAL_LLM_MODEL")
        if configured_env_model and is_model_installed(configured_env_model, installed_models):
            if _find_candidate(configured_env_model, ranking.agent_candidates(pool)):
                print(f"       ✅ Using configured local model: '{configured_env_model}' (Found locally. Zero download needed!)")
                _ledger_warning(configured_env_model, entries)
                return configured_env_model
            print(f"       '{configured_env_model}' (from .env) is an embedding or media model, which a coding agent cannot use. Choosing another.")

        # Rank the installed models: fits this PC, not failed, has tools, installed, probe passed, newer, name score last
        top_model = best["tag"]
        top_score = get_model_capability_score(top_model)
        badge_text = capabilities.format_badges(best["badges"])
        print(f"       🏆 Auto-selected MOST CAPABLE installed model: '{top_model}' (Capability Score: {top_score:.1f}/100"
              f"{'; ' + badge_text if badge_text else ''})")
        print(f"       ✅ Zero download needed—reusing existing local weights on this machine.")
        _ledger_warning(top_model, entries)
        update_env_model(top_model)
        return top_model

    # 3. No models installed on machine at all: evaluate PC build and select optimal cutting-edge model
    else:
        if display_names:
            print("       None of the installed models can drive a coding agent (embedding or media models only). "
                  "Looking at the hardware pick instead...")
        else:
            print("       Zero models found on machine. Evaluating hardware build for optimal cutting-edge model...")
        
        target_to_pull = hardware_tier_model(vram_gb, ram_gb)
        if target_to_pull == "qwen2.5-coder:14b":  # Workstation / Enthusiast PC
            print(f"       PC Build: High-performance workstation ({vram_gb:.1f}GB VRAM, {ram_gb:.1f}GB RAM)")
            print(f"       Selected cutting-edge agent model: '{target_to_pull}' (100% VRAM tool fit, flagship coding)")
            print(f"       (Note: You can also try 'deepseek-coder-v2:16b', 'command-r:35b', or 'codestral:22b')")
        elif target_to_pull == "qwen2.5-coder:7b":  # Mid-tier PC
            print(f"       PC Build: Mid-tier hardware ({vram_gb:.1f}GB VRAM, {ram_gb:.1f}GB RAM)")
            print(f"       Selected cutting-edge agent model: '{target_to_pull}'")
            print(f"       (Note: You can also try 'hf.co/mradermacher/nanbeige4.1-3b-gguf:q4_k_m', 'deepseek-coder:6.7b', or 'glm4:9b')")
        else:  # Entry-level / CPU
            print(f"       PC Build: Compact / CPU hardware ({ram_gb:.1f}GB RAM)")
            print(f"       Selected compact agent model: '{target_to_pull}'")

    # 4. Not installed: the gate asks first (and --yes, piped input and CI never download)
    print(f"\n📥 Model '{target_to_pull}' is not installed on this machine.")
    return _pull_with_gate(target_to_pull, interactive, hw, res)

async def run_agent(model, base_url="http://localhost:11434/v1"):
    """Run autonomous demonstration and interactive shell."""
    print("🎯 [4/4] Launching Google Antigravity Local Agent...")
    
    from google.antigravity import Agent, LocalOpenAIAgentConfig
    from google.antigravity.types import CapabilitiesConfig
    from google.antigravity.hooks import policy

    workspace_dir = os.path.join(PROJECT_DIR, "workspace")
    os.makedirs(workspace_dir, exist_ok=True)

    # Disable tools only if using Gemma under Ollama (which does not support Ollama tool schema)
    capabilities = CapabilitiesConfig(enabled_tools=[]) if "gemma" in model.lower() else None

    config = LocalOpenAIAgentConfig(
        model=model,
        base_url=base_url,
        workspaces=[workspace_dir],
        policies=[policy.allow_all()],
        capabilities=capabilities,
    )

    print("=============================================================================")
    print(" ✨ System Online: Autonomous Agent Ready!")
    print(f"    - Endpoint  : {base_url}")
    print(f"    - Model     : {model}")
    print(f"    - Workspace : {workspace_dir}")
    print("=============================================================================\n")

    # Autonomous Demonstration
    target_demo = os.path.join(workspace_dir, "index.html")
    print("▶ Running quick autonomous demonstration (Agent creating 'workspace/index.html')...")
    demo_prompt = (
        f"Create an index.html file with a modern dark-mode toggle at path {target_demo}. "
        "Call the write_to_file tool with TargetFile, CodeContent, and Overwrite=true."
    )
    
    task_report.set_aside(target_demo)
    before = task_report.snapshot(workspace_dir)
    try:
        async with Agent(config) as agent:
            response = await agent.chat(demo_prompt)
            async for chunk in response:
                print(chunk, end="", flush=True)
            created, changed = task_report.summarize(before, task_report.snapshot(workspace_dir))
            if "index.html" in created + changed and task_report.demo_page_ok(target_demo):
                print("\n\n✅ Demonstration complete! File generated at: workspace/index.html\n")
            else:
                print("\n\n⚠️ The agent finished, but it did not write a dark-mode page to workspace/index.html.")
                print("Small local models sometimes answer without writing anything. Try the same prompt below.\n")
    except Exception as exc:
        print(f"\n⚠️ Demo notice: {exc}\n")

    # Interactive Agent Shell
    print("=============================================================================")
    print(" 💬 Interactive Local Agent Shell (Type 'exit' or 'quit' to leave)")
    print(f"    Active Model: {model} (Prompt your agent to write code or inspect files)")
    print("=============================================================================")
    print("💡 Example prompts to try:")
    print("   - 'What files are in this repository?'")
    print("   - 'Create a python script called calculator.py with basic math functions.'")
    print("   - 'Create about.html, a small page with a heading and one paragraph.'\n")

    failures = 0  # consecutive per-turn errors; a dead backend must not loop forever
    async with Agent(config) as agent:
        while True:
            try:
                user_input = input("You > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ["exit", "quit", "q"]:
                    print("\n👋 Goodbye! Happy agent coding.\n")
                    break

                print("\nAgent > ", end="", flush=True)
                response = await agent.chat(user_input)
                async for chunk in response:
                    print(chunk, end="", flush=True)
                print("\n")
                failures = 0
            except (KeyboardInterrupt, EOFError):
                print("\n\n👋 Goodbye!\n")
                break
            except Exception as exc:
                print(f"\n❌ Error during response: {exc}\n")
                failures += 1
                if failures >= MAX_SHELL_FAILURES:
                    print(f"Stopping after {failures} errors in a row. Check that Ollama is running.\n")
                    break

def check_or_update_memory():
    """Ensure the 3-Tier Memory Fabric (.memory/index.sqlite) is indexed and up to date."""
    try:
        from memory import MemoryDatabase, EmbeddingProvider, MemoryIndexer
        db = MemoryDatabase()
        embedder = EmbeddingProvider()
        indexer = MemoryIndexer(db, embedder)
        stats = indexer.index_all(force=False)
        if stats["indexed"] > 0:
            print(f"[*] Memory Fabric auto-indexed {stats['indexed']} updated files ({stats['chunks']} chunks).")
    except Exception:
        pass


def run_probe_command(args):
    """`python run.py --probe [model]`: one live tool call, recorded in the local ledger. Returns the exit code.
    It runs before the venv step and never starts or pulls anything: it only talks to a server that is already up."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJECT_DIR, ".env"))
    except ImportError:
        pass
    base_api = os.environ.get("LOCAL_LLM_BASE_URL", DEFAULT_BASE_URL)
    backend = detect_backend(base_api)
    if backend is None:
        print(f"❌ Nothing answered at {base_api}. Start your model server, then run --probe again.")
        return 1
    host = base_api.replace("/v1", "").rstrip("/")
    entries = get_ledger_entries()
    model = args.model or os.environ.get("LOCAL_LLM_MODEL")
    if not model and backend == "ollama":
        names = sorted(n for n in get_installed_ollama_models(host) if ":" in n or "/" in n)
        best = ranking.best_for_agent(_installed_candidates(names, get_installed_details(host), get_hardware_profile(), entries))
        model = best["tag"] if best else None
    if not model:
        print("❌ No model to probe. Name one: python run.py --probe <model>")
        return 1
    print(f"🔬 Probing {_printable_tag(model)}: one live tool call (read a file, write a file)...")
    if ledger.fresh_pass(model, entries):
        print("       It passed a few minutes ago, so we are not repeating it (a pass is trusted for 5 minutes).")
        return 0
    result = probe.run_probe(base_api, model)
    ok, warning = ledger.append(model, result["verdict"], result["reason"], runtime=backend, harness="probe")
    if result["verdict"] == "pass":
        print(f"       ✅ Passed: {result['reason']}.")
    else:
        print(f"       ❌ Failed: {result['reason']}.")
        print("          Models that fail are ranked below ones we have not tried, but you can still pick them.")
    if result["tok_s"] is not None:
        print(f"       slow on this PC ({result['tok_s']} tok/s)" if result["tok_s"] < 5 else f"       Speed: {result['tok_s']} tok/s")
    if not ok:
        print(f"       Warning: {warning}")
    return 0 if result["verdict"] == "pass" else 1


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Plug-and-play bootstrap for Antigravity with a local Ollama model.")
    ap.add_argument("model", nargs="?", help="Ollama model to use (pulled if missing)")
    ap.add_argument("--serve", action="store_true", help="start the web UI + API (needs no Ollama)")
    ap.add_argument("--host", help="with --serve: bind address")
    ap.add_argument("--port", type=int, help="with --serve: port (default: a free one)")
    ap.add_argument("--probe", action="store_true",
                    help="run one live tool call against the model and record pass or fail in the local ledger, then exit")
    ap.add_argument("--scan-library", action="store_true",
                    help="also list models read off ollama.com/library (reads HTML, so it can break; the curated list stays)")
    ap.add_argument("-y", "--yes", action="store_true", help="skip the menu and every question: use the best installed model, or exit 1 and print the ollama pull command. Never downloads")
    ap.add_argument("--sync-memory", action="store_true", help="re-index the memory fabric and exit")
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
    ap.add_argument("--doctor", action="store_true",
                    help="with --agent claude: read-only check for settings that send normal Claude Code sessions "
                         "to a local model")
    ap.add_argument("--copy-user-settings", action="store_true",
                    help="with --agent claude: copy (once) a safe slice of ~/.claude into ~/.claude-local")
    ap.add_argument("--resume-from", metavar="ID|latest",
                    help="with --agent claude: EXPERIMENTAL, fork a Claude Code session into the local model")
    args = ap.parse_args(argv)
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


def _main(argv=None):
    raw = sys.argv[1:] if argv is None else list(argv)
    if raw and raw[0] == "handoff":  # `python run.py handoff ...`: stdlib only, no venv, no Ollama
        import handoff
        sys.exit(handoff.main(raw[1:]))
    args = parse_args(argv)  # before bootstrap_venv: --help / bad flags must not touch pip
    if args.doctor:  # read-only and stdlib: needs neither the venv nor Ollama
        import agent_setup
        agent_setup.claude_doctor()
        return
    if args.probe:  # stdlib only, no venv: talks to a model server that is already running
        sys.exit(run_probe_command(args))
    print_header()

    if args.sync_memory:
        try:
            from memory import cmd_sync
            import types
            cmd_sync(types.SimpleNamespace())
        except Exception as e:
            print(f"Error syncing memory: {e}")
        return

    # Step 1: Self-bootstrap inside venv if running in system Python
    if not is_in_venv():
        bootstrap_venv()
        return

    # --serve: web UI + API on a free port. Needs no Ollama (memory falls back to pure Python).
    if args.serve:
        import serve
        serve_argv = []
        if args.host:
            serve_argv += ["--host", args.host]
        if args.port is not None:
            serve_argv += ["--port", str(args.port)]
        serve.main(serve_argv)
        return

    # Step 2: Ensure Ollama is running
    base_api = os.environ.get("LOCAL_LLM_BASE_URL", DEFAULT_BASE_URL)
    ollama_host = base_api.replace("/v1", "").rstrip("/")
    backend = detect_backend(base_api)
    interactive = _is_tty(sys.stdin) and _is_tty(sys.stdout) and not args.yes
    if backend == "openai":
        print(f"🤖 [2/4] Found an OpenAI-compatible server at {base_api} (not Ollama). Nothing will be downloaded.")
        os.environ["LOCAL_LLM_BACKEND"] = "openai"  # memory.py and --agent claude read this
    else:
        os.environ.pop("LOCAL_LLM_BACKEND", None)
        if backend is None and not is_default_ollama_url(base_api):
            print(f"\n❌ Nothing answered at {base_api}: no Ollama (/api/tags) and no OpenAI-compatible /models. "
                  "Start your server, or fix LOCAL_LLM_BASE_URL in .env.")
            sys.exit(1)
        if not check_ollama_service(ollama_host):
            sys.exit(1)

    # Step 3: Check local inventory & auto-select most capable model
    try:
        if backend == "openai":
            model = select_openai_model(base_api, args.model, interactive=interactive)
        else:
            model = select_and_pull_model(ollama_host, args.model, interactive=interactive, scan_library=args.scan_library)
    except KeyboardInterrupt:
        print("\nCancelled. Nothing was saved.")
        sys.exit(130)
    if not model:
        sys.exit(1)

    # Step 3.2: --agent pi/opencode/codex/claude: configure that agent for this model and hand over (SDK shell stays default)
    if args.agent != "shell":
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
        sys.exit(agent_setup.run(args.agent, model, base_api, workspace, config_only=args.agent_config_only,
                                 continue_local=args.continue_local, resume_from=args.resume_from,
                                 copy_settings=args.copy_user_settings, find_transcript=finder))

    # Step 3.5: Auto-index memory fabric
    check_or_update_memory()

    # Step 4: Run agent via asyncio
    import asyncio
    asyncio.run(run_agent(model, base_api))

if __name__ == "__main__":
    main()
