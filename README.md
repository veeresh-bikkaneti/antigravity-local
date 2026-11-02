# 🚀 Local Google Antigravity Agent (Open-Source Edition)

> Run fully autonomous, private AI agents on your local machine using the official **Google Antigravity SDK** (`google-antigravity`) connected to local models (**Ollama**, **LM Studio**, **vLLM**) or Google's open-source **Research AI Harness**—with zero cloud lock-in and zero API fees.
>
> 📖 **From Zero to Start Coding**: For an end-to-end developer guide with real-world project recipes and the Python SDK handbook, read **[ZERO_TO_CODING.md](ZERO_TO_CODING.md)**.

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
1. 🔍 **Hardware & Inventory Inspection**: Probes dedicated GPU VRAM (via `nvidia-smi` / Apple Silicon) and System RAM. Checks local Ollama inventory first to reuse existing weights with **zero downloads**.
2. 🧠 **Cutting-Edge Model Matching**: Evaluates your PC build against modern agentic powerhouses (Nanbeige, DeepSeek, Qwen 2.5 Coder, Command-R, Codestral, GLM-4) and selects the most capable model matching your hardware.
3. 📦 **Virtual Environment Setup**: Creates isolated `venv`, installs `requirements.txt`, and generates `.env` if missing.
4. ⚙️ **Ollama Auto-Start**: Pings `http://localhost:11434`. If down, launches `ollama serve` in the background.
5. 🛠️ **Autonomous Verification**: Invokes the local agent to create a modern responsive `workspace/index.html` file using built-in tool calling.
6. 💬 **Interactive Shell**: Drops you straight into an interactive terminal where you can prompt your private local agent to write code, inspect files, or perform tasks!

---

## 📋 Table of Contents
1. [⚡ 1-Command Plug & Play](#-1-command-plug--play-zero-friction-setup)
2. [🏛️ System Architecture & Specifications (Docs & Archify)](docs/ARCHITECTURE.md)
3. [📊 System Execution Flows & Lifecycles](docs/FLOWS.md)
4. [📖 From Zero to Start Coding (Master Guide)](ZERO_TO_CODING.md)
5. [💻 Developer Coding Agent (code_agent.py)](#mode-3-developer-pair-programming-shell-code_agentpy)
6. [What is This?](#-what-is-this)
7. [Prerequisites Checklist](#-prerequisites-checklist)
8. [Step-by-Step Manual Setup](#-step-by-step-manual-setup)
9. [Project Structure](#-project-structure)
10. [How It Works & Architectural Flows](#-how-it-works)
11. [Common Gotchas & Troubleshooting](#-common-gotchas--troubleshooting)
12. [Advanced: Using Custom Research Harnesses & Servers](#-advanced-using-custom-research-harnesses--servers)
13. [License & Contributing](#-license--contributing)

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

### Step 2: Check Local Models & Select Best for Your PC Build

> 💡 **Best Engineering Practice**: Never default to a hardcoded download! Always check what is already installed on your machine first. If you have any capable agent model, the system reuses it with **zero download delay**.

1. **Check what models are already on your machine**:
   ```bash
   ollama list
   ```
2. **If you already have any capable model installed, SKIP downloading—you are ready to code!**  
   Our bootstrap orchestrator scans your local inventory and automatically adopts the highest-scoring model:
   - **`nanbeige`** (e.g., `nanbeige2:16b`, `nanbeige4.3:16b`, `nanbeige4.1:3b`): Top-tier multi-step agentic search and complex sequential tool calling.
   - **`deepseek-coder-v2` / `deepseek-r1`** (e.g., `deepseek-coder-v2:16b`, `deepseek-r1:14b`): State-of-the-art coding synthesis, fill-in-the-middle, and algorithmic problem solving.
   - **`qwen2.5-coder` / `qwen2.5`** (e.g., `qwen2.5-coder:14b`, `qwen2.5:14b`, `qwen2.5-coder:32b`): Open-weights coding benchmark champion with native OpenAI function calling.
   - **`command-r`** (e.g., `command-r:35b`): Cohere's enterprise model purpose-built for multi-step tool execution and structured outputs.
   - **`codestral`** (e.g., `codestral:22b`): Mistral's dedicated 32k context coding engine.
   - **`glm4`** (e.g., `glm4:9b`): Outstanding tool use, function calling, and multilingual reasoning.
   - **`llama3.3` / `llama3.1`** (e.g., `llama3.3:70b`, `llama3.1:8b`): Battle-tested general foundation models.
   - **`gemma2`** (e.g., `gemma2:27b`, `gemma2:9b`): Dense reasoning and high-speed streaming (tools disabled).

3. **Only if you have ZERO models installed, choose the cutting-edge model that matches your PC build**:

| PC Build Tier | Hardware Specs | Recommended Cutting-Edge Models | Pull Command |
| :--- | :--- | :--- | :--- |
| **High-End Workstation** | $\ge$ 16 GB VRAM GPU<br/>$\ge$ 32-128 GB System RAM | **`qwen2.5-coder:14b`** *(Fits 100% in 16GB VRAM)*<br/>**`nanbeige2:16b`** *(Top agentic tool caller)*<br/>**`deepseek-coder-v2:16b`** *(Deep code synthesis)*<br/>**`command-r:35b`** *(Layer offload to RAM)* | `ollama pull qwen2.5-coder:14b`<br/>*(or `ollama pull nanbeige2:16b`)* |
| **Mid-Tier PC** | 8 - 12 GB VRAM GPU<br/>16 - 32 GB System RAM | **`qwen2.5-coder:7b`**<br/>**`nanbeige4.1:3b`**<br/>**`deepseek-coder:6.7b`**<br/>**`glm4:9b`** | `ollama pull qwen2.5-coder:7b` |
| **Entry / CPU Only** | No dedicated GPU<br/>8 - 16 GB System RAM | **`llama3.2:3b`**<br/>**`qwen2.5:3b`**<br/>**`nanbeige4.1:3b`** | `ollama pull llama3.2:3b` |

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
├── ZERO_TO_CODING.md         # 📖 E2E Master Guide: From Zero to Coding Real Apps
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

### 🏛️ Interactive Architecture & Visual Flow Documents

For complete system topology, hardware offload physics, and lifecycle state machines, explore our comprehensive technical guides and interactive Archify visualizations:

- 📖 **Architecture Specification**: [**docs/ARCHITECTURE.md**](docs/ARCHITECTURE.md) (Component boundaries, cloud decoupling, hardware VRAM/RAM offload).
- 📊 **Master Flow Guide**: [**docs/FLOWS.md**](docs/FLOWS.md) (Step-by-step Mermaid sequence diagrams and lifecycles).

#### 🌐 Standalone Interactive HTML Visualizations (Powered by Archify):
Open these self-contained artifacts directly in any web browser to explore pan/zoom, theme switching, and live signal tracing:
- 🏛️ [**System Topology & Architecture (HTML)**](docs/diagrams/system-topology.html)
- 🚀 [**1-Command Bootstrap Lifecycle (HTML)**](docs/diagrams/bootstrap-workflow.html)
- ⚡ [**Autonomous Tool Execution Sequence (HTML)**](docs/diagrams/agent-tool-execution.html)
- 🧠 [**Model Pre-Check & Capability Pipeline (HTML)**](docs/diagrams/model-pipeline-workflow.html)

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
