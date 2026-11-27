"""Ollama service use case (Phase 5b): check service availability and auto-start if needed.

Nothing here writes directly to stdout or accesses the OS by itself: output goes through `out`,
and all system collaborators (process, platform, stage, sleep) are injected through `ports`.
"""
import json

from agl.core.vscode_models import DEFAULT_ENDPOINTS

DEFAULT_OLLAMA_HOSTS = DEFAULT_ENDPOINTS


def _is_tty(stream):
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def _server_urls(base_url, *, ports=None):
    """(ollama root, [candidate /models URLs]) for a LOCAL_LLM_BASE_URL such as http://localhost:1234/v1."""
    default_base = getattr(ports, "config", None).LLM_BASE_URL if (ports and hasattr(ports, "config")) else f"{DEFAULT_ENDPOINTS[0]}/v1"
    base = (base_url or default_base).strip().rstrip("/")
    if base.endswith("/v1"):
        return base[:-3].rstrip("/"), [base + "/models"]
    return base, [base + "/v1/models", base + "/models"]


def list_openai_models(base_url, *, ports=None):
    """Model ids from an OpenAI-compatible GET /models (the `data[].id` list). [] when it does not answer in that shape."""
    http_mod = getattr(ports, "http", None) if ports else None
    if http_mod is None:
        return []
    for url in _server_urls(base_url, ports=ports)[1]:
        body = http_mod.get_text(url, timeout=3)
        if body is None:
            continue
        try:
            data = json.loads(body).get("data")
        except Exception:
            continue
        if isinstance(data, list):
            return [m["id"] for m in data if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"].strip()]
    return []


def _openai_answers(base_url, *, ports=None):
    http_mod = getattr(ports, "http", None) if ports else None
    if http_mod is None:
        return False
    for url in _server_urls(base_url, ports=ports)[1]:
        body = http_mod.get_text(url, timeout=3)
        if body is None:
            continue
        try:
            if isinstance(json.loads(body).get("data"), list):
                return True
        except Exception:
            continue
    return False


def detect_backend(base_url, *, ports=None):
    """Which server answers at LOCAL_LLM_BASE_URL: "ollama" (its own /api/tags), "openai" (an OpenAI-compatible
    GET /models with a `data` list, e.g. LM Studio, llama.cpp, vLLM), or None when neither answers."""
    http_mod = getattr(ports, "http", None) if ports else None
    if http_mod is None:
        return None
    host = _server_urls(base_url, ports=ports)[0]
    if http_mod.get_text(f"{host}/api/tags", timeout=3) is not None:
        return "ollama"
    if _openai_answers(base_url, ports=ports):
        return "openai"
    return None


def is_default_ollama_url(base_url, *, ports=None):
    hosts = set(DEFAULT_OLLAMA_HOSTS)
    if ports and hasattr(ports, "config") and hasattr(ports.config, "OLLAMA_BASE_URL"):
        hosts.add(ports.config.OLLAMA_BASE_URL.lower())
    return _server_urls(base_url, ports=ports)[0].lower() in hosts


def setup_backend(args, *, ports, out):
    """Ensure Ollama or OpenAI-compatible server is answering."""
    base_api = ports.config.llm_base_url()
    ollama_host = base_api.replace("/v1", "").rstrip("/")
    backend = detect_backend(base_api, ports=ports)
    stdin = getattr(ports.sys, "stdin", None) if hasattr(ports, "sys") else None
    stdout = getattr(ports.sys, "stdout", None) if hasattr(ports, "sys") else None
    interactive = _is_tty(stdin) and _is_tty(stdout) and not getattr(args, "yes", False)
    if hasattr(ports, "_SETUP_ONLY"):
        ports._SETUP_ONLY = not interactive
    if backend == "openai":
        ports.stage(2, 5, "SERVER", "use the OpenAI-compatible server you already run")
        out(f"       Found an OpenAI-compatible server at {base_api} (not Ollama). Nothing will be downloaded.")
        if hasattr(ports, "os"):
            ports.os.environ["LOCAL_LLM_BACKEND"] = "openai"
        elif hasattr(ports, "environ_set"):
            ports.environ_set("LOCAL_LLM_BACKEND", "openai")
    else:
        if hasattr(ports, "os"):
            ports.os.environ.pop("LOCAL_LLM_BACKEND", None)
        elif hasattr(ports, "environ_pop"):
            ports.environ_pop("LOCAL_LLM_BACKEND")
        if backend is None and not is_default_ollama_url(base_api, ports=ports):
            out(f"\n❌ Nothing answered at {base_api}: no Ollama (/api/tags) and no OpenAI-compatible /models. "
                "Start your server, or fix LOCAL_LLM_BASE_URL in .env.")
            ports.sys.exit(1)
        if not check_ollama_service(ollama_host, ports=ports, out=out):
            ports.sys.exit(1)
    return base_api, ollama_host, backend, interactive


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
