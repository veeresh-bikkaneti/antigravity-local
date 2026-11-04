# From zero to start coding with local Google Antigravity agent

> A start-to-finish guide to setting up and using a private AI pair programmer on your own machine. It runs on the official Google Antigravity SDK (`google-antigravity`) and local open-source models (Ollama, LM Studio, vLLM).

---

## Table of Contents
1. [What can this agent do?](#1-what-can-this-agent-do)
2. [Prerequisites & system architecture](#2-prerequisites--system-architecture)
3. [Zero setup (3-minute quickstart)](#3-zero-setup-3-minute-quickstart)
4. [Start coding: interactive pair-programmer shell](#4-start-coding-interactive-pair-programmer-shell)
5. [Start coding: one-shot autonomous task CLI](#5-start-coding-one-shot-autonomous-task-cli)
6. [3 end-to-end real world coding recipes](#6-3-end-to-end-real-world-coding-recipes)
   - [Recipe 1: Scaffold a complete FastAPI backend microservice](#recipe-1-scaffold-a-complete-fastapi-backend-microservice)
   - [Recipe 2: Write automated unit tests for existing code](#recipe-2-write-automated-unit-tests-for-existing-code)
   - [Recipe 3: Refactor legacy code & modernize architecture](#recipe-3-refactor-legacy-code--modernize-architecture)
7. [The developer SDK handbook (writing your own agents in Python)](#7-the-developer-sdk-handbook-writing-your-own-agents-in-python)
8. [Advanced backend integration (LM Studio, vLLM & Google Research Harness)](#8-advanced-backend-integration-lm-studio-vllm--google-research-harness)
9. [Troubleshooting & pro-tips](#9-troubleshooting--pro-tips)
10. [Docker clean-room test drive](#10-docker-clean-room-test-drive)
11. [Product specification & consensus governance](#11-product-specification--consensus-governance)

---

## 1. What can this agent do?

Unlike web-based chat interfaces or API-metered plugins, this agent runs on your own hardware. Here is what that gets you:
- **100% Private**: No telemetry and no cloud calls, so your code stays on your SSD.
- **Zero Fees**: No monthly subscription ($0/mo) and no token billing.
- **Real Disk Access**: The agent inspects folders, reads your source code, writes new files, and applies changes directly in your project workspace.
- **Model Freedom**: Swap models whenever you like. Use `qwen2.5:14b` for complex code reasoning, `llama3.1:8b` for lightweight laptops, or `gemma2:27b` for creative design.

---

## 2. Prerequisites & system architecture

### Hardware matrix
| Component | Minimum | Recommended | Notes |
| :--- | :--- | :--- | :--- |
| **OS** | Windows 10/11, macOS, Linux | Any modern 64-bit OS | Fully tested on Windows 11 & Linux |
| **RAM** | 8 GB | 16 GB - 32 GB | System memory is used for CPU offloading |
| **GPU** | None (runs on CPU) | NVIDIA RTX (8GB+) or Apple Silicon | GPU accelerates token generation |
| **Python** | 3.11 | 3.12 or 3.13 | Global or managed via `uv` / `pyenv` |
| **Inference Server** | [Ollama](https://ollama.ai) | Ollama running locally | Serves OpenAI-compatible REST API |

### How it works under the hood
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

## 3. Zero setup (3-minute quickstart)

Goal: go from nothing to your first AI-written file. The bootstrap itself takes about 3 minutes, which is the quickstart in the heading. With Ollama installed, plan on about 10 minutes in total, plus a model download if you have none.

### Step 1: Install & launch Ollama
Takes about 3 minutes.
1. Download Ollama from [ollama.ai/download](https://ollama.ai/download) and install it.
2. Start it. On Windows it runs from the system tray on its own. Otherwise run `ollama serve` in a terminal and leave that window open.
3. Check that it answers:
   ```bash
   ollama --version
   ```

You should see a version number. If you get "command not found", close the terminal and open a new one. The installer updates your PATH, and an old terminal doesn't know yet.

### Step 2: Download the agent coding model
You can skip this step. Step 3 picks a model that fits your machine and downloads it if you have none, and it reuses any capable model you already have, so nothing downloads twice.

Want to choose the model yourself? Run one of these. The download time depends on your connection.
```bash
# Recommended (best tool-calling and coding results, needs about 9 GB of free GPU memory or RAM):
ollama pull qwen2.5:14b

# Smaller machines (under 12 GB RAM):
# ollama pull llama3.1:8b
```

You should see the model in `ollama list`.

### Step 3: Clone & bootstrap
Takes about 3 minutes the first time, and under a minute after that.
1. Check that Python and git are installed (use `python3` instead of `python` on macOS and Linux):
   ```bash
   python --version
   git --version
   ```
   You should see Python 3.11 or newer and a git version.
2. Get the code:
   ```bash
   git clone https://github.com/veeresh-bikkaneti/antigravity-local.git
   ```
3. Step into the folder and stay there for the rest of this guide:
   ```bash
   cd antigravity-local
   ```
4. Run the one-click bootstrap. Pick the line that matches your terminal.
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
5. Wait. The middle of the run is quiet, because the packages install silently. It looks stuck, but it isn't. On Windows the first run took 157 to 189 seconds, so go make a coffee.

The bootstrap creates your Python virtual environment, installs dependencies, configures `.env`, checks that Ollama answers, and runs a short demo that writes `workspace/index.html`. You should see four numbered stages, `[1/4]` to `[4/4]`, and `System Online: Autonomous Agent Ready!` near the end. A lot of HTML scrolls past while the model writes the demo page, and that is normal. You then land at a `You >` chat prompt. Type `exit` for now. Section 4 shows how to use it properly.

If Ollama isn't installed, the bootstrap says so. Go back to Step 1.

---

## 4. Start coding: interactive pair-programmer shell

The interactive shell lets you chat with your local agent about any project folder on your machine. Prefer working inside an editor? See [Use your local model from Antigravity or VS Code](README.md#use-your-local-model-from-antigravity-or-vs-code).

### Before you start: activate the virtual environment
Do this once per terminal window, from inside the `antigravity-local` folder. After that, plain `python` is the right command for everything below.
- **Windows PowerShell**: `.\venv\Scripts\Activate.ps1` (if PowerShell blocks scripts, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first)
- **Windows Command Prompt**: `venv\Scripts\activate.bat`
- **Git Bash on Windows**: `source venv/Scripts/activate`
- **macOS / Linux**: `source venv/bin/activate`

You should see `(venv)` at the start of your prompt.

### Launch on any project folder:
```powershell
# Start here: work inside the local workspace folder:
python code_agent.py --workspace ./workspace

# Later, point it at your own project:
python code_agent.py --workspace "C:\path\to\my-app"
```

### Example interactive session:
```text
============================================================================
 🚀 Google Antigravity - Local Developer Coding Shell
============================================================================
 • Server Endpoint : http://localhost:11434/v1
 • Active Model    : qwen2.5:14b
 • Active Workspace: C:\path\to\antigravity-local\workspace
 • Safety Policy   : policy.allow_all() (Autonomous Disk Access)
 • Memory Fabric   : AVAILABLE (/memory, /wiki)
============================================================================
 Type your coding request below (e.g., 'Create a calculator CLI in Python').
 Commands: /memory <query>, /wiki [topic], /files, /help, exit/quit
============================================================================

CodeAgent [You] > Create a python module database.py with an SQLite helper class that handles creating tables and inserting records safely.

CodeAgent [Local LLM] > I have created `database.py` in your workspace with parameterized queries, context manager connection handling, and error logging.

CodeAgent [You] > /files
📂 Files currently in ./workspace (3 total):
   - .gitkeep
   - database.py
   - index.html

CodeAgent [You] > Now create a test_database.py using pytest to verify table creation and inserts.

CodeAgent [Local LLM] > Created `test_database.py` with in-memory SQLite fixtures and test assertions.
```

Your model's wording will differ a little. `/files` also lists `index.html`, which the setup demo wrote.

### Built-in shell commands:
- `/memory <query>` : Searches your project notes and docs and shows the best matches.
- `/wiki [topic]`   : With no topic, lists the pages in `.wiki/`. With a topic, such as `/wiki architecture`, prints that page.
- `/files`          : Lists all files currently created in your workspace directory.
- `/help`           : Displays tips and syntax guides.
- `exit` or `quit`  : Closes the coding session.

### Automatic memory augmentation:
Launch with `--with-memory` to prepend the top 2-3 most relevant project memory chunks to the model's context for each coding task, which keeps the token window small:
```powershell
python code_agent.py --workspace ./workspace --with-memory
```

---

## 5. Start coding: one-shot autonomous task CLI

Want to hand the agent one job and let it finish without chatting? Use the same terminal as section 4 (the one showing `(venv)`) and pass the `--task` flag:

```powershell
python code_agent.py --workspace "./my-project" --task "Build a CLI tool in cli.py using argparse that converts JSON files to CSV."
```

The agent writes the code, saves `cli.py` to your workspace with its `create_file` tool, prints its reply, and exits. You should see `Task completed. Created 1, changed 0.` and the new file listed.

See a warning that no files were created instead? The model answered without writing anything, which small local models do now and then. Run the same command again, or name the file in the task, for example "Create hello.py that prints hi".

If the workspace folder doesn't exist yet, it is created for you. You may also see a line such as "The workflow is running in the background ... task logs are available at file:///...". That is the SDK's own task log, not an error. Look in your workspace folder for the new file.

---

## 6. 3 end-to-end real world coding recipes

Here are three copy-paste workflows you can run right now:

### Recipe 1: Scaffold a complete FastAPI backend microservice

Run this single command:
```powershell
python code_agent.py --workspace "./api_backend" --task "Build a complete FastAPI REST API in main.py for a Task Manager with endpoints: GET /tasks, POST /tasks, GET /tasks/{id}, and DELETE /tasks/{id}. Include Pydantic schemas for input validation and SQLite for storage."
```

The agent generates this inside `./api_backend/main.py`:
- Pydantic models: `TaskBase`, `TaskCreate`, `TaskResponse`.
- SQLite database initialization with auto-created tables.
- FastAPI dependency injection for database connections.
- JSON responses with HTTP status codes (200, 201, 404).

---

### Recipe 2: Write automated unit tests for existing code

Suppose you have an existing file `calculator.py` in your project folder. Tell the agent to inspect it and write tests:

```powershell
python code_agent.py --workspace "./my_codebase" --task "Inspect calculator.py and create tests/test_calculator.py with full pytest unit tests, including tests for boundary conditions, invalid types, and zero-division errors."
```

Then run your tests immediately:
```powershell
pytest ./my_codebase/tests/test_calculator.py
```

---

### Recipe 3: Refactor legacy code & modernize architecture

Ask the agent to refactor synchronous or blocking Python code into `asyncio`:

```powershell
python code_agent.py --workspace "./my_codebase" --task "Refactor fetcher.py to use httpx and asyncio instead of the blocking requests library. Ensure proper exception handling and timeout configurations."
```

---

## 7. The developer SDK handbook (writing your own agents in Python)

You aren't stuck with the pre-made scripts. The Google Antigravity SDK lets you build your own agents in under 30 lines of Python.

### Minimal custom agent script (`my_custom_agent.py`):

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

### Safety policies: autonomous vs. review mode
- **Autonomous Mode (`policy.allow_all()`)**: The agent can inspect and create files without asking for confirmation each time. Good for quick prototyping and automated tasks.
- **Review Mode (`policy.ask_review()`)**: The agent prompts you for confirmation before executing file writes or terminal commands.

---

## 8. Advanced backend integration (LM Studio, vLLM & Google Research Harness)

### Option 1: LM Studio
1. Open LM Studio, load your model (e.g., `Qwen2.5-14B-Instruct-GGUF`).
2. Start the Local Server (port `1234`).
3. Update `.env`:
   ```bash
   LOCAL_LLM_BASE_URL=http://localhost:1234/v1
   LOCAL_LLM_MODEL=qwen2.5-14b-instruct
   ```

### Option 2: vLLM (high-performance Linux server)
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

### Option 3: Google Research AI Harness binary
If you build Google's research agent harness from source, point Antigravity at your custom binary:
```powershell
$env:ANTIGRAVITY_HARNESS_PATH="C:\path\to\custom\localharness.exe"
```

---

## 9. Troubleshooting & pro-tips

### 1. Model tool calling compatibility
- ✅ **Qwen 2.5 (`qwen2.5:14b` or `qwen2.5:7b`)**: Strong agent performance. Native support for OpenAI tool schemas.
- ✅ **Llama 3.1 (`llama3.1:8b`)**: Lightweight, fast, supports function calling.
- ⚠️ **Gemma 2 (`gemma2:27b`)**: Good for streaming text and reasoning, but Ollama does not currently enable tool schemas on Gemma 2. Use it for text generation via `test_local.py`.

### 2. File path formatting
Use absolute paths, or relative paths inside the configured `workspaces` array. `policy.allow_all()` lets the agent write within declared workspaces.

### 3. Windows Terminal character encoding
If you see `'charmap' codec can't encode character`, make sure your Python scripts reconfigure stdout to UTF-8. `code_agent.py`, `run.py`, and `test_local.py` already do this:
```python
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

---

## 10. Docker clean-room test drive

To run the whole Antigravity Local stack in a disposable container without touching your host's Python environments, use the 1-command Docker test drive.

The exact command differs by shell (CMD, PowerShell, Git Bash, macOS, Linux), so it lives in one place. See the [README Docker section](README.md#1-command-docker-clean-room-test-drive). The one-liner that works everywhere: `python tests/e2e.py docker`.

The test drive checks:
1. Pure pip dependency installation in an unpolluted Linux environment.
2. SQLite FTS5 database initialization and BM25 index generation.
3. Hybrid semantic vector search and Reciprocal Rank Fusion retrieval.
4. Canonical topic loading from `.wiki/` with zero token waste.
5. Container-to-host bridge connection (`host.docker.internal:11434`) to your local Ollama instance.

---

## 11. Product specification & consensus governance

The architecture specs and governance records live in these docs:
- **[Refined Product Specification](docs/PRODUCT_SPEC.md)**: Covers the runtime engine, zero-download model scheduler, 3-tier zero-token memory fabric, and security policies.
- **[Council Consensus Manifest](docs/CONSENSUS_MANIFEST.md)**: Voting and deliberation record signed by the Council of Experts (Architect, QA Lead, Systems Engineer, UX Designer, Security Officer) and approved by the Advisor.
- **[3-Tier Memory Fabric Specification](docs/MEMORY_SPEC.md)**: Compares RAG, OKF, and vector DBs, and gives the math for Reciprocal Rank Fusion.

---

Run `python code_agent.py` to start your first session. The loop is simple: you ask, the agent reads and writes files in your workspace, and nothing leaves your machine. Happy coding.
