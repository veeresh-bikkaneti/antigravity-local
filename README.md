# 🚀 Local Google Antigravity Agent (Open-Source Edition)

> Run fully autonomous, private AI agents on your local machine using the official **Google Antigravity SDK** (`google-antigravity`) connected to local models (**Ollama**, **LM Studio**, **vLLM**) or Google's open-source **Research AI Harness**—with zero cloud lock-in and zero API fees.

---

## 📋 Table of Contents
1. [What is This?](#-what-is-this)
2. [Prerequisites Checklist](#-prerequisites-checklist)
3. [Zero-to-Hero Quickstart (5 Minutes)](#-zero-to-hero-quickstart-5-minutes)
4. [Project Structure](#-project-structure)
5. [How It Works](#-how-it-works)
6. [Common Gotchas & Troubleshooting](#-common-gotchas--troubleshooting)
7. [Advanced: Using Custom Research Harnesses & Servers](#-advanced-using-custom-research-harnesses--servers)
8. [License & Contributing](#-license--contributing)

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

## 🏁 Zero-to-Hero Quickstart (5 Minutes)

### Step 1: Install & Verify Ollama
1. Download and install Ollama from [ollama.ai/download](https://ollama.ai/download).
2. Open a terminal and check that Ollama is responding:
   ```bash
   ollama --version
   ```

### Step 2: Download a Local Model
For autonomous agent tasks (creating files, reading code), download **`qwen2.5:14b`** (or **`llama3.1:8b`** if you have less than 12 GB RAM):
```bash
# Recommended for agents with workspace tools:
ollama pull qwen2.5:14b

# If you have limited VRAM/RAM (under 12 GB), pull this smaller model instead:
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

---

## 📂 Project Structure

```
antigravity-local/
├── .env.example              # Template environment variables (server URL, model, paths)
├── requirements.txt          # Minimal Python dependencies (google-antigravity, python-dotenv)
├── setup.bat                 # 1-click automated setup script for Windows
├── setup.sh                  # 1-command automated setup script for macOS / Linux
├── LICENSE                   # Open-source MIT License
├── README.md                 # Complete beginner & developer documentation
├── test_local.py             # Script 1: Tests local connection & real-time token streaming
├── agent_with_workspace.py   # Script 2: Autonomous agent with file creation tools
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
