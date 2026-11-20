"""The subprocess adapter (Phase 4b): every command run.py starts goes through here now.

The venv bootstrap, the pip installs, the venv relaunch, `ollama pull`, the `ollama list` fallback and the
detached `ollama serve` are thin pass-throughs; the old names in run.py stay as shims until Phase 6. Each body is one line, so the subprocess attribute is looked up at call time (tests patch this module's
`subprocess`). Never shell=True: every command is an argument list a test can read.
"""
import subprocess

DEVNULL = subprocess.DEVNULL  # one alias per name: callers keep one place to look
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)  # Windows-only flag; 0 keeps this importable elsewhere
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0)  # Windows-only flag; 0 keeps this importable elsewhere
CalledProcessError = subprocess.CalledProcessError


def check_call(cmd, **kwargs):
    """A command that must succeed (run.py's venv bootstrap, `ollama pull`, the hardware probes)."""
    return subprocess.check_call(cmd, **kwargs)


def call(cmd, **kwargs):
    """A command whose return code run.py passes to sys.exit (the venv relaunch)."""
    return subprocess.call(cmd, **kwargs)


def check_output(cmd, **kwargs):
    """Command output as text: `ollama list` and the hardware probes."""
    return subprocess.check_output(cmd, **kwargs)


def popen(cmd, **kwargs):
    """A detached child: `ollama serve`, with Windows creationflags or POSIX start_new_session."""
    return subprocess.Popen(cmd, **kwargs)


def run(cmd, **kwargs):
    """A command we read the exit code and output of (memory.py's graphify sync)."""
    return subprocess.run(cmd, **kwargs)
