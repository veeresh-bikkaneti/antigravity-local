"""Agent setup use cases (Phase 6c): the setup run and the Claude doctor.

Nothing here writes to the terminal or reads the keyboard by itself: text leaves only through the injected
`out` callable, questions arrive through `input_fn`, and every platform collaborator (subprocess, files,
registry, git) is a keyword argument the root agent_setup.py shim wires with its own defaults, looked up
at call time. Standard library plus agl.core only.
"""

import copy
import difflib
import json
import os
from pathlib import Path

from agl.core import context_guard
from agl.core.agent_config import AgentSetupError
from agl.core.handoff import HandoffError


def resolve_model(cli_model, *, environ, default_base_url):
    """The one model/base-url resolution for every side script (Phase 6c): the CLI flag wins, then
    LOCAL_LLM_MODEL, then none; LOCAL_LLM_BASE_URL wins over the default base URL."""
    model = cli_model or environ.get("LOCAL_LLM_MODEL") or None
    base_url = environ.get("LOCAL_LLM_BASE_URL", default_base_url)
    return model, base_url


def _report_result(out, name, model, endpoint, backend, result, backup_suffix, hint):
    """The banner lines every setup run prints after the config write."""
    out("")
    out(f"       Agent    : {name}")
    out(f"       Model    : {model}")
    out(f"       Endpoint : {endpoint}")
    if name == "claude" and backend == "openai":
        out("       Note     : Claude Code needs an Anthropic-compatible endpoint (it talks /v1/messages). A plain "
            "OpenAI-compatible server may not answer that, so this session can fail to connect.")
    if result.files:
        out("       Config   : " + ", ".join(str(p) for p in result.files))
        out("       Your other settings were kept. If a config file already existed, a one-time backup "
            f"sits beside it, ending {backup_suffix}.")
    for note in result.notes:
        out(f"       Note     : {note}")
    out(f"       {hint()}")


def _claude_warnings(out, home, env, routing_warnings, context_of, window=None):
    for line in routing_warnings(home, env):
        out(f"       WARNING  : {line}")
    if window is not None:
        if window < context_guard.GREEN_FROM:
            out(f"       WARNING  : The model can hold {window:,} tokens at once, below the "
                f"{context_guard.GREEN_FROM:,} coding agents want.")
        return
    _, ctx_warning = context_of(env)
    if ctx_warning:
        out(f"       WARNING  : {ctx_warning}")


def _claude_setup(model, base_url, home, env, out, *, config_only, copy_settings, resume_from, find_transcript,
                  no_transcript, copy_settings_fn, child_env, mkdir, banner, local_config_name, window=None):
    """The claude-only half of a setup run. Returns (child_env, argv, exit_code_now); exit_code_now is 0
    when --agent-config-only stops the run right after the banner."""
    out(f"       {banner}")
    if config_only:
        out("       Claude Code has no config file for us to write: its settings are environment variables "
            "for one session. Run this without --agent-config-only, or use the wrapper function in the "
            "README. We will not print a bare `claude` command, because it would use your subscription.")
        return None, None, 0
    if copy_settings:
        copy_settings_fn(home, out=out)
    mkdir(home / local_config_name)
    window_kwargs = {} if window is None else {"window": window}
    child = child_env(model, base_url, home, env, **window_kwargs)
    argv = None
    if resume_from:
        path = (find_transcript or no_transcript)(resume_from)
        out("       Resume   : EXPERIMENTAL. Unverified: resuming across config folders, and how Ollama "
            "handles replayed thinking blocks. Claude Code issue 109452 reports the model changing after a "
            f"resume for some model ids, so check /status for the active model (should be {model}). To go "
            "back to your subscription, use HANDOFF.md, not this fork.")
        argv = lambda exe: [exe, "--resume", str(path), "--fork-session", "--model", model]
    return child, argv, None


def setup_run(name, model, base_url, workspace, *, config_only=False, home=None, which=None, input_fn=None,
              call=None, node_version=None, out=None, environ=None, continue_local=False, resume_from=None,
              copy_settings=False, find_transcript=None, validate=None, ensure_agent=None, write_config=None,
              launch=None, endpoint_of=None, context_of=None, routing_warnings=None, child_env=None,
              copy_settings_fn=None, hint=None, cmdline=None, no_transcript=None, mkdir=None,
              continue_prompt=None, backup_suffix=None, banner=None, local_config_name=None, window_of=None):
    """Install if the user agrees, write config, say what we did, then launch. Returns the exit code."""
    out = out or print
    env = os.environ if environ is None else environ
    try:
        validate(model)
        prompt = continue_prompt if continue_local else None
        if not config_only:
            ensure_agent(name, which=which, input_fn=input_fn, call=call, node_version=node_version, out=out)
        window = None
        if window_of is not None and env.get("LOCAL_LLM_BACKEND") != "openai":
            window, source = window_of(model, base_url, env)
            out(f"       Context  : the app is told {window:,} tokens (source: {source}).")
        window_kwargs = {} if window is None else {"window": window}
        result = write_config(name, model, base_url, home=home, **window_kwargs)
        _report_result(out, name, model, endpoint_of(base_url) if name == "claude" else base_url,
                       env.get("LOCAL_LLM_BACKEND"), result, backup_suffix, hint)
        child, argv = None, None
        if name == "claude":
            _claude_warnings(out, home, env, routing_warnings, context_of, window=window)
            child, argv, early = _claude_setup(model, base_url, home, env, out, config_only=config_only,
                                               copy_settings=copy_settings, resume_from=resume_from,
                                               find_transcript=find_transcript, no_transcript=no_transcript,
                                               copy_settings_fn=copy_settings_fn, child_env=child_env, mkdir=mkdir,
                                               banner=banner, local_config_name=local_config_name, window=window)
            if early is not None:
                return early
        if config_only:
            out(f"       Config written. To start it: cd \"{workspace}\" && {cmdline(result.command)}")
            return 0
        if prompt:
            out("       Continue : starting with the HANDOFF.md prompt.")
        out(f"       Starting {name} in {workspace} ...\n")
        return launch(name, model, workspace, call=call, which=which, env=child,
                      prompt=None if argv else prompt, argv=argv)
    except AgentSetupError as e:
        out(f"\n[agent setup] {e}")
        return e.code


def _hit(findings, out, where, what, fix):
    findings.append(where)
    out(f"  FOUND  {what}\n         where: {where}\n         fix  : {fix}")


def _env_findings(environ, is_claude_key, hit):
    for name in sorted(environ):
        if is_claude_key(name):
            hit("this process's environment", name, f"remove {name} from the shell profile or terminal that set it")


def _registry_findings(registry, platform, is_claude_key, hit):
    if platform != "win32":
        return
    for scope in ("User", "Machine"):
        for name in registry(scope):
            if is_claude_key(name):
                note = "; Machine scope needs an admin PowerShell" if scope == "Machine" else ""
                hit(f"Windows {scope} environment variables", name,
                    f"[Environment]::SetEnvironmentVariable('{name}', $null, '{scope}')  "
                    f"(then open a new terminal{note})")


def _settings_file_findings(candidates, settings_findings, hit):
    for path in candidates:
        if path.exists():
            for what, key in settings_findings(path):
                hit(str(path), what, f"delete {key} from that file")


def _vscode_findings(paths, read_text, hit):
    for path in paths:
        text = read_text(path)
        for key in ("claudeCode.environmentVariables", "claudeCode.disableLoginPrompt"):
            if key in text:
                hit(str(path), f'"{key}"', f"delete the {key} setting (VS Code: Settings, search 'Claude Code')")


def _desktop_finding(environ, read_json, hit):
    if environ.get("LOCALAPPDATA"):
        cfg = Path(environ["LOCALAPPDATA"]) / "Claude" / "claude_desktop_config.json"
        if read_json(cfg).get("deploymentMode") == "3p":
            hit(str(cfg), '"deploymentMode": "3p" (Claude Desktop is in third-party mode)',
                "ollama launch claude-desktop --restore")


def doctor(home, environ, projects, registry, platform, out, *, is_claude_key, settings_findings, read_json,
           read_text, managed_settings):
    """Read-only. Finds what would send normal Claude Code sessions to a local model. Returns the number of
    findings. Prints variable names and file paths, never values."""
    findings = []

    def hit(where, what, fix):
        _hit(findings, out, where, what, fix)

    _env_findings(environ, is_claude_key, hit)
    _registry_findings(registry, platform, is_claude_key, hit)
    candidates = [home / ".claude" / "settings.json"]
    for project in projects:
        candidates += [project / ".claude" / "settings.json", project / ".claude" / "settings.local.json"]
    _settings_file_findings(candidates, settings_findings, hit)
    vscode = [Path(environ["APPDATA"]) / "Code" / "User" / "settings.json"] if environ.get("APPDATA") else []
    vscode += [home / ".config" / "Code" / "User" / "settings.json",
               home / "Library" / "Application Support" / "Code" / "User" / "settings.json"]
    _vscode_findings(vscode, read_text, hit)
    managed = Path(managed_settings) if platform == "win32" else None
    if managed and managed.exists():
        for what, key in settings_findings(managed):
            hit(str(managed), what, "ask whoever manages this machine; it applies to every session")
    _desktop_finding(environ, read_json, hit)
    if findings:
        out(f"\n{len(findings)} thing(s) can route normal Claude Code sessions away from your subscription. "
            "Nothing was changed. After fixing, open a new terminal and run /status inside Claude Code.")
    else:
        out("Nothing found: no variable, settings file, VS Code setting or Desktop mode here routes normal Claude "
            "Code sessions to a local model. Nothing was changed.")
    return len(findings)


def write_handoff(transcript, repo, now=None, git_run=None, out=None, *, is_tracked, read_records, summarize,
                  render, backup_path, copy2, read_existing, write_file, marker, name="HANDOFF.md"):
    """Write HANDOFF.md. Refuses when the project tracks it. A file we did not write is backed up, never overwritten."""
    out = out or print
    if is_tracked(repo, git_run):
        raise HandoffError("This project already tracks HANDOFF.md in git, so hand-off notes written there would be "
                           "committed with their command output and any secrets in it. Nothing was written. Run "
                           "`git rm --cached HANDOFF.md` (keeps your file) and add it to .gitignore, or move your "
                           "tracked file elsewhere, then run this again.")
    info = summarize(read_records(transcript))
    target = Path(repo) / name
    existing = read_existing(target)
    if existing is not None and marker not in existing:
        backup = backup_path(target)
        copy2(target, backup)
        out(f"An existing HANDOFF.md that we did not write was saved to {backup} first.")
    write_file(target, render(info, transcript, repo, now=now))
    return target


def install_hook(repo, input_fn=None, out=None, *, hook_cmd, merge, read_text, atomic_text_write, copy2, mkdir,
                 backup_suffix):
    """Add the hooks to <repo>/.claude/settings.local.json only, after showing the diff and a typed y."""
    out = out or print
    input_fn = input_fn or input
    path = Path(repo) / ".claude" / "settings.local.json"
    before_text = read_text(path)
    try:
        settings = json.loads(before_text) if before_text.strip() else {}
    except ValueError as e:
        raise HandoffError(f"{path} is not valid JSON ({e}). We did not change it. Fix it and run again.")
    if not isinstance(settings, dict):
        raise HandoffError(f"{path} should hold a JSON object. We did not change it.")
    merged = merge(copy.deepcopy(settings), hook_cmd())
    after_text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    if merged == settings:  # compare what the file means, not how it is indented
        out(f"The hand-off hooks are already in {path}. Nothing to do.")
        return False
    out(f"This changes only {path} (never your user settings):\n")
    out("".join(difflib.unified_diff(before_text.splitlines(True), after_text.splitlines(True),
                                     "before", "after")))
    try:
        answer = input_fn("\nAdd these hooks? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip().lower() not in ("y", "yes"):
        out("Not changed.")
        return False
    mkdir(path.parent)
    backup = Path(str(path) + backup_suffix)
    if before_text and not backup.exists():
        copy2(path, backup)
    atomic_text_write(path, after_text)
    out(f"Added. When a rate limit stops a session, or before a compaction, HANDOFF.md is written in {repo}.")
    return True
