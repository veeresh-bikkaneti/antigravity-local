# 🚀 From Zero to Start Coding with Local Google Antigravity Agent

> A start-to-finish guide to setting up and using a private AI pair programmer on your own machine. It runs on the official Google Antigravity SDK (`google-antigravity`) and local open-source models (Ollama, LM Studio, vLLM).

---

## 📋 Table of Contents
1. [What Can This Agent Do?](#1-what-can-this-agent-do)
2. [Prerequisites & System Architecture](#2-prerequisites--system-architecture)
3. [Zero Setup (3-Minute Quickstart)](#3-zero-setup-3-minute-quickstart)
4. [Start Coding: Interactive Pair-Programmer Shell](#4-start-coding-interactive-pair-programmer-shell)
5. [Start Coding: One-Shot Autonomous Task CLI](#5-start-coding-one-shot-autonomous-task-cli)
6. [3 End-to-End Real World Coding Recipes](#6-3-end-to-end-real-world-coding-recipes)
   - [Recipe 1: Scaffold a Complete FastAPI Backend Microservice](#recipe-1-scaffold-a-complete-fastapi-backend-microservice)
   - [Recipe 2: Write Automated Unit Tests for Existing Code](#recipe-2-write-automated-unit-tests-for-existing-code)
   - [Recipe 3: Refactor Legacy Code & Modernize Architecture](#recipe-3-refactor-legacy-code--modernize-architecture)
7. [The Developer SDK Handbook (Writing Your Own Agents in Python)](#7-the-developer-sdk-handbook-writing-your-own-agents-in-python)
8. [Advanced Backend Integration (LM Studio, vLLM & Google Research Harness)](#8-advanced-backend-integration-lm-studio-vllm--google-research-harness)
9. [Troubleshooting & Pro-Tips](#9-troubleshooting--pro-tips)
10. [Docker Clean-Room Test Drive](#10-docker-clean-room-test-drive)
11. [Product Specification & Consensus Governance](#11-product-specification--consensus-governance)

---

## 1. What Can This Agent Do?

Unlike web-based chat interfaces or API-metered plugins, this agent runs on your own hardware. Here is what that gets you:
- **100% Private**: No telemetry and no cloud calls, so your code stays on your SSD.
- **Zero Fees**: No monthly subscription ($0/mo) and no token billing.
- **Real Disk Access**: The agent inspects folders, reads your source code, writes new files, and applies changes directly in your project workspace.
- **Model Freedom**: Swap models whenever you like. Use `qwen2.5:14b` for complex code reasoning, `llama3.1:8b` for lightweight laptops, or `gemma2:27b` for creative design.

---

## 2. Prerequisites & System Architecture

### Hardware Matrix
| Component | Minimum | Recommended | Notes |
| :--- | :--- | :--- | :--- |
| **OS** | Windows 10/11, macOS, Linux | Any modern 64-bit OS | Fully tested on Windows 11 & Linux |
| **RAM** | 8 GB | 16 GB - 32 GB | System memory is used for CPU offloading |
| **GPU** | None (runs on CPU) | NVIDIA RTX (8GB+) or Apple Silicon | GPU accelerates token generation |
| **Python** | 3.11 | 3.12 or 3.13 | Global or managed via `uv` / `pyenv` |
| **Inference Server** | [Ollama](https://ollama.ai) | Ollama running locally | Serves OpenAI-compatible REST API |

### How It Works Under the Hood
```
  Developer (Terminal / Python Script)
                │
                ▼
   ┌──────────────────────────────────────────────┐
   │ code_agent.py (Developer CLI & Shell)        │
   └──────────────────────┬───────────────────────┘
                          │ passes prompt + workspace paths
                          ▼
   ┌──────────────────────────────────────────────┐
   │ Google Antigravity SDK (`google-antigravity`) │
   └──────────────────────┬───────────────────────┘
                          │ LocalOpenAIConnectionStrategy (POST /v1/chat/completions)
                          ▼
   ┌──────────────────────────────────────────────┐
   │ Ollama Inference Engine (localhost:11434)    │
   │ Models: qwen2.5:14b / llama3.1:8b            │
   └──────────────────────┬───────────────────────┘
                          │ Model emits function call: create_file(Path, Content)
                          ▼
   ┌──────────────────────────────────────────────┐
   │ Security Policy Engine: policy.allow_all()   │
   └──────────────────────┬───────────────────────┘
                          │ Writes file directly to disk
                          ▼
   ┌──────────────────────────────────────────────┐
   │ Target Project Workspace (e.g., ./my-app)    │
   └──────────────────────────────────────────────┘
```

---

## 3. Zero Setup (3-Minute Quickstart)

### Step 1: Install & Launch Ollama
1. Download Ollama from [ollama.ai/download](https://ollama.ai/download).
2. Start Ollama (on Windows, it runs automatically in your system tray; or run `ollama serve` in a terminal).
3. Verify it is running:
   ```bash
   ollama --version
   ```

### Step 2: Download the Agent Coding Model
Run this in any terminal:
```bash
# Recommended (best agent tool-calling & coding performance, requires ~9GB VRAM/RAM):
ollama pull qwen2.5:14b

# Alternative for compact machines / laptops (under 12GB RAM):
# ollama pull llama3.1:8b
```

### Step 3: Clone & Bootstrap
```bash
git clone https://github.com/veeresh-bikkaneti/antigravity-local.git
cd antigravity-local
```

Run the 1-click bootstrap:
- **Windows (PowerShell)**:
  ```powershell
  .\run.ps1
  ```
- **Windows (Command Prompt)**:
  ```cmd
  run.bat
  ```
- **macOS / Linux**:
  ```bash
  chmod +x run.sh && ./run.sh
  ```

The bootstrap creates your Python virtual environment, installs dependencies, configures `.env`, and tests connectivity.

---

## 4. Start Coding: Interactive Pair-Programmer Shell

The interactive shell lets you chat with your local agent about any project folder on your machine.

### Launch on Any Project Folder:
```powershell
# Point to your own application directory:
.\venv\Scripts\python code_agent.py --workspace "C:\path\to\my-app"

# Or work inside the local workspace folder:
.\venv\Scripts\python code_agent.py --workspace ./workspace
```

### Example Interactive Session:
```text
============================================================================
 🚀 Google Antigravity - Local Developer Coding Shell
============================================================================
 • Server Endpoint : http://localhost:11434/v1
 • Active Model    : qwen2.5:14b
 • Active Workspace: C:\Users\veere\source\repos\local-antigravity\workspace
 • Safety Policy   : policy.allow_all() (Autonomous Disk Access)
============================================================================

CodeAgent [You] > Create a python module database.py with an SQLite helper class that handles creating tables and inserting records safely.

CodeAgent [Local LLM] > I have created `database.py` in your workspace with parameterized queries, context manager connection handling, and error logging.

CodeAgent [You] > /files
📂 Files currently in workspace (1 total):
   - database.py

CodeAgent [You] > Now create a test_database.py using pytest to verify table creation and inserts.

CodeAgent [Local LLM] > Created `test_database.py` with in-memory SQLite fixtures and test assertions.
```

### Built-in Shell Commands:
- `/memory <query>` : Searches project memory using SQLite FTS5 BM25 plus dense semantic vectors, merged with Reciprocal Rank Fusion.
- `/wiki [topic]`   : Loads canonical domain knowledge pages from `.wiki/` with zero token waste.
- `/files`          : Lists all files currently created in your workspace directory.
- `/help`           : Displays tips and syntax guides.
- `exit` or `quit`  : Closes the coding session.

### Automatic Memory Augmentation:
Launch with `--with-memory` to prepend the top 2-3 most relevant project memory chunks to the model's context for each coding task, which keeps the token window small:
```powershell
python code_agent.py --workspace ./workspace --with-memory
```

---

## 5. Start Coding: One-Shot Autonomous Task CLI

Want to execute a coding task non-interactively from the command line or CI/CD script? Pass the `--task` flag:

```powershell
.\venv\Scripts\python code_agent.py `
  --workspace "./my-project" `
  --task "Build a CLI tool in cli.py using argparse that converts JSON files to CSV."
```

The agent will:
1. Parse your request.
2. Formulate the code and structure.
3. Call the `create_file` tool to save `cli.py` to your specified workspace.
4. Report the created files and exit.

---

## 6. 3 End-to-End Real World Coding Recipes

Here are three copy-paste workflows you can run right now:

### Recipe 1: Scaffold a Complete FastAPI Backend Microservice

Run this single command:
```powershell
.\venv\Scripts\python code_agent.py `
  --workspace "./api_backend" `
  --task "Build a complete FastAPI REST API in main.py for a Task Manager with endpoints: GET /tasks, POST /tasks, GET /tasks/{id}, and DELETE /tasks/{id}. Include Pydantic schemas for input validation and SQLite for storage."
```

The agent generates this inside `./api_backend/main.py`:
- Pydantic models: `TaskBase`, `TaskCreate`, `TaskResponse`.
- SQLite database initialization with auto-created tables.
- FastAPI dependency injection for database connections.
- JSON responses with HTTP status codes (200, 201, 404).

---

### Recipe 2: Write Automated Unit Tests for Existing Code

Suppose you have an existing file `calculator.py` in your project folder. Tell the agent to inspect it and write tests:

```powershell
.\venv\Scripts\python code_agent.py `
  --workspace "./my_codebase" `
  --task "Inspect calculator.py and create tests/test_calculator.py with full pytest unit tests, including tests for boundary conditions, invalid types, and zero-division errors."
```

Then run your tests immediately:
```powershell
pytest ./my_codebase/tests/test_calculator.py
```

---

### Recipe 3: Refactor Legacy Code & Modernize Architecture

Ask the agent to refactor synchronous or blocking Python code into `asyncio`:

```powershell
.\venv\Scripts\python code_agent.py `
  --workspace "./my_codebase" `
  --task "Refactor fetcher.py to use httpx and asyncio instead of the blocking requests library. Ensure proper exception handling and timeout configurations."
```

---

## 7. The Developer SDK Handbook (Writing Your Own Agents in Python)

You aren't stuck with the pre-made scripts. The Google Antigravity SDK lets you build your own agents in under 30 lines of Python.

### Minimal Custom Agent Script (`my_custom_agent.py`):

```python
import asyncio
import os
from google.antigravity import Agent, LocalOpenAIAgentConfig
from google.antigravity.hooks import policy

async def build_software():
    # 1. Define your project workspace
    workspace = os.path.abspath("./my_new_app")
    os.makedirs(workspace, exist_ok=True)

    # 2. Configure the local agent
    config = LocalOpenAIAgentConfig(
        model="qwen2.5:14b",                          # Your local model
        base_url="http://localhost:11434/v1",         # Local Ollama endpoint
        workspaces=[workspace],                       # Allowed disk access
        policies=[policy.allow_all()],                # Autonomous permission
    )

    # 3. Launch the agent lifecycle
    async with Agent(config) as agent:
        prompt = (
            f"Create a file named server.py in workspace '{workspace}' "
            "that sets up a basic HTTP server listening on port 8080."
        )
        print(f"Instructing agent on workspace: {workspace}...\n")
        
        # 4. Stream response tokens in real-time
        response = await agent.chat(prompt)
        async for token in response:
            print(token, end="", flush=True)

    print("\n\n✅ Done! File created on disk.")

if __name__ == "__main__":
    asyncio.run(build_software())
```

### Safety Policies: Autonomous vs. Review Mode
- **Autonomous Mode (`policy.allow_all()`)**: The agent can inspect and create files without asking for confirmation each time. Good for quick prototyping and automated tasks.
- **Review Mode (`policy.ask_review()`)**: The agent prompts you for confirmation before executing file writes or terminal commands.

---

## 8. Advanced Backend Integration (LM Studio, vLLM & Google Research Harness)

### Option 1: LM Studio
1. Open LM Studio, load your model (e.g., `Qwen2.5-14B-Instruct-GGUF`).
2. Start the Local Server (port `1234`).
3. Update `.env`:
   ```bash
   LOCAL_LLM_BASE_URL=http://localhost:1234/v1
   LOCAL_LLM_MODEL=qwen2.5-14b-instruct
   ```

### Option 2: vLLM (High-Performance Linux Server)
```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-14B-Instruct \
  --port 8000
```
Then set in `.env`:
```bash
LOCAL_LLM_BASE_URL=http://localhost:8000/v1
LOCAL_LLM_MODEL=Qwen/Qwen2.5-14B-Instruct
```

### Option 3: Google Research AI Harness Binary
If you build Google's research agent harness from source, point Antigravity at your custom binary:
```powershell
$env:ANTIGRAVITY_HARNESS_PATH="C:\path\to\custom\localharness.exe"
```

---

## 9. Troubleshooting & Pro-Tips

### 1. Model Tool Calling Compatibility
- ✅ **Qwen 2.5 (`qwen2.5:14b` or `qwen2.5:7b`)**: Strong agent performance. Native support for OpenAI tool schemas.
- ✅ **Llama 3.1 (`llama3.1:8b`)**: Lightweight, fast, supports function calling.
- ⚠️ **Gemma 2 (`gemma2:27b`)**: Good for streaming text and reasoning, but Ollama does not currently enable tool schemas on Gemma 2. Use it for text generation via `test_local.py`.

### 2. File Path Formatting
Use absolute paths, or relative paths inside the configured `workspaces` array. `policy.allow_all()` lets the agent write within declared workspaces.

### 3. Windows Terminal Character Encoding
If you see `'charmap' codec can't encode character`, make sure your Python scripts reconfigure stdout to UTF-8. `code_agent.py`, `run.py`, and `test_local.py` already do this:
```python
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

---

## 10. Docker Clean-Room Test Drive

To run the whole Antigravity Local stack in a disposable container without touching your host's Python environments, use the 1-command Docker test drive.

The exact command differs by shell (CMD, PowerShell, Git Bash, macOS, Linux), so it lives in one place. See the [README Docker section](README.md#-1-command-docker-clean-room-test-drive). The one-liner that works everywhere: `python tests/e2e.py docker`.

The test drive checks:
1. Pure pip dependency installation in an unpolluted Linux environment.
2. SQLite FTS5 database initialization and BM25 index generation.
3. Hybrid semantic vector search and Reciprocal Rank Fusion retrieval.
4. Canonical topic loading from `.wiki/` with zero token waste.
5. Container-to-host bridge connection (`host.docker.internal:11434`) to your local Ollama instance.

---

## 11. Product Specification & Consensus Governance

The architecture specs and governance records live in these docs:
- **[Refined Product Specification](docs/PRODUCT_SPEC.md)**: Covers the runtime engine, zero-download model scheduler, 3-tier zero-token memory fabric, and security policies.
- **[Council Consensus Manifest](docs/CONSENSUS_MANIFEST.md)**: Voting and deliberation record signed by the Council of Experts (Architect, QA Lead, Systems Engineer, UX Designer, Security Officer) and approved by the Advisor.
- **[3-Tier Memory Fabric Specification](docs/MEMORY_SPEC.md)**: Compares RAG, OKF, and vector DBs, and gives the math for Reciprocal Rank Fusion.

---

Run `python code_agent.py` to start your first session.
