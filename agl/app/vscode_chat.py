"""Offer, once and only on a yes, to merge the VS Code Chat model entry into the user's files.

Nothing is written without a yes. Every message goes through `out`.
"""

import json
from pathlib import Path

from agl.core import vscode_models as vm


def _yes(input_fn, prompt):
    try:
        answer = input_fn(prompt)
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def _loaded(result):
    return isinstance(result, tuple) and len(result) == 2 and result[1] == "loaded"


def _paste(user_dirs, entry, out):
    out("       VS Code's user folder was not found. Paste this into chatLanguageModels.json "
        "in one of these folders:")
    for _, d in user_dirs:
        out(f"       {d}")
    out(json.dumps(vm.merge_models([], entry), indent=2))


def _write(files, path, merge, empty, paste, out):
    try:
        status = files.apply(path, merge, empty)
    except (OSError, ValueError) as e:
        out(f"       Not changed: {path} ({e}). Add this yourself:")
        out(json.dumps(paste, indent=2))
        return
    if status == "written":
        out(f"       Updated: {path} (an existing file was backed up first).")
    else:
        out(f"       Already up to date: {path}")


def _offer_endpoint(files, base_url, workspace, input_fn, out):
    path = Path(workspace) / ".vscode" / "settings.json"
    question = f"       Point VS Code Chat at your Ollama address? Writes ollama.endpoint to {path}. [y/N] "
    if not _yes(input_fn, question):
        return
    _write(files, path, lambda data: vm.merge_settings(data, base_url), {},
           vm.merge_settings({}, base_url), out)


def offer(result, model, base_url, workspace, *, user_dirs, tools_of, files, input_fn, out):
    """Ask once after the stage-4 banner. A yes merges the entry into each VS Code user folder found."""
    if not _loaded(result):
        return
    if not _yes(input_fn, "       " + vm.QUESTION):
        return
    entry = vm.model_entry(model, base_url, result[0], tools_of(base_url, model))
    found = [d for _, d in user_dirs if files.is_dir(d)]
    if not found:
        _paste(user_dirs, entry, out)
    for d in found:
        _write(files, d / "chatLanguageModels.json", lambda data: vm.merge_models(data, entry), [],
               vm.merge_models([], entry), out)
    if not vm.is_default_endpoint(base_url):
        _offer_endpoint(files, base_url, workspace, input_fn, out)
