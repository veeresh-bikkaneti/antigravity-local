"""Where this tool keeps its own small files (the fail ledger, the Hugging Face cache) on the user's machine.

One place, one override: ANTIGRAVITY_LOCAL_HOME wins, else a hidden folder in the home directory. Callers pass
`home=` or `env=` so tests never touch the real one. The folder is not created here; writers make it on first use.
"""
import os
from pathlib import Path


def data_dir(home=None, env=None):
    env = os.environ if env is None else env
    custom = (env.get("ANTIGRAVITY_LOCAL_HOME") or "").strip()
    if custom:
        return Path(custom)
    return Path(home or os.path.expanduser("~")) / ".antigravity-local"
