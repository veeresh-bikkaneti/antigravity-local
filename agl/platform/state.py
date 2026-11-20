"""Files-and-state adapter (Phase 4b): the .env file, the upgrade-stay file and the fail ledger.

This is the platform's own files-and-state domain: `userdata` is a 15-line stdlib-only path helper that
decides where those files live, so the reads and writes belong here too. Bodies moved verbatim from
run.py and ledger.py; the old names stay there as shims until Phase 6. No print in this module: the
caller decides whether and how to warn.
"""
import codecs
import datetime
import json
import os
import re
import socket
import time

import userdata

LEDGER_NAME = "ledger.jsonl"
REASON_CAP = 500
VERDICTS = ("pass", "fail")
UPGRADE_STAY_SECONDS = 7 * 24 * 3600  # a "stay" answer quiets that one model for a week


def ledger_path(home=None, env=None):
    return userdata.data_dir(home, env) / LEDGER_NAME


def _stamp(epoch):
    # same one-line body as ledger._stamp_epoch (kept there for the pure read side): the format lives in both places until Phase 6
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ends_mid_line(path):
    """True when the ledger has bytes and the last one is not a newline (a crash cut the last line short)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            if f.tell() == 0:
                return False
            f.seek(-1, 2)
            return f.read(1) != b"\n"
    except FileNotFoundError:
        return False


def append(model_ref, verdict, reason, *, runtime="ollama", harness="probe", evidence_key=None,
           home=None, env=None, now=None, host=None, stamp=None):
    """Record one verdict. Returns (ok, message); never raises. On failure the message is a one-line warning."""
    if verdict not in VERDICTS:
        return False, f"Ledger not written: verdict must be pass or fail, not {verdict!r}."
    entry = {
        "timestampUtc": _stamp(time.time() if now is None else now) if stamp is None else stamp,
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
        # ensure_ascii keeps every line pure ASCII, so a lone surrogate becomes a \udcff escape instead of a crash
        line = json.dumps(entry, separators=(",", ":"), ensure_ascii=True) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = b"\n" if _ends_mid_line(path) else b""
        with open(path, "ab") as f:
            f.write(prefix + line.encode("ascii"))
    except (OSError, ValueError) as exc:  # UnicodeError is a ValueError
        return False, f"Could not write the fail ledger ({exc.__class__.__name__}); carrying on without it."
    return True, ""


def read(home=None, env=None):
    """Every well-formed entry, oldest first. A missing file is []; corrupt lines and odd values are skipped.

    Split on b"\\n" only, so one bad byte costs only its own line, and U+2028 or NEL inside a reason stay put.
    """
    try:
        raw = ledger_path(home, env).read_bytes()
    except OSError:
        return []
    if raw.startswith(codecs.BOM_UTF8):
        raw = raw[len(codecs.BOM_UTF8):]
    entries = []
    for line in raw.split(b"\n"):
        try:
            item = json.loads(line.decode("utf-8"))
        except (ValueError, RecursionError):
            continue
        if isinstance(item, dict) and item.get("verdict") in VERDICTS and isinstance(item.get("modelRef"), str):
            entries.append(item)
    return entries


def load_env(env_file=None):
    """Load `env_file` into os.environ when python-dotenv is installed. Without it, .env is simply skipped."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_file)


def update_env_model(model_name, env_file=None):
    """Rewrite LOCAL_LLM_MODEL in `env_file` so the next run starts from this pick. Returns the caught
    exception, or None on success: the caller decides whether and how to warn."""
    env_file = ".env" if env_file is None else env_file
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                content = f.read()
            if "LOCAL_LLM_MODEL=" in content:
                content = re.sub(r"LOCAL_LLM_MODEL=.*", f"LOCAL_LLM_MODEL={model_name}", content)
            else:
                content += f"\nLOCAL_LLM_MODEL={model_name}\n"
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as exc:
            return exc
    return None


def read_upgrade_state(path=None):
    """The parsed stay-state file, {} when missing or not a dict."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def remember_upgrade_stay(current, now=None, path=None):
    """Enter on the model menu while the upgrade row was shown: that model's upgrade stays quiet for a week."""
    now = time.time() if now is None else now
    try:
        stays = read_upgrade_state(path).get("stay_until")
        stays = dict(stays) if isinstance(stays, dict) else {}
        stays[current] = now + UPGRADE_STAY_SECONDS
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"stay_until": stays}, f, indent=2)
    except OSError:
        pass  # the answer still counts for this run; we just cannot remember it
