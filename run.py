#!/usr/bin/env python3
"""Google Antigravity Local: 1-Command Plug & Play Bootstrap (write_to_file)."""

import argparse
import os
import sys

import memory
import runlog
from agl.app import agent, bootstrap, pick, ports as app_ports, probe as probe_app, server
from agl.platform import config, hardware, http, ollama, process, state
from agl.ui import banner, pick_menu
from agl.ui.cli_help import HELP as _HELP

banner.setup_console()
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
UPGRADE_STATE_FILE = os.path.join(PROJECT_DIR, ".antigravity_upgrade_state.json")
_SETUP_ONLY = False

def build_ports():
    """One explicit ports object per call: run globals are read here, at call time."""
    from agl.platform import claim_store, web_search
    return app_ports.AppPorts(
        banner,
        pick_menu,
        config,
        hardware,
        ollama,
        process,
        state,
        http,
        project_dir=PROJECT_DIR,
        env_file=os.path.join(PROJECT_DIR, ".env"),
        upgrade_state_file=UPGRADE_STATE_FILE,
        setup_only=_SETUP_ONLY,
        out=banner.out,
        index_memory=memory.index_for_probe,
        claim_store=claim_store.ClaimStore(os.path.join(PROJECT_DIR, ".claim_cache.sqlite")),
        web_search=web_search,
    )

def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Plug-and-play bootstrap for Antigravity with a local Ollama model."
    )
    add = ap.add_argument
    add("model", nargs="?", help=_HELP["model"])
    add("--model", dest="model_flag", metavar="TAG", help=_HELP["model_flag"])
    add("--serve", action="store_true", help=_HELP["serve"])
    add("--host", help=_HELP["host"])
    add("--port", type=int, help=_HELP["port"])
    add("--check-upgrades", action="store_true", help=_HELP["check_upgrades"])
    add("--probe", action="store_true", help=_HELP["probe"])
    add("--scan-library", action="store_true", help=_HELP["scan_library"])
    add("-y", "--yes", action="store_true", help=_HELP["yes"])
    add("--sync-memory", action="store_true", help=_HELP["sync_memory"])
    add("--plain", action="store_true", help=_HELP["plain"])
    add(
        "--agent",
        choices=["shell", "pi", "opencode", "codex", "claude"],
        default="shell",
        help=_HELP["agent"],
    )
    add("--agent-config-only", action="store_true", help=_HELP["agent_config_only"])
    add("--workspace", metavar="PATH", help=_HELP["workspace"])
    add("--continue-local", action="store_true", help=_HELP["continue_local"])
    add("--coding-apps", action="store_true", help=_HELP["coding_apps"])
    add("--doctor", action="store_true", help=_HELP["doctor"])
    add("--copy-user-settings", action="store_true", help=_HELP["copy_user_settings"])
    add("--resume-from", metavar="ID|latest", help=_HELP["resume_from"])
    args = ap.parse_args(argv)
    if args.model and args.model_flag and args.model != args.model_flag:
        ap.error("give the model once: python run.py <tag> or --model <tag>")
    args.model = args.model_flag or args.model
    shell_flags = (
        ("--workspace", args.workspace),
        ("--agent-config-only", args.agent_config_only),
        ("--continue-local", args.continue_local),
    )
    for flag, on in shell_flags:
        if on and args.agent == "shell":
            ap.error(f"{flag} needs --agent pi, opencode, codex or claude")
    claude_flags = (
        ("--doctor", args.doctor),
        ("--copy-user-settings", args.copy_user_settings),
        ("--resume-from", args.resume_from),
    )
    for flag, on in claude_flags:
        if on and args.agent != "claude":
            ap.error(f"{flag} needs --agent claude")
    if args.resume_from and args.continue_local:
        ap.error("--resume-from and --continue-local do different things; pick one")
    return args

def _dispatch_simple(args, ports):
    if args.coding_apps:
        import coding_apps

        backend = "openai" if ports.environ_get("LOCAL_LLM_BACKEND") == "openai" else "ollama"
        model = args.model or ports.environ_get("LOCAL_LLM_MODEL") or "<your-model>"
        banner.safe_print(
            "\n".join(coding_apps.lines(model, config.llm_base_url(), backend)), out=banner.out
        )
        return True
    if args.doctor:
        import agent_setup

        return agent_setup.claude_doctor() or True
    if args.probe:
        sys.exit(probe_app.run_probe_command(args, ports=ports, out=banner.out))
    if args.check_upgrades:
        sys.exit(pick.run_check_upgrades(ports=ports, out=banner.out))
    if args.sync_memory:
        try:
            memory.cmd_sync(argparse.Namespace())
        except Exception as exc:
            banner.out(f"Error syncing memory: {exc}")
        return True
    return False


def _run_serve(args):
    if not args.serve:
        return False
    import serve

    argv = ["--host", args.host] if args.host else []
    argv += ["--port", str(args.port)] if args.port is not None else []
    return serve.main(argv) or True


def _run_shell(model, base_api, ports):
    import asyncio

    try:
        result = agent.run_agent(model, base_api, ports=ports, out=banner.out, input_fn=input)
        if asyncio.iscoroutine(result):
            asyncio.run(result)
    except KeyboardInterrupt:
        banner.out("\n\n👋 Goodbye!\n")
        sys.exit(0)


def _main(argv=None):
    raw = sys.argv[1:] if argv is None else list(argv)
    if raw and raw[0] == "handoff":
        import handoff

        sys.exit(handoff.main(raw[1:]))
    args, ports = parse_args(argv), build_ports()
    if _dispatch_simple(args, ports):
        return
    ports.print_header()
    if not bootstrap.is_in_venv():
        bootstrap.bootstrap_venv(ports=ports, out=banner.out)
        return
    if _run_serve(args):
        return
    setup = server.setup_backend(args, ports=ports, out=banner.out)
    if setup is None:
        sys.exit(1)
    base_api, host, backend, interactive = setup
    try:
        if backend == "openai":
            model = pick_menu.select_openai_model(
                base_api, args.model, ports=ports, out=banner.out, interactive=interactive
            )
        else:
            ask = lambda *a, **k: pick_menu.ask_which_model(*a, ports=ports, out=banner.out, **k)
            model = pick.select_and_pull_model(
                host,
                args.model,
                interactive=interactive,
                scan_library=args.scan_library,
                ports=ports,
                out=banner.out,
                ask=ask,
                stage=banner.stage,
            )
    except KeyboardInterrupt:
        banner.out("\nStopped with Ctrl+C. Nothing was saved. Run python run.py to start again.")
        sys.exit(130)
    if not model:
        sys.exit(1)
    agent.handle_agent(args, model, base_api, interactive, ports=ports, out=banner.out)
    probe_app.check_or_update_memory(ports=ports, out=banner.out)
    _run_shell(model, base_api, ports)


def main(argv=None):
    state.load_env(os.path.join(PROJECT_DIR, ".env"))
    if os.environ.get("ANTIGRAVITY_NO_RUN_LOG"):
        return _main(argv)
    with runlog.tee(os.path.join(PROJECT_DIR, "logs")):
        return _main(argv)


if __name__ == "__main__":
    main()
