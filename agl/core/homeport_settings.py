"""Homeport settings (slice 1): proposed defaults, validation and merging. Pure: no I/O here."""

import re

# proposed defaults (inferred), confirm in a later slice
DEFAULTS = {
    "start": "demand",
    "port": "auto",
    "keep": "5m",
    "context": None,
    "refresh_s": 1,
    "first_drawer": "island",
    "motion": "auto",
    "theme": "auto",
    "alert_context_pct": 85,
    "alert_gpu_c": 84,
    "alert_spill": "on",
    "log_days": 14,
    "record_prompts": "off",
    "metrics_export": "off",
}

# The bind address is NOT a setting: the server always listens on loopback only.

_KEEP_RE = re.compile(r"^[0-9]+(s|m|h)$")


def _is_int(value):
    """True for real ints only: booleans are not accepted where a number is expected."""
    return isinstance(value, int) and not isinstance(value, bool)


def _choice(key, allowed):
    """Build a validator for a fixed set of strings."""
    def check(raw):
        if isinstance(raw, str) and raw in allowed:
            return True, raw
        return False, f"{key} must be one of: {', '.join(sorted(allowed))}"
    return check


def _int_range(key, lo, hi):
    """Build a validator for a whole number inside [lo, hi]."""
    def check(raw):
        if _is_int(raw) and lo <= raw <= hi:
            return True, raw
        return False, f"{key} must be a whole number from {lo} to {hi}"
    return check


def _check_port(raw):
    """port is "auto" or an integer from 1 to 65535."""
    if raw == "auto":
        return True, "auto"
    if _is_int(raw) and 1 <= raw <= 65535:
        return True, raw
    return False, "port must be 'auto' or a whole number from 1 to 65535"


def _check_keep(raw):
    """keep is a number followed by s, m or h."""
    if isinstance(raw, str) and _KEEP_RE.match(raw):
        return True, raw
    return False, "keep must be a number followed by s, m or h (for example 5m)"


def _check_context(raw):
    """context is null or a whole number of 1 or more."""
    if raw is None:
        return True, None
    if _is_int(raw) and raw >= 1:
        return True, raw
    return False, "context must be a whole number of 1 or more, or null"


def _check_refresh(raw):
    """refresh_s is a real number in [0.5, 10]."""
    if not isinstance(raw, bool) and isinstance(raw, (int, float)) and 0.5 <= raw <= 10:
        return True, raw
    return False, "refresh_s must be a number between 0.5 and 10"


_VALIDATORS = {
    "start": _choice("start", {"demand", "boot"}),
    "port": _check_port,
    "keep": _check_keep,
    "context": _check_context,
    "refresh_s": _check_refresh,
    "first_drawer": _choice("first_drawer", {"island", "dock"}),
    "motion": _choice("motion", {"auto", "on", "off"}),
    "theme": _choice("theme", {"auto", "light", "dark"}),
    "alert_context_pct": _int_range("alert_context_pct", 1, 100),
    "alert_gpu_c": _int_range("alert_gpu_c", 30, 110),
    "alert_spill": _choice("alert_spill", {"on", "off"}),
    "log_days": _int_range("log_days", 1, 365),
    "record_prompts": _choice("record_prompts", {"on", "off"}),
    "metrics_export": _choice("metrics_export", {"on", "off"}),
}


def validate(key, raw):
    """(True, normalized value) when raw is valid for key, else (False, what is wrong)."""
    check = _VALIDATORS.get(key)
    if check is None:
        return False, "unknown setting"
    return check(raw)


def merge(saved) -> dict:
    """DEFAULTS updated with the valid known entries of saved; unknown keys and bad values
    are dropped, so the default stays."""
    out = dict(DEFAULTS)
    if not isinstance(saved, dict):
        return out
    for key, raw in saved.items():
        ok, value = validate(key, raw)
        if ok:
            out[key] = value
    return out
