"""What a model can do, as short badges: tools, thinking, vision, embedding, image, video, audio, coding.

Two sources, one vocabulary. Ollama tells us for sure (`capabilities` from /api/show). Hugging Face only hints
(a chat template that mentions tools), so those badges carry a trailing "?" until a live probe passes on this PC.
`None` for badges means "we do not know" (an old Ollama sends no capabilities), which is never the same as "none".
"""
import re

OLLAMA_KNOWN = ("completion", "tools", "insert", "vision", "embedding", "thinking", "image", "audio", "decision", "speech")
_OLLAMA_BADGE = {"tools": "tools", "thinking": "thinking", "vision": "vision", "embedding": "embedding",
                 "image": "image", "audio": "audio", "speech": "audio"}
_HF_TAG_BADGE = {
    "image-text-to-text": "vision", "feature-extraction": "embedding",
    "text-to-image": "image", "image-to-image": "image",
    "text-to-video": "video", "image-to-video": "video",
    "automatic-speech-recognition": "audio", "text-to-speech": "audio",
}
_MEDIA_TAGS = {"text-to-image", "image-to-image", "text-to-video", "image-to-video",
               "automatic-speech-recognition", "text-to-speech"}
_EMBED_NAME = re.compile(r"embed|rerank|bge-|minilm|e5-", re.IGNORECASE)
_CODING_NAME = re.compile(r"coder|code|devstral|codestral", re.IGNORECASE)
_TOOLS_TEMPLATE = re.compile(r"\btools?\b|tool_call", re.IGNORECASE)
TEMPLATE_CAP = 4096  # only the head of a chat template is ever looked at


def ollama_badges(capabilities):
    """Badges from /api/show `capabilities`. Unknown values are ignored. None in, None out (we do not know)."""
    if capabilities is None:
        return None
    if isinstance(capabilities, str):
        return ()  # a bare string where a list belongs: nothing, no crash
    if not isinstance(capabilities, (list, tuple)):
        return None  # a dict or number is junk, so we do not know
    known = [c for c in capabilities if isinstance(c, str) and c in OLLAMA_KNOWN]
    if capabilities and not known:
        return None  # a non-empty list with no known word is junk, not "no tools"
    out = []
    for cap in known:
        badge = _OLLAMA_BADGE.get(cap)
        if badge and badge not in out:
            out.append(badge)
    return tuple(out)


def hf_badges(pipeline_tag, chat_template=None):
    """Badges from a Hugging Face repo. Template-based ones end in "?" because they are a guess."""
    out = []
    badge = _HF_TAG_BADGE.get(pipeline_tag) if isinstance(pipeline_tag, str) else None
    if badge:
        out.append(badge)
    template = (chat_template or "")[:TEMPLATE_CAP] if isinstance(chat_template, str) else ""
    if _TOOLS_TEMPLATE.search(template):
        out.append("tools?")
    if "<think>" in template:
        out.append("thinking?")
    return tuple(out)


def coding_badge(tag):
    return "coding" if _CODING_NAME.search(tag or "") else None


def kind_from_name(tag):
    return "embedding" if _EMBED_NAME.search(tag or "") else "chat"


def kind_from_ollama(capabilities):
    """'chat', 'embedding', 'media' or 'unknown' (no capabilities data)."""
    if capabilities is None or not isinstance(capabilities, (list, tuple)):
        return "unknown"
    caps = {c for c in capabilities if isinstance(c, str)}
    if "completion" in caps:
        return "chat"
    if "embedding" in caps:
        return "embedding"
    if caps & {"image", "audio", "speech"}:
        return "media"
    return "chat" if caps else "unknown"


def kind_from_hf(pipeline_tag):
    if not isinstance(pipeline_tag, str):
        return "chat"
    if pipeline_tag == "feature-extraction":
        return "embedding"
    if pipeline_tag in _MEDIA_TAGS:
        return "media"
    return "chat"


def resolve_kind(kind, tag):
    """An 'unknown' kind falls back to what the name suggests."""
    return kind_from_name(tag) if kind in (None, "unknown") else kind


def tools_level(badges):
    """2 confirmed tools, 1 a guess (tools?) or unknown, 0 known to lack tools."""
    if not isinstance(badges, (list, tuple)):
        return 1  # None or junk: unknown
    if "tools" in badges:
        return 2
    if "tools?" in badges:
        return 1
    return 0


def confirm_tools(badges):
    """After a probe passes on this PC, a guessed tools? badge becomes tools."""
    if not badges:
        return badges
    return tuple("tools" if b == "tools?" else b for b in dict.fromkeys(badges))


def format_badges(badges):
    if not isinstance(badges, (list, tuple)):
        return ""
    return ", ".join(b for b in badges if isinstance(b, str))


# Curated catalog: confirmed only where the catalog note already says native tool calling, a guess otherwise.
CATALOG_BADGES = {
    "devstral-small-2:24b": ("tools?", "coding"),
    "gpt-oss:20b": ("tools", "thinking?"),
    "qwen3.6:27b": ("tools", "thinking?"),
    "qwen3.8:27b": ("tools?", "thinking?"),
    "qwen3-coder:30b": ("tools?", "coding"),
    "laguna-xs.2:latest": ("tools?",),
    "hf.co/mradermacher/nanbeige4.1-3b-gguf:q4_k_m": ("tools?",),
}

# Media models Ollama can run on macOS (x/ namespace). (tag, badge, note, non_commercial)
MEDIA_MODELS = (
    ("x/z-image-turbo", "image", "text to image", False),
    ("x/flux2-klein", "image", "text to image (the 9B Klein is non-commercial)", True),
)


def catalog_badges(tag):
    return CATALOG_BADGES.get((tag or "").strip().lower())
