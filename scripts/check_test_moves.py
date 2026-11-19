"""R13 guard for refactors: versus BASE_REF, every removed or changed line under tests/ must be an
import line or a patch()/patch.object() target line. Added lines are free.
Usage: python scripts/check_test_moves.py BASE_REF. Exit 1 listing the offending lines.
"""
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORT = re.compile(r"^\s*(import\s|from\s+\S+\s+import\b)")


def main():
    if len(sys.argv) != 2:
        print("usage: python scripts/check_test_moves.py BASE_REF")
        sys.exit(2)
    proc = subprocess.run(["git", "diff", "-U0", "--no-color", sys.argv[1], "--", "tests"],
                          capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    if proc.returncode != 0:
        print(proc.stderr.strip() or f"git diff versus {sys.argv[1]} failed")
        sys.exit(2)

    current, checked, offenders = "tests", 0, []
    for line in proc.stdout.splitlines():
        if line.startswith("diff --git "):
            current = line.split(" b/", 1)[-1]
            continue
        if not line.startswith("-") or line.startswith("---"):
            continue
        removed = line[1:]
        if not removed.strip():  # blank removed lines carry no assertion
            continue
        checked += 1
        if IMPORT.match(removed) or "patch(" in removed or "patch.object(" in removed:
            continue
        offenders.append(f"{current}: {removed}")

    if offenders:
        print("\n".join(offenders))
        sys.exit(1)
    print(f"test moves ok ({checked} removed lines checked)")
    sys.exit(0)


if __name__ == "__main__":
    main()
