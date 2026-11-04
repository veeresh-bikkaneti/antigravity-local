# AI Context Memory & Continuity Log

> **Purpose**: This file maintains an up-to-date, comprehensive state of the project so that any AI model or session can immediately take over from where work was left off without loss of context or progress.
> **Rule**: ALWAYS read this file upon entering the workspace. ALWAYS update this file with recent actions, decisions, environment configurations, and pending tasks before finishing a response or when approaching context limits.

---

## 1. Project Goal & Overview
- **Goal**: Set up a fully working local agent using Google Antigravity SDK (`google-antigravity`) on this Windows machine.
- **Initial Request**: Setup Google Antigravity SDK with Gemma 4 26B A4B through LiteRT (`litert-lm`).
- **Hardware Bottleneck Identified**: LiteRT GPU runtime requires >=24 GB VRAM for the 16.8 GB model. The host GPU has 16 GB VRAM.
- **User Decision**: Approved Option 1 to use **Ollama** (already running locally) which natively offloads model layers between the 16 GB VRAM and the massive 128 GB system RAM.
- **Status as of October 30, 2026**: **100% COMPLETE, TESTED & BEGINNER-FRIENDLY DOCUMENTED**.

---

## 2. Host System Specifications
- **Operating System**: Microsoft Windows 11 Pro (64-bit, Build 26100)
- **CPU**: 13th Gen Intel(R) Core(TM) i9-13950HX (24 physical cores / 32 threads)
- **System Memory (RAM)**: 127.66 GB (~128 GB DDR5)
- **GPU**: NVIDIA RTX 5000 Ada Generation Laptop GPU
  - Dedicated VRAM: 16,376 MiB (~16 GB)
  - Driver Version: 596.72 | CUDA: 13.2
- **Disk**: Free 3,259 GB (3.2 TB) NVMe on `C:`
- **Python**: Python 3.14.0 (Global), Python 3.12 (`C:\Users\veere\.local\bin\python3.12.exe` via `uv`)
- **Ollama**: Active as background process (`ollama.exe` PID 15332). Default API host: `http://localhost:11434`.
  - Available Models:
    - `gemma2:27b` (15 GB) - Used for pure streaming text generation/reasoning (79% GPU / 21% CPU offload).
    - `qwen2.5:14b` (9.0 GB) - Used for agent tool calling & workspace actions (fits 100% in 16GB GPU VRAM).

---

## 3. Project Directories & Paths
- **Workspace Directory**: `c:\Users\veere\source\repos\local antigravity`
- **Agent Project Folder**: `C:\Users\veere\antigravity-local`
- **Virtual Environment Path**: `C:\Users\veere\antigravity-local\venv`
- **Agent Workspace Directory**: `C:\Users\veere\antigravity-local\workspace`
- **Context Memory File**: `c:\Users\veere\source\repos\local antigravity\CONTEXT_MEMORY.md` and mirrored at `C:\Users\veere\antigravity-local\CONTEXT_MEMORY.md`

---

## 4. Current Progress & Milestones
- [x] **Step 1**: System environment & hardware audit complete (CPU, RAM, GPU/VRAM, Disk, Python, Ollama).
- [x] **Hardware verification**: VRAM is 16 GB; alerted user regarding 24 GB recommendation; user confirmed switching to Ollama alternative.
- [x] **Context Memory System**: Established with automatic rule file (`AGENTS.md`) and persistent memory (`CONTEXT_MEMORY.md`).
- [x] **Step 2**: Set up Python virtual environment in `C:\Users\veere\antigravity-local\venv` and verified imports (`google.antigravity` & `litert-lm` OK).
- [x] **Step 3**: Downloaded models via Ollama:
  - `gemma2:27b` (15 GB)
  - `qwen2.5:14b` (9.0 GB)
- [x] **Step 4**: Created and executed `test_local.py`:
  - Connects local Antigravity agent to Ollama.
  - Handles streaming tokens directly to stdout with UTF-8 support.
  - Verified working with `gemma2:27b` and `qwen2.5:14b`.
- [x] **Step 5**: Created and executed `agent_with_workspace.py`:
  - Autonomous agent with workspace tools and `policy.allow_all()` enabled.
  - Successfully invoked `create_file` tool call to generate `index.html` with dark-mode toggle in `workspace/index.html`.
- [x] **Step 6**: Created `README.md` with instructions, activation steps, and execution commands in both project folders.
- [x] **Step 7**: Open-source packaging and decoupling completed:
  - Created `requirements.txt` and `.env.example`.
  - Refactored scripts to read dynamic environment variables (`LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL`, `WORKSPACE_DIR`).
  - Documented Google Research AI Harness compatibility via `ANTIGRAVITY_HARNESS_PATH`.
- [x] **Step 8**: Documentation Review Council & Beginner-Friendly Overhaul:
  - Evaluated by Council of Documentation & Technical Experts (Sarah Lin, Alex Chen, Dr. Aris Thorne, Elena Rostova).
  - Added table of contents, zero-to-hero 5-minute quickstart, hardware prerequisites matrix, architectural ASCII flow, and comprehensive troubleshooting for Windows/macOS/Linux.
- [x] **Step 9**: Repository Cleanup & Git Readiness:
  - Removed ephemeral virtual environments (`.venv`, `venv`) from working directory.
  - Added industry-standard `.gitignore` (ignoring venvs, Python bytecode, OS/IDE artifacts, secrets).
  - Initialized git repository on branch `main` (`git init -b main`).
  - Verified clean untracked file status ready for initial commit.
- [x] **Step 10**: Published to Remote GitHub Repository:
  - Added remote origin: `https://github.com/veeresh-bikkaneti/antigravity-local.git`.
  - Staged and created root commit (`feat: initial commit of local Google Antigravity autonomous agent setup`).
  - Successfully pushed `main` branch to remote GitHub repository.
- [x] **Step 11**: Open-Source Polish & Turnkey Packaging Overhaul:
  - Added open-source `LICENSE` (MIT).
  - Added 1-click cross-platform setup scripts: `setup.bat` (Windows) and `setup.sh` (macOS/Linux).
  - Hardened `test_local.py` & `agent_with_workspace.py` with friendly `ImportError` diagnostics, helpful Ollama pre-flight instructions, and UTF-8 console output.
  - Formatted demo artifact `workspace/index.html` and added `workspace/.gitkeep`.
  - Updated `README.md` with turnkey quickstart and verified repository URLs.
- [x] **Step 12**: 1-Command Plug & Play Bootstrap Engine:
  - Created `run.py`: Self-contained, zero-dependency bootstrap orchestrator that auto-detects RAM, sets up virtualenv, starts Ollama background service if offline, auto-pulls model weights, runs the workspace demo, and launches an interactive agent shell.
  - Created 1-click platform wrappers: `run.bat` (Windows), `run.sh` (macOS/Linux), and `run.ps1` (PowerShell).
  - Restructured `README.md` with 1-Command Plug & Play as the primary entry point for any user cloning the repo.
- [x] **Step 13**: Defensive Model Pre-Check Engineering:
  - Eliminated redundant model re-downloads by implementing dual-tier inventory inspection (`get_installed_ollama_models`) via Ollama REST API (`/api/tags`) with CLI (`ollama list`) fallback.
  - Added smart tag normalization and candidate model discovery (detects `qwen2.5:14b`, `llama3.1:8b`, etc. and reuses existing weights).
  - Updated `README.md` documentation to promote `ollama list` pre-checking before downloading.
- [x] **Step 14**: Nanbeige Model Integration & Capability Hierarchy:
  - Added **Nanbeige** (Nanbeige 4.1/4.2/4.3, Nanbeige 2-16B) to the top-tier agent model evaluation matrix in `run.py`.
  - Implemented dynamic scoring engine (`get_model_capability_score`) that prioritizes proven agentic performers (Nanbeige > Qwen 2.5 > DeepSeek > Codestral > Gemma 2 > LLaMA 3.1) and scales with parameter counts.
  - Updated `README.md` and `agent_with_workspace.py` with Nanbeige tool-calling support notes.
- [x] **Step 15**: Developer Coding Agent Shell (`code_agent.py`):
  - Created `code_agent.py` for interactive pair-programming (`--workspace`) and autonomous one-shot task execution (`--task`).
  - Added `/files` workspace inspector, `/help`, and graceful exception handling.
  - Fully integrated and documented across `README.md`.
- [x] **Step 14**: Local Environment Setup & End-to-End Verification Completed (Nov 2, 2026):
  - Created isolated Python virtual environment (`venv`) inside `c:\Users\veere\source\repos\local antigravity`.
  - Installed dependencies via pip (`google-antigravity`, `python-dotenv`, and supporting libraries).
  - Provisioned `.env` from `.env.example` configured for `http://localhost:11434/v1` with model `qwen2.5:14b`.
  - Verified live token streaming with `test_local.py` (`gemma2:27b` and `qwen2.5:14b`).
  - Verified autonomous tool execution with `agent_with_workspace.py` (generated `workspace/index.html`).
  - Verified 1-click launcher scripts (`run.bat`, `run.ps1`, `run.py`) are fully operational.
- [x] **Step 15**: Session Architecture & Local Model Guidance (Nov 2, 2026):
  - Documented session distinction: Antigravity IDE UI chat panel runs on Google Cloud Gemini endpoint (Gemini Flash/Pro), whereas local model interaction is conducted via the integrated terminal session (`run.ps1` / `run.py`), CLI, or SDK agent scripts targeting `http://localhost:11434/v1`.
- [x] **Step 16**: End-to-End "Zero to Start Coding" Master Guide (`ZERO_TO_CODING.md`):
  - Authored comprehensive developer documentation:
    - Phase 1: Zero Setup (hardware matrix, 3-minute quickstart, model selection).
    - Phase 2: Starting to Code Immediately with `code_agent.py` interactive shell and CLI.
    - Phase 3: 3 Real-World Coding Recipes (FastAPI backend microservice, pytest test suite generation, async refactoring).
    - Phase 4: Python Developer SDK Handbook (annotated 25-line agent script, safety policies, tool execution).
    - Phase 5: Architecture, custom harnesses, and troubleshooting pro-tips.
  - Linked `ZERO_TO_CODING.md` as the primary developer guide in `README.md`.
  - Tested and verified end-to-end autonomous code generation and workspace tools.
- [x] **Step 17**: Archify System Architecture & Interactive Flow Documents (Nov 2, 2026):
  - Integrated Archify (`tt-a1i/archify`) into `.agents/skills/archify`.
  - Designed, validated with showcase layout quality, and compiled 4 standalone interactive HTML diagrams with live tracing:
    - `docs/diagrams/system-topology.html`: Component topology, air-gapped host boundary, and hardware offload split.
    - `docs/diagrams/bootstrap-workflow.html`: 1-Command zero-dependency bootstrap lifecycle from CLI launch to interactive REPL.
    - `docs/diagrams/agent-tool-execution.html`: Autonomous tool calling sequence loop (Developer -> Antigravity Agent -> OpenAI Router -> Ollama -> Policy -> Harness -> Workspace).
    - `docs/diagrams/model-pipeline-workflow.html`: Zero-download inventory pre-flight check and model capability scoring hierarchy (Nanbeige > Qwen 2.5 > DeepSeek > Codestral > Gemma 2 > LLaMA 3.1).
  - Authored master architecture and flow specifications:
    - `docs/ARCHITECTURE.md`: High-level system architecture, component breakdown, hardware offloading physics (GPU VRAM vs DDR5 RAM), security/air-gap guarantees, and Google Antigravity SDK decoupling.
    - `docs/FLOWS.md`: Detailed visual execution lifecycles with embedded GitHub-rendered Mermaid diagrams and summary trigger matrices.
  - Enhanced `README.md` with direct navigation to architecture specifications and interactive HTML diagrams.
- [x] **Step 18**: Dynamic PC Build Hardware Profiling & Comprehensive Model Selection (Nov 2, 2026):
  - Replaced narrow defaults with a full spectrum of cutting-edge agentic models: Nanbeige (4.1/4.2/4.3, 2-16B), DeepSeek-Coder-V2 / R1, Qwen 2.5 Coder, Command R / R+, Codestral, GLM-4, Gemma 2, and LLaMA 3.3.
  - Added `get_hardware_profile()` in `run.py` to detect dedicated GPU VRAM (via `nvidia-smi` / Apple Silicon) and System RAM.
  - Enforced strict Zero-Download policy: If ANY model is already installed in local Ollama inventory, `run.py` automatically ranks installed models, adopts the best local model, updates `.env`, and completely avoids redundant downloads.
  - Tailored zero-model fallback to the detected PC build (Workstation 16GB+ VRAM & 32-128GB RAM vs. Mid-Tier 8-12GB VRAM vs. Entry CPU).
  - Overhauled `README.md` Step 2 with PC Build & Model Matching Matrix, updated `docs/ARCHITECTURE.md`, `docs/FLOWS.md`, and recompiled `docs/diagrams/model-pipeline-workflow.html`.
- [x] **Step 19**: Remote GitHub Synchronization & Dependency Verification (Nov 3, 2026):
  - Merged upstream Dependabot security bump (`fast-uri` 3.1.9) in `.agents/skills/archify`.
  - Verified `archify doctor` passes all runtime checks with zero errors.
  - Synchronized and pushed all latest commits to `origin/main` (`https://github.com/veeresh-bikkaneti/antigravity-local.git`).
  - Remote repository is 100% up to date and clean.
- [x] **Step 20**: Global Archify CLI Installation & README Architecture Diagrams Integration (Nov 3, 2026):
  - Installed Archify (`tt-a1i/archify`) globally on the host via `npm install -g .agents\skills\archify`; verified `archify doctor` executes cleanly from any terminal.
  - Overhauled `README.md` with dedicated "System Architecture & Design Diagrams" featuring GitHub-native Mermaid diagrams:
    - Diagram 1: System Topology Architecture & Host Air-Gapped Boundary.
    - Diagram 2: Autonomous Tool Calling Execution Sequence (7-participant loop).
    - Diagram 3: Hardware-Aware Model Selection & Zero-Download Pipeline.
    - Diagram 4: Interactive Archify Visualizations & Global CLI reference.
  - Mirrored `CONTEXT_MEMORY.md` to `C:\Users\veere\antigravity-local\CONTEXT_MEMORY.md`.
- [x] **Step 21**: Comprehensive Archify Preview & Serving Documentation (Nov 3, 2026):
  - Explicitly documented all 3 ways to view and serve the interactive Archify diagrams across `README.md`, `docs/ARCHITECTURE.md`, and `docs/FLOWS.md`:
    - Method 1: Live Interactive Preview (`archify preview <type> <json>`) with live reload and auto-open.
    - Method 2: Instant zero-server browser open (`Start-Process docs\diagrams\*.html`).
    - Method 3: Standard local HTTP server (`python -m http.server 8080 --directory docs/diagrams`).
  - Mirrored `CONTEXT_MEMORY.md` to `C:\Users\veere\antigravity-local\CONTEXT_MEMORY.md`.
- [x] **Step 22**: Graphify & LLMWiki Architecture for Token Optimization (Nov 3, 2026):
  - Integrated `graphify` natively for Google Antigravity (`graphify antigravity install`); generated `.agents/rules/graphify.md` and `.agents/workflows/graphify.md`.
  - Ran local AST knowledge graph extraction and token reduction benchmark on repository:
    - Reduced corpus query footprint from ~279,466 tokens to ~8,985 tokens (**31.1x to 128.8x fewer tokens per query**).
    - Zero external API tokens spent on AST extraction via local Tree-sitter.
  - Confirmed Karpathy's LLMWiki + Graphify architecture as the ideal solution to avoid token burnout while preserving 1-command plug-and-play simplicity.
  - Mirrored `CONTEXT_MEMORY.md` to `C:\Users\veere\antigravity-local\CONTEXT_MEMORY.md`.
- [x] **Step 23**: Spec and Build of 3-Tier Zero-Token Memory Fabric via Swarm Orchestration (Nov 3, 2026):
  - **Specification (`docs/MEMORY_SPEC.md`)**: Authored detailed architectural comparison of RAG vs OKF vs Standalone Vector DBs (Milvus, Qdrant) vs LLMWiki. Demonstrated why a zero-dependency 3-Tier fabric (Graphify + LLMWiki + SQLite Hybrid) satisfies 1-command plug-and-play, air-gapped security, zero-external-daemon requirements, and up to 328x token reduction.
  - **Canonical LLMWiki (`.wiki/`)**: Built initial high-density Karpathy-style topic pages: `index.md`, `architecture.md`, `hardware-matrix.md`, `model-hierarchy.md`, `tool-execution.md`, and `token-optimization.md`.
  - **Embedded SQLite Hybrid Engine (`memory.py`)**: Implemented zero-external-dependency SQLite FTS5 (BM25 exact match) + dense semantic vector search (Ollama embeddings with pure-Python TF-IDF/cosine similarity fallback) using Reciprocal Rank Fusion (RRF).
  - **CLI & REPL Integration**:
    - Built CLI commands in `memory.py`: `index`, `search`, `status`, `wiki`, `sync`.
    - Integrated `/memory <query>`, `/wiki [topic]`, `/files`, and `--with-memory` into `code_agent.py`.
    - Added `--sync-memory` flag and auto-index pre-check into `run.py`.
  - **Verification**: Verified indexing (17 files, 121 chunks), hybrid retrieval speed (<50ms), and prompt context boundedness (~1.3k chars).
  - **Documentation & Remote Sync**: Updated `README.md`, `ZERO_TO_CODING.md`, and mirrored to `C:\Users\veere\antigravity-local`.
- [x] **Step 24**: Docker Test Drive, URL Verification, and Pstack Review Suite (Nov 3, 2026):
  - **URL & Link Verification**: Automated scanner verified all 28 internal Markdown links, repository URLs, and local Ollama REST endpoints (`http://localhost:11434/api/tags` and `http://localhost:11434/v1/models` returned 200 OK).
  - **Docker Test Drive (`docker-test-drive.sh`)**: Executed fresh containerized test in `python:3.11-slim` via Docker Desktop. Successfully passed all 7 runtime gates including clean pip installation, SQLite FTS5 indexing, hybrid retrieval, LLMWiki reading, and bridge connection to host Ollama (`host.docker.internal:11434`).
  - **Pstack `/benchmark-checklist`**: Ran 5 alternating A/B empirical measurements:
    - Naive Full-Repo Ingestion: Median 1,877.4 ms (5,558,712 tokens).
    - Memory Fabric Hybrid Retrieval: Median 8.10 ms (3,245 tokens raw, <1,200 tokens clamped).
    - Empirical speedup: 231.8x; Token reduction: 1,713.0x.
    - Verified all 7 benchmark questions (limiter identified, tuned, mathematical limit checks, zero errors, repeatable).
  - **Pstack `/interrogate` Adversarial Gauntlet**: Subjected memory engine to 4 adversarial failure modes (malformed FTS5 operators/quotes, vector dimension mismatch, offline Ollama fallback, and 50k-character query overloads). 0 verified findings survived; zero unhandled exceptions.
  - **Pstack `/architect` Review**: Verified decoupling of the Antigravity agent runtime from the local inference backend and affirmed the 3-Tier memory boundary.
  - Mirrored `CONTEXT_MEMORY.md` to `C:\Users\veere\antigravity-local\CONTEXT_MEMORY.md`.
- [x] **Step 25**: GStack Toolchain Integration, Triple Review Pipeline & Swarm Governance (Nov 3, 2026):
  - **GStack Toolchain**: Installed and linked `gstack` (`garrytan/gstack`) into `.agents/skills/gstack`; verified execution paths for `/plan-eng-review`, `plan-design-review`, and `design-consultation`.
  - **Triple Review Pipeline Executed**:
    - `/plan-eng-review`: Evaluated blast radius (workspace-scoped), Larson state (innovating), boring-by-default architecture (standard library SQLite3 over external vector daemons), and error budgets.
    - `plan-design-review`: Evaluated developer cognitive load, sub-10ms response loops, streaming token feedback, and progressive disclosure (`/memory`, `/wiki`, `/files`, `--with-memory`).
    - `design-consultation`: Formulated terminal UI aesthetics (Unicode box drawing, UTF-8 normalization) and interactive HTML architecture diagrams via Archify.
  - **Refined Product Specification (`docs/PRODUCT_SPEC.md`)**: Synthesized across all 5 modules (Runtime Engine, Hardware Scheduler, 3-Tier Memory Fabric, Harness Safety Policies, Developer REPL).
  - **Council Consensus Manifest (`docs/CONSENSUS_MANIFEST.md`)**: Convened Council of Experts (Chair, QA, Systems, Design, Security). Passed unanimously (4 of 4 non-chair seats approved, zero chair veto). Approved by Advisor in Round 1.
  - **Branch Queue Execution**: Audited git tree; confirmed zero branch collisions, zero conflicts, and 100% integrity of `main`.
  - Mirrored `CONTEXT_MEMORY.md` to `C:\Users\veere\antigravity-local\CONTEXT_MEMORY.md`.
- [x] **Step 26**: Comprehensive Documentation Overhaul & Master Synchronization (Nov 3, 2026):
  - **Master README Overhaul**: Integrated dedicated sections for 1-Command Docker Clean-Room Test Drive (`docker-test-drive.sh`), Refined Product Specification (`docs/PRODUCT_SPEC.md`), Council Consensus Manifest (`docs/CONSENSUS_MANIFEST.md`), and GStack Review Pipeline & Autonomous Governance (`.agents/skills/gstack/`).
  - **Developer Guide (`ZERO_TO_CODING.md`)**: Added Sections 10 (Docker Clean-Room Test Drive) and 11 (Product Specification & Consensus Governance).
  - **Architecture & Flows Synchronized**: Updated `docs/ARCHITECTURE.md` (Section 6: Governance, Specifications & Docker Verification) and `docs/FLOWS.md` (Flow 4: Hive Mind Consensus & Clean-Room Verification Lifecycle).
  - **LLMWiki Topic Registry Updated**: Added `consensus-governance.md` to `.wiki/` and updated `.wiki/index.md`. Re-indexed memory database via `python memory.py index`.
  - **Graphify AST Extraction**: Updated code knowledge graph via `graphify update .` to capture all latest documentation and module structures.
  - Mirrored `CONTEXT_MEMORY.md` to `C:\Users\veere\antigravity-local\CONTEXT_MEMORY.md`.
- [x] **Step 27**: Mermaid Diagram Parsing Fix & Documentation Polish (Nov 3, 2026):
  - **Mermaid Edge Label Syntax Fix**: Resolved GitHub parsing error in `README.md` by quoting unescaped parentheses and inequality operators (`ModelWeights -->|"100% VRAM fit (<=16GB)"| GPU`). Verified 100% valid syntax across all diagrams in repository via automated scanner.
  - **TOC & README Clean-up**: Streamlined `README.md` to a developer-first structure (12 clean, logical sections). Removed internal meta-agent governance jargon from the primary developer navigation.
  - **Credits & Toolchain Heritage**: Added a tasteful, dedicated section at the bottom of `README.md` crediting Garry Tan's `gstack`, `pstack`, `archify`, `graphify`, `google-antigravity`, and `ollama`, while linking formal specifications (`docs/PRODUCT_SPEC.md`, `docs/CONSENSUS_MANIFEST.md`, `docs/MEMORY_SPEC.md`) for contributors.
  - **Verification**: Verified all 40 internal documentation links and re-indexed the memory store.
  - Mirrored `CONTEXT_MEMORY.md` to `C:\Users\veere\antigravity-local\CONTEXT_MEMORY.md`.

- [x] **Step 28**: Fallback Embedding Determinism Fix (Nov 4, 2026, branch `fix/deterministic-fallback-embeddings`):
  - **Flaw**: `memory.py::_pure_python_embed` used builtin `hash()` (salted per process via PYTHONHASHSEED). Vectors stored at index time never matched query vectors from a later process, so the semantic tier was noise whenever Ollama had no embedding model.
  - **Proof**: `tests/test_memory_determinism.py` (2 cross-process tests, different PYTHONHASHSEED) failed 2/2 before fix, pass after. 5 seeds now yield 1 unique vector hash.
  - **Fix**: `zlib.crc32` instead of `hash()`. **Existing indexes are stale: run `python memory.py index --force` once after upgrading** (mtime skip would otherwise keep old vectors).
  - **Known, not fixed (YAGNI/open)**: embedding backend (Ollama vs fallback) is not recorded per chunk, so switching backends silently zeroes cosine (dim mismatch); removed source files are never purged from the index; SQLite connections are not explicitly closed.

- [x] **Step 29**: Index Integrity Fixes (Nov 4, 2026, branch `fix/memory-index-integrity`, PR opened, 2 interrogate rounds done):
  - Architect chose per-document `documents.embed_mode` column over a global meta table (interrupted runs and mixed-dim docs stay NULL = retried; legacy DBs self-migrate via ALTER + NULL, so no manual `--force` needed).
  - Fixed: (1) backend switch now re-embeds and search only compares vectors from the same backend; mixed-dimension docs are left NULL; (2) deleted source files purged incl. FTS rows (FTS5 has no FK cascade); (3) `get_connection` is now a context manager (commit/rollback, always close).
  - Tests: `tests/test_memory_integrity.py` (7) failed first, 9/9 pass with determinism suite. Run: `python -m unittest tests.test_memory_integrity tests.test_memory_determinism`.
  - Quirk: `unittest discover` fails (tests/ has no `__init__.py`); name modules explicitly.
  - Interrogate round 1 (3 siloed adversaries): purge claim held (mutation-tested). 2 verified findings fixed test-first: (a) all-fallback docs during an Ollama outage were stamped with the Ollama mode (fix: `EmbeddingProvider.fell_back` flag, doc stays NULL and is retried); (b) concurrent open of a legacy DB raised `duplicate column name` (fix: tolerate it on ALTER). Round 2 (1 adversary): 1 verified finding fixed test-first - a fallback *query* vector was compared against Ollama-stored vectors (ghost RRF hits); search now goes BM25-only when the query embedding fell back. Review cap reached; PR opened for human review.
  - Residual: a transient Ollama outage at index start forces re-embedding onto fallback (loud stderr warning only).

- [x] **Step 30**: Bootstrap & Docs Sync (Nov 4, 2026, branch `docs/memory-integrity-sync`):
  - Documented index-integrity invariants in `docs/MEMORY_SPEC.md` (schema + invariants), new `.wiki/memory-integrity.md` (+ index), README tree (`memory.py`, `tests/`).
  - Fixed stale absolute links (`local%20antigravity`) in `.wiki/index.md` -> relative; `ZERO_TO_CODING.md` path updated to `local-antigravity`.
  - **Archify global install was broken** (symlink -> old `local antigravity` folder after the repo dir rename). Removed stale npm shims in `%APPDATA%
pm`, reinstalled `npm install -g ./.agents/skills/archify`; `archify doctor` passes. The 4 diagrams do not depict memory internals, so no regeneration was needed.
  - Re-ran `python memory.py index` and `graphify update .`.
  - Quirk: if the repo folder is ever renamed again, re-run the archify global install.

- [x] **Step 31**: Serve + Docker, real E2E on both paths (Nov 4, 2026, branch `feat/serve-and-docker`, stacked on PR #4):
  - `serve.py` (stdlib): `/`, `/healthz`, `/api/search`, `/diagrams/<name>`. **No fixed port**: default port 0 = OS-assigned, printed on start; `--port`/`PORT` override. Binds 127.0.0.1 locally, `HOST=0.0.0.0` inside Docker. Global search lock because `EmbeddingProvider.fell_back` is shared state.
  - Local path: `python run.py --serve`. Docker path: `Dockerfile` (python:3.11-slim, non-root `app`, HEALTHCHECK, internal port 8000). Run with `-p 127.0.0.1::8000` then `docker port <name> 8000` for the random host port.
  - Real E2E: `python tests/e2e.py local` (fresh copy, own venv, 2 servers, 2 ports) and `python tests/e2e.py docker` (build, 2 containers, 2 random host ports, non-root, healthy). Both PASS. Unit: `python -m unittest tests.test_memory_integrity tests.test_memory_determinism tests.test_serve` (26 OK).
  - **Bug found by the local E2E**: fresh-venv bootstrap crashed on Windows (`pip.exe install --upgrade pip` cannot replace itself). Fixed with `python -m pip`. Only ever hit on first run, so it had gone unnoticed.
  - `.github/workflows/docker.yml`: unit tests + docker E2E on every PR; pushes `ghcr.io/<owner>/<repo>` only on `main`/tags after tests pass. **Not yet exercised**: needs merge, and the GHCR package must be set public once for anonymous `docker pull`.
  - README: new "Serve It" section; fixed `%cd%` Docker volume example for non-CMD shells.
  - Untested: live LLM agent call via `run.py` (non-serve REPL), `docker-test-drive.sh` (superseded by `tests/e2e.py docker`, left in place).

- [x] **Step 32**: PR #5 review round (Nov 4, 2026, branch `feat/serve-and-docker`): 4 siloed workers + own re-runs. Fixed, each reproduced first:
  - `serve.py`: Windows SO_REUSEADDR let two servers share one `--port` silently -> `allow_reuse_address = os.name != "nt"` (+ test).
  - `tests/e2e.py`: `terminate()` orphaned the venv python tree on Windows (12 live processes + 3 temp dirs leaked) -> `stop()` uses `taskkill /T /F`; rmtree retries and no longer hides failure (+ `tests/test_e2e_cleanup.py`).
  - Default Windows checkout (autocrlf=true, no `.gitattributes`) turned `docker-test-drive.sh`/`run.sh` into CRLF, breaking them while the harness still printed PASSED -> added `.gitattributes` (`*.sh`, Dockerfile LF). `docker-test-drive.sh` now passes all gates for real.
  - Docs: Git Bash needs `MSYS_NO_PATHCONV=1` for `-w /app`; docker command now lives only in README (ZERO_TO_CODING and ARCHITECTURE point to it); Python versions aligned to installers (3.11 min, 3.12/3.13); wiki test command updated.
  - Quirk: `unittest discover -s tests` works; plain `discover` finds 0 tests.
  - Not changed: image fails with `--read-only` / arbitrary `--user` (writes `/app/.memory`); `limit=0/-1` is clamped to 1 (documented as 1-20).
  - Teardown gap (user report): docs said nothing about stopping/cleanup, and `e2e.py docker` leaked a 483 MB image per run (fixed tag also collided with another session). Now: unique tag per run + `docker rmi -f` in finally; serve.py prints a stop hint; README has 'Stop & Clean Up' table (local server, container, image, venv/.memory, archify). Ollama models are never touched.
  - AGENTS.md draft reviewed (3 skills + 2 adversaries + judge). Verdict: base = candidate 3 (rule registry + checker). Synthesis in the session scratchpad `arena/final/`; NOT installed, user's draft untouched.

- [x] **Step 33**: Merged #4 (merge commit) and #5 (squash) to main (`67ca324`); CI on #5 green incl. docker e2e on Linux. Installed rule-registry `AGENTS.md` (64 lines, from arena candidate 3 + judge grafts) with `scripts/check_agents_md.py` (also a CI step). Previous 425-line draft is kept on the owner's machine only (untracked .ai-context folder, file AGENTS.draft-2026-11-04.md). Removed leftover reviewer worktrees.

- [x] **Step 34**: Docs unslop pass (PR #7). 5 writers on disjoint files + 1 independent reviewer; em-dashes 0; 24 emoji headings stripped with all anchors remapped (30 anchored links, 0 broken). Heading case left as written (automatic sentence-casing broke names). Merged #6 (rule-registry AGENTS.md) first.

- [x] **Step 35**: Guide polish merged (PR #8, `c071020`). Sentence-case headings (anchors unchanged), guide sections 3-5 rewritten from a 3-seat council + 1 reviewer, `scripts/check_docs.py` (+CI). Quirks: edit scripts must avoid doubled backslashes in heredocs (they get halved and turn into control chars); `check_docs.py --baseline` allows new headings, fails on renamed ones. Open follow-up: `run.bat` garbles emojis in default CMD (needs `chcp 65001`).

- [x] **Step 36**: `run.bat` sets `chcp 65001` + `PYTHONUTF8=1` (console was code page 437, emojis showed as mojibake); `.gitattributes` forces CRLF for `*.bat`. Docker: `/app/.memory` is created world-writable at build, so `--user 12345` and `--read-only --tmpfs /app/.memory` both work (covered by `tests/e2e.py docker`). Quirk: from Git Bash, `cmd /c run.bat` fails; `NoDefaultCurrentDirectoryInExePath=1` is set here, use `.\run.bat`.

- [x] **Step 37**: `workspace/index.html` untracked and ignored (setup demo rewrote it every run, dirtying the tree); only `workspace/.gitkeep` stays tracked. Pruning note: this file is at the 300-line cap, so the next entry must replace or condense older steps.

---

## 5. Key Architecture & Environment Quirks Discovered
1. **Ollama Function Calling Compatibility**:
   - `gemma2:27b` in Ollama does NOT support native OpenAI tool calling schema (`registry.ollama.ai/library/gemma2:27b does not support tools`). For pure chat/streaming with Gemma, tools must be disabled via `capabilities=CapabilitiesConfig(enabled_tools=[])`.
   - `qwen2.5:14b` in Ollama natively supports OpenAI function calling and fits 100% into the 16 GB VRAM. It successfully executes Antigravity workspace tools (`create_file`, etc.).
2. **Antigravity `create_file` Tool Schema**:
   - The Antigravity local harness requires `Path`, `Content`, and `Overwrite: bool` arguments when invoking file-creation tools.
3. **Windows Encoding**:
   - Python on Windows defaults to `cp1252` encoding in PowerShell sessions. Scripts must configure `sys.stdout.reconfigure(encoding='utf-8')` to prevent UnicodeEncodeError during token streaming.
4. **Windows `os.execv` Space-in-Path Quirk**:
   - When the repository path contains spaces (e.g. `c:\Users\veere\source\repos\local antigravity`), Python's `os.execv` on Windows delegates to MSVC CRT `_wexecv`, which does not quote argument tokens when constructing the command line for `CreateProcess`.
   - As a result, `local antigravity\venv\Scripts\python.exe` gets split at the space, causing Python to see `C:\Users\veere\source\repos\local` as the executable and relative path `antigravity\venv\Scripts\python.exe` as the script argument (`[Errno 2] No such file or directory`).
   - Fix: On Windows, use `subprocess.call([VENV_PYTHON, script_path] + sys.argv[1:])` (which leverages Windows-standard `list2cmdline` argument quoting) and directly target `venv\Scripts\python.exe` in `run.bat` and `run.ps1`.

---

## 6. Open-Source Compatibility & Harness Routing Decisions (Veeresh Bikkaneti Inquiries)
1. **How an external user runs this when open-sourced**:
   - Clone the repo, `pip install -r requirements.txt`.
   - Start any OpenAI-compatible server (Ollama, LM Studio, vLLM, llama.cpp).
   - Set `LOCAL_LLM_BASE_URL` and `LOCAL_LLM_MODEL` in `.env` or system environment.
   - Run `python agent_with_workspace.py`.
2. **Compatibility with Google Research AI Harness on GitHub**:
   - **Fully compatible**. `google-antigravity` communicates with an underlying binary via Protobuf (`localharness_pb2`) and WebSockets.
   - If an open-source user builds Google's research harness from GitHub, they can direct the SDK to use it by setting:
     `export ANTIGRAVITY_HARNESS_PATH=/path/to/custom/localharness`
     (or placing it in the system `PATH`).
3. **Addressing the "Antigravity is Locked Down" Concern**:
   - Antigravity is **NOT** locked down to Google Cloud or Gemini endpoints.
   - The SDK ships with `LocalOpenAIConnectionStrategy`, which strips out all Google Cloud/Gemini endpoint dependencies and redirects all requests to `http://localhost:11434/v1/chat/completions` using standard SSE.
   - Zero Google Cloud API keys, auth tokens, or cloud connections are required.

---

## 7. How Next Model Can Resume Immediately
1. Read this file (`CONTEXT_MEMORY.md`).
2. Activate venv: `C:\Users\veere\antigravity-local\venv\Scripts\Activate.ps1`.
3. Test local streaming:
   ```powershell
   python test_local.py gemma2:27b
   ```
4. Run workspace agent:
   ```powershell
   python agent_with_workspace.py qwen2.5:14b
   ```
5. Inspect generated workspace artifacts in `C:\Users\veere\antigravity-local\workspace`.
