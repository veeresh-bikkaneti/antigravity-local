"""Disk and process I/O for step mode (C4): the checkpoint file, the git guard, and the optional test command.

agl.app may not import this package, so run.py hands this module to AppPorts as `step_io`. Never shell=True:
the test command is split into an argument list and run through process.run with a timeout.
"""
import os
import shlex
from pathlib import Path

from agl.core.agent_config import AgentSetupError
from agl.platform import agent_files, process

CHECKPOINT = Path(".agl") / "checkpoint.md"
TEST_TIMEOUT = 120
TAIL_LINES = 5


def checkpoint_path(workspace):
    """The checkpoint file inside `workspace`."""
    return Path(workspace) / CHECKPOINT


def read_checkpoint(workspace):
    """The checkpoint text, or "" when there is none yet."""
    return agent_files.read_text_or(checkpoint_path(workspace), "")


def write_checkpoint(workspace, text):
    """Write the checkpoint atomically, creating .agl/ when needed."""
    agent_files.write_text_atomic(checkpoint_path(workspace), text)


def is_tracked(workspace):
    """True when git tracks the checkpoint, or when git can't tell us inside a repo (refuse rather than guess)."""
    try:
        return agent_files.git_tracks(workspace, CHECKPOINT.as_posix())
    except AgentSetupError:
        return True


def run_test(cmd, workspace, *, run_fn=None, timeout=TEST_TIMEOUT):
    """Run the user's own test command. Returns (exit_code, last_lines); exit_code is None on a timeout."""
    args = shlex.split(cmd, posix=os.name != "nt")
    try:
        done = (run_fn or process.run)(args, cwd=str(workspace), capture_output=True, text=True,
                                       timeout=timeout, check=False)
    except process.TimeoutExpired:
        return None, []
    except OSError as exc:
        return 127, [str(exc)]
    lines = ((done.stdout or "") + (done.stderr or "")).splitlines()
    return done.returncode, lines[-TAIL_LINES:]
