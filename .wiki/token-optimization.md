# Token Optimization & Memory Fabric Physics

## 1. Context Economics Problem
Ingesting an entire codebase into an LLM prompt burns between 50,000 and 300,000 tokens per interaction.
On local models (e.g. Qwen 2.5 14B), this causes:
- GPU memory saturation for KV cache.
- TTFT (Time-To-First-Token) delays of 20–60 seconds.
- Context window truncation and reasoning hallucinations.

## 2. Benchmark Token Reduction
| Method | Tokens per Query | Reduction Factor |
| :--- | :--- | :--- |
| Naive Full Repo Reading | ~279,466 tokens | 1.0x (Baseline) |
| Traditional Unfiltered RAG | ~25,000 tokens | ~11.1x |
| Graphify AST Knowledge Graph | ~2,170 tokens | 128.8x |
| LLMWiki Topic Reading | ~850 tokens | 328.7x |
| Hybrid Memory Engine (memory.py) | ~1,200 tokens | 232.8x |

## 3. Retrieval Strategy Rules
1. **Structural Code Questions** (e.g., "Where is function X called?"):
   Use `graphify query "<question>"` or `graphify path "<A>" "<B>"`.
2. **System Design & Invariants** (e.g., "What is the hardware profile?"):
   Use `python memory.py wiki <topic>`.
3. **Fuzzy Concepts, History, & Decisions** (e.g., "Why did we switch from LiteRT to Ollama?"):
   Use `python memory.py search "<query>"`.

