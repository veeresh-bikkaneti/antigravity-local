Before:

After:

How:

**Layer touched:** (shell, ui, app, core, platform, site - list each one the diff touches)

**Baseline delta:** per-file-ignores entries before: N, after: N (may not grow; `python scripts/check_arch.py`)

**Mockup:** n/a: no visible change (any UI or site change needs a mockup linked and approved before code)

**Gates:**
- python -m unittest discover -s tests  (count + result)
- python scripts/check_docs.py
- python scripts/check_agents_md.py
- python scripts/check_commit_trailers.py origin/main..HEAD
- python scripts/check_arch.py --report-only

Serves:
