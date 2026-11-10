# Google Antigravity Local: product specification
## Refined autonomous product specification (v1.0.0)

> **Governance**: Drafted with a swarm of agents and a council of expert roles. See the [consensus manifest](CONSENSUS_MANIFEST.md) for what that record does and does not verify.
> **Execution precedence**: Frozen core, then consensus manifest, then task plan, then user request.

---

## 1. Product vision and value

Google Antigravity Local pulls the official `google-antigravity` SDK off Google Cloud Gemini and points it at local open-weights models (Nanbeige, Qwen 2.5 Coder, DeepSeek, Codestral, Command R, Gemma 2) served by Ollama. Inference runs on your machine. Setup still downloads Python packages, Ollama, and the model, so you need internet for that part.

### Core value pillars
1. One command setup. `run.bat`, `run.ps1`, `run.sh`, or `python run.py` creates a virtualenv, checks hardware, starts Ollama, picks a model, and opens an agent REPL. Plan on a few minutes plus the model download. The 14B model is roughly 9 GB.
2. Zero-download scheduler. It scans the existing Ollama inventory first and skips multi-gigabyte downloads when a capable model is already on disk.
3. Three-tier memory. Graphify AST graphs, LLMWiki topic pages in `.wiki/`, and an embedded SQLite FTS5 plus vector engine (`memory.py`). It needs no Docker or database server. See the measured numbers in section 4.
4. Local tool execution. The agent creates files, edits code, and reads the workspace on local disk, scoped to the workspace folder (`policy.allow_all()`).

---

## 2. Module specifications

### Module 1: runtime engine (`run.py`, `agent_with_workspace.py`)
- Protocol: `LocalOpenAIConnectionStrategy` turns Antigravity SDK agent calls into OpenAI-compatible Server-Sent Events sent to `http://localhost:11434/v1/chat/completions`.
- Harness bridge: talks to the local binary harness over WebSockets and Protocol Buffers (`localharness_pb2`). Set `ANTIGRAVITY_HARNESS_PATH` to use a custom binary.
- Host boundary: no telemetry, no Google Cloud API keys, no credential prompts during inference.

### Module 2: hardware-aware model selection
- Hardware profiler: reads dedicated GPU VRAM (`nvidia-smi`, or unified memory on Apple Silicon) and system RAM. If RAM is unknown, it reports 0 and the smallest model wins.
- Tiers, as coded in `run.py` for a machine with no models installed:
  - Workstation: VRAM of 15 GB or more, or VRAM of 8 GB or more with 32 GB RAM or more. Pulls `qwen2.5-coder:14b`.
  - Mid-tier: VRAM of 8 GB or more, or RAM of 16 GB or more. Pulls `qwen2.5-coder:7b`.
  - Compact: anything smaller. Pulls `llama3.2:3b`.
- Inventory scoring, used when models are already installed. `get_model_capability_score` adds a family base score, a size bonus, and keyword bonuses, then caps the total at 100:
  - Family base: Nanbeige 92, DeepSeek 90, Qwen 2.5 88, Command R 86, Codestral 84, GLM-4 82, Mistral Large or Devstral 80, Gemma 2 76, LLaMA 3.x 74, Phi 68, other Mistral 65, anything else 45.
  - Size bonus: parameter count in billions (capped at 72) times 0.3. No size in the name adds 4.
  - Keyword bonus: +8 for `coder` or `code`, +8 for `agent`, `tool`, or `search`, +4 for `instruct` or `chat`.
  - Computed examples: `nanbeige4.1:3b` 92.9, `qwen2.5:14b` 92.2, `qwen2.5:3b` 88.9, `llama3.3:70b` 95.0, `codestral:22b` 98.6, `qwen2.5-coder:7b` 98.1, `gemma2:9b` 78.7, `llama3.1:8b` 76.4. `qwen2.5-coder:14b`, `qwen2.5-coder:32b`, and `deepseek-coder-v2:16b` all hit the 100 cap.
  - The family base alone does not decide the winner. Size and keyword bonuses move the ranking, and the cap produces ties at the top.

### Module 3: three-tier memory (`memory.py`, `.wiki/`, `graphify-out/`)
- Tier 1, Graphify AST: code structure, call hierarchies, and community clusters in `graphify-out/graph.json`. The committed graph has 8,547 nodes, 13,383 edges, and 591 communities. Graphify is not wired into the runtime agent path. Only `python memory.py sync` calls `graphify update .`, and only when the `graphify` command is installed.
- Tier 2, LLMWiki: curated Markdown topic pages in `.wiki/*.md`.
- Tier 3, SQLite hybrid engine: `.memory/index.sqlite` with SQLite FTS5 (BM25) plus cosine vector similarity, fused with Reciprocal Rank Fusion:
  $$RRF(d) = \frac{0.5}{60 + \text{Rank}_{BM25}(d)} + \frac{0.5}{60 + \text{Rank}_{vector}(d)}$$
  Embeddings come from Ollama (`nomic-embed-text`) when it is available, and from a pure-Python TF-IDF vectorizer otherwise.

### Module 4: tool execution and security policy
- Tool calling schema: OpenAI function-calling format with capitalized arguments (`write_to_file`: `TargetFile`, `CodeContent`, `Overwrite=true`).
- Policy: `policy.allow_all()` allows headless file operations inside `./workspace` and rejects path traversal outside it.

### Module 5: coding agent shell (`code_agent.py`)
- Interactive REPL with streamed output and UTF-8 console handling on Windows. The prompt reads `CodeAgent [You] >`.
- Slash commands:
  - `/memory <query>`: hybrid memory search.
  - `/wiki [topic]`: show a wiki page.
  - `/files`: list the workspace.
  - `/clear`: reset the conversation with a fresh agent session.
  - `/help`: usage guide.
- Context injection: `--with-memory` prepends the top 2 memory excerpts, each clamped to 1,200 characters, so a local model does not drown in context.

### Module 6: memory web app (`serve.py`)
- `python run.py --serve` or the Docker image starts a small standard-library web server with a search page, `GET /api/search`, `GET /healthz`, and the Archify diagrams under `/diagrams/`.
- It has no authentication. Locally it binds to `127.0.0.1` on a free port. The Docker image sets `HOST=0.0.0.0`, so publish its port to `127.0.0.1` only (`-p 127.0.0.1::8000`) unless you want other machines to reach it.
- It indexes the repository's memory when it starts, so the first start takes longer than later ones.

### Module 7: project site and zero-to-coding game (`site/`)
- The GitHub Pages site is built with Vite and published from `site/dist`. The front page walks the seven setup steps beside a Three.js drawing of the machine, with the Archify diagrams.
- The game is a static page at `site/public/game/index.html`, served at `/game/`. It plays the nine setup steps as a side-scroller (launcher, Ollama pull, model pull, serve, endpoint, Agent, Agent calls Ollama, workspace write, Memory + Editor), collecting each system's tool into a pocket, and ends with Hello World in the IDE. It is documentation: it runs no Ollama and writes no files.
- Publishing rule: Vite copies `site/public/` verbatim into `site/dist`. A page placed directly under `site/` is not published.

---

## 3. Engineering and design review notes

### Engineering review
- Blast radius: the agent writes inside `./workspace`. The scripts need no root or admin rights.
- Boring technology: standard library Python (`sqlite3`, `re`, `urllib`) with no external daemons, so baseline operation is Docker-free.
- Reversibility: configuration lives in `.env`, and `python memory.py index` rebuilds the memory database.

### Design review
- Cognitive load: one entry command (`run.bat` or `run.ps1`).
- Feedback loops: memory lookups return quickly, and LLM output streams as tokens arrive.
- Safe defaults: the zero-download check avoids surprise multi-gigabyte downloads on metered connections.

### Visual style
- CLI palette: Unicode box drawing and a few emoji, with high contrast.
- Diagrams: standalone HTML files built with Archify (`docs/diagrams/*.html`), with dark and light themes, live motion tracing, and SVG or WebM export.

---

## 4. Quality notes and known limits
- Tests: `python3 -m unittest discover -s tests` runs 96 tests, 3 skipped (verified 2026-11-06 on main). The demo and one-shot tasks verify the workspace write with `task_report` and warn instead of claiming success when the agent writes nothing.
- Docker: `docker-test-drive.sh` prints results but does not assert on them, and CI does not run it. CI runs `python tests/e2e.py docker` instead. Earlier records of "7 gates passed" came from a manual run and are not a CI guarantee.
- Memory benchmark: one manual run on a single laptop compared naive full-repo ingestion with memory retrieval over 5 alternating runs. The median was 1,877.4 ms against 8.10 ms. See `CONTEXT_MEMORY.md` for the raw figures. We do not claim a general speedup beyond that machine.
- Adversarial testing: a manual pass probed malformed FTS5 queries, vector dimension mismatches, and 50,000-character queries, and found no unhandled exceptions. That is not a proof of security.
- Privacy: inference is local. Setup downloads packages, Ollama, and the model.
