"""A small fail ledger: what a live probe said about each model on this PC, kept in ~/.antigravity-local/ledger.jsonl.

Append-only, one compact JSON object per line. A model's LATEST entry decides: no entry is "unproven", which ranks above
"fail". It warns and never refuses, and a write that fails only warns, so the ledger can never stop a run.
"""
import datetime
import json
import socket
import time

import model_wizard
import userdata

LEDGER_NAME = "ledger.jsonl"
REASON_CAP = 500
PASS_TTL_SECONDS = 300  # a pass this young is reused instead of probing again straight away
VERDICTS = ("pass", "fail")


def ledger_path(home=None, env=None):
    return userdata.data_dir(home, env) / LEDGER_NAME


def _stamp(epoch):
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _epoch(stamp):
    try:
        return datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def append(model_ref, verdict, reason, *, runtime="ollama", harness="probe", evidence_key=None,
           home=None, env=None, now=None, host=None):
    """Record one verdict. Returns (ok, message); never raises. On failure the message is a one-line warning."""
    if verdict not in VERDICTS:
        return False, f"Ledger not written: verdict must be pass or fail, not {verdict!r}."
    entry = {
        "timestampUtc": _stamp(time.time() if now is None else now),
        "host": host if host is not None else socket.gethostname(),
        "modelRef": str(model_ref),
        "runtime": runtime,
        "harness": harness,
    }
    if evidence_key:
        entry["evidenceKey"] = str(evidence_key)
    entry["reason"] = str(reason or "")[:REASON_CAP]
    entry["verdict"] = verdict
    path = ledger_path(home, env)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")
    except OSError as exc:
        return False, f"Could not write the fail ledger ({exc.__class__.__name__}); carrying on without it."
    return True, ""


def read(home=None, env=None):
    """Every well-formed entry, oldest first. A missing file is []; corrupt lines and odd values are skipped."""
    try:
        text = ledger_path(home, env).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    entries = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(item, dict) and item.get("verdict") in VERDICTS and isinstance(item.get("modelRef"), str):
            entries.append(item)
    return entries


def _latest(model_ref, entries):
    want = model_wizard._norm(str(model_ref))
    found = None
    for item in entries or []:
        if model_wizard._norm(item["modelRef"]) == want:
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
