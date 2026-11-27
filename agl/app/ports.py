"""The one explicit ports object for the app layer (Phase 6e, task 1a): AppPorts.

agl.app may not import agl.platform, agl.ui or the banned stdlib modules (.importlinter; the
Layer contract in docs/ARCHITECTURE.md), so everything from those packages arrives through
the constructor. Everything the app layer MAY import (stdlib, agl.core, the root modules and
the agl.app siblings) is imported here and shared as a plain module attribute, so
mock.patch.object on the owner module bites. The Protocol shapes this object satisfies are
documented in agl/core/ports.py.

Function attributes are @property objects reading the owner module attribute at call time,
so a patched owner (banner, pick_menu, hardware, ollama, ledger, ranking, agl.app.pick) still
bites. Nothing here prints: the one warning goes through the injected `out`.
"""
import os
import shutil
import sys
import time

import agent_setup
import coding_apps
import download_size
import handoff
import ledger
import model_wizard
import probe
import pull_gate
import quant_pick
import runlog
import task_report
from agl.app import agent, pick, probe as app_probe, server
from agl.core import capabilities, ranking


def _noop(*args, **kwargs):
    """The default injected callable (`out`, `index_memory`): swallow everything, return None."""
    return None


class AppPorts:
    """One ports object for every app-layer use case; the shapes live in agl/core/ports.py.

    The constructor receives ONLY what import-linter forbids agl.app from importing - the ui
    modules (banner, pick_menu) and the platform modules (config, hardware, ollama, process,
    state) - plus the shell state: project_dir, env_file, upgrade_state_file, setup_only, out,
    index_memory, claim_store, open_claim_store, web_search and step_io. run.py wires the real modules in.
    """

    def __init__(self, banner, pick_menu, config, hardware, ollama, process, state, http, *,
                 project_dir, env_file, upgrade_state_file, setup_only=False, out=None,
                 index_memory=None, claim_store=None, open_claim_store=None, web_search=None,
                 step_io=None):
        self._banner = banner
        self.pick_menu = pick_menu
        self.config = config
        self._hardware = hardware
        self.ollama = ollama
        self.process = process
        self._state = state
        self.http = http
        self.state = state
        self.coding_apps = coding_apps
        self.handoff = handoff
        self.PROJECT_DIR = project_dir
        self._env_file = env_file
        self._upgrade_state_file = upgrade_state_file
        self._SETUP_ONLY = setup_only
        self._out = out if out is not None else _noop
        self.index_memory = index_memory if index_memory is not None else _noop
        self.claim_store = claim_store
        self.open_claim_store = open_claim_store
        self.web_search = web_search
        self.step_io = step_io  # agl/platform/step_io.py: checkpoint, git guard, test command (C4)
        self.os = os
        self.sys = sys
        self.shutil = shutil
        self.time = time
        self.capabilities = capabilities
        self.ranking = ranking
        self.pull_gate = pull_gate
        self.quant_pick = quant_pick
        self.task_report = task_report
        self.model_wizard = model_wizard
        self.ledger = ledger
        self.download_size = download_size
        self.probe = probe
        self.runlog = runlog
        self.agent_setup = agent_setup

    # -- agl.ui.banner, read at call time -------------------------------------
    @property
    def stage(self):
        return self._banner.stage

    @property
    def level_clear(self):
        return self._banner.level_clear

    @property
    def context_check(self):
        return self._banner.context_check

    @property
    def print_header(self):
        return self._banner.print_header

    @property
    def _FACTS(self):
        default = {"model": "unknown", "size": "unknown", "source": "catalog"}
        return getattr(self._banner, "_FACTS", default)

    # -- agl.ui.pick_menu ------------------------------------------------------
    @property
    def _refuse_non_chat(self):
        return self.pick_menu.refuse_non_chat

    @property
    def _ledger_warning(self):
        return self.pick_menu.ledger_warning

    @property
    def _hf_tag_ok(self):
        return self.pick_menu.hf_tag_ok

    # -- agl.platform.hardware -------------------------------------------------
    @property
    def get_hardware_profile(self):
        return self._hardware.get_hardware_profile

    @property
    def get_free_resources(self):
        return self._hardware.free_resources

    # -- agl.platform.ollama ---------------------------------------------------
    @property
    def get_installed_ollama_models(self):
        return self.ollama.installed_models

    @property
    def get_installed_details(self):
        return self.ollama.installed_details

    # -- root ledger -----------------------------------------------------------
    @property
    def get_ledger_entries(self):
        return self.ledger.read

    # -- agl.core.ranking (the scoring helpers moved out of run.py) ------------
    @property
    def get_model_capability_score(self):
        return self.ranking.get_model_capability_score

    @property
    def capability_rank_key(self):
        return self.ranking.capability_rank_key

    @property
    def hardware_tier_model(self):
        return self.ranking.hardware_tier_model

    # -- agl.app.pick ----------------------------------------------------------
    @property
    def _installed_candidates(self):
        return pick._installed_candidates

    @property
    def _printable_tag(self):
        return pick._printable_tag

    # -- names the old shell ports resolved from run.py globals ------------------
    @property
    def is_model_installed(self):
        return pick.is_model_installed

    @property
    def get_media_rows(self):
        return pick.get_media_rows

    @property
    def get_library_rows(self):
        return pick.get_library_rows

    @property
    def hf_menu_search_sized(self):
        return pick.hf_menu_search_sized

    @property
    def get_installed_info(self):
        return self.ollama.installed_info

    @property
    def UPGRADE_STATE_FILE(self):
        return self._upgrade_state_file

    @property
    def HEADER_FLAG(self):
        return self._banner.HEADER_FLAG

    @property
    def _remember_upgrade_stay(self):
        fn = getattr(pick, "_remember_upgrade_stay", None)
        if fn is not None:
            return fn
        return lambda current, now=None: self._state.remember_upgrade_stay(current, now=now, path=self._upgrade_state_file)

    # -- os wrappers, read at call time ----------------------------------------
    @property
    def environ_get(self):
        return self.os.environ.get

    @property
    def environ_set(self):
        return self.os.environ.__setitem__

    @property
    def environ_pop(self):
        return self.os.environ.pop

    def environ_copy(self):
        return dict(self.os.environ)

    @property
    def path_join(self):
        return self.os.path.join

    @property
    def makedirs(self):
        return self.os.makedirs

    # -- knobs ------------------------------------------------------------------
    @property
    def IS_WIN(self):
        return self.sys.platform == "win32"

    @property
    def LOOPBACK_OLLAMA_HOST(self):
        return self.config.LOOPBACK_OLLAMA_HOST

    @property
    def MAX_SHELL_FAILURES(self):
        return agent.MAX_SHELL_FAILURES

    # -- app use cases that need ports=self / out --------------------------------
    def detect_backend(self, url):
        return server.detect_backend(url, ports=self)

    def is_default_ollama_url(self, url):
        return server.is_default_ollama_url(url, ports=self)

    def list_openai_models(self, url):
        return server.list_openai_models(url, ports=self)

    def check_ollama_service(self, host):
        return server.check_ollama_service(host, ports=self, out=self._out)

    def check_or_update_memory(self, *, ports=None, out=None):
        return app_probe.check_or_update_memory(ports=ports or self, out=out or self._out)

    def _load_env(self):
        self._state.load_env(self._env_file)

    def update_env_model(self, model_name):
        exc = self._state.update_env_model(model_name, env_file=self._env_file)
        if exc is not None:
            self._out(f"Couldn't update .env: {exc}")

    def agent_sdk(self):
        sdk = self.sys.modules.get("google.antigravity")
        return sdk or getattr(__import__("google.antigravity"), "antigravity", None)

    def complete(self, system, user):
        """One local chat completion for the claim verifier. Never pulls a model."""
        url = self.config.llm_base_url().rstrip("/") + "/chat/completions"
        model, note = self.ollama.verifier_model(
            self.os.environ, base_url=self.config.ollama_api_base(self.os.environ))
        if note:
            self._out(note)
        reply = self.ollama.chat_json(url, _chat_body(model, system, user))
        return _chat_text(reply)


def _chat_body(model, system, user):
    """The chat-completions body. stream is off so the reply is one JSON object."""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }


def _chat_text(reply):
    """The assistant string, or empty when the payload is not a chat completion."""
    try:
        content = reply["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    if isinstance(content, str):
        return content
    return ""
