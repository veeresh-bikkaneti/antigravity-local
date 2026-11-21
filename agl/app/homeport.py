"""Homeport slice-1 snapshot: live Ollama, GPU and saved settings combined into one JSON-safe dict.

All hardware/service/file facts arrive through `ports` (see agl.core.homeport_ports), so this
module imports only agl.core and does no I/O itself.
"""

from agl.core import homeport_settings, usage


def snapshot(ports) -> dict:
    """Build the Homeport snapshot: state, service flag, loaded model, VRAM split, context fill,
    GPU readings, merged settings and plain-words captions. The result is JSON-safe."""
    service_up = bool(ports.ollama.check_service())
    rows = ports.ollama.loaded_models()
    loaded = rows[0] if rows else None
    st = usage.state(service_up, loaded)
    vram = usage.vram_split((loaded or {}).get("size") or 0, (loaded or {}).get("size_vram") or 0)
    used_tokens = None if not loaded else loaded.get("used_tokens")
    context_fill = usage.context_fill(used_tokens, (loaded or {}).get("context_length"))
    gpu = ports.gpu.read_gpu()
    settings = homeport_settings.merge(ports.store.load())
    result = {
        "state": st,
        "service_up": service_up,
        "model": loaded,
        "vram": vram,
        "context_fill": context_fill,
        "gpu": gpu,
        "settings": settings,
    }
    result["captions"] = usage.captions(result)
    return result
