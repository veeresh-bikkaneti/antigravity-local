"""Docs checks: anchored links resolve, no em dashes, no emoji in headings.
Usage: python scripts/check_docs.py [--root DIR] [--baseline GIT_REF]
With --baseline, every heading must keep the same anchor as in that ref, so edits are case-only.
Exit 1 on any failure."""
import argparse, glob, os, re, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=".")
ap.add_argument("--baseline")
args = ap.parse_args()
root = args.root
FILES = ["README.md", "ZERO_TO_CODING.md"] + sorted(
    os.path.relpath(p, root).replace("\\", "/") for p in glob.glob(os.path.join(root, "docs", "*.md")) + glob.glob(os.path.join(root, ".wiki", "*.md")))
errors = []

def read(rel):
    return open(os.path.join(root, rel), encoding="utf-8").read().replace("\r\n", "\n")

def prose(t):
    return re.sub(r"```.*?```", "", t, flags=re.S)

def slug_list(t):
    seen, out = {}, []
    for line in prose(t).splitlines():
        if re.match(r"#{1,6} ", line):
            s = re.sub(r"[^\w\- ]", "", re.sub(r"^#+ ", "", line).lower()).replace(" ", "-")
            n = seen.get(s, 0); seen[s] = n + 1
            out.append(s if n == 0 else f"{s}-{n}")
    return out

for rel in FILES:
    if not os.path.exists(os.path.join(root, rel)):
        continue
    t = read(rel)
    if "—" in t:
        errors.append(f"{rel}: contains an em dash")
    for line in prose(t).splitlines():
        if re.match(r"#{1,6} ", line) and re.search(r"[^\x00-\x7F]", line):
            errors.append(f"{rel}: non-ASCII in heading: {line.encode('ascii', 'replace').decode()}")
    for tgt, anc in re.findall(r"\]\(([^)#\s]*)#([^)\s]+)\)", prose(t)):
        if tgt.startswith("http"):
            continue
        dest = rel if tgt == "" else os.path.normpath(os.path.join(os.path.dirname(rel), tgt)).replace("\\", "/")
        if not os.path.exists(os.path.join(root, dest)):
            errors.append(f"{rel}: link target missing: {tgt}")
        elif anc not in slug_list(read(dest)):
            errors.append(f"{rel}: dead anchor #{anc} in {dest}")
    if args.baseline:
        old = subprocess.run(["git", "-C", root, "show", f"{args.baseline}:{rel}"], capture_output=True, text=True, encoding="utf-8").stdout
        if slug_list(old.replace("\r\n", "\n")) != slug_list(t):
            errors.append(f"{rel}: a heading anchor changed versus {args.baseline}")

print("\n".join(errors) or "docs ok")
sys.exit(1 if errors else 0)
