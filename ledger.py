"""A small fail ledger: what a live probe said about each model on this PC, kept in ~/.antigravity-local/ledger.jsonl.

Append-only, one compact JSON object per line. A model's LATEST entry decides: no entry is "unproven", which ranks above
"fail". It warns and never refuses, and a write that fails only warns, so the ledger can never stop a run.
moved, shim until Phase 6: the file I/O (ledger_path, append/read/_ends_mid_line, the gethostname call) now lives
in agl/platform/state.py; this module keeps the pure read side (_latest/status/fresh_pass and their stamps) and re-exports
the moved names so old callers and tests keep working.
"""
import datetime
import time

from agl.core import menu
from agl.platform import state

LEDGER_NAME = state.LEDGER_NAME  # moved, shim until Phase 6: the constant now lives in agl.platform.state
REASON_CAP = state.REASON_CAP  # moved, shim until Phase 6
VERDICTS = state.VERDICTS  # moved, shim until Phase 6
PASS_TTL_SECONDS = 300  # a pass this young is reused instead of probing again straight away


def _stamp_epoch(epoch):
    """was _stamp: renamed so one name means one thing (runlog._stamp stamps a log line)."""
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


_stamp = _stamp_epoch  # renamed, shim until Phase 6: alias kept for callers and tests that use the old name


def _epoch(stamp):
    try:
        return datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def ledger_path(home=None, env=None):
    return state.ledger_path(home, env)  # moved, shim until Phase 6


def append(model_ref, verdict, reason, *, runtime="ollama", harness="probe", evidence_key=None,
           home=None, env=None, now=None, host=None):
    """Record one verdict. Returns (ok, message); never raises. On failure the message is a one-line warning."""
    return state.append(model_ref, verdict, reason, runtime=runtime, harness=harness, evidence_key=evidence_key,
                        home=home, env=env, now=now, host=host,
                        stamp=_stamp_epoch(time.time() if now is None else now))  # moved, shim until Phase 6


def read(home=None, env=None):
    """Every well-formed entry, oldest first (a missing file is []); see agl.platform.state.read."""
    return state.read(home, env)  # moved, shim until Phase 6


def _ends_mid_line(path):
    """True when the ledger has bytes and the last one is not a newline (a crash cut the last line short)."""
    return state._ends_mid_line(path)  # moved, shim until Phase 6


def _latest(model_ref, entries):
    want = menu._norm(str(model_ref))
    found = None
    for item in entries or []:
        if menu._norm(item["modelRef"]) == want:
            found = item  # later lines win
    return found


def status(model_ref, entries):
    """'pass', 'fail' or 'unproven'. The latest entry for the model decides."""
    item = _latest(model_ref, entries)
    return item["verdict"] if item else "unproven"


def fresh_pass(model_ref, entries, now=None, ttl=PASS_TTL_SECONDS):
    """True when the model's latest entry is a pass no older than ttl seconds."""
    item = _latest(model_ref, entries)
    if not item or item["verdict"] != "pass":
        return False
    when = _epoch(item.get("timestampUtc"))
    if when is None:
        return False
    age = (time.time() if now is None else now) - when
    return 0 <= age <= ttl
