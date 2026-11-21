"""Subprocess and registry access for the agent setup scripts (Phase 6c).

Every subprocess/shutil attribute is looked up at call time (inside the function body), like
agl/platform/process.py, so tests that patch `subprocess` keep hitting. `import winreg` stays inside
registry_env so a patched sys.modules['winreg'] is picked up, and the platform string arrives as an
argument read from the caller's own `sys` at call time.
"""

import shlex
import shutil
import subprocess
from pathlib import Path

from agl.core.agent_config import AgentSetupError, agent_command


def which(name):
    return shutil.which(name)


def call(cmd, **kwargs):
    return subprocess.call(cmd, **kwargs)


def run(cmd, **kwargs):
    return subprocess.run(cmd, **kwargs)


def node_version():
    try:
        return subprocess.check_output(["node", "--version"], text=True, timeout=10).strip()
    except Exception:
        return ""


def cmdline(argv, platform):
    return subprocess.list2cmdline(argv) if platform == "win32" else shlex.join(argv)


def claude_install_argv(platform):
    if platform == "win32":
        return ["powershell", "-NoProfile", "-Command", "irm https://claude.ai/install.ps1 | iex"]
    return ["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"]


def ensure_claude(which_fn, input_fn, call_fn, out, platform):
    shown = ("irm https://claude.ai/install.ps1 | iex" if platform == "win32"
             else "curl -fsSL https://claude.ai/install.sh | bash")
    out(f"       claude is not installed. To install it yourself (Anthropic's official script): {shown}")
    try:
        answer = input_fn("       Install it now with that script? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip().lower() not in ("y", "yes"):
        out("       Not installing. Run the command above yourself, then run this again.")
        raise AgentSetupError("claude is not installed.")
    if call_fn(claude_install_argv(platform)) != 0:
        raise AgentSetupError("The Claude Code install script failed. Run the command above in a terminal to see why.")
    found = which_fn("claude")
    if not found:
        out("       Installed, but 'claude' is not on your PATH yet. Open a new terminal, then run this again.")
        raise AgentSetupError("claude was installed but is not on PATH.")
    return found


def launch(name, model, workspace, call_fn=None, which_fn=None, env=None, prompt=None, argv=None):
    """Start the agent as a child process in `workspace` and return its exit code.
    `env` (Claude Code) is a full child environment; `argv(exe)` replaces the default command (resume)."""
    call_fn = call_fn or subprocess.call
    which_fn = which_fn or shutil.which
    exe = which_fn(name) or name
    command = argv(exe) if argv else agent_command(name, model, exe, prompt=prompt)
    if env is not None:
        return call_fn(command, cwd=workspace, env=env)
    return call_fn(command, cwd=workspace)


def git(args, repo, run_fn=None):
    run_fn = run_fn or subprocess.run
    try:
        r = run_fn(["git"] + args, cwd=str(repo), capture_output=True, text=True, timeout=30)
        return (r.stdout or "").rstrip() or "(none)"  # rstrip only: status columns start with a space
    except Exception as e:
        return f"(git unavailable: {e.__class__.__name__})"


def repo_root(cwd, run_fn=None):
    run_fn = run_fn or subprocess.run
    try:
        r = run_fn(["git", "rev-parse", "--show-toplevel"], cwd=str(cwd), capture_output=True, text=True, timeout=30)
        top = (r.stdout or "").strip()
        if r.returncode == 0 and top:
            return Path(top)
    except Exception:
        pass
    return Path(cwd)


def is_tracked(repo, run_fn=None):
    """True when git already tracks HANDOFF.md in this project (`git ls-files --error-unmatch` succeeds).
    If git cannot be run we cannot tell, so say no and let ensure_ignored warn."""
    run_fn = run_fn or subprocess.run
    try:
        return run_fn(["git", "ls-files", "--error-unmatch", "HANDOFF.md"], cwd=str(repo), capture_output=True,
                      text=True, timeout=30).returncode == 0
    except Exception:
        return False


def registry_env(scope, platform, machine_env_key):
    """Variable NAMES in a Windows environment hive ('User' or 'Machine'). Empty elsewhere."""
    if platform != "win32":
        return []
    try:
        import winreg
        hive, sub = ((winreg.HKEY_CURRENT_USER, "Environment") if scope == "User"
                     else (winreg.HKEY_LOCAL_MACHINE, machine_env_key))
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
