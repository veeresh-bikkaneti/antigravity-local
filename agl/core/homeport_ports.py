"""Homeport ports (slice 1): the shapes the app layer needs from the platform layer."""

from typing import Protocol


class OllamaLive(Protocol):
    """Live Ollama facts: agl.platform.ollama and agl.platform.ollama_live."""

    def check_service(self, base_url=...) -> bool:
        """True when {base_url}/api/tags answers 200 (agl.platform.ollama.check_service)."""
        ...

    def loaded_models(self, base_url=..., *, timeout=3, get_json=None) -> list:
        """Rows of /api/ps as five-key dicts, or [] (agl.platform.ollama_live.loaded_models)."""
        ...

    def installed_details(self, base_url=..., opener=None, timeout=3) -> dict:
        """{tag: details} from /api/tags, or {} (agl.platform.ollama.installed_details)."""
        ...


class GpuReader(Protocol):
    """One GPU snapshot: agl.platform.gpu."""

    def read_gpu(self, check_output=..., which=..., on_wsl=None) -> dict:
        """{"util_pct", "vram_used_mb", "vram_total_mb", "temp_c", "power_w", "source"}
        (agl.platform.gpu.read_gpu)."""
        ...


class SettingsStore(Protocol):
    """The saved Homeport settings file: agl.platform.homeport_store."""

    def load(self, path=None) -> dict:
        """Saved settings, or {} (agl.platform.homeport_store.load)."""
        ...

    def save(self, values, path=None) -> None:
        """Write settings atomically (agl.platform.homeport_store.save)."""
        ...
