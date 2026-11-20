"""What a model can do, as short badges: tools, thinking, vision, embedding, image, video, audio, coding.

moved, shim until Phase 6: the module now lives at agl.core.capabilities; this file only re-exports it.
"""
from agl.core.capabilities import (  # noqa: F401
    CATALOG_BADGES,
    MEDIA_MODELS,
    OLLAMA_KNOWN,
    TEMPLATE_CAP,
    _CODING_NAME,
    _EMBED_NAME,
    _HF_TAG_BADGE,
    _MEDIA_TAGS,
    _OLLAMA_BADGE,
    _TOOLS_TEMPLATE,
    catalog_badges,
    coding_badge,
    confirm_tools,
    format_badges,
    hf_badges,
    kind_from_hf,
    kind_from_name,
    kind_from_ollama,
    ollama_badges,
    resolve_kind,
    tools_level,
)
