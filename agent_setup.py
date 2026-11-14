"""One-step setup for better terminal coding agents on top of the local Ollama model. Standard library only.

`python run.py --agent pi|opencode|codex` lands here after run.py has picked the model. We install the agent
only if the user says yes, merge a provider block into the agent's own config without touching anything else,
and start it in the folder the user is working in.

Every collaborator (which, input, subprocess, home) is passed in and looked up at call time, so tests never
touch the real machine. Do not bind `input` or `subprocess.call` as default arguments: that freezes the real
one at import time and the mocks stop working.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

AGENTS = ("pi", "opencode", "codex")
PACKAGES = {"pi": "@earendil-works/pi-coding-agent", "opencode": "opencode-ai", "codex": "@openai/codex"}
NODE_DOWNLOAD = "https://nodejs.org/en/download"
PI_NODE_MIN = (22, 19)
BACKUP_SUFFIX = ".bak-antigravity-local"
CONTEXT_WINDOW = 65536
OPENCODE_SCHEMA = "https://opencode.ai/config.json"
# Letters, digits and . _ / - only, plus an optional :tag. Real tags such as hf.co/user/repo:Q4_K_M pass. Shell
# characters (& | ; < > ^ % quotes $) do not: on Windows the agents are .cmd files that run through cmd.exe.
MODEL_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*(:[A-Za-z0-9._-]+)?$")


class AgentSetupError(Exception):
    """Something the user has to fix. `code` is the process exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


@dataclass
class Result:
    command: list
    files: list = field(default_factory=list)
    changed: bool = False
    notes: list = field(default_factory=list)


def validate_model_tag(model):
    """Reject anything that could be read as a flag, split into arguments, or run by a shell."""
    if not isinstance(model, str) or not model.strip():
        raise AgentSetupError("No model name to configure.")
    if not MODEL_TAG_RE.match(model):
        raise AgentSetupError(f"'{model}' is not a model tag. Use letters, digits and . _ / - with an optional "
                              ":tag, and no leading '-'. Example: qwen3.6:27b")


def node_ok(version):
    """True for Node >= 22.19 (what pi needs). Accepts 'v26.13.0'."""
    m = re.match(r"v?(\d+)\.(\d+)", (version or "").strip())
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= PI_NODE_MIN


def _node_version():
    try:
        return subprocess.check_output(["node", "--version"], text=True, timeout=10).strip()
    except Exception:
        return ""


def ensure_agent(name, which=None, input_fn=None, call=None, node_version=None, out=print):
    """Return the agent's path. If it is missing, show the command and install only when the user types y."""
    which = which or shutil.which
    input_fn = input_fn or input
    call = call or subprocess.call
    node_version = node_version or _node_version

    found = which(name)
    if found:
        return found

    pkg = PACKAGES[name]
    out(f"       {name} is not installed. To install it yourself: npm install -g {pkg}")
    npm = which("npm")
    if not npm or not which("node"):
        out(f"       npm (Node.js) is needed first: {NODE_DOWNLOAD}")
        raise AgentSetupError(f"{name} is not installed and npm was not found.")
    if name == "pi" and not node_ok(node_version()):
        out(f"       pi needs Node 22.19 or newer (found {node_version() or 'none'}). Get it at {NODE_DOWNLOAD}")
        raise AgentSetupError("Node is too old for pi.")
    try:
        answer = input_fn("       Install it now with npm? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip().lower() not in ("y", "yes"):
        out("       Not installing. Run the command above yourself, then run this again.")
        raise AgentSetupError(f"{name} is not installed.")
    if call([npm, "install", "-g", pkg]) != 0:
        raise AgentSetupError(f"npm could not install {pkg}. Try the command above in a terminal to see why.")
    found = which(name)
    if not found:
        out(f"       Installed, but '{name}' is not on your PATH yet. Open a new terminal (npm's global bin folder "
            "must be on PATH), then run this again.")
        raise AgentSetupError(f"{name} was installed but is not on PATH.")
    return found


# ---------- config merging ----------

def _load(path):
    """(data, existing_text). A missing file is an empty object. Anything we cannot safely merge into is refused."""
    if not path.exists():
        return {}, None
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise AgentSetupError(
            f"{path} is not valid JSON ({e}). We did not change it. Fix the file (or move it aside) and run again.")
    if not isinstance(data, dict):
        raise AgentSetupError(f"{path} should hold a JSON object. We did not change it. Fix it and run again.")
    return data, text


def _obj(parent, key, path):
    """parent[key] as a dict, created if missing. A non-object there means a config we should not guess about."""
    child = parent.setdefault(key, {})
    if not isinstance(child, dict):
        raise AgentSetupError(f"{path}: '{key}' should be a JSON object. We did not change the file.")
    return child


def _pi_models(data, model, base_url, path):
    prov = _obj(_obj(data, "providers", path), "ollama", path)
    prov["baseUrl"] = base_url
    prov["api"] = "openai-completions"
    prov["apiKey"] = "ollama"
    compat = _obj(prov, "compat", path)
    compat["supportsDeveloperRole"] = False
    compat["supportsReasoningEffort"] = False
    models = prov.setdefault("models", [])
    if not isinstance(models, list):
        raise AgentSetupError(f"{path}: 'models' should be a JSON list. We did not change the file.")
    if not any(isinstance(m, dict) and m.get("id") == model for m in models):
        models.append({"id": model, "contextWindow": CONTEXT_WINDOW})


def _pi_settings(data, model, base_url, path):
    data["defaultProvider"] = "ollama"
    data["defaultModel"] = model


def _opencode(data, model, base_url, path):
    data.setdefault("$schema", OPENCODE_SCHEMA)
    prov = _obj(_obj(data, "provider", path), "ollama", path)
    prov["npm"] = "@ai-sdk/openai-compatible"
    prov.setdefault("name", "Ollama (local)")
    _obj(prov, "options", path)["baseURL"] = base_url
    _obj(prov, "models", path).setdefault(model, {"name": model})


def _targets(name, home):
    """(path, merge function) per file we own a block in. Codex has none."""
    if name == "pi":
        agent = home / ".pi" / "agent"
        return [(agent / "models.json", _pi_models), (agent / "settings.json", _pi_settings)]
    if name == "opencode":
        return [(home / ".config" / "opencode" / "opencode.json", _opencode)]
    return []


def _render(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_config(name, model, base_url, home=None):
    """Merge our Ollama block into the agent's config. Plans every file first, so a broken file stops us
    before anything is written. A file whose parsed content would not change is left exactly as it is."""
    validate_model_tag(model)
    home = Path(home) if home else Path.home()

    if name == "codex":
        notes = []
        if "11434" not in base_url:
            notes.append(f"codex --oss talks to Ollama on its default port (11434); {base_url} is not used by it.")
        return Result(command=["codex", "--oss", "-m", model], notes=notes)

    plans = []
    for path, merge in _targets(name, home):
        data, text = _load(path)
        before = json.loads(text) if text is not None else None
        merge(data, model, base_url, path)
        plans.append((path, text is not None, data != before, data))

    changed = False
    for path, existed, differs, data in plans:
        if not differs:
            continue
        backup = Path(str(path) + BACKUP_SUFFIX)
        if existed and not backup.exists():
            shutil.copy2(path, backup)
        _atomic_write(path, _render(data))
        changed = True
    command = ["pi"] if name == "pi" else ["opencode", "--model", f"ollama/{model}"]
    return Result(command=command, files=[p for p, *_ in plans], changed=changed)


def context_hint():
    return ("Heads up: coding agents want a 64k+ token context. Ollama's default is smaller on most PCs "
            "(4k below 24 GB of VRAM). Raise it in the Ollama app's settings, or start the server with "
            "OLLAMA_CONTEXT_LENGTH=65536. We do not change your Ollama settings.")


def _cmdline(argv):
    return subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)


def launch(name, model, workspace, call=None, which=None):
    """Start the agent as a child process in `workspace` and return its exit code."""
    call = call or subprocess.call
    which = which or shutil.which
    exe = which(name) or name
    argv = {"pi": [exe],
            "opencode": [exe, "--model", f"ollama/{model}"],
            "codex": [exe, "--oss", "-m", model]}[name]
    return call(argv, cwd=workspace)


def run(name, model, base_url, workspace, config_only=False, home=None, which=None, input_fn=None, call=None,
        node_version=None, out=print):
    """Install if the user agrees, write config, say what we did, then launch. Returns the exit code."""
    try:
        validate_model_tag(model)
        if not config_only:
            ensure_agent(name, which=which, input_fn=input_fn, call=call, node_version=node_version, out=out)
        result = write_config(name, model, base_url, home=home)
        out("")
        out(f"       Agent    : {name}")
        out(f"       Model    : {model}")
        out(f"       Endpoint : {base_url}")
        if result.files:
            out("       Config   : " + ", ".join(str(p) for p in result.files))
            out("       Your other settings were kept. If a config file already existed, a one-time backup "
                f"sits beside it, ending {BACKUP_SUFFIX}.")
        for note in result.notes:
            out(f"       Note     : {note}")
        out(f"       {context_hint()}")
        if config_only:
            out(f"       Config written. To start it: cd \"{workspace}\" && {_cmdline(result.command)}")
            return 0
        out(f"       Starting {name} in {workspace} ...\n")
        return launch(name, model, workspace, call=call, which=which)
    except AgentSetupError as e:
        out(f"\n[agent setup] {e}")
        return e.code
