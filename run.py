#!/usr/bin/env python3
"""
=============================================================================
 Google Antigravity Local - 1-Command Plug & Play Bootstrap
=============================================================================
One command to rule them all:
- Auto-detects OS and system hardware (RAM/VRAM)
- Auto-creates virtual environment & installs dependencies
- Auto-detects / starts Ollama local server in background
- Auto-downloads the optimal agent model (qwen2.5:14b or llama3.1:8b)
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

def select_and_pull_model(base_url="http://localhost:11434"):
    """Auto-detect hardware and ensure the best tool-capable model is downloaded."""
    print("🧠 [3/4] Checking Local Agent Model...")
    ram_gb = get_system_ram_gb()
    
    # Choose optimal model based on available RAM
    if ram_gb >= 15.0:
        recommended_model = "qwen2.5:14b"
        print(f"       Detected {ram_gb:.1f} GB RAM -> Selected: {recommended_model} (14B params, top agent performance)")
    else:
        recommended_model = "llama3.1:8b"
        print(f"       Detected {ram_gb:.1f} GB RAM -> Selected: {recommended_model} (8B params, optimized for compact RAM)")

    # Check existing models in Ollama
    tags_url = f"{base_url}/api/tags"
    existing_models = []
    try:
        with urllib.request.urlopen(tags_url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            existing_models = [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass

    # Check if target model or any tool model is present
    has_target = any(recommended_model in m for m in existing_models)
    if has_target:
        print(f"       Model '{recommended_model}' is already downloaded and ready to use.")
        return recommended_model

    # Check if any compatible tool-capable model is present
    compatible = [m for m in existing_models if any(k in m for k in ["qwen2.5", "llama3.1", "llama3.2", "mistral-nemo"])]
    if compatible:
        chosen = compatible[0]
        print(f"       Found alternative tool-calling model: '{chosen}'. Using it!")
        return chosen

    # Auto-pull the recommended model
    print(f"\n📥 Downloading model '{recommended_model}' via Ollama (~5-9 GB, one-time download)...")
    print("   Please wait, downloading model weights...")
    try:
        subprocess.check_call(["ollama", "pull", recommended_model])
        print(f"✅ Model '{recommended_model}' successfully pulled!\n")
        return recommended_model
    except Exception as exc:
        print(f"\n❌ Failed to pull model: {exc}")
        print(f"   You can manually pull it via: ollama pull {recommended_model}\n")
        return recommended_model

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
    print("=============================================================================\n")

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

    # Step 3: Hardware auto-detect & model auto-pull
    model = select_and_pull_model(ollama_host)

    # Step 4: Run agent via asyncio
    import asyncio
    asyncio.run(run_agent(model, base_api))

if __name__ == "__main__":
    main()
