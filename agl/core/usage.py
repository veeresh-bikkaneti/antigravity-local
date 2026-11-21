"""Pure presentation math for Homeport: VRAM split, context fill, state and captions.

No I/O and no platform imports: everything here is a plain function of its arguments.
"""

GEN = "GEN"  # reserved for slice 15b (pass-through while an answer is being written); never returned yet


def vram_split(size, size_vram) -> dict:
    """{"gpu_pct": int, "spills": bool}: the share of the model resident on the GPU.
    A non-positive size means nothing is loaded: 0 percent, no spill."""
    if size <= 0:
        return {"gpu_pct": 0, "spills": False}
    return {"gpu_pct": min(100, round(100 * size_vram / size)), "spills": size_vram < size}


def context_fill(used_tokens, context_length) -> int:
    """Percent of the context window in use, clamped to 0-100; None when context_length
    is missing or not positive."""
    if context_length is None or context_length <= 0:
        return None
    return max(0, min(100, round(100 * (used_tokens or 0) / context_length)))


def state(service_up, loaded) -> str:
    """One of STOPPED / UNLOADED / LOADING / IDLE for the service and the first loaded model."""
    if not service_up:
        return "STOPPED"
    if not loaded:
        return "UNLOADED"
    if loaded.get("size_vram") == 0 and (loaded.get("size") or 0) > 0:
        # INFERRED state - Ollama lists the model with size_vram 0 while weights are still moving into VRAM
        return "LOADING"
    return "IDLE"


def captions(snapshot) -> list:
    """Plain-words sentences for a novice, one per fact, for the snapshot's state.
    No digits appear in any caption, so nothing can be read as GB or percent."""
    st = snapshot.get("state")
    if st == "STOPPED":
        return ["The local model service is not reachable right now."]
    if st == "UNLOADED":
        return ["The service is up, but no model is loaded yet."]
    if st == "LOADING":
        return ["The model is moving into your graphics card right now."]
    if (snapshot.get("vram") or {}).get("spills"):
        return ["Part of the model spills into system memory, so answers are slower."]
    return ["The model fits on your graphics card."]
