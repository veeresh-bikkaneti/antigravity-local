"""What this PC has right now: total and FREE video memory, free RAM, free disk at the Ollama models folder.

Standard library only. Every probe fails quietly to "unknown" (0.0), because inventing numbers is worse than saying
we don't know. Free memory is what matters for fitting a model: a browser or a game can be sitting on your VRAM.

this file lives here; the root hardware.py re-exports these names for old callers.
"""
import math
import os
import shutil
import subprocess
import sys

IS_WIN = sys.platform == "win32"
GB = 1024 ** 3


def get_system_ram_gb():
    """Detect approximate system RAM in GB without external packages. 0.0 means unknown."""
    try:
        if IS_WIN:
            output = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum / 1GB"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            return float(output)
        elif sys.platform == "darwin":
            output = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            return float(output) / GB
        else:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return float(line.split()[1]) / (1024 ** 2)
    except Exception:
        pass
    return 0.0  # unknown: never invent RAM; tier logic then picks the smallest model


def _nvidia_rows(fields):
    """Rows of numbers/strings from nvidia-smi, or [] when it is missing or prints junk."""
    if not shutil.which("nvidia-smi"):
        return []
    try:
        output = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
            text=True, stderr=subprocess.DEVNULL, timeout=10
        ).strip()
    except Exception:
        return []
    return [[c.strip() for c in line.split(",")] for line in output.splitlines() if line.strip()]


def get_hardware_profile():
    """System RAM, GPU name and dedicated VRAM (total), to match the PC build with models."""
    ram_gb = get_system_ram_gb()
    vram_gb = 0.0
    gpu_name = "CPU Only"

    rows = _nvidia_rows("name,memory.total")
    if rows:
        try:
            gpu_name = rows[0][0]
            vram_gb = float(rows[0][1]) / 1024.0
        except (IndexError, ValueError):
            gpu_name, vram_gb = "CPU Only", 0.0
    elif sys.platform == "darwin":
        try:
            cpu_brand = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
            if "Apple" in cpu_brand:
                gpu_name = f"Apple Silicon ({cpu_brand})"
                vram_gb = ram_gb  # unified memory acts as VRAM
        except Exception:
            pass

    return {"ram_gb": ram_gb, "vram_gb": vram_gb, "gpu_name": gpu_name}


def get_free_ram_gb():
    """RAM that is free right now, in GB. 0.0 means unknown."""
    try:
        if IS_WIN:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
                text=True, stderr=subprocess.DEVNULL, timeout=15
            ).strip()
            return float(out) / (1024 ** 2)  # the value is in KB
        if sys.platform == "darwin":
            out = subprocess.check_output(["vm_stat"], text=True, timeout=10)
            page = 4096.0
            pages = 0.0
            for line in out.splitlines():
                if "page size of" in line:
                    page = float(line.split("page size of")[1].split()[0])
                elif line.startswith(("Pages free", "Pages inactive")):
                    pages += float(line.split(":")[1].strip().rstrip("."))
            return pages * page / GB
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return float(line.split()[1]) / (1024 ** 2)
    except Exception:
        pass
    return 0.0


def get_free_vram_gb():
    """(free_vram_gb, gpu_known). Two GPUs: the one with the most free memory, because one card holds the model.
    Apple Silicon: unified memory, so free VRAM is free RAM. Unknown GPU: (0.0, False)."""
    rows = _nvidia_rows("memory.free")
    best = None
    for row in rows:
        try:
            mib = float(row[0])
        except (IndexError, ValueError):
            continue
        if not math.isfinite(mib):  # "nan" and "inf" parse as floats; they are not a reading
            continue
        mib = max(mib, 0.0)
        best = mib if best is None else max(best, mib)
    if best is not None:
        return best / 1024.0, True
    if sys.platform == "darwin":
        free = get_free_ram_gb()
        return free, free > 0
    return 0.0, False


def ollama_models_dir(env=None, home=None):
    """Where Ollama keeps models: OLLAMA_MODELS if set, else .ollama/models under the home folder."""
    env = os.environ if env is None else env
    custom = (env.get("OLLAMA_MODELS") or "").strip()
    if custom:
        return custom
    return os.path.join(home or os.path.expanduser("~"), ".ollama", "models")


def free_disk_gb(path):
    """(free_gb, total_gb) of the disk holding `path`, walking up to a parent that exists. (0.0, 0.0) if unknown."""
    probe = os.path.abspath(path)
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        usage = shutil.disk_usage(probe)
    except Exception:
        return 0.0, 0.0
    return usage.free / GB, usage.total / GB


def free_resources(env=None, home=None):
    """Everything the fit rule and the disk gate need, in one dict."""
    free_vram, gpu_known = get_free_vram_gb()
    models_dir = ollama_models_dir(env, home)
    disk_free, disk_total = free_disk_gb(models_dir)
    return {
        "free_vram_gb": free_vram,
        "gpu_known": gpu_known,
        "free_ram_gb": get_free_ram_gb(),
        "free_disk_gb": disk_free,
        "disk_total_gb": disk_total,
        "models_dir": models_dir,
    }
