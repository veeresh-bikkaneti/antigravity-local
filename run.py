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

import model_wizard
import task_report

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
    """Detect approximate system RAM in GB without external packages."""
    try:
        if IS_WIN:
            output = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum / 1GB"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            return float(output)
        elif sys.platform == "darwin":
            output = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            return float(output) / (1024 ** 3)
        else:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = float(line.split()[1])
                        return kb / (1024 ** 2)
    except Exception:
        pass
    return 0.0  # unknown: never invent RAM; tier logic then picks the smallest model

def get_hardware_profile():
    """
    Detects hardware profile (System RAM, GPU Model, Dedicated VRAM)
    to match the PC build with optimal, cutting-edge models.
    """
    ram_gb = get_system_ram_gb()
    vram_gb = 0.0
    gpu_name = "CPU Only"

    # 1. NVIDIA GPU / VRAM check via nvidia-smi
    if shutil.which("nvidia-smi"):
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            if output:
                first_gpu = output.splitlines()[0].split(",")
                gpu_name = first_gpu[0].strip()
                vram_mb = float(first_gpu[1].strip())
                vram_gb = vram_mb / 1024.0
        except Exception:
            pass

    # 2. Apple Silicon unified memory check
    elif sys.platform == "darwin":
        try:
            cpu_brand = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
            if "Apple" in cpu_brand:
                gpu_name = f"Apple Silicon ({cpu_brand})"
                vram_gb = ram_gb  # Unified memory acts as VRAM
        except Exception:
            pass

    return {
        "ram_gb": ram_gb,
        "vram_gb": vram_gb,
        "gpu_name": gpu_name
    }

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
            print("   👉 Windows: Download from https://ollama.ai/download or run: winget install Ollama.Ollama")
        elif sys.platform == "darwin":
            print("   👉 macOS: Download from https://ollama.ai/download or run: brew install ollama")
        else:
            print("   👉 Linux: Run: curl -fsSL https://ollama.com/install.sh | sh")
        print("\n   Once installed, run this command again!\n")
        sys.exit(1)

    print("       Ollama service is not running. Launching 'ollama serve' in background...")
    try:
        if IS_WIN:
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
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

def get_model_capability_score(model_name: str) -> float:
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
    if "qwen3" in name or "devstral-small-2" in name or "gpt-oss" in name or "laguna" in name:
        score += 94.0   # 2026 agentic families (see model_wizard.CATALOG); outrank qwen2.5
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

    return min(score, 100.0)

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

def _ask_which_model(display_names, installed_models, vram_gb, ram_gb):
    """Run the wizard. Returns the chosen tag, or None to continue with the automatic pick."""
    configured = os.environ.get("LOCAL_LLM_MODEL")
    if configured and is_model_installed(configured, installed_models):
        default = configured
    elif display_names:
        default = max(display_names, key=get_model_capability_score)
    else:
        default = None
    menu = model_wizard.build_menu(display_names, vram_gb, ram_gb)
    if not default:
        default = next((m["tag"] for m in menu if m["fit"] == "gpu"), menu[0]["tag"] if menu else None)
    chosen = model_wizard.choose(menu, default)
    if not chosen or model_wizard._norm(chosen) == model_wizard._norm(default or ""):
        # Kept the default: for an installed model the automatic path handles it; otherwise pull it.
        return None if chosen and is_model_installed(chosen, installed_models) else chosen
    if not is_model_installed(chosen, installed_models) and model_wizard.tag_exists(chosen) is False:
        print(f"       '{chosen}' is not on the Ollama registry. Continuing with the automatic pick.")
        return None
    return chosen


def select_and_pull_model(base_url="http://localhost:11434", requested_model=None, interactive=False):
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
    ram_gb = hw["ram_gb"]
    vram_gb = hw["vram_gb"]
    gpu_name = hw["gpu_name"]
    ram_txt = f"{ram_gb:.1f} GB RAM" if ram_gb else "RAM unknown"
    print(f"       Detected PC Build: {gpu_name} ({vram_gb:.1f} GB VRAM) | {ram_txt}")

    # Check existing models locally FIRST
    installed_models = get_installed_ollama_models(base_url)
    display_names = sorted(list(set(m for m in installed_models if ":" in m or "/" in m)))
    if display_names:
        print(f"       Found {len(display_names)} local model(s) in machine inventory: {', '.join(display_names)}")
    else:
        print("       No local models found in machine inventory.")

    # 1. Did the user explicitly pass a model via CLI command-line?
    cli_requested_model = requested_model

    # 1b. On a real terminal, offer a short menu (installed + newer candidates) instead of silently auto-picking.
    #     Enter keeps the current pick. Piped runs, CI and --yes skip this and behave exactly as before.
    if interactive and not cli_requested_model:
        cli_requested_model = _ask_which_model(display_names, installed_models, vram_gb, ram_gb)

    if cli_requested_model:
        if is_model_installed(cli_requested_model, installed_models):
            print(f"       ✅ Using explicitly requested model: '{cli_requested_model}' (Found locally. Skipping download!)")
            update_env_model(cli_requested_model)
            return cli_requested_model
        else:
            print(f"       User explicitly requested model '{cli_requested_model}' which is not in local inventory.")
            target_to_pull = cli_requested_model

    # 2. ZERO-DOWNLOAD BEST PRACTICE: If models are already installed on this machine, REUSE THEM!
    elif display_names:
        # Check if .env model is installed
        configured_env_model = os.environ.get("LOCAL_LLM_MODEL")
        if configured_env_model and is_model_installed(configured_env_model, installed_models):
            print(f"       ✅ Using configured local model: '{configured_env_model}' (Found locally. Zero download needed!)")
            return configured_env_model

        # Rank all installed models by capability score
        ranked_models = sorted(display_names, key=get_model_capability_score, reverse=True)
        top_model = ranked_models[0]
        top_score = get_model_capability_score(top_model)
        
        print(f"       🏆 Auto-selected MOST CAPABLE installed model: '{top_model}' (Capability Score: {top_score:.1f}/100)")
        print(f"       ✅ Zero download needed—reusing existing local weights on this machine.")
        update_env_model(top_model)
        return top_model

    # 3. No models installed on machine at all: evaluate PC build and select optimal cutting-edge model
    else:
        print("       Zero models found on machine. Evaluating hardware build for optimal cutting-edge model...")
        
        # Workstation / Enthusiast PC (>= 15 GB VRAM or >= 32 GB RAM)
        if vram_gb >= 15.0 or (vram_gb >= 8.0 and ram_gb >= 32.0):
            target_to_pull = "qwen2.5-coder:14b"
            print(f"       PC Build: High-performance workstation ({vram_gb:.1f}GB VRAM, {ram_gb:.1f}GB RAM)")
            print(f"       Selected cutting-edge agent model: '{target_to_pull}' (100% VRAM tool fit, flagship coding)")
            print(f"       (Note: You can also try 'nanbeige2:16b', 'deepseek-coder-v2:16b', 'command-r:35b', or 'codestral:22b')")
        # Mid-Tier PC (8-14 GB VRAM or 16-32 GB RAM)
        elif vram_gb >= 8.0 or ram_gb >= 16.0:
            target_to_pull = "qwen2.5-coder:7b"
            print(f"       PC Build: Mid-tier hardware ({vram_gb:.1f}GB VRAM, {ram_gb:.1f}GB RAM)")
            print(f"       Selected cutting-edge agent model: '{target_to_pull}'")
            print(f"       (Note: You can also try 'nanbeige4.1:3b', 'deepseek-coder:6.7b', or 'glm4:9b')")
        # Entry-Level / CPU (< 16 GB RAM)
        else:
            target_to_pull = "llama3.2:3b"
            print(f"       PC Build: Compact / CPU hardware ({ram_gb:.1f}GB RAM)")
            print(f"       Selected compact agent model: '{target_to_pull}'")

    # 4. Only if completely missing from local inventory, perform download
    print(f"\n📥 Model '{target_to_pull}' not found locally. Initiating one-time download via Ollama...")
    print("   Please wait while model weights are downloaded...")
    try:
        subprocess.check_call(["ollama", "pull", target_to_pull])
        print(f"✅ Model '{target_to_pull}' successfully pulled!\n")
        return target_to_pull
    except Exception as exc:
        print(f"\n❌ Failed to pull model: {exc}")
        print(f"   You can manually pull it via: ollama pull {target_to_pull}\n")
        return None

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
        "Call write_file or create_file with Path, Content, and Overwrite=True."
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


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Plug-and-play bootstrap for Antigravity with a local Ollama model.")
    ap.add_argument("model", nargs="?", help="Ollama model to use (pulled if missing)")
    ap.add_argument("--serve", action="store_true", help="start the web UI + API (needs no Ollama)")
    ap.add_argument("--host", help="with --serve: bind address")
    ap.add_argument("--port", type=int, help="with --serve: port (default: a free one)")
    ap.add_argument("-y", "--yes", action="store_true", help="skip the model menu and auto-pick (same as a piped run)")
    ap.add_argument("--sync-memory", action="store_true", help="re-index the memory fabric and exit")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)  # before bootstrap_venv: --help / bad flags must not touch pip
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
    base_api = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    ollama_host = base_api.replace("/v1", "").rstrip("/")
    if not check_ollama_service(ollama_host):
        sys.exit(1)

    # Step 3: Check local inventory & auto-select most capable model
    model = select_and_pull_model(ollama_host, args.model,
                                  interactive=sys.stdin.isatty() and sys.stdout.isatty() and not args.yes)
    if not model:
        sys.exit(1)

    # Step 3.5: Auto-index memory fabric
    check_or_update_memory()

    # Step 4: Run agent via asyncio
    import asyncio
    asyncio.run(run_agent(model, base_api))

if __name__ == "__main__":
    main()
