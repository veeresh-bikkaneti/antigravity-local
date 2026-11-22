"""The picker with badges: embedding-only never picked, tools first, a ledger fail ranks low, offline warns once,
plus the media, library and Hugging Face search rows. Everything is faked: no Ollama, no network, no real home."""
import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import run  # noqa: E402
import hf_search  # noqa: E402
import ledger  # noqa: E402
import model_wizard  # noqa: E402
import ollama_library  # noqa: E402
import probe  # noqa: E402
import test_run  # noqa: E402  (a module import, so its own tests are not collected here)
import agl.app.bootstrap  # noqa: E402
import agl.app.probe  # noqa: E402
import agl.app.server  # noqa: E402
from agl.core import ranking  # noqa: E402
from agl.ui import banner, pick_menu  # noqa: E402
from agl.app import pick  # noqa: E402

HW = {"ram_gb": 128.0, "vram_gb": 16.0, "gpu_name": "RTX"}


def d(name, caps, size_gb=5.0, modified="2026-11-01T00:00:00Z"):
    """One installed model's details, keyed the way ollama_models keys them."""
    key = name if ":" in name.split("/")[-1] else name + ":latest"
    return key, {"name": name, "size_gb": size_gb, "modified_at": modified, "caps": caps}


def details(*items):
    return dict(items)


def ledger_entry(tag, verdict):
    return {"modelRef": tag, "verdict": verdict, "timestampUtc": "2026-11-10T00:00:00Z", "reason": "r"}


class PickBase(unittest.TestCase):
    HW = HW
    sel = test_run.ModelWizardInRun.sel  # the shared fake terminal, hardware and pull

    def setUp(self):
        pick_menu._WARNED.clear()


class EmbeddingOnly(PickBase):
    def test_an_embedding_only_install_is_never_picked_and_the_pull_command_is_printed(self):
        det = details(d("nomic-embed-text:latest", ["embedding"]))
        got, pulls, _ = self.sel({"nomic-embed-text:latest"}, interactive=False, details=det)
        self.assertEqual((got, pulls), (None, []))
        self.assertIn("None of the installed models can drive a coding agent", self.printed)
        self.assertIn("ollama pull qwen2.5-coder:14b", self.printed)

    def test_capabilities_beat_the_name_when_the_name_looks_like_a_chat_model(self):
        det = details(d("mystery:1b", ["embedding"]), d("qwen2.5:14b", ["completion", "tools"]))
        got, pulls, _ = self.sel({"mystery:1b", "qwen2.5:14b"}, interactive=False, details=det)
        self.assertEqual(got, "qwen2.5:14b")

    def test_a_configured_embedding_model_is_ignored_with_a_note(self):
        det = details(d("nomic-embed-text:latest", ["embedding"]), d("qwen2.5:14b", ["completion", "tools"]))
        got, _, _ = self.sel({"nomic-embed-text:latest", "qwen2.5:14b"}, interactive=False, details=det,
                             env="nomic-embed-text:latest")
        self.assertEqual(got, "qwen2.5:14b")
        self.assertIn("embedding or media model, which a coding agent cannot use", self.printed)

    def test_asking_for_an_embedding_model_by_name_is_refused(self):
        det = details(d("nomic-embed-text:latest", ["embedding"]))
        got, pulls, _ = self.sel({"nomic-embed-text:latest"}, interactive=False, details=det,
                                 requested="nomic-embed-text:latest")
        self.assertEqual((got, pulls), (None, []))
        self.assertIn("a coding agent cannot use it", self.printed)

    def test_a_media_only_model_is_never_picked_either(self):
        det = details(d("flux:1", ["image"]))
        got, _, _ = self.sel({"flux:1"}, interactive=False, details=det)
        self.assertIsNone(got)


class Ranking(PickBase):
    def test_a_model_without_tools_ranks_below_one_with_tools_even_with_a_better_name(self):
        det = details(d("qwen3.6:27b", ["completion"], 17.8), d("gemma2:27b", ["completion", "tools"], 15.0))
        got, _, _ = self.sel({"qwen3.6:27b", "gemma2:27b"}, interactive=False, details=det)
        self.assertEqual(got, "gemma2:27b")

    def test_unknown_capabilities_from_an_old_ollama_fall_back_to_the_name_score(self):
        det = details(d("qwen3.6:27b", None, 9.0), d("qwen2.5:14b", None, 9.0))
        got, _, _ = self.sel({"qwen3.6:27b", "qwen2.5:14b"}, interactive=False, details=det)
        self.assertEqual(got, "qwen3.6:27b")  # unknown is not "no tools", so nothing is penalised

    def test_a_ledger_fail_ranks_below_unproven(self):
        det = details(d("qwen3.6:27b", ["completion", "tools"], 9.0), d("qwen2.5:14b", ["completion", "tools"], 9.0))
        got, _, _ = self.sel({"qwen3.6:27b", "qwen2.5:14b"}, interactive=False, details=det,
                             entries=[ledger_entry("qwen3.6:27b", "fail")])
        self.assertEqual(got, "qwen2.5:14b")

    def test_a_model_that_failed_can_still_be_asked_for_and_gets_one_warning_line(self):
        det = details(d("qwen3.6:27b", ["completion", "tools"], 17.8))
        got, _, _ = self.sel({"qwen3.6:27b"}, interactive=False, details=det, requested="qwen3.6:27b",
                             entries=[ledger_entry("qwen3.6:27b", "fail")])
        self.assertEqual(got, "qwen3.6:27b")
        self.assertEqual(self.printed.count("failed a tool-call probe"), 1)

    def test_a_later_pass_clears_the_fail(self):
        det = details(d("qwen3.6:27b", ["completion", "tools"], 9.0), d("qwen2.5:14b", ["completion", "tools"], 9.0))
        entries = [ledger_entry("qwen3.6:27b", "fail"), ledger_entry("qwen3.6:27b", "pass")]
        got, _, _ = self.sel({"qwen3.6:27b", "qwen2.5:14b"}, interactive=False, details=det, entries=entries)
        self.assertEqual(got, "qwen3.6:27b")
        self.assertNotIn("failed a tool-call probe", self.printed)

    def test_an_hf_model_listed_twice_is_one_candidate(self):
        names = ["hf.co/u/m:q4_k_m", "m:q4_k_m"]
        det = details(d("hf.co/u/m:q4_k_m", ["completion", "tools"]))
        pool = pick._installed_candidates(names, det, HW, [], ports=run.build_ports())
        self.assertEqual([c["tag"] for c in pool], ["hf.co/u/m:q4_k_m"])

    def test_fit_for_an_installed_model_uses_total_memory_not_what_is_free_now(self):
        det = details(d("big:1", ["completion"], 13.0))
        pool = pick._installed_candidates(["big:1"], det, {"vram_gb": 16.0, "ram_gb": 128.0}, [], ports=run.build_ports())
        self.assertEqual(pool[0]["fit"], "gpu")  # 13 x 1.2 = 15.6 <= 16, even if a loaded model holds the free VRAM

    def test_a_passed_probe_confirms_a_guessed_tools_badge(self):
        det = details(d("m:1", None))
        pool = pick._installed_candidates(["m:1"], det, HW, [ledger_entry("m:1", "pass")], ports=run.build_ports())
        self.assertEqual(pool[0]["ledger"], "pass")


class MenuRows(PickBase):
    def test_installed_rows_show_badges_after_the_bracket(self):
        det = details(d("qwen2.5:14b", ["completion", "tools", "thinking"]))
        got, _, _ = self.sel({"qwen2.5:14b"}, [""], details=det)
        row = next(l for l in self.printed.splitlines() if "qwen2.5:14b" in l and "tools" in l)
        self.assertIn("tools", row)  # v1.2.5: one word per row; the thinking badge no longer clutters the main list
        self.assertNotIn("thinking", row)

    def test_media_models_are_listed_in_their_own_section_and_never_picked(self):
        media = [{"tag": "x/z-image-turbo", "badges": ("image",), "note": "text to image",
                  "hint": 'Run it yourself with: ollama run x/z-image-turbo "your prompt"'}]
        det = details(d("qwen2.5:14b", ["completion", "tools"]))
        n = None
        # find the media row number from a first dry render, then pick it and press Enter
        with contextlib.redirect_stdout(io.StringIO()):
            rows = model_wizard.build_menu(["qwen2.5:14b"], 16, 128, media=media)
        n = [m["tag"] for m in model_wizard._visible(rows)].index(model_wizard.MEDIA_ROW_TAG) + 1
        got, pulls, _ = self.sel({"qwen2.5:14b"}, [str(n), "1", "", ""], details=det, media=media)
        self.assertEqual((got, pulls), ("qwen2.5:14b", []))
        self.assertIn("Image and video models", self.printed)
        self.assertIn('ollama run x/z-image-turbo "your prompt"', self.printed)

    def test_typing_words_at_the_hf_row_searches_and_a_pick_goes_through_the_download_gate(self):
        rows = [{"repo": "Org/Fast-GGUF", "badges": ("tools?",), "downloads": 5000}]
        menu = model_wizard.build_menu([], 16, 128, recommended=ranking.hardware_tier_model(16.0, 128.0), media=lambda: [])  # run.py passes the lazy loader
        n = len(model_wizard._visible(menu))  # the HF row is last on the main list (an empty machine also shows the "recommended for this PC" row)
        with mock.patch("agl.app.pick.hf_menu_search", return_value=rows):
            got, pulls, _ = self.sel(set(), [str(n), "fast coder", "1"], gate="y")
        self.assertEqual((got, pulls), ("hf.co/org/fast-gguf", [["ollama", "pull", "hf.co/org/fast-gguf"]]))
        self.assertIn("Org/Fast-GGUF  (tools?)", self.printed)
        self.assertEqual(len(self.gate_asked), 1)  # a searched model still asks before downloading


class Offline(PickBase):
    def test_hugging_face_unreachable_warns_exactly_once_for_the_whole_run(self):
        out = io.StringIO()
        with mock.patch.object(hf_search, "fetch_json", return_value=(None, "offline")), \
                mock.patch.object(sys, "platform", "linux"), contextlib.redirect_stdout(out):
            self.assertEqual(pick.hf_menu_search("anything", ports=run.build_ports(), out=banner.out), [])
            pick.get_media_rows("ollama", ports=run.build_ports(), out=banner.out)  # two more searches (images, video)
            pick.hf_menu_search("again", ports=run.build_ports(), out=banner.out)
        self.assertEqual(out.getvalue().count("Could not reach Hugging Face"), 1)

    def test_a_stale_cache_says_so_once_and_still_returns_rows(self):
        out = io.StringIO()
        data = [{"id": "u/r", "pipeline_tag": "text-generation", "downloads": 3}]
        with mock.patch.object(hf_search, "fetch_json", return_value=(data, "stale")), contextlib.redirect_stdout(out):
            rows = pick.hf_menu_search("x", ports=run.build_ports(), out=banner.out)
            pick.hf_menu_search("y", ports=run.build_ports(), out=banner.out)
        self.assertEqual([r["repo"] for r in rows], ["u/r"])
        self.assertEqual(out.getvalue().count("Showing results saved earlier"), 1)

    def test_offline_the_pick_still_uses_the_installed_models(self):
        det = details(d("qwen2.5:14b", ["completion", "tools"]))
        with mock.patch.object(hf_search, "fetch_json", return_value=(None, "offline")):
            got, _, _ = self.sel({"qwen2.5:14b"}, interactive=False, details=det)
        self.assertEqual(got, "qwen2.5:14b")

    def test_the_hf_token_is_passed_only_when_it_is_in_the_environment(self):
        seen = []

        def fake(url, **kw):
            seen.append(kw.get("token"))
            return [], "net"
        with mock.patch.object(hf_search, "fetch_json", side_effect=fake):
            with mock.patch.dict(os.environ, {"HF_TOKEN": "hf_abc"}):
                pick.hf_menu_search("x", ports=run.build_ports(), out=banner.out)
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("HF_TOKEN", None)
                pick.hf_menu_search("y", ports=run.build_ports(), out=banner.out)
        self.assertEqual(seen, ["hf_abc", None])


class MediaAndLibrary(PickBase):
    def test_on_macos_ollama_runs_the_two_x_image_models_and_klein_is_flagged(self):
        with mock.patch.object(sys, "platform", "darwin"):
            rows = pick.get_media_rows("ollama", ports=run.build_ports(), out=banner.out)
        self.assertEqual([r["tag"] for r in rows], ["x/z-image-turbo", "x/flux2-klein"])
        self.assertIn('ollama run x/z-image-turbo "your prompt"', rows[0]["hint"])
        self.assertIn("non-commercial", rows[1]["hint"])
        self.assertNotIn("non-commercial", rows[0]["hint"])

    def test_elsewhere_hf_text_to_image_and_video_repos_are_listed_with_a_runtime_note(self):
        def fake(words, pipeline_tag="text-generation", limit=20):
            return [{"repo": f"org/{pipeline_tag}-{i}", "badges": ("image",)} for i in range(5)]
        with mock.patch.object(sys, "platform", "linux"), mock.patch("agl.app.pick.hf_menu_search", side_effect=fake):
            rows = pick.get_media_rows("ollama", ports=run.build_ports(), out=banner.out)
        self.assertEqual(len(rows), 6)  # three of each kind
        self.assertTrue(all("separate runtime" in r["hint"] for r in rows))
        self.assertEqual(rows[0]["tag"], "huggingface.co/org/text-to-image-0")

    def test_no_media_section_on_another_backend(self):
        self.assertEqual(pick.get_media_rows("openai", ports=run.build_ports(), out=banner.out), [])

    def test_library_rows_only_with_the_flag(self):
        with mock.patch.object(ollama_library, "scan", side_effect=AssertionError("must not scan without the flag")):
            self.assertEqual(pick.get_library_rows(False, ports=run.build_ports(), out=banner.out), [])
        scanned = [{"name": "newmodel", "badges": ("tools",), "sizes": ("7b",), "note": "Fast."}]
        with mock.patch.object(ollama_library, "scan", return_value=scanned):
            rows = pick.get_library_rows(True, ports=run.build_ports(), out=banner.out)
        self.assertEqual(rows, [{"tag": "newmodel", "badges": ("tools",), "note": "sizes 7b: Fast."}])

    def test_an_unreadable_library_page_warns_once_and_changes_nothing(self):
        out = io.StringIO()
        with mock.patch.object(ollama_library, "scan", return_value=[]), contextlib.redirect_stdout(out):
            self.assertEqual(pick.get_library_rows(True, ports=run.build_ports(), out=banner.out), [])
            pick.get_library_rows(True, ports=run.build_ports(), out=banner.out)
        self.assertEqual(out.getvalue().count("--scan-library is fragile"), 1)


class ProbeCommand(unittest.TestCase):
    """python run.py --probe: one live tool call, recorded in a real (temporary) ledger."""
    PASS = {"verdict": "pass", "reason": "read the marker and wrote it back through tools", "tok_s": 12.3, "calls": 2}
    FAIL = {"verdict": "fail", "reason": "no structured tool call", "tok_s": 3.2, "calls": 0}

    def go(self, args=("--probe", "qwen3:8b"), result=None, backend="ollama", env=None, before=None, **patches):
        import tempfile
        out, calls = io.StringIO(), []
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as proj:
            envs = {"ANTIGRAVITY_LOCAL_HOME": home, "LOCAL_LLM_BASE_URL": "http://localhost:11434/v1"}
            envs.update(env or {})
            with mock.patch.dict(os.environ, envs), \
                    mock.patch.object(run, "PROJECT_DIR", proj), \
                    mock.patch("agl.app.server.detect_backend", return_value=backend), \
                    mock.patch.object(probe, "run_probe", side_effect=lambda *a, **k: calls.append((a, k)) or result), \
                    contextlib.redirect_stdout(out):
                if before:
                    before()
                for name, value in patches.items():
                    target = {"get_installed_ollama_models": "agl.platform.ollama.installed_models",
                              "get_installed_details": "agl.platform.ollama.installed_details",
                              "get_hardware_profile": "agl.platform.hardware.get_hardware_profile"}[name]
                    mock.patch(target, value).start()
                try:
                    code = agl.app.probe.run_probe_command(run.parse_args(list(args)), ports=run.build_ports(), out=banner.out)
                finally:
                    mock.patch.stopall()
                entries = ledger.read()
        return code, out.getvalue(), calls, entries

    def test_a_pass_is_recorded_and_exits_zero(self):
        code, text, calls, entries = self.go(result=self.PASS)
        self.assertEqual(code, 0)
        self.assertEqual([(e["modelRef"], e["verdict"], e["harness"], e["runtime"]) for e in entries],
                         [("qwen3:8b", "pass", "probe", "ollama")])
        self.assertEqual(calls[0][0][1], "qwen3:8b")
        self.assertIn("Passed:", text)
        self.assertIn("Speed: 12.3 tok/s", text)

    def test_a_fail_is_recorded_exits_one_and_a_slow_model_is_called_slow(self):
        code, text, _, entries = self.go(result=self.FAIL)
        self.assertEqual(code, 1)
        self.assertEqual((entries[0]["verdict"], entries[0]["reason"]), ("fail", "no structured tool call"))
        self.assertIn("Failed: no structured tool call", text)
        self.assertIn("slow on this PC (3.2 tok/s)", text)

    def test_exactly_five_tokens_a_second_is_not_slow(self):
        _, text, _, _ = self.go(result=dict(self.PASS, tok_s=5.0))
        self.assertNotIn("slow on this PC", text)
        self.assertIn("Speed: 5.0 tok/s", text)

    def test_no_token_count_prints_nothing_about_speed(self):
        _, text, _, _ = self.go(result=dict(self.PASS, tok_s=None))
        self.assertNotIn("tok/s", text)

    def test_a_pass_from_the_last_five_minutes_is_not_repeated(self):
        def earlier_pass():
            ledger.append("qwen3:8b", "pass", "earlier")
        code, text, calls, entries = self.go(result=self.PASS, before=earlier_pass)
        self.assertEqual((code, calls, len(entries)), (0, [], 1))
        self.assertIn("not repeating", text)

    def test_nothing_answering_is_exit_one_and_no_probe(self):
        code, text, calls, entries = self.go(result=self.PASS, backend=None)
        self.assertEqual((code, calls, entries), (1, [], []))
        self.assertIn("Nothing answered", text)

    def test_the_model_comes_from_the_environment_when_not_named(self):
        _, _, calls, _ = self.go(args=("--probe",), result=self.PASS, env={"LOCAL_LLM_MODEL": "from-env:1b"})
        self.assertEqual(calls[0][0][1], "from-env:1b")

    def test_with_no_model_named_the_best_installed_chat_model_is_probed(self):
        det = details(d("nomic-embed-text:latest", ["embedding"]), d("qwen2.5:14b", ["completion", "tools"]))
        _, _, calls, _ = self.go(args=("--probe",), result=self.PASS, env={"LOCAL_LLM_MODEL": ""},
                                 get_installed_ollama_models=lambda base: {"nomic-embed-text:latest", "qwen2.5:14b"},
                                 get_installed_details=lambda base: det, get_hardware_profile=lambda: HW)
        self.assertEqual(calls[0][0][1], "qwen2.5:14b")

    def test_no_model_anywhere_is_exit_one(self):
        code, text, calls, _ = self.go(args=("--probe",), result=self.PASS, env={"LOCAL_LLM_MODEL": ""},
                                       get_installed_ollama_models=lambda base: set(),
                                       get_installed_details=lambda base: {}, get_hardware_profile=lambda: HW)
        self.assertEqual((code, calls), (1, []))
        self.assertIn("No model to probe", text)

    def test_a_ledger_that_cannot_be_written_warns_and_the_exit_code_still_follows_the_verdict(self):
        import tempfile
        with tempfile.NamedTemporaryFile() as blocker:  # a file where the folder should be
            code, text, _, _ = self.go(result=self.PASS, env={"ANTIGRAVITY_LOCAL_HOME": blocker.name + os.sep + "x"})
        self.assertEqual(code, 0)
        self.assertEqual(text.count("Could not write the fail ledger"), 1)

    def test_probe_is_an_early_exit_that_never_touches_the_venv_or_ollama_setup(self):
        with mock.patch.object(agl.app.probe, "run_probe_command", return_value=0) as cmd, \
                mock.patch.object(agl.app.bootstrap, "bootstrap_venv", side_effect=AssertionError("no venv for --probe")), \
                mock.patch.object(agl.app.server, "check_ollama_service", side_effect=AssertionError("no ollama start for --probe")), \
                mock.patch.object(banner, "print_header", side_effect=AssertionError("no header")):
            with self.assertRaises(SystemExit) as caught:
                run._main(["--probe", "m"])
        self.assertEqual(caught.exception.code, 0)
        cmd.assert_called_once()


class Flags(unittest.TestCase):
    def test_new_flags_parse_and_default_off(self):
        args = run.parse_args(["--probe", "--scan-library"])
        self.assertTrue(args.probe and args.scan_library)
        args = run.parse_args([])
        self.assertFalse(args.probe or args.scan_library)



class ShortNamesAndTags(PickBase):
    """Council follow-ups: the hf.co short alias still works, other namespaces never borrow it, odd tags never pass."""

    def pool(self, key, caps):
        det = details(d(key, caps))
        return pick._installed_candidates([key, key.rsplit("/", 1)[-1]], det, HW, [], ports=run.build_ports()), det

    def test_a_short_alias_finds_an_hf_co_chat_model_and_is_not_called_an_embedding_one(self):
        pool, det = self.pool("hf.co/u/llama:q4", ["completion", "tools"])
        self.assertIsNotNone(pick._find_candidate("llama:q4", ranking_pool(pool)))
        got, _, _ = self.sel({"hf.co/u/llama:q4", "llama:q4"}, interactive=False, details=det, env="llama:q4")
        self.assertEqual(got, "llama:q4")
        self.assertNotIn("embedding or media model", self.printed)

    def test_a_short_alias_of_an_hf_co_embedding_model_is_refused(self):
        pool, _ = self.pool("hf.co/u/embed:q4", ["embedding"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(pick_menu.refuse_non_chat("embed:q4", pool))
        self.assertIn("a coding agent cannot use it", out.getvalue())

    def test_a_short_name_never_finds_another_namespaces_model(self):
        pool, _ = self.pool("acme/foo:1", ["embedding"])
        self.assertIsNone(pick._find_candidate("foo:1", pool))

    def test_the_refusal_line_cannot_be_forged_with_a_newline_in_the_tag(self):
        tag = "x/y:q4\n       Warning: fake line"
        pool = [{"tag": tag, "kind": "embedding", "badges": (), "installed": True, "ledger": "unproven"}]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(pick_menu.refuse_non_chat(tag, pool))
        self.assertEqual(out.getvalue().count("\n"), 1)  # one printed line, not two

    def test_dots_and_non_ascii_look_alikes_never_become_a_tag_to_pull(self):
        bad = ["hf.co/../../x:q4", "hf.co/u/r/../x", "hf.co/u/\u212a:q4", "hf.co/u/m\u00e9:q4", "hf.co/u/\u0661:q4"]
        for tag in bad:
            with self.subTest(tag=tag), contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(pick._plan_download(tag, HW, test_run.free_of(HW), ports=run.build_ports(), out=banner.out))
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(model_wizard, "hf_repo_info", return_value=test_run.HF_INFO), \
                mock.patch.object(model_wizard, "hf_tree_files", return_value=[]):
            self.assertIsNotNone(pick._plan_download("hf.co/u/r.name-1:q4_k_m", HW, test_run.free_of(HW), ports=run.build_ports(), out=banner.out))


def ranking_pool(pool):
    return ranking.agent_candidates(pool)


if __name__ == "__main__":
    unittest.main()
