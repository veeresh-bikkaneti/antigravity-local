"""Window fit, pure core: the largest context window this GPU can hold on top of the model's weights.

Standard library only. No I/O. The caller passes in free graphics memory, the weight size and the
/api/show model_info dict. KV cache only: the compute graph has no closed form, so it is not counted.
"""

import re

from agl.core.menu import FIT_HEADROOM

GIB = 2 ** 30
RUNGS = (8192, 16384, 32768, 65536)  # windows we offer, smallest first
WRITE_CAP = 64000  # Ollama's docs want at least 64000 for coding tools; we never write more
BYTES_PER_VALUE = {"f16": 2.0, "q8_0": 1.0625, "q4_0": 0.5625}  # llama.cpp block sizes per cached value


def _count(value):
    """A positive int, or the sum of a per-layer list of them. None for anything else."""
    if isinstance(value, list):
        parts = [_count(v) for v in value]
        return sum(parts) if parts and None not in parts else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def kv_bytes_per_token(model_info, kv_type=None):
    """Bytes of KV cache one token needs, from GGUF keys in model_info, or None when the shape is missing.
    tokens x layers x kv heads x (key length + value length) x bytes per value."""
    if not isinstance(model_info, dict):
        return None
    arch = model_info.get("general.architecture")
    if not isinstance(arch, str) or not arch:
        return None

    def key(name):
        return model_info.get(f"{arch}.{name}")

    layers, heads = _count(key("block_count")), _count(key("attention.head_count"))
    kv_heads = key("attention.head_count_kv")
    per_layer = _count(kv_heads) if isinstance(kv_heads, list) else None
    kv_heads = None if isinstance(kv_heads, list) else _count(kv_heads)
    width = _count(key("embedding_length"))
    fallback = width // heads if width and heads else None
    k_len = _count(key("attention.key_length")) or fallback
    v_len = _count(key("attention.value_length")) or fallback
    per_value = BYTES_PER_VALUE.get((kv_type or "f16").strip().lower())
    if not (layers and k_len and v_len and per_value) or not (per_layer or kv_heads):
        return None
    heads_total = per_layer if per_layer else layers * kv_heads
    return heads_total * (k_len + v_len) * per_value


def room_gib(free_gib, weight_bytes, loaded_vram_bytes=0):
    """GiB left for the cache: free memory, plus this model's own share when it is already loaded,
    minus the weights x FIT_HEADROOM. None when either reading is missing."""
    if not isinstance(free_gib, (int, float)) or isinstance(free_gib, bool):
        return None
    if not isinstance(weight_bytes, (int, float)) or isinstance(weight_bytes, bool) or weight_bytes <= 0:
        return None
    loaded = loaded_vram_bytes if isinstance(loaded_vram_bytes, (int, float)) and loaded_vram_bytes > 0 else 0
    return free_gib + (loaded - weight_bytes * FIT_HEADROOM) / GIB


def target_window(room, per_token, trained=None):
    """The window to aim for: the largest rung whose cache fits in `room` GiB and is at most `trained`,
    then capped at WRITE_CAP. 0 when not even the smallest rung fits; None when a reading is missing."""
    if room is None or per_token is None:
        return None
    for rung in reversed(RUNGS):
        if trained and rung > trained:
            continue
        if rung * per_token <= room * GIB:
            return min(rung, WRITE_CAP)
    return 0


def wants_copy(tokens, target, trained=None):
    """True when a bigger copy would help: a target was read, the model can go higher, and the window
    running now is under the target."""
    if not target or not isinstance(tokens, int):
        return False
    if trained and tokens >= trained:
        return False
    return tokens < target


def copy_name(tag, tokens):
    """The copy's tag: the window in thousands, e.g. qwen2.5:14b-ctx16k. A tag that is already a copy
    keeps one suffix: qwen2.5:14b-ctx8k becomes qwen2.5:14b-ctx16k."""
    return f"{re.sub(r'-ctx[0-9]+k$', '', tag)}-ctx{tokens // 1000}k"


def article(tokens):
    """'an' for numbers said with a vowel first (8,192, 11,000, 18,000), else 'a'."""
    lead = f"{tokens:,}".split(",")[0]
    return "an" if lead.startswith("8") or lead in ("11", "18") else "a"
