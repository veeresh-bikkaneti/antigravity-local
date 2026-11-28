"""C2 relay: pure decisions for the local relay that sits between a coding app and Ollama. No I/O.

When a chat request is bigger than the real window, keep the system messages, the first user message (the goal)
and the latest messages, and drop the oldest middle turns. An assistant turn and the tool results after it go
together, so a tool call is never left without its result. The relay also reports the real window in /api/show,
so the app budgets for the window that is loaded, not the model's trained maximum (inferred root cause, C2 doc).
"""

import json

CHARS_PER_TOKEN = 4  # the same rough count as agl.core.checkpoint.tokens
RESERVE = 1024       # room left for the answer
KEEP_LAST = 6        # the latest messages are always kept
CHAT_PATHS = ("/api/chat", "/v1/chat/completions")
NOTE = ("({n} earlier messages were trimmed to fit the {window}-token window. "
        "Read .agl/checkpoint.md for the plan and what is done.)")


def tokens(value):
    """A rough token count of a message list or a request body."""
    return len(json.dumps(value, ensure_ascii=False)) // CHARS_PER_TOKEN


def _units(middle):
    """Group the middle messages so a tool result always stays with the turn before it."""
    units = []
    for msg in middle:
        if units and isinstance(msg, dict) and msg.get("role") == "tool":
            units[-1].append(msg)
        else:
            units.append([msg])
    return units


def _split(messages):
    """(head, middle, tail): head is every leading system message plus the first user message."""
    head_end = 0
    while head_end < len(messages) and isinstance(messages[head_end], dict) \
            and messages[head_end].get("role") == "system":
        head_end += 1
    if head_end < len(messages):
        head_end += 1  # the goal: the first message that is not a system message
    while head_end < len(messages) and isinstance(messages[head_end], dict) \
            and messages[head_end].get("role") == "tool":
        head_end += 1  # tool results right after the goal stay with it
    tail_start = max(head_end, len(messages) - KEEP_LAST)
    while tail_start > head_end and isinstance(messages[tail_start], dict) \
            and messages[tail_start].get("role") == "tool":
        tail_start -= 1  # never start the tail on a tool result
    return messages[:head_end], messages[head_end:tail_start], messages[tail_start:]


def trim(body, window, *, reserve=RESERVE):
    """(new_body, dropped). `body` is a parsed chat request. Returns it unchanged when it fits or has no messages."""
    messages = body.get("messages") if isinstance(body, dict) else None
    limit = window - reserve
    if not isinstance(messages, list) or tokens(body) <= limit:
        return body, 0
    head, middle, tail = _split(messages)
    units = _units(middle)
    dropped = 0
    note = {"role": "system", "content": ""}
    while units:
        dropped += len(units.pop(0))
        note["content"] = NOTE.format(n=dropped, window=window)
        kept = head + [note] + [m for u in units for m in u] + tail
        if tokens({**body, "messages": kept}) <= limit:
            break
    if not dropped:
        return body, 0
    return {**body, "messages": head + [note] + [m for u in units for m in u] + tail}, dropped


LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


def loopback_host(value):
    """True when a Host header names this machine. Any other name may be a DNS-rebinding page in a browser."""
    host = (value or "").strip().lower()
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]  # [::1]:11435
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]  # localhost:11435
    return host in LOOPBACK_HOSTS


def patch_show(reply, window):
    """An /api/show reply with every `*.context_length` in model_info capped at the real window."""
    info = reply.get("model_info") if isinstance(reply, dict) else None
    if not isinstance(info, dict):
        return reply
    fixed = {k: (min(v, window) if k.endswith(".context_length") and isinstance(v, int) else v)
             for k, v in info.items()}
    return {**reply, "model_info": fixed}
