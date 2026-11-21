"""Every model pull asks first. This module only decides; the caller pulls on "yes".

the module lives at agl.core.pull_gate; this file only re-exports it.
"""
from agl.core.pull_gate import (  # noqa: F401
    MIN_FREE_SHARE,
    NON_COMMERCIAL,
    SOURCE_TEXT,
    _repo_page,
    ask_pull,
    check_disk,
    size_line,
)
