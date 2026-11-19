"""Arch guardrails: ruff boundary rules, optional import-linter, and the baseline ratchet.

Usage: python scripts/check_arch.py [--report-only]. --report-only prints everything and exits 0.
Exit 2: a tool is missing (then it prints pip install -r requirements-dev.txt and never passes silently).
Exit 1: ruff or lint-imports reports violations, or the baseline grew versus origin/main.
"""
import argparse, configparser, re, shutil, subprocess, sys, tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIP = "pip install -r requirements-dev.txt"
FINDING = re.compile(r"^\S.*:\d+:\d+:")  # one concise ruff diagnostic per line


def show(proc):
    for part in (proc.stdout, proc.stderr):
        if part:
            print(part.rstrip("\n"))


def find_ruff():
    """ruff on PATH, else `python -m ruff`; exit 2 with the pip line when neither runs."""
    exe = shutil.which("ruff")
    if exe:
        return [exe]
    if subprocess.run([sys.executable, "-m", "ruff", "--version"],
                      capture_output=True, text=True, cwd=ROOT).returncode == 0:
        return [sys.executable, "-m", "ruff"]
    print(PIP)
    sys.exit(2)


def run_ruff(ruff):
    # --extend-exclude=DIR/**: untracked local scratch dirs, absent from a clean CI checkout.
    # Joined with "=" on purpose: as two tokens ruff drops the pattern. Not --exclude, which
    # replaces the config exclude list and re-opens tests/. The /** suffix is required too.
    argv = ruff + ["check", "--output-format", "concise", ".",
                   "--extend-exclude=v1*-work/**", "--extend-exclude=scan-craft-anything/**"]
    proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    show(proc)
    failed = proc.returncode != 0
    n = sum(1 for line in (proc.stdout or "").splitlines() if FINDING.match(line))
    print("ruff: all checks passed" if not failed else f"ruff: {n} problems")
    return failed


def run_importlinter():
    exe = shutil.which("lint-imports")
    if not exe:
        print(PIP)
        sys.exit(2)
    proc = subprocess.run([exe], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    show(proc)
    return proc.returncode != 0


def count_ruff(text, name):
    """Sum of per-file-ignores entries, or None when the file will not parse."""
    try:
        table = tomllib.loads(text).get("lint", {}).get("per-file-ignores", {})
    except Exception as exc:
        print(f"ratchet: cannot parse {name}: {exc}")
        return None
    return sum(len(v) for v in table.values() if isinstance(v, list))


def count_imports(text, name):
    """Sum of ignore_imports lines across every contract section."""
    cp = configparser.ConfigParser()
    try:
        cp.read_string(text)
    except configparser.Error as exc:
        print(f"ratchet: cannot parse {name}: {exc}")
        return None
    return sum(len([ln for ln in cp.get(sect, "ignore_imports", fallback="").splitlines() if ln.strip()])
               for sect in cp.sections())


def git_show(name):
    """Text of `name` at origin/main, or None when git fails: the file is new here."""
    proc = subprocess.run(["git", "show", f"origin/main:{name}"], capture_output=True,
                          text=True, encoding="utf-8", cwd=ROOT)
    return proc.stdout if proc.returncode == 0 else None


def ratchet():
    specs = [("ruff.toml", count_ruff)]
    if (ROOT / ".importlinter").exists():
        specs.append((".importlinter", count_imports))
    failed = False
    for name, count in specs:
        path = ROOT / name
        if not path.exists():
            print(f"ratchet: {name} missing in the working tree")
            failed = True
            continue
        now = count(path.read_text(encoding="utf-8"), name)
        base_text = git_show(name)
        if base_text is None:
            print(f"ratchet: {name} is new here ({now} entries); baseline starts at this PR")
            continue
        base = count(base_text, name)
        if now is None or base is None:
            failed = True
        elif now > base:
            print(f"baseline grew: {name} {base} -> {now} entries")
            failed = True
        else:
            print(f"ratchet: {name} {base} -> {now} entries")
    return failed


def main():
    ap = argparse.ArgumentParser(description="Arch guardrails: ruff, optional import-linter, baseline ratchet.")
    ap.add_argument("--report-only", action="store_true", help="print everything, always exit 0")
    args = ap.parse_args()

    failed = run_ruff(find_ruff())
    if (ROOT / ".importlinter").exists():  # contract file is optional until a later phase
        failed = run_importlinter() or failed
    failed = ratchet() or failed

    if failed:
        print("arch problems")
        sys.exit(0 if args.report_only else 1)
    print("arch ok")
    sys.exit(0)


if __name__ == "__main__":
    main()
