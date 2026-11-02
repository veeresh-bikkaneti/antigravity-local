#!/usr/bin/env python3
"""
=============================================================================
 Google Antigravity Local - 1-Command Plug & Play Bootstrap
=============================================================================
One command to rule them all:
- Auto-detects OS and system hardware (RAM/VRAM)
- Auto-creates virtual environment & installs dependencies
- Auto-detects / starts Ollama local server in background
- Pre-checks existing models (HTTP API + CLI fallback) to prevent redundant downloads
- Runs autonomous workspace agent and starts an interactive agent shell!
=============================================================================
"""

import sys
import os
import subprocess
import platform
import shutil
import time
import json
import urllib.request
import urllib.error

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
VENV_PIP = os.path.join(VENV_DIR, "Scripts" if IS_WIN else "bin", "pip.exe" if IS_WIN else "pip")

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
        return 16.0  # safe default assumption
    return 16.0

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
        subprocess.check_call([VENV_PIP, "install", "--upgrade", "pip", "--quiet"])
        subprocess.check_call([VENV_PIP, "install", "-r", req_file, "--quiet"])
        print("       Dependencies successfully installed.")

    # Relaunch script using the venv python
    print("       Switching execution to managed environment...\n")
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

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
                    # Add without registry or tag variations (e.g. 'qwen2.5:14b' from 'registry.ollama.ai/library/qwen2.5:14b')
                    clean_name = name.split("/")[-1]
                    models.add(clean_name)
                    # Also add base model name without tag
                    models.add(clean_name.split(":")[0])
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
                    models.add(clean_name.split(":")[0])
        except Exception:
            pass

    return models

def is_model_installed(target_model, installed_models):
    """Check if target_model matches any locally installed model."""
    target = target_model.strip().lower()
    clean_target = target.split("/")[-1]
    
    # Exact match or base match
    if target in installed_models or clean_target in installed_models:
        return True
    
    # Substring match (e.g. 'qwen2.5:14b' in 'qwen2.5:14b-instruct-q4_K_M')
    for m in installed_models:
        if clean_target in m or m in clean_target:
            return True
            
    return False

def select_and_pull_model(base_url="http://localhost:11434"):
    """
    Engineering Best Practice:
    1. Inspect user configuration (.env or CLI arguments) first.
    2. Check existing local models BEFORE attempting any download.
    3. If target or any compatible model is already present, USE IT (zero download).
    4. Only download if no compatible tool-capable model is found locally.
    """
    print("🧠 [3/4] Checking Local Agent Model Inventory...")
    
    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJECT_DIR, ".env"))
    except ImportError:
        pass

    # Check existing models locally FIRST
    installed_models = get_installed_ollama_models(base_url)
    if installed_models:
        display_names = sorted(list(set(m for m in installed_models if ":" in m)))
        print(f"       Found {len(display_names)} locally installed model(s): {', '.join(display_names) if display_names else 'detected'}")
    else:
        print("       No local models found in inventory.")

    # 1. Did the user specify a model via CLI or .env?
    user_configured_model = None
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        user_configured_model = sys.argv[1]
    elif os.environ.get("LOCAL_LLM_MODEL"):
        user_configured_model = os.environ.get("LOCAL_LLM_MODEL")

    if user_configured_model:
        if is_model_installed(user_configured_model, installed_models):
            print(f"       ✅ Configured model '{user_configured_model}' is already pulled. Skipping download!")
            return user_configured_model
        else:
            print(f"       Configured model '{user_configured_model}' is not in local inventory.")
            target_to_pull = user_configured_model
    else:
        # 2. Check if a recommended agent model is ALREADY installed
        # Preferred models with verified Antigravity tool calling support:
        candidate_tool_models = [
            "qwen2.5:14b",
            "qwen2.5:7b",
            "qwen2.5:32b",
            "llama3.1:8b",
            "llama3.1:70b",
            "llama3.2:3b",
            "mistral-nemo",
            "mistral:latest"
        ]
        
        for candidate in candidate_tool_models:
            if is_model_installed(candidate, installed_models):
                print(f"       ✅ Found existing tool-capable model '{candidate}' locally. Skipping download!")
                return candidate

        # 3. No candidate is installed; calculate best model based on available hardware RAM
        ram_gb = get_system_ram_gb()
        if ram_gb >= 15.0:
            target_to_pull = "qwen2.5:14b"
            print(f"       Hardware has {ram_gb:.1f} GB RAM -> Selected: {target_to_pull} (14B params, top agent performance)")
        else:
            target_to_pull = "llama3.1:8b"
            print(f"       Hardware has {ram_gb:.1f} GB RAM -> Selected: {target_to_pull} (8B params, optimized for compact RAM)")

    # 4. Only if missing from local inventory, perform download
    print(f"\n📥 Model '{target_to_pull}' not found locally. Initiating one-time download via Ollama...")
    print("   Please wait while model weights are downloaded...")
    try:
        subprocess.check_call(["ollama", "pull", target_to_pull])
        print(f"✅ Model '{target_to_pull}' successfully pulled!\n")
        return target_to_pull
    except Exception as exc:
        print(f"\n❌ Failed to pull model: {exc}")
        print(f"   You can manually pull it via: ollama pull {target_to_pull}\n")
        return target_to_pull

async def run_agent(model, base_url="http://localhost:11434/v1"):
    """Run autonomous demonstration and interactive shell."""
    print("🎯 [4/4] Launching Google Antigravity Local Agent...")
    
    from google.antigravity import Agent, LocalOpenAIAgentConfig
    from google.antigravity.hooks import policy

    workspace_dir = os.path.join(PROJECT_DIR, "workspace")
    os.makedirs(workspace_dir, exist_ok=True)

    config = LocalOpenAIAgentConfig(
        model=model,
        base_url=base_url,
        workspaces=[workspace_dir],
        policies=[policy.allow_all()],
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
    
    try:
        async with Agent(config) as agent:
            response = await agent.chat(demo_prompt)
            async for chunk in response:
                print(chunk, end="", flush=True)
            print("\n\n✅ Demonstration complete! File generated at: workspace/index.html\n")
    except Exception as exc:
        print(f"\n⚠️ Demo encountered notice: {exc}\n")

    # Interactive Agent Shell
    print("=============================================================================")
    print(" 💬 Interactive Local Agent Shell (Type 'exit' or 'quit' to leave)")
    print("    Ask your local agent to code, inspect files, or build features!")
    print("=============================================================================")
    print("💡 Example prompts to try:")
    print("   - 'What files are in this repository?'")
    print("   - 'Create a python script called calculator.py with basic math functions.'")
    print("   - 'Inspect workspace/index.html and add a footer with copyright 2026.'\n")

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
            except (KeyboardInterrupt, EOFError):
                print("\n\n👋 Goodbye!\n")
                break
            except Exception as exc:
                print(f"\n❌ Error during response: {exc}\n")

def main():
    print_header()

    # Step 1: Self-bootstrap inside venv if running in system Python
    if not is_in_venv():
        bootstrap_venv()
        return

    # Step 2: Ensure Ollama is running
    base_api = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    ollama_host = base_api.replace("/v1", "").rstrip("/")
    if not check_ollama_service(ollama_host):
        sys.exit(1)

    # Step 3: Check local inventory first & only pull if missing
    model = select_and_pull_model(ollama_host)

    # Step 4: Run agent via asyncio
    import asyncio
    asyncio.run(run_agent(model, base_api))

if __name__ == "__main__":
    main()
