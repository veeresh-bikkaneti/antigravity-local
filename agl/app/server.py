"""Ollama service use case (Phase 5b): check service availability and auto-start if needed.

Nothing here writes directly to stdout or accesses the OS by itself: output goes through `out`,
and all system collaborators (process, platform, stage, sleep) are injected through `ports`.
"""


def check_ollama_service(base_url, *, ports, out):
    """Check if Ollama is running; if not, attempt to start it."""
    ports.stage(2, 5, "SERVER", "make sure Ollama is answering")

    # 1. Test if already responsive
    if ports.ollama.check_service(base_url=base_url, timeout=3):  # the HTTP ask lives in agl.platform.ollama
        out(f"       Connected to Ollama service at: {base_url}")
        return True

    # 2. Ollama is not responding, check if ollama binary exists to auto-start
    ollama_bin = ports.shutil.which("ollama")
    if not ollama_bin:
        out("\n❌ [ERROR] Ollama is not installed or not in your system PATH.")
        out("   Please install Ollama (free, open-source local LLM engine):")
        if ports.IS_WIN:
            out("   👉 Windows: Download from https://ollama.com/download or run: winget install Ollama.Ollama")
        elif ports.sys.platform == "darwin":
            out("   👉 macOS: Download from https://ollama.com/download or run: brew install ollama")
        else:
            out("   👉 Linux: Run: curl -fsSL https://ollama.com/install.sh | sh")
        out("\n   Once installed, run this command again!\n")
        ports.sys.exit(1)

    out("       Ollama service is not running. Launching 'ollama serve' in background (this PC only)...")
    env_copy = ports.environ_copy() if hasattr(ports, "environ_copy") else {}
    child_env = dict(env_copy, OLLAMA_HOST=ports.LOOPBACK_OLLAMA_HOST)  # child only: our own environment stays as it was
    host = ports.environ_get("OLLAMA_HOST") if hasattr(ports, "environ_get") else child_env.get("OLLAMA_HOST")
    if host and host != ports.LOOPBACK_OLLAMA_HOST:
        out(f"       (Your OLLAMA_HOST is set; the server we start listens on {ports.LOOPBACK_OLLAMA_HOST} only.)")
    try:
        if ports.IS_WIN:
            ports.process.popen(
                ["ollama", "serve"],
                creationflags=ports.process.CREATE_NEW_PROCESS_GROUP | ports.process.DETACHED_PROCESS,
                stdout=ports.process.DEVNULL,
                stderr=ports.process.DEVNULL,
                env=child_env,
            )
        else:
            ports.process.popen(
                ["ollama", "serve"],
                stdout=ports.process.DEVNULL,
                stderr=ports.process.DEVNULL,
                start_new_session=True,
                env=child_env,
            )

        # Wait up to 12 seconds for Ollama to spin up
        for _ in range(12):
            ports.time.sleep(1)
            if ports.ollama.check_service(base_url=base_url, timeout=1):  # the HTTP ask lives in agl.platform.ollama
                out("       Ollama service successfully started.")
                return True
    except Exception as exc:
        out(f"       Warning: Auto-start attempted but got: {exc}")

    out(f"\n⚠️  Please ensure Ollama is running (`ollama serve`) at {base_url} and re-run.\n")
    return False
