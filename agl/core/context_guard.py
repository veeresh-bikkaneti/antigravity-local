"""Context window guard, pure core: which context window is real, and which band it falls in.

Standard library only. No I/O, no env reads, no imports from the platform, app or ui layers.
The caller passes in the loaded-model rows, the raw env value and the graphics memory.
"""

import math

# Ollama's documented default context lengths, chosen by graphics memory.
DEFAULT_CONTEXT_SMALL = 4096  # Ollama's documented default under 24 GiB of graphics memory.
DEFAULT_CONTEXT_MEDIUM = 32768  # Ollama's documented default from 24 GiB, below 48 GiB.
DEFAULT_CONTEXT_LARGE = 262144  # Ollama's documented default from 48 GiB of graphics memory up.
VRAM_MEDIUM_FROM_GIB = 24  # Graphics memory (GiB) where the default steps up to medium.
VRAM_LARGE_FROM_GIB = 48  # Graphics memory (GiB) where the default steps up to large.

# Band edges in tokens: red below AMBER_FROM, amber below GREEN_FROM, green from there up.
AMBER_FROM = 16384
GREEN_FROM = 65536

_LATEST = ":latest"


def _canonical_name(name):
    """'x' and 'x:latest' name the same model; any other tag stays as it is. None if unusable."""
    if not isinstance(name, str) or not name:
        return None
    if name.endswith(_LATEST):
        name = name[: -len(_LATEST)]
    return name or None


def _is_window(value):
    """A context length is a positive int. Bools, strings and floats are not."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _loaded_window(loaded_rows, model):
    """Context length of the first loaded row for `model`, or None."""
    wanted = _canonical_name(model)
    if not isinstance(loaded_rows, list) or wanted is None:
        return None
    for row in loaded_rows:
        if not isinstance(row, dict):
            continue
        if _canonical_name(row.get("name")) == wanted and _is_window(row.get("context_length")):
            return row["context_length"]
    return None


def _env_window(env_value):
    """A plain ASCII positive integer in the env value, or None."""
    if not isinstance(env_value, str):
        return None
    text = env_value.strip()
    if not (text.isascii() and text.isdigit()):
        return None
    value = int(text)
    return value if value > 0 else None


def _gib_number(vram_gib):
    """A finite int or float GiB figure, or None for anything else (bools included)."""
    if isinstance(vram_gib, bool) or not isinstance(vram_gib, (int, float)):
        return None
    return vram_gib if math.isfinite(vram_gib) else None


def _default_window(vram_gib):
    """Ollama's documented default for this much graphics memory. Junk counts as under 24 GiB."""
    gib = _gib_number(vram_gib)
    if gib is None or gib < VRAM_MEDIUM_FROM_GIB:
        return DEFAULT_CONTEXT_SMALL
    if gib < VRAM_LARGE_FROM_GIB:
        return DEFAULT_CONTEXT_MEDIUM
    return DEFAULT_CONTEXT_LARGE


def real_window(loaded_rows, model, env_value, vram_gib):
    """Return (tokens, source). Source is "loaded", "env" or "default", tried in that order."""
    tokens = _loaded_window(loaded_rows, model)
    if tokens is not None:
        return tokens, "loaded"
    tokens = _env_window(env_value)
    if tokens is not None:
        return tokens, "env"
    return _default_window(vram_gib), "default"


def band(tokens):
    """Band for a context window: "red", "amber" or "green"."""
    if tokens < AMBER_FROM:
        return "red"
    if tokens < GREEN_FROM:
        return "amber"
    return "green"
