# 🚀 Local Google Antigravity Agent (Open-Source Edition)

> Run fully autonomous, private AI agents on your local machine using the official **Google Antigravity SDK** (`google-antigravity`) connected to local models (**Ollama**, **LM Studio**, **vLLM**) or Google's open-source **Research AI Harness**—with zero cloud lock-in and zero API fees.

---

## ⚡ 1-Command Plug & Play (Zero-Friction Setup)

No manual environment creation or dependency hunting. Clone and run **one command**—the bootstrap orchestrator automatically configures your environment, starts Ollama, downloads the best model for your hardware, runs an autonomous demonstration, and opens an interactive agent chat:

### Windows (CMD or PowerShell):
```cmd
git clone https://github.com/veeresh-bikkaneti/antigravity-local.git
cd antigravity-local
run.bat
```
*(Or in PowerShell: `.\run.ps1` or `python run.py`)*

### macOS / Linux:
```bash
git clone https://github.com/veeresh-bikkaneti/antigravity-local.git
cd antigravity-local
chmod +x run.sh && ./run.sh
```
*(Or: `python3 run.py`)*

#### 🤖 What the 1-Command Bootstrap Does Automatically:
1. 🔍 **Hardware Detection**: Probes system RAM and selects `qwen2.5:14b` (for systems with >=16GB RAM) or `llama3.1:8b` (for systems under 16GB RAM).
2. 📦 **Virtual Environment Setup**: Creates isolated `venv`, installs `requirements.txt`, and generates `.env` if missing.
3. ⚙️ **Ollama Auto-Start**: Pings `http://localhost:11434`. If down, launches `ollama serve` in the background.
4. 📥 **Model Auto-Pull**: Inspects downloaded models and automatically pulls the optimal model if not yet present.
5. 🛠️ **Autonomous Demo**: Invokes the local agent to create a modern responsive `workspace/index.html` file using built-in tool calling.
6. 💬 **Interactive Shell**: Drops you straight into an interactive terminal where you can prompt your private local agent to write code, inspect files, or perform tasks!

---

## 📋 Table of Contents
1. [⚡ 1-Command Plug & Play](#-1-command-plug--play-zero-friction-setup)
2. [What is This?](#-what-is-this)
3. [Prerequisites Checklist](#-prerequisites-checklist)
4. [Step-by-Step Manual Setup](#-step-by-step-manual-setup)
5. [Project Structure](#-project-structure)
6. [How It Works](#-how-it-works)
7. [Common Gotchas & Troubleshooting](#-common-gotchas--troubleshooting)
8. [Advanced: Using Custom Research Harnesses & Servers](#-advanced-using-custom-research-harnesses--servers)
9. [License & Contributing](#-license--contributing)

---

## 💡 What is This?

Google Antigravity is an agentic AI framework designed for autonomous code generation, workspace manipulation, and tool use. 

Normally, developer tools configure Antigravity to call cloud Gemini APIs. **This repository shows you how to point Antigravity entirely at local models running on your own PC.**

- 🔒 **100% Private**: Your code, files, and prompts never leave your local hardware.
- 💸 **Zero Cost**: No OpenAI or Google Cloud API subscriptions required.
- 🛠️ **Autonomous Tool Calling**: The agent can inspect folders, read code, write files, and execute commands locally using standard safety policies.

---

## ⚙️ Prerequisites Checklist

Before you start, make sure you have:

| Requirement | Minimum | Recommended | Notes |
| :--- | :--- | :--- | :--- |
| **Operating System** | Windows 10/11, macOS, Linux | Any modern 64-bit OS | Fully tested on Windows 11 & Linux. |
| **Python** | 3.10 | 3.11 or 3.12 | Check with `python --version`. |
| **System RAM** | 8 GB | 16 GB - 32 GB | More RAM allows running larger models. |
| **GPU (Optional)** | None (runs on CPU) | NVIDIA RTX (8GB+) or Apple Silicon | GPU speeds up token generation. |
| **Ollama** | Installed & running | [ollama.ai](https://ollama.ai/download) | Local LLM inference server. |

---

## 🛠️ Step-by-Step Manual Setup (Optional Alternative)

If you prefer to configure each component step-by-step rather than using the 1-command bootstrap (`run.bat` / `run.sh` / `run.py`):

### Step 1: Install & Verify Ollama
1. Download and install Ollama from [ollama.ai/download](https://ollama.ai/download).
2. Open a terminal and check that Ollama is responding:
   ```bash
   ollama --version
   ```

### Step 2: Check Local Models & Pull Only If Missing

> 💡 **Best Engineering Practice**: Always check your existing local inventory before downloading multiple gigabytes!

1. Check what models are already installed on your machine:
   ```bash
   ollama list
   ```
2. If you already have a proven agent model, **skip downloading—you're already ready to go!**
   - **`nanbeige`** (e.g., `nanbeige4.1:3b`, `nanbeige2:16b`): Specially optimized for deep search and multi-step sequential tool calling.
   - **`qwen2.5`** (e.g., `qwen2.5:14b`, `qwen2.5:7b`, `qwen2.5:32b`): Flagship open coding and OpenAI-compatible tool use.
   - **`llama3.1`** (e.g., `llama3.1:8b`): Battle-tested, compact 8B agent runner.
   - **`gemma2`** (e.g., `gemma2:27b`): High-quality reasoning and token streaming.
3. Only if you don't have an agent model installed, download one:
   ```bash
   # Option A: Flagship agent model (systems with >= 12 GB RAM):
   ollama pull qwen2.5:14b

   # Option B: Ultra-compact agent & tool-calling model (any system):
   # ollama pull llama3.1:8b
   ```

### Step 3: Clone the Repository & 1-Command Setup

```bash
git clone https://github.com/veeresh-bikkaneti/antigravity-local.git
cd antigravity-local
```

#### Option A: 1-Click Automated Setup (Recommended)
- **Windows**:
  ```cmd
  setup.bat
  ```
- **macOS / Linux**:
  ```bash
  chmod +x setup.sh && ./setup.sh
  ```
*(This automatically creates a virtual environment, installs dependencies from `requirements.txt`, and generates your `.env` file.)*

#### Option B: Manual Setup
```bash
# 1. Create a virtual environment
python -m venv venv
```

**Activate your virtual environment:**
- **Windows PowerShell**:
  ```powershell
  # If PowerShell blocks scripts, run this first:
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\venv\Scripts\Activate.ps1
  ```
- **macOS / Linux**:
  ```bash
  source venv/bin/activate
  ```

### Step 4: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 5: Configure Your Environment (Optional)
Copy the example environment configuration:
- **Windows PowerShell**:
  ```powershell
  Copy-Item .env.example .env
  ```
- **macOS / Linux**:
  ```bash
  cp .env.example .env
  ```
*By default, the `.env` points to `http://localhost:11434/v1` with model `qwen2.5:14b`. No edits needed if using defaults!*

### Step 6: Test Your Agent!

#### Test 1: Live Token Streaming (`test_local.py`)
Verify your local connection to Ollama and watch tokens stream live to your console:
```bash
python test_local.py
```

#### Test 2: Autonomous Workspace Agent (`agent_with_workspace.py`)
Watch the local Antigravity agent inspect its workspace, invoke its built-in `create_file` tool, and write a modern dark-mode `index.html` to disk:
```bash
python agent_with_workspace.py
```
After completion, inspect your newly generated file at `workspace/index.html`!

#### Mode 3: Developer Pair-Programming Shell (`code_agent.py`)
Pair program with your local agent to write code, generate project scaffolds, or execute one-shot autonomous tasks:
```bash
# 1. Interactive pair-programming shell in ./workspace:
python code_agent.py --workspace ./workspace

# 2. One-shot autonomous coding task:
python code_agent.py --workspace ./workspace --task "Create a Python CLI calculator with unit tests"

# 3. Use a specific model (e.g., Nanbeige or Qwen):
python code_agent.py --model nanbeige4.1:3b
```

---

## 📂 Project Structure

```
antigravity-local/
├── run.py                    # ⚡ 1-Command Plug & Play auto-bootstrap orchestrator
├── run.bat                   # 1-Click launcher for Windows
├── run.sh                    # 1-Command launcher for macOS & Linux
├── run.ps1                   # 1-Command launcher for PowerShell
├── setup.bat                 # Standalone venv setup for Windows
├── setup.sh                  # Standalone venv setup for macOS & Linux
├── .env.example              # Template environment variables (server URL, model, paths)
├── requirements.txt          # Minimal Python dependencies (google-antigravity, python-dotenv)
├── LICENSE                   # Open-source MIT License
├── README.md                 # Complete beginner & developer documentation
├── test_local.py             # Script 1: Tests local connection & real-time token streaming
├── agent_with_workspace.py   # Script 2: Autonomous agent with file creation tools
├── code_agent.py             # Script 3: Interactive developer coding shell & pair-programmer
└── workspace/                # Sandboxed folder where the agent creates/edits files
    ├── .gitkeep              # Keeps directory tracked in git
    └── index.html            # Artifact generated automatically by the agent
```

---

## 🔍 How It Works

```
   ┌───────────────────────┐
   │ agent_with_workspace  │ (User Python script)
   └───────────┬───────────┘
               │ 1. Passes prompt + workspace tools (create_file)
               ▼
   ┌───────────────────────┐
   │ google-antigravity    │ (SDK + Bundled localharness engine)
   └───────────┬───────────┘
               │ 2. Translates to OpenAI REST: POST /v1/chat/completions
               ▼
   ┌───────────────────────┐
   │ Ollama (:11434)       │ (Runs qwen2.5:14b / llama3.1:8b locally)
   └───────────┬───────────┘
               │ 3. Model emits tool-call JSON: create_file("index.html")
               ▼
   ┌───────────────────────┐
   │ Policy Engine         │ (policy.allow_all() approves execution)
   └───────────┬───────────┘
               │ 4. Writes file directly to disk on your machine
               ▼
   ┌───────────────────────┐
   │ workspace/index.html  │ (Created successfully!)
   └───────────────────────┘
```

1. **LocalOpenAIAgentConfig**: Replaces Google's cloud Gemini endpoint with a local OpenAI-compatible endpoint (`http://localhost:11434/v1`).
2. **Built-in Workspace Tools**: Antigravity automatically gives the model tools to explore and edit files in the designated `workspace/` directory.
3. **Execution Policy**: `policy.allow_all()` permits the agent to write files autonomously. You can customize this to ask for confirmation before writing.

---

## 🛠️ Common Gotchas & Troubleshooting

### 1. PowerShell: "Running scripts is disabled on this system"
**Cause**: Windows restricts PowerShell script execution by default.  
**Fix**: In your PowerShell window, run:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

### 2. "Connection Refused" or Cannot Connect to localhost:11434
**Cause**: Ollama is not running in the background.  
**Fix**: Open a terminal and run `ollama serve` (or start the Ollama desktop app from your Start Menu/Applications).

### 3. Model Error: "model does not support tools"
**Cause**: Some models (such as `gemma2:27b` in Ollama) do not support function calling / tools in their Ollama templates.  
**Fix**: Use a tool-capable model for `agent_with_workspace.py`:
- `qwen2.5:14b` (Recommended)
- `llama3.1:8b` (Fast / Lightweight)  
*Note: You can still use `gemma2:27b` for text generation and reasoning with `test_local.py`.*

### 4. Windows UnicodeEncodeError ('charmap' codec can't encode character)
**Cause**: The Windows terminal defaults to legacy `cp1252` encoding instead of `UTF-8`.  
**Fix**: Our scripts automatically handle this with:
```python
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

---

## 🔬 Advanced: Using Custom Research Harnesses & Servers

### Pointing to LM Studio, vLLM, or llama.cpp
If you prefer running a server other than Ollama, simply change the `LOCAL_LLM_BASE_URL` in `.env`:
```bash
# Example for LM Studio local server:
LOCAL_LLM_BASE_URL=http://localhost:1234/v1
LOCAL_LLM_MODEL=qwen2.5-14b-instruct

# Example for vLLM or text-generation-webui:
LOCAL_LLM_BASE_URL=http://localhost:8000/v1
LOCAL_LLM_MODEL=Qwen/Qwen2.5-14B-Instruct
```

### Pointing to Google's Open-Source Research AI Harness
If you clone and build Google's open-source research agent harness from GitHub, you can override Antigravity's default bundled binary by setting the `ANTIGRAVITY_HARNESS_PATH` environment variable:

```bash
# Linux / macOS:
export ANTIGRAVITY_HARNESS_PATH="/path/to/custom/localharness"

# Windows PowerShell:
$env:ANTIGRAVITY_HARNESS_PATH="C:\path\to\custom\localharness.exe"
```
The SDK will automatically detect your custom binary on startup and route all agent operations through it.

---

## 📄 License & Contributing

This project is licensed under the [MIT License](LICENSE) - free to use, modify, and distribute for personal and commercial projects.

Contributions are welcome! Please open an issue or pull request if you have suggestions, optimizations, or new tool integrations.
