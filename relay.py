#!/usr/bin/env python3
"""C2 local relay trial: `python relay.py [--window N] [--port P]`.

Runs a small server on 127.0.0.1 that a coding app such as Copilot can use instead of Ollama. Chat requests
bigger than the window are trimmed (instructions, tools, the goal and the latest messages are kept), and
/api/show reports the real window. Nothing on your machine is changed: you point the app at the relay
yourself, and Ctrl+C stops it.
"""
import argparse
import sys
import time

from agl.core import relay_trim
from agl.platform import config, relay_server

PORT = 11435  # Ollama's own port plus one


def main(argv=None, out=print, wait=None):
    ap = argparse.ArgumentParser(prog="relay.py", description="Trim chat requests to the real window (C2 trial).")
    ap.add_argument("--window", type=int, default=8192, help="the window Ollama loads the model with (default 8192)")
    ap.add_argument("--port", type=int, default=PORT, help=f"the port to listen on (default {PORT})")
    ap.add_argument("--upstream", default=config.ollama_api_base(), help="where Ollama answers")
    args = ap.parse_args(argv)
    if args.window <= relay_trim.RESERVE:
        out(f"[relay] --window must be bigger than {relay_trim.RESERVE}.")
        return 2
    try:
        server = relay_server.serve(args.port, args.upstream, args.window, trim=relay_trim.trim,
                                    patch_show=relay_trim.patch_show, chat_paths=relay_trim.CHAT_PATHS, log=out)
    except OSError as exc:
        out(f"[relay] could not listen on {relay_server.HOST}:{args.port} ({exc}). Try another --port.")
        return 1
    out(f"Relay on http://{relay_server.HOST}:{args.port}, forwarding to {args.upstream}, window {args.window}.")
    out("Point your coding app's Ollama address at it to try it. Nothing was changed for you. Ctrl+C stops it.")
    try:
        if wait:
            wait()
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        out("[relay] stopped.")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
