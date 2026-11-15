# Model Selection Hierarchy & Zero-Download Logic

## 1. Zero-Download Pre-Flight Guarantee
Before downloading any model, `run.py` performs a two-tier inventory pre-flight check:
1. REST API query to `http://localhost:11434/api/tags`.
2. CLI fallback via `ollama list`.

**Rule**: If ANY capable model is already present on disk (e.g. `qwen2.5:14b`), the runner reuses the highest-ranked local model, updates `.env`, and skips the download. On a real terminal (stdin and stdout both terminals, no `--yes`) it first shows a short menu: Enter keeps the pick, Ctrl+C cancels and downloads nothing, and a model you download is saved to `.env` as the pick for the next run. `--yes`, piped input and CI skip the menu and never download: with nothing installed they exit 1 and print the `ollama pull` command. Every pull on a terminal asks `Download? [y/N]` first, and the fit uses free VRAM and RAM.

## 2. Model Scoring Hierarchy
Models are ranked by family base score, highest first (the numbers are in `run.py`, `_raw_capability_score`):

1. **2026 families (97)**: qwen3 (including qwen3-coder), devstral-small-2, gpt-oss, laguna.
2. **Nanbeige (92)**: Strong agentic reasoning and precise tool calling.
3. **DeepSeek-Coder-V2 / R1 (90)**: Code synthesis and reasoning.
4. **Qwen 2.5 and Qwen 2.5 Coder (88)**: Open coding model that fits in 16GB VRAM.
5. **Command R / R+ (86)**: Native enterprise agent tool calling and structured output.
6. **Codestral (84)**: Mistral code completion engine.
7. **GLM-4 (82)**, then **Mistral Large / Devstral (80)**.
8. **Gemma 2 (76)**: Google reasoning model (requires pure text streaming; no tool schemas).
9. **LLaMA 3.x (74)**, **Phi (68)**, other **Mistral (65)**, anything else (45).
10. **Embedding and reranker tags (5)**: names containing `embed` or `rerank` are checked first, so they never rank as chat models.

## 3. Parameter Scaling Formula
Rank score = `Base_Score(family) + min(param_count_in_billions, 72) * 0.3` plus keyword bonuses: +8 for `coder` or `code`, +8 for `agent`, `tool` or `search`, +4 for `instruct` or `chat`. A name with no size adds 4 instead of the size term. `run.capability_rank_key` ranks on this raw number. `get_model_capability_score` caps it at 100, for display only.
