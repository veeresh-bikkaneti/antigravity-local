"""GPU readings for Homeport: one nvidia-smi query, parsed into five numbers.

All subprocess goes through agl.platform.process; this module never imports subprocess.
The reader never raises: a missing binary, junk output or a timeout all become Nones.
"""

import shutil

from agl.platform import process

# These field names are [Moderate] confidence, not checked against nvidia-smi --help-query-gpu.
NVIDIA_SMI_FIELDS = "utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"

_KEYS = ("util_pct", "vram_used_mb", "vram_total_mb", "temp_c", "power_w")


def _wsl(on_wsl):
    """Auto-detect WSL from /proc/version when on_wsl is None; a missing file means not WSL."""
    if on_wsl is not None:
        return bool(on_wsl)
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            return "microsoft" in fh.read().lower()
    except Exception:
        return False


def _no_readings(source):
    """The all-None result dict for the given source label."""
    return {"util_pct": None, "vram_used_mb": None, "vram_total_mb": None,
            "temp_c": None, "power_w": None, "source": source}


def read_gpu(check_output=process.check_output, which=shutil.which, on_wsl=None) -> dict:
    """One nvidia-smi snapshot: {"util_pct", "vram_used_mb", "vram_total_mb", "temp_c",
    "power_w", "source"} with float readings or None per field. NEVER raises.

    On WSL the binary is "nvidia-smi.exe", because WSL cannot read GPU load
    (https://docs.nvidia.com/cuda/wsl-user-guide/index.html). Without a binary the
    readings are None and source is "none"; otherwise source is the binary used.
    """
    try:
        binary = "nvidia-smi.exe" if _wsl(on_wsl) else "nvidia-smi"
        if which(binary) is None:
            return _no_readings("none")
        try:
            text = check_output(
                [binary, f"--query-gpu={NVIDIA_SMI_FIELDS}", "--format=csv,noheader,nounits"],
                text=True, stderr=process.DEVNULL, timeout=10,
            )
        except Exception:
            return _no_readings(binary)
        line = ""
        for candidate in text.splitlines():
            if candidate.strip():
                line = candidate
                break
        fields = [part.strip() for part in line.split(",")]
        out = _no_readings(binary)
        for key, raw in zip(_KEYS, fields):
            try:
                out[key] = float(raw)
            except Exception:
                out[key] = None
        return out
    except Exception:
        return _no_readings("none")
