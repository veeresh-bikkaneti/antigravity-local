# Model Selection Hierarchy & Zero-Download Logic

## 1. Zero-Download Pre-Flight Guarantee
Before downloading any model, `run.py` performs a two-tier inventory pre-flight check:
1. REST API query to `http://localhost:11434/api/tags`.
2. CLI fallback via `ollama list`.

**Rule**: If ANY capable model is already present on disk (e.g. `qwen2.5:14b`), the runner selects the highest-scoring local model, updates `.env`, and skips the download.

## 2. Model Scoring Hierarchy
Models are scored on benchmarked autonomous agent performance:

1. **Nanbeige (4.1 / 4.2 / 4.3, 2-16B)**: Strong agentic reasoning and precise tool calling.
2. **Qwen 2.5 Coder (14B / 32B / 7B)**: Open coding model that fits in 16GB VRAM.
3. **DeepSeek-Coder-V2 / R1 (16B / 14B)**: Code synthesis and reasoning.
4. **Command R / R+ (32B)**: Native enterprise agent tool calling and structured output.
5. **Codestral (22B)**: Mistral code completion engine.
6. **Gemma 2 (27B / 9B)**: Google reasoning model (requires pure text streaming; no tool schemas).
7. **LLaMA 3.3 / 3.1 (70B / 8B)**: General reasoning model.

## 3. Parameter Scaling Formula
Final Score = `Base_Score(family) + min(param_count * 0.4, 25.0)`.

