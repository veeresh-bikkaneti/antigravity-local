"""What Ollama knows about the models installed on this machine: size, age and what each can do.

/api/tags lists them (newer servers include `capabilities` right there). Where that field is missing we ask
/api/show once per model. If neither answers, capabilities stay None, which means "unknown", never "none":
an old Ollama must not make every model look tool-less.

the HTTP machinery (requests, caps, the /api/show fallback) lives at
agl/platform/ollama; this file keeps the same names and defaults for old imports.
"""
import json

import model_wizard
from agl.platform import config, http
from agl.platform import ollama as ollama_platform

MAX_SHOW_CALLS = ollama_platform.MAX_SHOW_CALLS  # moved to agl.platform.ollama


def _get_json(opener, url, timeout, data=None):
    # moved to agl.platform.ollama
    return ollama_platform._get_json(opener, url, timeout, data=data)


def _caps(value):
    """Known-type entries only. A non-empty list with nothing usable is unknown (None), not an empty list."""
    # moved to agl.platform.ollama
    return ollama_platform._caps(value)


def installed_details(base_url=config.OLLAMA_BASE_URL, opener=None, timeout=3):
    """{normalised tag: {"name", "size_gb", "modified_at", "caps"}}. {} when the server does not answer."""
    # moved to agl.platform.ollama
    return ollama_platform.installed_details(base_url, opener=opener, timeout=timeout)


def lookup(details, name):
    """The details for a tag: the exact normalised tag first.

    A short name (m:q4) may find an hf.co/ model (hf.co/u/m:q4), because run.py
    lists that short alias. It never finds a model in any other namespace:
    acme/foo:1 does not answer to foo:1.
    """
    # moved to agl.platform.ollama
    return ollama_platform.lookup(details, name)
