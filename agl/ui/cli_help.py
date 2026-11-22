"""CLI help text for run.py's argument parser.

The ui layer owns terminal text, so the parser in the shell stays thin: it wires the
options and their validation, the sentences a user reads live here.
"""

HELP = {
    "model": "Ollama model to use (pulled if missing)",
    "model_flag": "same as the positional model",
    "serve": "start the web UI + API (needs no Ollama)",
    "host": "with --serve: bind address",
    "port": "with --serve: port (default: a free one)",
    "check_upgrades": (
        "list catalog models that beat your best installed one and fit this PC; "
        "report only, never pulls"
    ),
    "probe": (
        "run one live tool call against the model and record pass or fail "
        "in the local ledger, then exit"
    ),
    "scan_library": (
        "also list models read off ollama.com/library (reads HTML, so it can break; "
        "the curated list stays)"
    ),
    "yes": (
        "skip the menu and every question: use the best installed model, or exit 1 "
        "and print the ollama pull command. Never downloads"
    ),
    "sync_memory": "re-index the memory fabric and exit",
    "plain": "no colour, no art, ASCII only (NO_COLOR does the same)",
    "agent": (
        "coding agent to land in: shell (default, Antigravity SDK), or pi / opencode / "
        "codex / claude pre-configured for your local model"
    ),
    "agent_config_only": "with --agent: write the agent's config, print how to start it, and exit",
    "workspace": (
        "with --agent: the project folder the agent works in (default: the folder you "
        "ran this from, or this repo's workspace/ folder when you run it from here)"
    ),
    "continue_local": (
        "with --agent: start with the prompt that makes the agent read HANDOFF.md and carry on"
    ),
    "coding_apps": (
        "print how to connect VS Code, Continue, terminal agents, Antigravity and "
        "Gemini CLI to your model, then exit"
    ),
    "doctor": (
        "with --agent claude: read-only check for settings that send normal Claude "
        "Code sessions to a local model"
    ),
    "copy_user_settings": (
        "with --agent claude: copy (once) a safe slice of ~/.claude into ~/.claude-local"
    ),
    "resume_from": (
        "with --agent claude: EXPERIMENTAL, fork a Claude Code session into the local model"
    ),
}
