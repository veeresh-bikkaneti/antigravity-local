"""What this PC has right now: free VRAM, free RAM, free disk at the Ollama models folder.

the probes live in agl/platform/hardware.py; this module re-exports the names for old callers.
"""
from agl.platform.hardware import (  # moved to agl.platform.hardware
    GB,
    IS_WIN,
    _nvidia_rows,
    free_disk_gb,
    free_resources,
    get_free_ram_gb,
    get_free_vram_gb,
    get_hardware_profile,
    get_system_ram_gb,
    ollama_models_dir,
)

