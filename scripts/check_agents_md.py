"""Checks R3, R5, R6 from AGENTS.md. Usage: python scripts/check_agents_md.py [repo_root]. Exit 1 on any failure."""
import re, sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
CAPS = {"AGENTS.md": 100, "CONTEXT_MEMORY.md": 300}  # R5, R3
errors = []

for name, cap in CAPS.items():
    p = root / name
    if not p.exists():
        errors.append(f"{name}: missing")
        continue
    text = p.read_text(encoding="utf-8")
    n = len(text.splitlines())
    if n > cap:
        errors.append(f"{name}: {n} lines, cap {cap}")
    if name == "AGENTS.md":  # R5: ASCII only covers emoji and em-dashes
        for i, line in enumerate(text.splitlines(), 1):
            bad = [c for c in line if ord(c) > 127]
            if bad:
                errors.append(f"{name}:{i}: non-ASCII {bad[:3]}")
    # R6: backticked repo paths must exist (bare names only checked in AGENTS.md; CONTEXT_MEMORY uses wiki-relative names)
    for tok in set(re.findall(r"`([^`\s]+)`", text)):
        if tok.startswith(("~", "<")) or tok.endswith("/") or "<" in tok or "..." in tok:
            continue
        if "/" not in tok and name != "AGENTS.md":
            continue
        if re.search(r"\.(py|md|yml|json|sh|bat|ps1)$", tok) and not (root / tok).exists():
            errors.append(f"{name}: referenced path missing: {tok}")

print("\n".join(errors).encode("ascii", "replace").decode() or "ok")
sys.exit(1 if errors else 0)
