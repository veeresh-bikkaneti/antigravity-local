# Hardware Profile & Offloading Physics

## 1. Host Hardware Baseline
- **GPU**: NVIDIA RTX 5000 Ada Generation Laptop GPU (16,376 MiB / 16 GB dedicated GDDR6 VRAM).
- **CPU**: 13th Gen Intel Core i9-13950HX (24 cores / 32 threads).
- **RAM**: 128 GB DDR5 System Memory.
- **Driver / CUDA**: Driver 596.72 | CUDA 13.2.

## 2. Offloading Mechanics
- **LiteRT Limitation**: `litert-lm` requires >=24 GB VRAM for models >16 GB, failing on 16 GB laptop cards.
- **Ollama Layer Splitting**: Ollama dynamically splits transformer layers across VRAM and System RAM.
  - `qwen2.5:14b` (9.0 GB): 100% fits into 16 GB VRAM. Zero CPU offload, maximum token generation throughput (~45 tok/s). Native OpenAI tool calling supported.
  - `gemma2:27b` (15 GB): 79% GPU layers, 21% CPU RAM offload. Ideal for reasoning and text generation; tool calling must be disabled.

## 3. Dynamic Hardware Detection (`run.py`)
- Evaluates dedicated VRAM via `nvidia-smi` or Apple Silicon unified memory.
- Categorizes host into:
  - **Workstation (16GB+ VRAM & 32-128GB RAM)**: Models 14B to 32B.
  - **Mid-Tier (8-12GB VRAM & 16-32GB RAM)**: Models 7B to 14B.
  - **Entry (<=6GB VRAM or CPU)**: Models 3B to 8B quantized.

