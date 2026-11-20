"""Which installed or suggested model should drive a coding agent?

moved, shim until Phase 6: the module now lives at agl.core.ranking; this file only re-exports it.
"""
from agl.core.ranking import (  # noqa: F401
    SMALL_GB,
    _num,
    agent_candidates,
    best_for_agent,
    epoch,
    rank_key,
    size_class,
)
