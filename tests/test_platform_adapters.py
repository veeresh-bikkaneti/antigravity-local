"""Phase 4a, offline: the per-service platform adapters satisfy the core ports.

No network, no Ollama, no subprocess. The adapters are wired with keyword collaborators and platform
defaults (arena A); these tests only check the shapes, so they stay small until Phase 4b adds pull.
"""
import os
import sys
import unittest
from typing import Any, Protocol, runtime_checkable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agl.core.ports as ports  # noqa: E402
from agl.platform import hub  # noqa: E402
from agl.platform import hardware as platform_hardware  # noqa: E402
from agl.platform import ollama as ollama_platform  # noqa: E402
from agl.platform import process  # noqa: E402
from agl.platform import registry  # noqa: E402
from agl.platform import state  # noqa: E402


@runtime_checkable
class _HubClient(ports.HubClient, Protocol):
    """The Hub port, made runtime-checkable so the adapter can be asserted against it without any network."""


class _HubAdapter:
    """agl.platform.hub behind the HubClient shape: the module functions, held as static methods."""

    hf_repo_info = staticmethod(hub.hf_repo_info)
    hf_tree_files = staticmethod(hub.hf_tree_files)
    hf_check = staticmethod(hub.hf_check)
    search_models = staticmethod(hub.search_models)


@runtime_checkable
class _OllamaClient4a(Protocol):
    """The Phase 4a subset of ports.OllamaClient: installed details, the lookup and the service check.
    The pull and the process-start arrive with Phase 4b."""

    def installed_details(self, base_url=..., opener=None, timeout=3) -> dict:
        """{normalised tag: {"name", "size_gb", "modified_at", "caps"}} or {} untold."""
        ...

    def lookup(self, details, name) -> Any:
        """The details row for a tag: the exact normalised tag first, then the hf.co short alias."""
        ...

    def check_service(self, base_url=...) -> bool:
        """True when /api/tags answers; False when it does not."""
        ...


class _OllamaAdapter:
    """agl.platform.ollama behind the 4a subset of the Ollama port."""

    installed_details = staticmethod(ollama_platform.installed_details)
    lookup = staticmethod(ollama_platform.lookup)
    check_service = staticmethod(ollama_platform.check_service)


class HubPort(unittest.TestCase):
    def test_the_hub_adapter_satisfies_the_port(self):
        self.assertIsInstance(_HubAdapter(), _HubClient)


class OllamaPort(unittest.TestCase):
    def test_the_ollama_adapter_satisfies_the_4a_subset(self):
        self.assertIsInstance(_OllamaAdapter(), _OllamaClient4a)

    def test_the_port_still_documents_the_4b_parts(self):
        # "the pull" and the `ollama serve` start are Phase 4b; the port names them until then.
        self.assertIn("pull", ports.OllamaClient.__doc__)
        self.assertIn("serve", ports.OllamaClient.check_service.__doc__)


class RegistryAdapter(unittest.TestCase):
    def test_the_registry_module_exposes_its_three_calls(self):
        self.assertTrue(callable(registry.tag_exists))
        self.assertTrue(callable(registry.registry_reachable))
        self.assertTrue(callable(registry.ollama_registry_size))


@runtime_checkable
class _ProcessRunner(ports.ProcessRunner, Protocol):
    """The ProcessRunner port, made runtime-checkable so the adapter can be asserted against it, no process spawned."""


class _ProcessAdapter:
    """agl.platform.process behind the ProcessRunner shape: the module functions, held as static methods."""

    check_call = staticmethod(process.check_call)
    call = staticmethod(process.call)
    check_output = staticmethod(process.check_output)
    popen = staticmethod(process.popen)


@runtime_checkable
class _StateStore(ports.StateStore, Protocol):
    """The StateStore port, made runtime-checkable so the adapter can be asserted against it, no file touched."""


class _StateAdapter:
    """agl.platform.state behind the StateStore shape: the module functions, held as static methods."""

    load_env = staticmethod(state.load_env)
    update_env_model = staticmethod(state.update_env_model)
    read_upgrade_state = staticmethod(state.read_upgrade_state)
    remember_upgrade_stay = staticmethod(state.remember_upgrade_stay)
    append = staticmethod(state.append)
    read = staticmethod(state.read)


@runtime_checkable
class _HardwareProbe(ports.HardwareProbe, Protocol):
    """The HardwareProbe port, made runtime-checkable so the adapter can be asserted against it, no probe run."""


class _HardwareAdapter:
    """agl.platform.hardware behind the HardwareProbe shape: all eight moved functions, held as static methods."""

    get_system_ram_gb = staticmethod(platform_hardware.get_system_ram_gb)
    _nvidia_rows = staticmethod(platform_hardware._nvidia_rows)
    get_hardware_profile = staticmethod(platform_hardware.get_hardware_profile)
    get_free_ram_gb = staticmethod(platform_hardware.get_free_ram_gb)
    get_free_vram_gb = staticmethod(platform_hardware.get_free_vram_gb)
    ollama_models_dir = staticmethod(platform_hardware.ollama_models_dir)
    free_disk_gb = staticmethod(platform_hardware.free_disk_gb)
    free_resources = staticmethod(platform_hardware.free_resources)


class ProcessPort(unittest.TestCase):
    def test_the_process_adapter_satisfies_the_port(self):
        self.assertIsInstance(_ProcessAdapter(), _ProcessRunner)


class StatePort(unittest.TestCase):
    def test_the_state_adapter_satisfies_the_port(self):
        self.assertIsInstance(_StateAdapter(), _StateStore)


class HardwarePort(unittest.TestCase):
    def test_the_hardware_adapter_satisfies_the_port(self):
        self.assertIsInstance(_HardwareAdapter(), _HardwareProbe)


if __name__ == "__main__":
    unittest.main()
