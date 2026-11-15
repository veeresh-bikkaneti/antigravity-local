"""Pick the largest GGUF quant that fits the memory that is free right now."""
from model_wizard import QUANT_RE

HEADROOM = 1.2
# File sizes are decimal GB (bytes / 1e9), the way Hugging Face and Ollama print them. Free memory is in GiB, so the
# comparison errs a little on the safe side.
SPLIT_RAM_SHARE = 0.7
# (prefix, bits per weight), first match wins.
BPW = (("IQ4_XS", 4.25), ("BF16", 16), ("F16", 16), ("F32", 32), ("IQ1", 1.7), ("IQ2", 2.4),
       ("IQ3", 3.3), ("IQ4", 4.25), ("Q8", 8.5), ("Q6", 6.6), ("Q5", 5.5), ("Q4", 4.5),
       ("Q3", 3.5), ("Q2", 2.7), ("Q1", 1.7))
BELOW_Q3 = ("Q1", "Q2", "IQ1", "IQ2")
SKIP = ("mmproj", "imatrix")


def quant_of(filename):
    found = QUANT_RE.findall(filename or "")
    return found[-1].upper() if found else None


def _bpw(quant):
    return next((b for p, b in BPW if quant.startswith(p)), None)


def _group(files):
    """{quant: size_bytes or None}; split parts are summed, any unsized part makes the quant unsized.
    A repeated file name (same quant in two folders) is counted once."""
    groups, seen = {}, set()
    for f in files or []:
        name = f.get("name") or ""
        q = quant_of(name)
        if not q or _bpw(q) is None or any(s in name.lower() for s in SKIP) or not name.lower().endswith(".gguf"):
            continue
        base = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if base in seen:  # same file name in two folders is a copy, not another split part
            continue
        seen.add(base)
        size, prev = f.get("size"), groups.get(q, 0)
        if not isinstance(size, (int, float)) or size <= 0:
            size = None
        groups[q] = None if size is None or prev is None else prev + size
    return groups


def pick_quant(files, free_vram, free_ram, wanted=None):
    groups = _group(files)
    sized = [(q, s) for q, s in sorted(groups.items()) if s]
    params = sized[0][1] * 8 / _bpw(sized[0][0]) if sized else None  # weights implied by one real file
    cands = []
    for q, s in groups.items():
        est = not s
        if est:
            if params is None:
                continue
            s = params * _bpw(q) / 8
        cands.append({"quant": q, "size_gb": s / 1e9, "estimated": est})
    split_room = free_vram + SPLIT_RAM_SHARE * free_ram

    def judge(c):
        need = c["size_gb"] * HEADROOM
        if need <= free_vram:
            return dict(c, fit="gpu", why=f"fits {free_vram:g} GB free VRAM")
        if need <= split_room:
            return dict(c, fit="split", why=f"runs, part on CPU (slow): needs {need:.1f} GB, VRAM {free_vram:g} GB + RAM")
        return dict(c, fit="too big", why=f"needs {need:.1f} GB, only {split_room:.1f} GB usable")

    if wanted:
        return next((judge(c) for c in cands if c["quant"] == wanted.upper()), None)
    judged = [judge(c) for c in cands if not c["quant"].startswith(BELOW_Q3)]
    for fit in ("gpu", "split"):
        hits = [j for j in judged if j["fit"] == fit]
        if hits:
            return max(hits, key=lambda j: j["size_gb"])
    return None
