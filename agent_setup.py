"""One-step setup for better terminal coding agents on top of the local Ollama model. Standard library only.

`python run.py --agent pi|opencode|codex` lands here after run.py has picked the model. We install the agent
only if the user says yes, merge a provider block into the agent's own config without touching anything else,
and start it in the folder the user is working in.

Every collaborator (which, input, subprocess, home) is passed in and looked up at call time, so tests never
touch the real machine. Do not bind `input` or `subprocess.call` as default arguments: that freezes the real
one at import time and the mocks stop working.

The subprocess/file/registry I/O lives in agl/platform (agent_files.py, agent_proc.py), the pure decisions in
agl/core/agent_config.py, and the orchestration (run, claude_doctor) in agl/app/agent_session.py. What is left
here is this module's own shell: its constants, the thin wrappers that read them, and the entry points run.py
calls.
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from agl.app import agent_session, vscode_chat
from agl.core import agent_config as core_config
from agl.core import context_guard, vscode_models
from agl.core.agent_config import AgentSetupError
from agl.platform import agent_files, agent_proc, config, hardware, ollama, ollama_live, vscode_files

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
CONTEXT_WINDOW = core_config.UNKNOWN_CONTEXT_WINDOW
OPENCODE_SCHEMA = "https://opencode.ai/config.json"
# Letters, digits and . _ / - only, plus an optional :tag. Real tags such as hf.co/user/repo:Q4_K_M pass. Shell
# characters (& | ; < > ^ % quotes $) do not: on Windows the agents are .cmd files that run through cmd.exe.
MODEL_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*(:[A-Za-z0-9._-]+)?$")


@dataclass
class Result:
    command: list
    files: list = field(default_factory=list)
    changed: bool = False
    notes: list = field(default_factory=list)


def validate_model_tag(model):  # decision in agl.core.agent_config
    """Reject anything that could be read as a flag, split into arguments, or run by a shell."""
    err = core_config.validate_model_tag(model, MODEL_TAG_RE)
    if err is not None:
        raise AgentSetupError(err)


def node_ok(version):  # decision in agl.core.agent_config
    """True for Node >= 22.19 (what pi needs). Accepts 'v26.13.0'."""
    return core_config.node_ok(version, PI_NODE_MIN)


def ensure_agent(name, which=None, input_fn=None, call=None, node_version=None, out=print):  # I/O in agl.platform.agent_proc
    """Return the agent's path. If it is missing, show the command and install only when the user types y."""
    which = which or agent_proc.which
    input_fn = input_fn or input
    call = call or agent_proc.call
    node_version = node_version or agent_proc.node_version

    found = which(name)
    if found:
        return found

    if name == "claude":
        return agent_proc.ensure_claude(which, input_fn, call, out, sys.platform)

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

def write_config(name, model, base_url, home=None, window=None):  # this module's own shell
    """Merge our Ollama block into the agent's config. Plans every file first, so a broken file stops us
    before anything is written. A file whose parsed content would not change is left exactly as it is."""
    validate_model_tag(model)
    home = Path(home) if home else Path.home()

    if name == "claude":
        return Result(command=core_config.agent_command("claude", model))

    if name == "codex":
        notes = []
        if "11434" not in base_url:
            notes.append(f"codex --oss talks to Ollama on its default port (11434); {base_url} is not used by it.")
        return Result(command=core_config.agent_command("codex", model), notes=notes)

    plans = []
    for path, merge in core_config.targets(name, home, window, OPENCODE_SCHEMA):
        data, text = agent_files.load(path)
        before = json.loads(text) if text is not None else None
        merge(data, model, base_url, path)
        plans.append((path, text is not None, data != before, data))

    changed = False
    for path, existed, differs, data in plans:
        if not differs:
            continue
        backup = Path(str(path) + BACKUP_SUFFIX)
        if existed and not backup.exists():
            agent_files.copy2(path, backup)
        agent_files.atomic_write(path, core_config.render_json(data))
        changed = True
    return Result(command=core_config.agent_command(name, model), files=[p for p, *_ in plans], changed=changed)


def resolve_workspace(arg, cwd, project_dir, out=None):  # this module's own shell
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
    if core_config.same_folder(here, project_dir):
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


def claude_context(environ):  # decision in agl.core.agent_config
    """(tokens, warning or None). The window Ollama really runs with is what Claude Code must plan for."""
    return core_config.claude_context(environ, CONTEXT_WINDOW)


def live_window(model, base_url, environ=None):  # reads Ollama now; the rule is in agl.core.context_guard
    """(tokens, source) for the window Ollama really runs, read now."""
    env = os.environ if environ is None else environ
    rows = ollama_live.loaded_models(core_config.claude_base_url(base_url, config.OLLAMA_BASE_URL))
    vram = hardware.get_hardware_profile()["vram_gb"]
    return context_guard.real_window(rows, model, env.get("OLLAMA_CONTEXT_LENGTH"), vram)


def offer_vscode(result, model, base_url, workspace, input_fn=None, out=print):
    """After the stage-4 banner: offer to give VS Code Chat the real window. Steps: agl.app.vscode_chat."""

    def tools_of(url, name):
        root = core_config.claude_base_url(url, config.OLLAMA_BASE_URL)
        found = ollama.lookup(ollama.installed_details(root), name)
        return "tools" in ((found or {}).get("caps") or [])

    vscode_chat.offer(
        result,
        model,
        core_config.claude_base_url(base_url, config.OLLAMA_BASE_URL),
        workspace,
        user_dirs=vscode_models.user_dirs(sys.platform, str(Path.home()), os.environ),
        tools_of=tools_of,
        files=vscode_files,
        input_fn=input_fn or input,
        out=out,
    )


def claude_child_env(model, base_url, home=None, environ=None, window=None):  # this module's own shell
    """A COPY of the environment with everything Claude Code needs to talk to Ollama. Never applied to os.environ."""
    home = Path(home) if home else Path.home()
    env = dict(os.environ if environ is None else environ)
    tokens, _ = claude_context(env)
    if window is not None:
        tokens = window
    # Anything else that can pick a different login, model, endpoint or cloud would leak through the inherited
    # environment (a subscription token would be sent to the local server). Drop it for this child only.
    for key in [k for k in env if k.startswith("ANTHROPIC_") or k in INHERITED_AUTH_VARS]:
        del env[key]
    env.update({
        "CLAUDE_CONFIG_DIR": str((home / LOCAL_CONFIG_NAME).resolve()),
        "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST": "1",
        "ANTHROPIC_BASE_URL": core_config.claude_base_url(base_url, config.OLLAMA_BASE_URL),
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
    if window is not None:
        env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(window)
    return env


def claude_routing_warnings(home=None, environ=None):  # this module's own shell
    """Where a routing variable is already set. Names and places only, never values. Read-only."""
    home = Path(home) if home else Path.home()
    environ = os.environ if environ is None else environ
    found = [f"{v} is set in this terminal's environment" for v in ROUTING_VARS if environ.get(v)]
    settings = home / ".claude" / "settings.json"
    env_block = agent_files.read_json(settings).get("env")
    if isinstance(env_block, dict):
        found += [f"{v} is set in the env block of {settings}" for v in ROUTING_VARS if v in env_block]
    if not found:
        return []
    return found + ["That routes (or bills) every normal Claude Code session, and the VS Code extension, which "
                    "shares that file and inherits Windows environment variables. We did not edit anything. Run "
                    "`python run.py --agent claude --doctor` to see exactly what to remove."]


def copy_user_settings(home=None, out=None):  # I/O in agl.platform.agent_files
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
        agent_files.copy2(src / "CLAUDE.md", dst / "CLAUDE.md")
        copied.append("CLAUDE.md")
    for folder in ("skills", "agents", "commands"):
        if (src / folder).is_dir():
            agent_files.copytree(src / folder, dst / folder)
            copied.append(folder + "/")
    settings = agent_files.read_json(src / "settings.json")
    if settings:
        kept = {k: v for k, v in settings.items() if k not in DROP_SETTINGS_KEYS}
        agent_files.atomic_write(dst / "settings.json", core_config.render_json(kept))
        copied.append("settings.json (without env, model, modelSettings, apiKeyHelper)")
    (dst / COPY_MARKER).write_text("copied once; delete this file to copy again\n", encoding="utf-8")
    out(f"       Settings : copied {', '.join(copied) or 'nothing (no ~/.claude files found)'} into {dst}")
    return copied


def _registry_env(scope):  # I/O in agl.platform.agent_proc
    """Variable NAMES in a Windows environment hive ('User' or 'Machine'). Empty elsewhere."""
    return agent_proc.registry_env(scope, sys.platform, MACHINE_ENV_KEY)


def _settings_findings(path):  # this module's own shell
    data = agent_files.read_json(path)
    hits = []
    if isinstance(data.get("env"), dict):
        hits += [(f'"{k}" inside the "env" block', k) for k in data["env"] if core_config.is_claude_key(k)]
    if "apiKeyHelper" in data:
        hits.append(('the "apiKeyHelper" line', "apiKeyHelper"))
    model = data.get("model")
    if isinstance(model, str) and model not in MODEL_ALIASES and not model.startswith("claude-"):
        hits.append((f'the "model" line (it names a non-Claude model: {model})', "model"))
    return hits


def project_roots(cwd=None, git_run=None):  # I/O in agl.platform.agent_proc
    """The folders whose .claude/settings*.json apply here: the current folder and, when it is inside a git
    repository, the repository root. Claude Code reads the project settings from the root even when you start it
    in a subfolder, so a doctor that only looked at the current folder would miss them."""
    run = git_run or agent_proc.run
    here = Path(cwd) if cwd else Path.cwd()
    roots = [here]
    try:
        r = run(["git", "rev-parse", "--show-toplevel"], cwd=str(here), capture_output=True, text=True, timeout=30)
        top = (r.stdout or "").strip()
        if r.returncode == 0 and top and not core_config.same_folder(top, here):
            roots.append(Path(top))
    except Exception:
        pass
    return roots


def claude_doctor(home=None, environ=None, project=None, registry=None, platform=None, out=None, cwd=None,
                  git_run=None):  # orchestration in agl.app.agent_session
    """Read-only. Finds what would send normal Claude Code sessions to a local model. Returns the number of
    findings. Prints variable names and file paths, never values. `project` pins one folder (tests); otherwise
    it looks at the current folder and its git root."""
    return agent_session.doctor(
        Path(home) if home else Path.home(), os.environ if environ is None else environ,
        [Path(project)] if project else project_roots(cwd, git_run),
        registry or _registry_env, platform or sys.platform, out or print,
        is_claude_key=core_config.is_claude_key, settings_findings=_settings_findings,
        read_json=agent_files.read_json, read_text=agent_files.read_text_or, managed_settings=MANAGED_SETTINGS)


def launch(name, model, workspace, call=None, which=None, env=None, prompt=None, argv=None):  # I/O in agl.platform.agent_proc
    """Start the agent as a child process in `workspace` and return its exit code.
    `env` (Claude Code) is a full child environment; `argv(exe)` replaces the default command (resume)."""
    return agent_proc.launch(name, model, workspace, call_fn=call, which_fn=which, env=env, prompt=prompt, argv=argv)


def run(name, model, base_url, workspace, config_only=False, home=None, which=None, input_fn=None, call=None,
        node_version=None, out=print, environ=None, continue_local=False, resume_from=None,
        copy_settings=False, find_transcript=None, window_of=None):  # orchestration in agl.app.agent_session
    """Install if the user agrees, write config, say what we did, then launch. Returns the exit code."""
    return agent_session.setup_run(
        name, model, base_url, workspace, config_only=config_only, home=Path(home) if home else Path.home(),
        which=which, input_fn=input_fn, call=call, node_version=node_version, out=out, environ=environ,
        continue_local=continue_local, resume_from=resume_from, copy_settings=copy_settings,
        find_transcript=find_transcript, window_of=window_of, validate=validate_model_tag, ensure_agent=ensure_agent,
        write_config=write_config, launch=launch,
        endpoint_of=lambda b: core_config.claude_base_url(b, config.OLLAMA_BASE_URL),
        context_of=lambda e: core_config.claude_context(e, CONTEXT_WINDOW),
        routing_warnings=claude_routing_warnings, child_env=claude_child_env, copy_settings_fn=copy_user_settings,
        hint=lambda: core_config.context_hint(), cmdline=lambda argv: agent_proc.cmdline(argv, sys.platform),
        no_transcript=_no_transcript,
        mkdir=agent_files.mkdir, continue_prompt=CONTINUE_PROMPT, backup_suffix=BACKUP_SUFFIX, banner=CLAUDE_BANNER,
        local_config_name=LOCAL_CONFIG_NAME)


def _no_transcript(_ident):
    raise AgentSetupError("No transcript lookup is available.")
