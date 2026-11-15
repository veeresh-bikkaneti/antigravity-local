"""Which installed or suggested model should drive a coding agent?

Pure functions: no network, no clock, no files. Feed in candidate dicts, get a
winner back. Higher rank_key wins, and the levels are compared strictly in order,
so a lower level can never rescue a candidate that lost on a higher one.
"""
from datetime import datetime, timezone

import capabilities

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
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def rank_key(c):
    """Tuple where HIGHER is better, in the spec order. Missing keys count as unknown or zero."""
    fit = _FIT.get(c.get("fit"), 1)
    not_failed = 0 if c.get("ledger") == "fail" else 1
    tools = capabilities.tools_level(c.get("badges"))
    installed = 1 if c.get("installed") else 0
    passed = 1 if c.get("ledger") == "pass" else 0
    freshness = (epoch(c.get("last_modified")), _num(c.get("downloads")), _num(c.get("size_gb")))
    return (fit, not_failed, tools, installed, passed, freshness, _num(c.get("name_score")))


def agent_candidates(cands):
    """Only chat-capable models. Embedding and media never reach the ranking."""
    return [c for c in cands
            if capabilities.resolve_kind(c.get("kind"), c.get("tag") or "") == "chat"]


def best_for_agent(cands):
    """The best chat-capable candidate, or None. First in input order wins a full tie."""
    pool = agent_candidates(cands)
    return max(pool, key=rank_key) if pool else None
