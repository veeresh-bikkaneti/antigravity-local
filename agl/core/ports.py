"""Ports: the shapes of the world outside the core (HTTP, Ollama, the Hub, subprocess, state, hardware).

Protocol classes only, so Phase 4 can inject the real modules (and tests can inject fakes) without the core
importing them. Every method signature is today's real one, copied from the module named in its docstring;
docs/ARCHITECTURE.md ("Layer contract") keeps this file free of behaviour, imports of typing only.
"""
from typing import Any, Protocol


class HttpJson(Protocol):
    """One JSON entry point over HTTP, as agl.platform.http get_json does it today."""

    def get_json(self, url, *, timeout, headers=None, data=None, opener=None) -> Any:
        """The parsed JSON of the reply. `timeout` has no default on purpose: the caller passes its own.
        `data` is a POST body (a GET when it is None); `opener` as in agl.platform.http._open."""
        ...


class OllamaClient(Protocol):
    """The Ollama server: installed-model details, the service check and the pull, as ollama_models.py
    and run.py's pull do them today."""

    def installed_details(self, base_url=..., opener=None, timeout=3) -> dict:
        """{normalised tag: {"name", "size_gb", "modified_at", "caps"}} or {} when the server does not answer
        (ollama_models.installed_details)."""
        ...

    def lookup(self, details, name) -> Any:
        """The details row for a tag: the exact normalised tag first, then the hf.co short alias
        (ollama_models.lookup)."""
        ...

    def check_service(self, base_url=...) -> bool:
        """True when /api/tags answers; False after a failed attempt to start `ollama serve`
        (run.check_ollama_service)."""
        ...

    def pull(self, tag) -> None:
        """`ollama pull <tag>`: run.py's download, through subprocess.check_call, raising on failure."""
        ...


class HubClient(Protocol):
    """The Hugging Face Hub: repo facts, the file tree, tag vetting and the cached search, as
    model_wizard.hf_repo_info / hf_tree_files / hf_check and hf_search do them today."""

    def hf_repo_info(self, user, repo, timeout=4) -> dict:
        """{'status': 'ok'|'missing'|'unknown', 'gated': bool, 'license': str|None} (model_wizard.hf_repo_info)."""
        ...

    def hf_tree_files(self, user, repo, timeout=6, max_pages=5) -> list:
        """[{'name', 'size'}] for every file in the repo; any failure gives [] (model_wizard.hf_tree_files)."""
        ...

    def hf_check(self, tag, timeout=4) -> tuple:
        """(status, detail) for an hf.co tag: 'ok', 'missing', 'no_quant', 'bad_tag' or 'unknown'
        (model_wizard.hf_check)."""
        ...

    def search_models(self, cache_dir, query=None, pipeline_tag="text-generation", limit=20, **kw) -> tuple:
        """([result dicts], source); cached 24 h, offline gives ([], 'offline') (hf_search.search_models)."""
        ...


class ProcessRunner(Protocol):
    """The subprocess call shapes run.py and hardware.py use today (subprocess.check_call / check_output /
    call / Popen)."""

    def check_call(self, cmd, **kwargs) -> None:
        """A command that must succeed (run.py's venv bootstrap, `ollama pull`, hardware probes)."""
        ...

    def call(self, cmd, **kwargs) -> int:
        """The Windows relaunch into the venv python; the return code is passed to sys.exit (run.bootstrap_venv)."""
        ...

    def check_output(self, cmd, *, text=False, stderr=None, timeout=None) -> Any:
        """Command output as text: `ollama list`, the hardware probes (hardware._nvidia_rows and friends)."""
        ...

    def popen(self, cmd, **kwargs) -> Any:
        """A detached child: `ollama serve` with a loopback OLLAMA_HOST (run.check_ollama_service)."""
        ...


class StateStore(Protocol):
    """State on this disk: the .env file, the upgrade-stay file and the fail ledger, as run.py's .env helpers
    and ledger.py's append/read do them today."""

    def load_env(self) -> None:
        """PROJECT_DIR/.env into os.environ when python-dotenv is installed (run._load_env)."""
        ...

    def update_env_model(self, model_name: str) -> None:
        """Rewrite LOCAL_LLM_MODEL in PROJECT_DIR/.env so the next run starts from this pick
        (run.update_env_model)."""
        ...

    def read_upgrade_state(self) -> dict:
        """The parsed UPGRADE_STATE_FILE, {} when missing or not a dict (run._read_upgrade_state)."""
        ...

    def remember_upgrade_stay(self, current, now=None) -> None:
        """stay_until[current] = now + UPGRADE_STAY_SECONDS, written best-effort
        (run._remember_upgrade_stay)."""
        ...

    def append(self, model_ref, verdict, reason, *, runtime="ollama", harness="probe", evidence_key=None,
               home=None, env=None, now=None, host=None) -> tuple:
        """Record one verdict in ledger.jsonl. Returns (ok, message); never raises (ledger.append)."""
        ...

    def read(self, home=None, env=None) -> list:
        """Every well-formed ledger entry, oldest first (ledger.read)."""
        ...


class HardwareProbe(Protocol):
    """What this PC has right now, as hardware.py's functions do them today. Every probe fails quietly
    to "unknown" (0.0), because inventing numbers is worse than saying we don't know."""

    def get_system_ram_gb(self) -> float:
        """Approximate total RAM in GB; 0.0 means unknown (hardware.get_system_ram_gb)."""
        ...

    def get_free_ram_gb(self) -> float:
        """RAM that is free right now, in GB; 0.0 means unknown (hardware.get_free_ram_gb)."""
        ...

    def get_free_vram_gb(self) -> tuple:
        """(free_vram_gb, gpu_known): the freest GPU, unified memory on Apple Silicon (hardware.get_free_vram_gb)."""
        ...

    def free_disk_gb(self, path) -> tuple:
        """(free_gb, total_gb) of the disk holding `path`; (0.0, 0.0) if unknown (hardware.free_disk_gb)."""
        ...

    def ollama_models_dir(self, env=None, home=None) -> Any:
        """Where Ollama keeps models: OLLAMA_MODELS if set, else ~/.ollama/models (hardware.ollama_models_dir)."""
        ...

    def get_hardware_profile(self) -> dict:
        """{"ram_gb", "vram_gb", "gpu_name"} (hardware.get_hardware_profile)."""
        ...

    def free_resources(self, env=None, home=None) -> dict:
        """Everything the fit rule and the disk gate need, in one dict (hardware.free_resources)."""
        ...
