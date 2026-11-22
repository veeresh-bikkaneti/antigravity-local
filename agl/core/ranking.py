"""Which installed or suggested model should drive a coding agent?

Pure functions: no network, no clock, no files. Feed in candidate dicts, get a
winner back. Higher rank_key wins, and the levels are compared strictly in order,
so a lower level can never rescue a candidate that lost on a higher one.
"""
import math
import re
from datetime import datetime, timezone

from agl.core import capabilities

_FIT = {"gpu": 2, "split": 1, "too big": 0}  # unknown fit (None) counts like split


def epoch(value):
    """ISO 8601 text to UTC seconds. Accepts Z, +00:00, -06:00; anything else is 0."""
    if not isinstance(value, str) or not value.strip():
        return 0
    text = value.strip()
    if text[-1] in "zZ":
        text = text[:-1] + "+00:00"
    try:
        when = datetime.fromisoformat(text)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when.timestamp()
    except (ValueError, OverflowError, OSError):
        return 0


def _num(value):
    """A real, finite number, else 0. NaN and inf would make the winner depend on input order."""
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    return value if ok else 0


SMALL_GB = 4.0  # under this a model is "small" and ranks below any "big" one that also fits


def size_class(c):
    """1 = big (4.0 GB or more, or size unknown), 0 = small (a known size under 4.0 GB). Unknown counts as big."""
    size = _num(c.get("size_gb"))  # 0 when missing or not a number
    return 0 if 0 < size < SMALL_GB else 1


def rank_key(c):
    """Tuple where HIGHER is better, in the spec order. Missing keys count as unknown or zero."""
    fit_name = c.get("fit")
    fit = _FIT.get(fit_name, 1) if isinstance(fit_name, str) else 1
    not_failed = 0 if c.get("ledger") == "fail" else 1
    tools = capabilities.tools_level(c.get("badges"))
    installed = 1 if c.get("installed") else 0
    passed = 1 if c.get("ledger") == "pass" else 0
    freshness = (epoch(c.get("last_modified")), _num(c.get("downloads")), _num(c.get("size_gb")))
    return (fit, not_failed, tools, size_class(c), installed, passed, freshness, _num(c.get("name_score")))


def agent_candidates(cands):
    """Only chat-capable models. Embedding and media never reach the ranking."""
    return [c for c in cands
            if capabilities.resolve_kind(c.get("kind"), c.get("tag") or "") == "chat"]


def best_for_agent(cands):
    """The best chat-capable candidate, or None. First in input order wins a full tie."""
    pool = agent_candidates(cands)
    return max(pool, key=rank_key) if pool else None


# Scoring helpers moved verbatim from run.py (Phase 6e, task 1a): from task 1b run.py imports
# these from here instead of defining its own copies.
FAMILIES = [
    (("embed", "rerank"), 5.0), (("qwen3", "devstral-small-2", "gpt-oss", "laguna"), 97.0), (("nanbeige",), 92.0), (("deepseek",), 90.0), (("qwen2.5",), 88.0),
    (("command-r",), 86.0), (("codestral",), 84.0), (("glm4", "glm-4"), 82.0), (("mistral-large", "devstral"), 80.0), (("gemma2",), 76.0),
    (("llama3.3", "llama3.1", "llama3.2", "llama3"), 74.0), (("phi4", "phi3"), 68.0), (("mistral",), 65.0),
]


def _raw_capability_score(model_name: str) -> float:
    name = str(model_name).lower().strip()
    score = next((sc for keys, sc in FAMILIES if any(k in name for k in keys)), 45.0)
    m = re.search(r"(\d+)(?:\.\d+)?b", name)
    score += min(float(m.group(1)), 72.0) * 0.3 if m else 4.0
    if "coder" in name or "code" in name: score += 8.0
    if any(k in name for k in ("agent", "tool", "search")): score += 8.0
    if "instruct" in name or "chat" in name: score += 4.0
    return score


def get_model_capability_score(name: str) -> float: return min(_raw_capability_score(name), 100.0)
def capability_rank_key(name: str) -> float: return _raw_capability_score(name)
def hardware_tier_model(vram: float, ram: float) -> str: return "qwen2.5-coder:14b" if (vram >= 15.0 or (vram >= 8.0 and ram >= 32.0)) else ("qwen2.5-coder:7b" if (vram >= 8.0 or ram >= 16.0) else "llama3.2:3b")
