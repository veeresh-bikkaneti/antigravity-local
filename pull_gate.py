"""Every model pull asks first. This module only decides; the caller pulls on "yes"."""
MIN_FREE_SHARE = 0.10
NON_COMMERCIAL = ("non-commercial", "noncommercial", "cc-by-nc", "research only")


def check_disk(plan):
    """(ok, free GB left after the pull). Exactly 10% of the disk left is fine."""
    after = float(plan.get("free_disk_gb") or 0) - float(plan.get("size_gb") or 0)
    return after >= MIN_FREE_SHARE * float(plan.get("disk_total_gb") or 0), after


def _repo_page(tag):
    name = tag.split(":")[0]
    for prefix in ("hf.co/", "huggingface.co/"):
        if name.startswith(prefix):
            return "https://huggingface.co/" + name[len(prefix):]
    return "https://ollama.com/library/" + name


SOURCE_TEXT = {"registry": "Ollama registry", "hugging face": "Hugging Face", "list": "our list", "estimate": "estimate"}


def size_line(size, source):
    """'14.0 GB (from Ollama registry)', or '~15.2 GB (estimate)' when the number is a guess."""
    if source == "estimate":
        return f"~{float(size):.1f} GB (estimate)"
    return f"{float(size):.1f} GB (from {SOURCE_TEXT.get(source, 'an unknown source')})"


def ask_pull(plan, interactive, input_fn=None, out=None):
    input_fn = input_fn or input  # looked up now, not at import, so a terminal or a test can swap it
    out = out or print
    if plan.get("gated"):
        out(f"{plan['tag']} is gated. Accept its terms on the repo page first: {_repo_page(plan['tag'])}")
        return "gated"
    ok, after = check_disk(plan)
    if not ok:
        total = float(plan.get("disk_total_gb") or 0)
        if total <= 0:
            out("Could not read the free disk space where Ollama keeps models, so nothing was downloaded.")
        else:
            out(f"Not enough disk: {after:.1f} GB would be left of {total:.0f} GB (need {MIN_FREE_SHARE:.0%}).")
        return "disk_refused"
    if not interactive:
        return "non_interactive"
    lic = plan.get("license")
    lic = str(lic) if lic else None
    flag = " (NON-COMMERCIAL, check before business use)" if lic and any(k in lic.lower() for k in NON_COMMERCIAL) else ""
    size = plan.get("size_gb")
    size_text = size_line(size, plan.get("size_source")) if size else "unknown (the disk check could not run)"
    disk_text = f"{after:.1f} GB" if size else "unknown"
    out(f"model: {plan['tag']}\nquant: {plan.get('quant') or 'unknown'}\nsize: {size_text}\n"
        f"license: {lic or 'unknown'}{flag}\nfree disk after: {disk_text}")
    try:
        answer = input_fn("Download? [y/N] ")
    except EOFError:
        return "no"
    return "yes" if answer.strip().lower() in ("y", "yes") else "no"
