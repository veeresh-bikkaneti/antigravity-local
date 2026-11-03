# Memory Architecture Specification: 3-Tier Zero-Token Memory Fabric
## Graphify (AST OKF) + LLMWiki (Karpathy Paradigm) + Embedded Hybrid SQLite Engine

> **Status**: APPROVED & IMPLEMENTED  
> **Philosophy**: 1-Command Plug-and-Play, 100% Local Air-Gapped, Zero External Daemons, Minimal Token Burn  
> **Authors**: Antigravity Autonomous Agent Architecture Council  

---

## 1. Executive Summary & Design Rationale

When running local autonomous coding agents (such as Qwen 2.5 14B or Gemma 2 27B via Ollama) and pairing them with cloud IDE models (Antigravity Gemini / Claude), maintaining persistent context across sessions without overwhelming model context windows is the single biggest engineering bottleneck.

A typical codebase contains hundreds of thousands of tokens. Ingesting raw files into prompts burns tokens at an unsustainable rate (e.g., 280,000 tokens per prompt), causing:
1. **Context Exhaustion**: Rapidly exceeding context windows (e.g. 32k or 128k tokens).
2. **"Needle-in-a-Haystack" Degradation**: Reasoning accuracy drops dramatically as prompt size increases.
3. **Severe Local Inference Latency**: Local models experience massive time-to-first-token (TTFT) slowdowns when processing 50k+ input tokens on consumer or workstation GPUs.

### The Architectural Question: RAG vs. OKF vs. Vector DB vs. LLMWiki

| Dimension | Standalone Vector DB (Milvus, Qdrant, Chroma) | Traditional Naive RAG (Vector-only) | OKF / Knowledge Graph (Graphify) | LLMWiki (Karpathy Paradigm) | **Our 3-Tier Fabric (Graphify + LLMWiki + SQLite Hybrid)** |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **External Dependencies** | Requires Docker, C++ binaries, or external daemon ports (6333, 8000, 19530). | Moderate to High (vector libraries, API keys). | **Zero** (local Python CLI, Tree-sitter AST parser). | **Zero** (pure Markdown repository files). | **ZERO** (built into Python standard library `sqlite3` + Markdown + local AST). |
| **Code Structure Accuracy** | Poor (treats code as generic unstructured prose chunks). | Poor (misses call graphs, inheritance, module boundaries). | **100% Deterministic** (extracts exact functions, calls, classes). | High (human/agent curated domain knowledge). | **Deterministic AST + Curated Domain Truth + Fuzzy Semantic Retrieval**. |
| **Exact Symbol Search (BM25)** | Weak (vector embeddings struggle with exact token hits like `get_hardware_profile`). | Missing or secondary. | Indirect (AST node lookup). | Fast (grep / markdown file reading). | **Built-in FTS5 BM25** with rank scoring. |
| **Semantic / Fuzzy Search** | Strong. | Strong. | Weak (relationship-based only). | Moderate (topic navigation). | **Dual-Engine**: Local Ollama embedding with fallback cosine similarity. |
| **Token Consumption** | High (dumps multi-chunk text snippets into prompt). | High (8,000–30,000 tokens per query). | **Zero tokens to build**; ~800 tokens to query (up to **128x reduction**). | **Ultra-Low** (curated 500–1,500 token atomic pages). | **Ultra-Low (<1,200 tokens loaded per targeted action)**. |
| **Plug & Play Ethos** | Breaks 1-command bootstrap. | Fragile setup. | Native CLI & rules. | Native Git files. | **100% 1-Command Plug & Play**. |

---

## 2. The 3-Tier Memory Fabric Architecture

Rather than relying on a heavy vector database that breaks the 1-command plug-and-play promise, this repository implements a unified 3-tier memory fabric:

```mermaid
flowchart TD
    subgraph UI_AGENT["Agent Query / Task Execution"]
        Q["User Task / Prompt / Symbol Search"]
    end

    subgraph TIER1["Tier 1: Deterministic Structural Graph (Graphify)"]
        G_DB[("graphify-out/graph.json<br/>4,192 Nodes | 8,674 Edges")]
        G_CMD["graphify query / path / explain"]
        Q -->|"Code structure, call-flow, imports"| G_CMD
        G_CMD --> G_DB
    end

    subgraph TIER2["Tier 2: High-Density Domain Wiki (.wiki/)"]
        W_DIR[".wiki/*.md<br/>Karpathy Paradigm Topic Pages"]
        W_CMD["python memory.py wiki [topic]"]
        Q -->|"Architecture, hardware specs, model rules"| W_CMD
        W_CMD --> W_DIR
    end

    subgraph TIER3["Tier 3: Embedded Hybrid Retrieval Engine (memory.py)"]
        MEM_DB[(".memory/index.sqlite<br/>SQLite FTS5 + Vector Store")]
        FTS["FTS5 Full-Text Index (BM25 Exact Matching)"]
        VEC["Semantic Vector Index (Ollama / Local Embeddings)"]
        RRF["Reciprocal Rank Fusion (RRF)"]
        
        Q -->|"Fuzzy concepts, past decisions, doc search"| MEM_DB
        MEM_DB --> FTS
        MEM_DB --> VEC
        FTS --> RRF
        VEC --> RRF
    end

    TIER1 -->|"Tight context (<1k tokens)"| CTX["Targeted Prompt Context"]
    TIER2 -->|"Atomic topic (<1.2k tokens)"| CTX
    TIER3 -->|"Fused Top-K Snippets (<1.5k tokens)"| CTX
    CTX --> LOCAL_LLM["Local LLM (Qwen 2.5 14B / Gemma 2 27B) / Cloud Model"]
```

---

## 3. Tier Deep-Dive Specifications

### Tier 1: Graphify (AST Code Knowledge Graph)
- **Location**: `graphify-out/graph.json` and `.agents/rules/graphify.md`
- **Purpose**: Answer structural code questions with zero hallucinations and zero token waste.
- **How it Works**: Tree-sitter parses the repository's Python, Bash, HTML, and Markdown files into an AST graph. Nodes represent files, functions, classes, and environment variables; edges represent imports, calls, and file containment.
- **Commands**:
  - `graphify query "<question>"`: Returns a tightly bounded subgraph.
  - `graphify path "<node_A>" "<node_B>"`: Returns exact call-chain or dependency path.
  - `graphify explain "<concept>"`: Explains community cluster connections.
  - `graphify update .`: Synchronizes the graph after local code changes at **zero API cost**.
- **Benchmark Measured**: 31.1x to 128.8x token reduction compared to full-context file reading.

### Tier 2: LLMWiki (Karpathy Concept Pages)
- **Location**: `.wiki/`
- **Purpose**: Maintain canonical, high-density, human- and LLM-curated Markdown files that serve as the project's single source of truth for conceptual knowledge.
- **Concept Anatomy**:
  - Each wiki file is atomic (500–1,500 tokens), structured with clear headings, bulleted invariants, and cross-references.
  - Models read an individual `.wiki/<topic>.md` file in a single tool call rather than trawling dozens of documentation pages.
- **Core Topics**:
  1. `index.md`: Master topic registry and cross-reference table.
  2. `architecture.md`: Local decoupled runtime, harness connection, and air-gapped guarantees.
  3. `hardware-matrix.md`: GPU VRAM offloading physics (RTX 5000 Ada 16GB + 128GB DDR5 RAM).
  4. `model-hierarchy.md`: Dynamic model capability scoring (Nanbeige > Qwen 2.5 > DeepSeek > Gemma 2) and zero-download logic.
  5. `tool-execution.md`: Antigravity SDK workspace tool schemas and safety policy enforcement.
  6. `token-optimization.md`: Token physics, benchmarking results, and memory switchboard guidance.

### Tier 3: Embedded Hybrid Memory Engine (`memory.py`)
- **Location**: `memory.py` and persistent store at `.memory/index.sqlite`
- **Engine Principles**:
  - **Zero External Dependencies**: Uses Python's standard library `sqlite3`, `re`, `json`, `math`, `urllib.request`. No `pip install` required for base functionality.
  - **FTS5 Full-Text Search (BM25)**: SQLite's native FTS5 extension tokenizes documents into trigrams/words, scoring exact matches via BM25 ranking.
  - **Dense Vector Embedding Engine**:
    - Queries local Ollama embedding API (`http://localhost:11434/api/embeddings`) using model `nomic-embed-text` (or `all-minilm`) if present.
    - If no embedding model is present in Ollama, automatically falls back to an internal pure-Python n-gram/TF-IDF term vectorizer with cosine similarity.
  - **Reciprocal Rank Fusion (RRF)**:
    Combines BM25 lexical rank with dense vector similarity rank using the standard information retrieval formula:
    $$RRF\_Score(d) = \frac{w_{lex}}{k + Rank_{BM25}(d)} + \frac{w_{sem}}{k + Rank_{vector}(d)}$$
    *(Default constants: $k = 60$, $w_{lex} = 0.5$, $w_{sem} = 0.5$)*.

---

## 4. SQLite Schema (`.memory/index.sqlite`)

The database is structured for durability, instant queries (<50ms), and zero-maintenance schema migrations:

```sql
-- Document Metadata Table
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,       -- 'wiki', 'doc', 'context', 'workspace'
    mtime REAL NOT NULL,
    chunk_count INTEGER NOT NULL,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Text Chunks Table
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding TEXT                -- JSON-encoded float vector (or NULL if pure lexical)
);

-- SQLite FTS5 Virtual Table for BM25 Search
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    doc_id UNINDEXED,
    chunk_index UNINDEXED,
    tokenize = 'porter unicode61'
);
```

---

## 5. CLI & Agent Integration Interface

`memory.py` provides an intuitive CLI and programmatic API:

```powershell
# 1. Index or re-index all memory (wiki, docs, context, code)
python memory.py index

# 2. Hybrid search across indexed memory
python memory.py search "how does hardware offloading work with 16GB VRAM"

# 3. View memory engine status and indexed chunk count
python memory.py status

# 4. Read canonical LLMWiki pages directly
python memory.py wiki architecture
python memory.py wiki hardware-matrix

# 5. Dual-sync: Update Graphify AST graph + SQLite memory store in one step
python memory.py sync
```

### Agent Integration:
In `code_agent.py`, interactive slash commands are exposed:
- `/memory <query>`: Executes a hybrid search and injects the top-K relevant chunks into the agent's immediate context.
- `/wiki [topic]`: Loads the requested wiki page directly without burning context on full repo files.
