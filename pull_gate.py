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


def ask_pull(plan, interactive, input_fn=input, out=print):
    if plan.get("gated"):
        out(f"{plan['tag']} is gated. Accept its terms on the repo page first: {_repo_page(plan['tag'])}")
        return "gated"
    ok, after = check_disk(plan)
    if not ok:
        out(f"Not enough disk: {after:.1f} GB would be left of {float(plan.get('disk_total_gb') or 0):.0f} GB (need {MIN_FREE_SHARE:.0%}).")
        return "disk_refused"
    if not interactive:
        return "non_interactive"
    lic = plan.get("license")
    lic = str(lic) if lic else None
    flag = " (NON-COMMERCIAL, check before business use)" if lic and any(k in lic.lower() for k in NON_COMMERCIAL) else ""
    out(f"model: {plan['tag']}\nquant: {plan.get('quant') or 'unknown'}\nsize: {float(plan.get('size_gb') or 0):.1f} GB\n"
        f"license: {lic or 'unknown'}{flag}\nfree disk after: {after:.1f} GB")
    try:
        answer = input_fn("Download? [y/N] ")
    except EOFError:
        return "no"
    return "yes" if answer.strip().lower() in ("y", "yes") else "no"
