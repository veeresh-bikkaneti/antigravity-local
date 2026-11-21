"""One live tool call, to find out whether a model really works as a coding agent on this PC.

The model gets a throw-away folder with seed.md in it (MARKER=<128 random bits>) and two tools, read_file and
write_file. It must read the marker through a tool and write it to output.md through a tool. The marker never
appears in the prompt, in anything we print, or in the ledger: only the model sees it, through read_file.

Plain stdlib, talking to /v1/chat/completions, so it works for Ollama and for any OpenAI-compatible server.
"""
import json
import os
import re
import secrets
import shutil
import tempfile
import time
import urllib.error
from dataclasses import dataclass

from agl.platform import ollama as ollama_platform

REASON_CAP = 200
PROMPT = ("Use your tools. First call read_file with path seed.md; it holds one line of the form MARKER=<value>. "
          "Then call write_file with path output.md and content set to just the <value> part, nothing else. "
          "Do not explain, just make the two tool calls.")
TOOLS = [
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a text file from the working folder.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Write a text file in the working folder.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
]


@dataclass
class _State:
    """Everything the loop learns: token and call counts, the flags, the server's exception name."""

    tokens: int = 0
    calls: int = 0
    tool_seen: bool = False
    outside: bool = False
    looped: bool = False
    malformed: bool = False
    timed_out: bool = False
    errored: str = ""
    wrote_as_text: bool = False


def _inside(folder, path):
    """The real path of `path` under `folder`, or None when it would land outside (absolute, .., symlink tricks)."""
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        return None
    # Same answer on every OS: a backslash is a separator, and a drive letter, a leading slash or any ".." is out.
    path = path.replace("\\", "/")
    if path.startswith("/") or re.match(r"[A-Za-z]:", path) or ".." in path.split("/"):
        return None
    root = os.path.realpath(folder)
    target = os.path.realpath(os.path.join(root, path))
    try:
        return target if os.path.commonpath([root, target]) == root else None
    except ValueError:  # another drive on Windows
        return None


def _function(call):
    """The call's function object, or None when the model sent something else (a string, a list, null)."""
    fn = call.get("function")
    return fn if isinstance(fn, dict) and isinstance(fn.get("name"), str) else None


def _tool_args(fn):
    raw = fn.get("arguments")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _run_tool(folder, name, args):
    """Run one tool inside the folder. Returns (result text, outside_path flag)."""
    if name not in ("read_file", "write_file") or args is None:
        return "error: unknown tool or bad arguments", False
    target = _inside(folder, args.get("path"))
    if target is None:
        return "", True
    if name == "read_file":
        try:
            with open(target, encoding="utf-8") as f:
                return f.read(), False
        except OSError:
            return "error: no such file", False
    content = args.get("content")
    if not isinstance(content, str):
        return "error: content must be text", False
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write(content)
    except OSError:
        return "error: could not write", False
    return "ok", False


def _chat(opener, url, body, timeout):
    # moved, shim until Phase 6
    return ollama_platform.chat_json(url, body, opener=opener, timeout=timeout)


def _turn(opener, url, model, messages, timeout):
    """One chat round-trip. Returns (message, raw tool_calls, completion tokens). Raises on any server problem."""
    reply = _chat(opener, url, {"model": model, "messages": messages, "tools": TOOLS, "stream": False,
                                "temperature": 0}, timeout)
    message = reply["choices"][0]["message"]
    if not isinstance(message, dict):
        raise ValueError("message is not an object")
    raw_calls = message.get("tool_calls") or []
    if not isinstance(raw_calls, list):
        raise ValueError("tool_calls is not a list")
    used = (reply.get("usage") or {}).get("completion_tokens")
    tokens = used if isinstance(used, int) and not isinstance(used, bool) and used > 0 else 0
    return message, raw_calls, tokens


def _run_calls(messages, folder, tool_calls, state, max_calls):
    """Run each tool call and append its result. Stops on the first outside, looped or malformed call."""
    for call in tool_calls:
        state.calls += 1
        if state.calls > max_calls:
            state.looped = True
            return
        fn = _function(call)
        if fn is None:
            state.malformed = True
            return
        text, bad_path = _run_tool(folder, fn["name"], _tool_args(fn))
        if bad_path:
            state.outside = True
            return
        messages.append({"role": "tool", "tool_call_id": call.get("id") or f"call_{state.calls}", "content": text})


def _result(verdict, reason, marker, tokens, started, clock, calls):
    reason = str(reason).replace(marker, "<marker>")[:REASON_CAP]
    elapsed = clock() - started
    tok_s = round(tokens / elapsed, 1) if tokens > 0 and elapsed > 0 else None
    return {"verdict": verdict, "reason": reason, "tok_s": tok_s, "calls": calls}


def _verdict(state, max_calls, timeout):
    # The spec's order: time, server, path outside the folder, name, no tool call, loop. None = check output.md.
    if state.timed_out:
        return "fail", f"timed out after {timeout} s"
    if state.errored:
        return "fail", f"the server did not answer properly ({state.errored})"
    if state.outside:
        return "fail", "a tool call asked for a path outside the working folder"
    if state.malformed:
        return "fail", "a tool call had no usable function name"
    if not state.tool_seen:
        return "fail", "no structured tool call" + (" (it wrote the call out as plain text)"
                                                    if state.wrote_as_text else "")
    if state.looped:
        return "fail", f"tool-call loop: more than {max_calls} tool calls"
    return None


def run_probe(base_url, model, *, opener=None, clock=None, timeout=120, max_calls=8):
    """Run the probe. Returns {"verdict": "pass"|"fail", "reason", "tok_s" (float or None), "calls"}. Never raises.
    moved, shim until Phase 6: an opener left as None now resolves inside the platform adapter (chat_json)."""
    clock = time.monotonic if clock is None else clock
    base = base_url.rstrip("/")
    url = (base if base.endswith("/v1") else base + "/v1") + "/chat/completions"
    marker = secrets.token_hex(16)
    folder = tempfile.mkdtemp(prefix="antigravity-probe-")
    started = clock()
    state = _State()
    messages = [{"role": "user", "content": PROMPT}]

    def done(verdict, reason):
        return _result(verdict, reason, marker, state.tokens, started, clock, state.calls)

    try:
        with open(os.path.join(folder, "seed.md"), "w", encoding="utf-8", newline="") as f:
            f.write(f"MARKER={marker}")
        while True:
            left = timeout - (clock() - started)
            if left <= 0:
                state.timed_out = True
                break
            try:
                message, raw_calls, used = _turn(opener, url, model, messages, min(left, 60))
                state.tokens += used
            except Exception as exc:  # transport, HTTP status, bad JSON, missing fields: all "the server did not work"
                state.errored = type(exc).__name__
                break
            tool_calls = [c for c in raw_calls if isinstance(c, dict)]
            if not tool_calls:
                text = message.get("content") if isinstance(message.get("content"), str) else ""
                state.wrote_as_text = "read_file" in text or "write_file" in text
                break
            state.tool_seen = True
            messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
            _run_calls(messages, folder, tool_calls, state, max_calls)
            if state.outside or state.looped or state.malformed:
                break

        verdict = _verdict(state, max_calls, timeout)
        if verdict is not None:
            return done(*verdict)
        out_path = os.path.join(folder, "output.md")
        try:
            with open(out_path, encoding="utf-8", newline="") as f:
                written = f.read()
        except OSError:
            return done("fail", "output.md was not written")
        if not written:
            return done("fail", "output.md is empty")
        if written != marker and written != marker + "\n":  # one trailing newline is tolerated (a DEFAULT)
            return done("fail", "output.md does not hold the marker")
        return done("pass", "read the marker and wrote it back through tools")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
