# LLMWiki: Master Knowledge Index & Registry

> **Format**: Karpathy-style canonical topic pages for token-optimized LLM and human comprehension.  
> **Rule**: When seeking conceptual knowledge, read the specific `.wiki/<topic>.md` file first before reading entire source trees.

---

## Topic Registry

| Topic File | Scope & Invariants | Token Size |
| :--- | :--- | :--- |
| [`architecture.md`](architecture.md) | Decoupled local runtime, OpenAI-compatible proxy, WebSocket harness. | ~850 tokens |
| [`hardware-matrix.md`](hardware-matrix.md) | VRAM/RAM hardware offload, GPU detection, RTX 5000 Ada profile. | ~920 tokens |
| [`model-hierarchy.md`](model-hierarchy.md) | Nanbeige, Qwen 2.5, DeepSeek scoring hierarchy, zero-download pre-flight logic. | ~1,100 tokens |
| [`tool-execution.md`](tool-execution.md) | Antigravity tool calling schema (`create_file`), safety policies, workspace boundaries. | ~800 tokens |
| [`token-optimization.md`](token-optimization.md) | 3-Tier Memory Fabric, Graphify AST benchmarks (31x–128x), RRF retrieval formula. | ~950 tokens |
| [`memory-integrity.md`](memory-integrity.md) | Index invariants (stable vectors, per-doc backend, purge, closed connections). | ~250 tokens |
| [`consensus-governance.md`](consensus-governance.md) | Frozen Core invariants, Council deliberation pass rule, Advisor loop. | ~750 tokens |

---

## How Agents Navigate this Wiki
1. Run `python memory.py wiki <topic>` to read a topic into context.
2. In the `code_agent.py` interactive shell, type `/wiki <topic>` or `/memory <query>`.
3. To update or add topics, write Markdown in `.wiki/<topic>.md` and run `python memory.py index`.

