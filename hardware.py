"""What this PC has right now: free VRAM, free RAM, free disk at the Ollama models folder.

moved, shim until Phase 6: the probes moved verbatim to agl/platform/hardware.py; this module only
re-exports the names so old callers and tests keep working.
"""
import shutil  # kept: old patch targets (hardware.shutil / hardware.sys, same module objects) keep working
import sys

from agl.platform.hardware import (  # moved, shim until Phase 6: every old name still resolves
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
