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
import urllib.request

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


def _tool_args(call):
    raw = (call.get("function") or {}).get("arguments")
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
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
    with opener(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _result(verdict, reason, marker, tokens, started, clock, calls):
    reason = str(reason).replace(marker, "<marker>")[:REASON_CAP]
    elapsed = clock() - started
    tok_s = round(tokens / elapsed, 1) if tokens > 0 and elapsed > 0 else None
    return {"verdict": verdict, "reason": reason, "tok_s": tok_s, "calls": calls}


def run_probe(base_url, model, *, opener=None, clock=None, timeout=120, max_calls=8):
    """Run the probe. Returns {"verdict": "pass"|"fail", "reason", "tok_s" (float or None), "calls"}. Never raises."""
    opener = urllib.request.urlopen if opener is None else opener
    clock = time.monotonic if clock is None else clock
    base = base_url.rstrip("/")
    url = (base if base.endswith("/v1") else base + "/v1") + "/chat/completions"
    marker = secrets.token_hex(16)
    folder = tempfile.mkdtemp(prefix="antigravity-probe-")
    started, tokens, calls = clock(), 0, 0
    tool_seen = outside = looped = errored = timed_out = False
    wrote_as_text = False
    messages = [{"role": "user", "content": PROMPT}]

    def done(verdict, reason):
        return _result(verdict, reason, marker, tokens, started, clock, calls)

    try:
        with open(os.path.join(folder, "seed.md"), "w", encoding="utf-8", newline="") as f:
            f.write(f"MARKER={marker}")
        while True:
            left = timeout - (clock() - started)
            if left <= 0:
                timed_out = True
                break
            try:
                reply = _chat(opener, url, {"model": model, "messages": messages, "tools": TOOLS, "stream": False,
                                            "temperature": 0}, min(left, 60))
                message = reply["choices"][0]["message"]
                used = (reply.get("usage") or {}).get("completion_tokens")
                tokens += used if isinstance(used, int) and not isinstance(used, bool) and used > 0 else 0
            except Exception as exc:  # transport, HTTP status, bad JSON, missing fields: all "the server did not work"
                errored = type(exc).__name__
                break
            tool_calls = [c for c in (message.get("tool_calls") or []) if isinstance(c, dict)]
            if not tool_calls:
                text = message.get("content") if isinstance(message.get("content"), str) else ""
                wrote_as_text = "read_file" in text or "write_file" in text
                break
            tool_seen = True
            messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
            for call in tool_calls:
                calls += 1
                if calls > max_calls:
                    looped = True
                    break
                name = (call.get("function") or {}).get("name")
                text, bad_path = _run_tool(folder, name, _tool_args(call))
                if bad_path:
                    outside = True
                    break
                messages.append({"role": "tool", "tool_call_id": call.get("id") or f"call_{calls}", "content": text})
            if outside or looped:
                break

        # The spec's order: server error, path outside the folder, no structured tool call, loop, then the file itself.
        if timed_out:
            return done("fail", f"timed out after {timeout} s")
        if errored:
            return done("fail", f"the server did not answer properly ({errored})")
        if outside:
            return done("fail", "a tool call asked for a path outside the working folder")
        if not tool_seen:
            return done("fail", "no structured tool call"
                        + (" (it wrote the call out as plain text)" if wrote_as_text else ""))
        if looped:
            return done("fail", f"tool-call loop: more than {max_calls} tool calls")
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
