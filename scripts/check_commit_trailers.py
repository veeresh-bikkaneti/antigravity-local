"""Fail if any commit message in a range has an AI co-author trailer or a "Generated with <AI tool>" line.
Usage: python scripts/check_commit_trailers.py [range]   (default: origin/main..HEAD). Exit 1 naming each bad commit.
The names to block live in .githooks/ai-vendor-patterns.txt, the same file the commit-msg hook reads."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN_FILE = ROOT / ".githooks" / "ai-vendor-patterns.txt"


def vendor_patterns():
    lines = [ln.strip() for ln in PATTERN_FILE.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def bad_lines(message, patterns=None):
    """Lines of a commit message that name an AI tool in a Co-Authored-By trailer or a Generated-with line.
    Lines starting with # are git comments and are ignored."""
    patterns = vendor_patterns() if patterns is None else patterns
    if not patterns:
        return []
    # Whole words only ("Raider" is not "aider"), and "generated with" only at the start of a line
    # (after optional non-letters, so the robot-emoji form still matches). Keep in step with .githooks/commit-msg.
    word = rf"(?<![A-Za-z0-9_])({'|'.join(patterns)})(?![A-Za-z0-9_])"
    rule = re.compile(rf"^\s*co-authored-by:.*{word}|^\W*generated with\W.*{word}", re.IGNORECASE)
    return [ln for ln in message.splitlines() if not ln.lstrip().startswith("#") and rule.search(ln)]


def git(repo, *args):
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def main(argv, repo=ROOT):
    rng = argv[0] if argv else "origin/main..HEAD"
    failures = []
    for sha in git(repo, "rev-list", rng).split():
        for line in bad_lines(git(repo, "log", "-1", "--format=%B", sha)):
            failures.append(f"{sha[:7]} {git(repo, 'log', '-1', '--format=%s', sha).strip()!r}: {line.strip()}")
    for f in failures:
        print("AI trailer in commit:", f)
    if failures:
        print("Reword those commits (new commits on top do not help: the old message stays in the range).")
        return 1
    print(f"commit trailers ok ({rng})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
