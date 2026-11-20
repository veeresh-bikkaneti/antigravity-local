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

from agl.platform import config

AGENTS = ("pi", "opencode", "codex", "claude")
PACKAGES = {"pi": "@earendil-works/pi-coding-agent", "opencode": "opencode-ai", "codex": "@openai/codex"}
CONTINUE_PROMPT = ("Read HANDOFF.md and AGENTS.md, then continue the task. Check git state before editing. "
                   "Update HANDOFF.md before you stop. "
                   "Project memory: this project keeps a local index of its code, docs and wiki pages. "
                   "Before you guess, search it: python memory.py search \"<words>\" gives ranked hits. "
                   "For a topic page, run python memory.py wiki <topic>. If results look stale, run python memory.py index.")
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

    if name == "claude":
        return _ensure_claude(which, input_fn, call, out)

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


def _claude_install_argv():
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-Command", "irm https://claude.ai/install.ps1 | iex"]
    return ["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"]


def _ensure_claude(which, input_fn, call, out):
    shown = ("irm https://claude.ai/install.ps1 | iex" if sys.platform == "win32"
             else "curl -fsSL https://claude.ai/install.sh | bash")
    out(f"       claude is not installed. To install it yourself (Anthropic's official script): {shown}")
    try:
        answer = input_fn("       Install it now with that script? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip().lower() not in ("y", "yes"):
        out("       Not installing. Run the command above yourself, then run this again.")
        raise AgentSetupError("claude is not installed.")
    if call(_claude_install_argv()) != 0:
        raise AgentSetupError("The Claude Code install script failed. Run the command above in a terminal to see why.")
    found = which("claude")
    if not found:
        out("       Installed, but 'claude' is not on your PATH yet. Open a new terminal, then run this again.")
        raise AgentSetupError("claude was installed but is not on PATH.")
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
        return [(agent / "models.json", _pi_models)]  # never settings.json: pi's own default is the user's
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


def agent_command(name, model, exe=None, prompt=None):
    """The one argv for each agent, used by the printed hint, write_config's result and launch.
    `prompt` is the agent's first message (--continue-local); every agent takes it on its command line."""
    exe = exe or name
    argv = {"pi": [exe, "--provider", "ollama", "--model", model],
            "opencode": [exe, "--model", f"ollama/{model}"],
            "codex": [exe, "--oss", "-m", model],
            "claude": [exe, "--model", model]}[name]
    if prompt:
        argv += ["--prompt", prompt] if name == "opencode" else [prompt]
    return argv


def write_config(name, model, base_url, home=None):
    """Merge our Ollama block into the agent's config. Plans every file first, so a broken file stops us
    before anything is written. A file whose parsed content would not change is left exactly as it is."""
    validate_model_tag(model)
    home = Path(home) if home else Path.home()

    if name == "claude":
        return Result(command=agent_command("claude", model))
    if name == "codex":
        notes = []
        if "11434" not in base_url:
            notes.append(f"codex --oss talks to Ollama on its default port (11434); {base_url} is not used by it.")
        return Result(command=agent_command("codex", model), notes=notes)

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
    return Result(command=agent_command(name, model), files=[p for p, *_ in plans], changed=changed)


def context_hint():
    return ("Heads up: coding agents want a 64k+ token context. Ollama's default is smaller on most PCs "
            "(4k below 24 GB of VRAM). Raise it in the Ollama app's settings, or start the server with "
            "OLLAMA_CONTEXT_LENGTH=65536. We do not change your Ollama settings.")


def _cmdline(argv):
    return subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)


def _same_folder(a, b):
    """True when two paths are the same folder: resolved, and case-insensitive where the OS is (Windows)."""
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def resolve_workspace(arg, cwd, project_dir, out=None):
    """The folder the agent works in, and one printed line that says which.

    --workspace wins. With no flag it is the folder the command was run from, except inside this repo's own
    folder (run.sh and run.bat always cd there first): then it is <repo>/workspace, the same folder the SDK shell
    uses, so a new agent cannot start out editing antigravity-local itself.
    """
    out = out or print
    if arg:
        path = Path(arg).expanduser()
        path = (path if path.is_absolute() else Path(cwd) / path).resolve()
        if not path.exists():
            raise AgentSetupError(f"The --workspace folder was not found: {path}. We never create your project "
                                  "folder for you. Check the path, or create it first.")
        if not path.is_dir():
            raise AgentSetupError(f"The --workspace path is a file, not a folder: {path}")
        out(f"       Folder   : {path} (from --workspace)")
        return str(path)
    here = Path(cwd).resolve()
    if _same_folder(here, project_dir):
        path = Path(project_dir).resolve() / "workspace"
        path.mkdir(exist_ok=True)
        out(f"       Folder   : {path} (you ran this inside antigravity-local, so the agent works in its "
            "workspace/ folder and not on this repo's own files. To use your own project, add "
            "--workspace <path to your project>)")
        return str(path)
    out(f"       Folder   : {here} (the folder you ran this from)")
    return str(here)


# ---------- Claude Code: environment for ONE child process, never written anywhere ----------

LOCAL_CONFIG_NAME = ".claude-local"
ROUTING_VARS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")
COPY_MARKER = ".antigravity-local-copied"
DROP_SETTINGS_KEYS = ("env", "model", "modelSettings", "apiKeyHelper")
MODEL_ALIASES = {"default", "best", "sonnet", "opus", "haiku", "opusplan", "sonnet[1m]", "opus[1m]"}
INHERITED_AUTH_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "CLAUDE_CODE_OAUTH_SCOPES")
MACHINE_ENV_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
MANAGED_SETTINGS = r"C:\Program Files\ClaudeCode\managed-settings.json"
CLAUDE_BANNER = ("This session uses your local model. Plain `claude`, VS Code and Claude Desktop still use your "
                 "subscription. Uninstall: delete ~/.claude-local.")


def claude_base_url(base_url):
    """LOCAL_LLM_BASE_URL minus a trailing slash and /v1: Claude Code wants the server root."""
    url = (base_url or config.OLLAMA_BASE_URL).strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url.rstrip("/") or config.OLLAMA_BASE_URL


def claude_context(environ):
    """(tokens, warning or None). The window Ollama really runs with is what Claude Code must plan for."""
    raw = (environ.get("OLLAMA_CONTEXT_LENGTH") or "").strip()
    if raw.isdigit() and int(raw) > 0:
        n = int(raw)
        return n, (None if n >= CONTEXT_WINDOW else
                   f"OLLAMA_CONTEXT_LENGTH is {n}, below the 64k (65536) coding agents want.")
    return CONTEXT_WINDOW, ("OLLAMA_CONTEXT_LENGTH is not set in this terminal. Ollama's default window is 4096, "
                            "so start the Ollama server with OLLAMA_CONTEXT_LENGTH=65536 (we assume 65536 here; if "
                            "the server runs smaller, Claude Code will overrun it).")


def claude_child_env(model, base_url, home=None, environ=None):
    """A COPY of the environment with everything Claude Code needs to talk to Ollama. Never applied to os.environ."""
    home = Path(home) if home else Path.home()
    env = dict(os.environ if environ is None else environ)
    tokens, _ = claude_context(env)
    # Anything else that can pick a different login, model, endpoint or cloud would leak through the inherited
    # environment (a subscription token would be sent to the local server). Drop it for this child only.
    for key in [k for k in env if k.startswith("ANTHROPIC_") or k in INHERITED_AUTH_VARS]:
        del env[key]
    env.update({
        "CLAUDE_CONFIG_DIR": str((home / LOCAL_CONFIG_NAME).resolve()),
        "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST": "1",
        "ANTHROPIC_BASE_URL": claude_base_url(base_url),
        "ANTHROPIC_AUTH_TOKEN": "ollama",
        "ANTHROPIC_API_KEY": "",
        "CLAUDE_CODE_USE_BEDROCK": "",
        "CLAUDE_CODE_USE_VERTEX": "",
        "CLAUDE_CODE_USE_FOUNDRY": "",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "CLAUDE_CODE_SUBAGENT_MODEL": model,
        "CLAUDE_CODE_MAX_CONTEXT_TOKENS": str(tokens),
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    })
    return env


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def claude_routing_warnings(home=None, environ=None):
    """Where a routing variable is already set. Names and places only, never values. Read-only."""
    home = Path(home) if home else Path.home()
    environ = os.environ if environ is None else environ
    found = [f"{v} is set in this terminal's environment" for v in ROUTING_VARS if environ.get(v)]
    settings = home / ".claude" / "settings.json"
    env_block = _read_json(settings).get("env")
    if isinstance(env_block, dict):
        found += [f"{v} is set in the env block of {settings}" for v in ROUTING_VARS if v in env_block]
    if not found:
        return []
    return found + ["That routes (or bills) every normal Claude Code session, and the VS Code extension, which "
                    "shares that file and inherits Windows environment variables. We did not edit anything. Run "
                    "`python run.py --agent claude --doctor` to see exactly what to remove."]


def copy_user_settings(home=None, out=None):
    """Copy (never link) a safe slice of ~/.claude into ~/.claude-local, once. Reads ~/.claude, writes only the copy."""
    out = out or print
    home = Path(home) if home else Path.home()
    src, dst = home / ".claude", home / LOCAL_CONFIG_NAME
    if (dst / COPY_MARKER).exists():
        out(f"       Settings : already copied into {dst} on an earlier run, so left alone.")
        return []
    dst.mkdir(parents=True, exist_ok=True)
    copied = []
    if (src / "CLAUDE.md").is_file():
        shutil.copy2(src / "CLAUDE.md", dst / "CLAUDE.md")
        copied.append("CLAUDE.md")
    for folder in ("skills", "agents", "commands"):
        if (src / folder).is_dir():
            shutil.copytree(src / folder, dst / folder, dirs_exist_ok=True)
            copied.append(folder + "/")
    settings = _read_json(src / "settings.json")
    if settings:
        kept = {k: v for k, v in settings.items() if k not in DROP_SETTINGS_KEYS}
        _atomic_write(dst / "settings.json", _render(kept))
        copied.append("settings.json (without env, model, modelSettings, apiKeyHelper)")
    (dst / COPY_MARKER).write_text("copied once; delete this file to copy again\n", encoding="utf-8")
    out(f"       Settings : copied {', '.join(copied) or 'nothing (no ~/.claude files found)'} into {dst}")
    return copied


def _is_claude_key(name):
    return (name.startswith("ANTHROPIC_") or name.startswith("CLAUDE_CODE_USE_")
            or name in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR"))


def _registry_env(scope):
    """Variable NAMES in a Windows environment hive ('User' or 'Machine'). Empty elsewhere."""
    if sys.platform != "win32":
        return []
    try:
        import winreg
        hive, sub = ((winreg.HKEY_CURRENT_USER, "Environment") if scope == "User"
                     else (winreg.HKEY_LOCAL_MACHINE, MACHINE_ENV_KEY))
        names = []
        with winreg.OpenKey(hive, sub) as key:
            i = 0
            while True:
                try:
                    names.append(winreg.EnumValue(key, i)[0])
                except OSError:
                    break
                i += 1
        return names
    except Exception:
        return []


def _settings_findings(path):
    data = _read_json(path)
    hits = []
    if isinstance(data.get("env"), dict):
        hits += [(f'"{k}" inside the "env" block', k) for k in data["env"] if _is_claude_key(k)]
    if "apiKeyHelper" in data:
        hits.append(('the "apiKeyHelper" line', "apiKeyHelper"))
    model = data.get("model")
    if isinstance(model, str) and model not in MODEL_ALIASES and not model.startswith("claude-"):
        hits.append((f'the "model" line (it names a non-Claude model: {model})', "model"))
    return hits


def project_roots(cwd=None, git_run=None):
    """The folders whose .claude/settings*.json apply here: the current folder and, when it is inside a git
    repository, the repository root. Claude Code reads the project settings from the root even when you start it
    in a subfolder, so a doctor that only looked at the current folder would miss them."""
    run = git_run or subprocess.run
    here = Path(cwd) if cwd else Path.cwd()
    roots = [here]
    try:
        r = run(["git", "rev-parse", "--show-toplevel"], cwd=str(here), capture_output=True, text=True, timeout=30)
        top = (r.stdout or "").strip()
        if r.returncode == 0 and top and not _same_folder(top, here):
            roots.append(Path(top))
    except Exception:
        pass
    return roots


def claude_doctor(home=None, environ=None, project=None, registry=None, platform=None, out=None, cwd=None,
                  git_run=None):
    """Read-only. Finds what would send normal Claude Code sessions to a local model. Returns the number of
    findings. Prints variable names and file paths, never values. `project` pins one folder (tests); otherwise
    it looks at the current folder and its git root."""
    out = out or print
    home = Path(home) if home else Path.home()
    environ = os.environ if environ is None else environ
    projects = [Path(project)] if project else project_roots(cwd, git_run)
    registry = registry or _registry_env
    platform = platform or sys.platform
    findings = []

    def hit(where, what, fix):
        findings.append(where)
        out(f"  FOUND  {what}\n         where: {where}\n         fix  : {fix}")

    for name in sorted(environ):
        if _is_claude_key(name):
            hit("this process's environment", name, f"remove {name} from the shell profile or terminal that set it")
    if platform == "win32":
        for scope in ("User", "Machine"):
            for name in registry(scope):
                if _is_claude_key(name):
                    note = "; Machine scope needs an admin PowerShell" if scope == "Machine" else ""
                    hit(f"Windows {scope} environment variables", name,
                        f"[Environment]::SetEnvironmentVariable('{name}', $null, '{scope}')  "
                        f"(then open a new terminal{note})")
    candidates = [home / ".claude" / "settings.json"]
    for project in projects:
        candidates += [project / ".claude" / "settings.json", project / ".claude" / "settings.local.json"]
    for path in candidates:
        if path.exists():
            for what, key in _settings_findings(path):
                hit(str(path), what, f"delete {key} from that file")

    vscode = [Path(environ["APPDATA"]) / "Code" / "User" / "settings.json"] if environ.get("APPDATA") else []
    vscode += [home / ".config" / "Code" / "User" / "settings.json",
               home / "Library" / "Application Support" / "Code" / "User" / "settings.json"]
    for path in vscode:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for key in ("claudeCode.environmentVariables", "claudeCode.disableLoginPrompt"):
            if key in text:
                hit(str(path), f'"{key}"', f"delete the {key} setting (VS Code: Settings, search 'Claude Code')")

    managed = Path(MANAGED_SETTINGS) if platform == "win32" else None
    if managed and managed.exists():
        for what, key in _settings_findings(managed):
            hit(str(managed), what, "ask whoever manages this machine; it applies to every session")
    if environ.get("LOCALAPPDATA"):
        cfg = Path(environ["LOCALAPPDATA"]) / "Claude" / "claude_desktop_config.json"
        if _read_json(cfg).get("deploymentMode") == "3p":
            hit(str(cfg), '"deploymentMode": "3p" (Claude Desktop is in third-party mode)',
                "ollama launch claude-desktop --restore")
    if findings:
        out(f"\n{len(findings)} thing(s) can route normal Claude Code sessions away from your subscription. "
            "Nothing was changed. After fixing, open a new terminal and run /status inside Claude Code.")
    else:
        out("Nothing found: no variable, settings file, VS Code setting or Desktop mode here routes normal Claude "
            "Code sessions to a local model. Nothing was changed.")
    return len(findings)


def launch(name, model, workspace, call=None, which=None, env=None, prompt=None, argv=None):
    """Start the agent as a child process in `workspace` and return its exit code.
    `env` (Claude Code) is a full child environment; `argv(exe)` replaces the default command (resume)."""
    call = call or subprocess.call
    which = which or shutil.which
    exe = which(name) or name
    command = argv(exe) if argv else agent_command(name, model, exe, prompt=prompt)
    if env is not None:
        return call(command, cwd=workspace, env=env)
    return call(command, cwd=workspace)


def run(name, model, base_url, workspace, config_only=False, home=None, which=None, input_fn=None, call=None,
        node_version=None, out=print, environ=None, continue_local=False, resume_from=None,
        copy_settings=False, find_transcript=None):
    """Install if the user agrees, write config, say what we did, then launch. Returns the exit code."""
    try:
        validate_model_tag(model)
        prompt = CONTINUE_PROMPT if continue_local else None
        if not config_only:
            ensure_agent(name, which=which, input_fn=input_fn, call=call, node_version=node_version, out=out)
        result = write_config(name, model, base_url, home=home)
        out("")
        out(f"       Agent    : {name}")
        out(f"       Model    : {model}")
        out(f"       Endpoint : {claude_base_url(base_url) if name == 'claude' else base_url}")
        if name == "claude" and (os.environ if environ is None else environ).get("LOCAL_LLM_BACKEND") == "openai":
            out("       Note     : Claude Code needs an Anthropic-compatible endpoint (it talks /v1/messages). A plain "
                "OpenAI-compatible server may not answer that, so this session can fail to connect.")
        if result.files:
            out("       Config   : " + ", ".join(str(p) for p in result.files))
            out("       Your other settings were kept. If a config file already existed, a one-time backup "
                f"sits beside it, ending {BACKUP_SUFFIX}.")
        for note in result.notes:
            out(f"       Note     : {note}")
        out(f"       {context_hint()}")

        env, argv = None, None
        if name == "claude":
            real_home = Path(home) if home else Path.home()
            for line in claude_routing_warnings(real_home, environ):
                out(f"       WARNING  : {line}")
            _, ctx_warning = claude_context(os.environ if environ is None else environ)
            if ctx_warning:
                out(f"       WARNING  : {ctx_warning}")
            out(f"       {CLAUDE_BANNER}")
            if config_only:
                out("       Claude Code has no config file for us to write: its settings are environment variables "
                    "for one session. Run this without --agent-config-only, or use the wrapper function in the "
                    "README. We will not print a bare `claude` command, because it would use your subscription.")
                return 0
            if copy_settings:
                copy_user_settings(real_home, out=out)
            (real_home / LOCAL_CONFIG_NAME).mkdir(parents=True, exist_ok=True)
            env = claude_child_env(model, base_url, real_home, environ)
            if resume_from:
                path = (find_transcript or _no_transcript)(resume_from)
                out("       Resume   : EXPERIMENTAL. Unverified: resuming across config folders, and how Ollama "
                    "handles replayed thinking blocks. Claude Code issue 109452 reports the model changing after a "
                    f"resume for some model ids, so check /status for the active model (should be {model}). To go "
                    "back to your subscription, use HANDOFF.md, not this fork.")
                argv = lambda exe: [exe, "--resume", str(path), "--fork-session", "--model", model]
        if config_only:
            out(f"       Config written. To start it: cd \"{workspace}\" && {_cmdline(result.command)}")
            return 0
        if prompt:
            out("       Continue : starting with the HANDOFF.md prompt.")
        out(f"       Starting {name} in {workspace} ...\n")
        return launch(name, model, workspace, call=call, which=which, env=env,
                      prompt=None if argv else prompt, argv=argv)
    except AgentSetupError as e:
        out(f"\n[agent setup] {e}")
        return e.code


def _no_transcript(_ident):
    raise AgentSetupError("No transcript lookup is available.")
