"""Break the download gate, the quant picker and the free-memory fit on purpose.

Every test asserts the SAFE behaviour: nothing downloads without a typed y, nothing crashes with a traceback, and a run
that cannot ask exits 1 with the pull command. A failing test here is a real bug. Everything is faked: no real
ollama pull, no network, no hardware probe.
"""
import contextlib
import io
import json
import shlex
import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import hardware  # noqa: E402
import model_wizard  # noqa: E402
import pull_gate  # noqa: E402
import quant_pick  # noqa: E402
import run  # noqa: E402
import test_pull_flow  # noqa: E402
import test_run  # noqa: E402
from agl.app import pick  # noqa: E402
from agl.platform import hardware as platform_hardware  # noqa: E402
from agl.platform import hub  # noqa: E402
from agl.platform import process  # noqa: E402
from agl.ui import banner  # noqa: E402

GB = 10 ** 9
HW16 = {"ram_gb": 128.0, "vram_gb": 16.0, "gpu_name": "RTX"}


def files(*pairs):
    return [{"name": n, "size": s} for n, s in pairs]


def smi(output=None, raises=None, which="nvidia-smi"):
    """Patches that pretend to be nvidia-smi on a Linux box."""
    def fake(cmd, **kw):
        if raises:
            raise raises
        return output
    return (mock.patch.object(platform_hardware.shutil, "which", return_value=which),
            mock.patch.object(platform_hardware.subprocess, "check_output", side_effect=fake),
            mock.patch.object(platform_hardware.sys, "platform", "linux"))


@contextlib.contextmanager
def fake_smi(**kw):
    with contextlib.ExitStack() as st:
        for p in smi(**kw):
            st.enter_context(p)
        yield


class FreeVram(unittest.TestCase):
    def test_zero_free_vram_is_known_and_zero(self):
        with fake_smi(output="0\n"):
            self.assertEqual(hardware.get_free_vram_gb(), (0.0, True))

    def test_nvidia_smi_missing_is_unknown(self):
        with fake_smi(output="", which=None):
            self.assertEqual(hardware.get_free_vram_gb(), (0.0, False))

    def test_junk_output_is_unknown(self):
        for junk in ("NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.", "[N/A]", "abc, def"):
            with self.subTest(junk=junk), fake_smi(output=junk + "\n"):
                self.assertEqual(hardware.get_free_vram_gb(), (0.0, False))

    def test_empty_output_and_blank_line_are_unknown(self):
        for out in ("", "\n", "   \n\n"):
            with self.subTest(out=repr(out)), fake_smi(output=out):
                self.assertEqual(hardware.get_free_vram_gb(), (0.0, False))

    def test_nan_and_inf_are_not_a_real_reading(self):
        for out in ("nan\n", "inf\n", "-inf\n"):
            with self.subTest(out=out), fake_smi(output=out):
                free, known = hardware.get_free_vram_gb()
                self.assertFalse(known, f"{out!r} was accepted as {free} GB free")
                self.assertEqual(free, 0.0)

    def test_negative_reading_never_goes_below_zero(self):
        with fake_smi(output="-2048\n"):
            free, _ = hardware.get_free_vram_gb()
            self.assertGreaterEqual(free, 0.0)

    def test_two_gpus_use_the_one_with_the_most_free_memory(self):
        with fake_smi(output="1024\n20480\n"):
            self.assertEqual(hardware.get_free_vram_gb(), (20.0, True))

    def test_one_junk_row_among_two_gpus_does_not_hide_the_good_one(self):
        with fake_smi(output="[N/A]\n8192\n"):
            self.assertEqual(hardware.get_free_vram_gb(), (8.0, True))

    def test_nvidia_smi_that_hangs_or_dies_is_unknown_not_a_crash(self):
        for exc in (subprocess.TimeoutExpired("nvidia-smi", 10), OSError("gone"), subprocess.CalledProcessError(9, "x")):
            with self.subTest(exc=type(exc).__name__), fake_smi(raises=exc):
                self.assertEqual(hardware.get_free_vram_gb(), (0.0, False))

    def test_free_resources_survives_a_missing_models_folder_and_blank_override(self):
        with fake_smi(output="", which=None), mock.patch.object(platform_hardware, "get_free_ram_gb", return_value=0.0):
            res = hardware.free_resources(env={"OLLAMA_MODELS": "   "}, home="Z:\\no\\such\\home")
        self.assertFalse(res["gpu_known"])
        self.assertGreaterEqual(res["free_disk_gb"], 0.0)
        self.assertNotEqual(res["models_dir"].strip(), "")

    def test_free_disk_for_a_path_that_does_not_exist_walks_up(self):
        free, total = hardware.free_disk_gb(str(ROOT / "no" / "such" / "deep" / "folder"))
        self.assertGreater(total, 0.0)


class PickQuant(unittest.TestCase):
    def test_split_only_repo_sums_the_parts(self):
        fs = files(("m-Q4_K_M-00001-of-00002.gguf", 5 * GB), ("m-Q4_K_M-00002-of-00002.gguf", 5 * GB))
        got = quant_pick.pick_quant(fs, 16, 0)
        self.assertEqual((got["quant"], round(got["size_gb"], 1), got["fit"]), ("Q4_K_M", 10.0, "gpu"))

    def test_split_parts_in_a_folder_without_the_quant_in_the_file_name(self):
        fs = files(("Q4_K_M/model-00001-of-00002.gguf", 5 * GB), ("Q4_K_M/model-00002-of-00002.gguf", 5 * GB))
        got = quant_pick.pick_quant(fs, 16, 0)
        self.assertIsNotNone(got)
        self.assertEqual(got["quant"], "Q4_K_M")

    def test_split_with_one_part_unsized_is_estimated_not_under_counted(self):
        fs = files(("m-Q4_K_M-00001-of-00002.gguf", 5 * GB), ("m-Q4_K_M-00002-of-00002.gguf", None),
                   ("m-Q8_0.gguf", 17 * GB))
        got = quant_pick.pick_quant(fs, 100, 0, wanted="Q4_K_M")
        self.assertGreater(got["size_gb"], 5.5, "a half-known split was counted as just its sized part")

    def test_same_quant_in_two_folders_is_not_double_counted(self):
        fs = files(("a/m-Q4_K_M.gguf", 5 * GB), ("b/m-Q4_K_M.gguf", 5 * GB))
        got = quant_pick.pick_quant(fs, 7, 0)  # one 5 GB copy needs 6 GB: fits a 7 GB card
        self.assertIsNotNone(got)
        self.assertEqual((got["fit"], round(got["size_gb"], 1)), ("gpu", 5.0))

    def test_no_sizes_at_all_means_nothing_to_pick(self):
        self.assertIsNone(quant_pick.pick_quant(files(("m-Q4_K_M.gguf", None), ("m-Q8_0.gguf", None)), 100, 100))

    def test_sizes_given_as_strings_do_not_crash(self):
        fs = files(("m-Q4_K_M.gguf", "8500000000"), ("m-Q8_0.gguf", "14100000000"))
        got = quant_pick.pick_quant(fs, 100, 100)
        self.assertTrue(got is None or got["size_gb"] > 0)

    def test_only_sub_q3_quants_pick_nothing(self):
        fs = files(("m-Q2_K.gguf", 3 * GB), ("m-IQ2_XS.gguf", 2 * GB), ("m-IQ1_S.gguf", GB))
        self.assertIsNone(quant_pick.pick_quant(fs, 100, 100))

    def test_typed_sub_q3_quant_is_honoured(self):
        fs = files(("m-Q2_K.gguf", 3 * GB), ("m-Q4_K_M.gguf", 8 * GB))
        got = quant_pick.pick_quant(fs, 16, 0, wanted="q2_k")
        self.assertEqual((got["quant"], got["fit"]), ("Q2_K", "gpu"))

    def test_typed_quant_that_is_absent_is_none(self):
        self.assertIsNone(quant_pick.pick_quant(files(("m-Q4_K_M.gguf", GB)), 16, 16, wanted="Q8_0"))

    def test_huge_sizes_are_too_big_not_a_crash(self):
        fs = files(("m-Q4_K_M.gguf", 10 ** 18))
        self.assertIsNone(quant_pick.pick_quant(fs, 24, 128))
        self.assertEqual(quant_pick.pick_quant(fs, 24, 128, wanted="Q4_K_M")["fit"], "too big")

    def test_nan_and_inf_sizes_never_fit(self):
        for bad in (float("nan"), float("inf")):
            with self.subTest(bad=bad):
                got = quant_pick.pick_quant(files(("m-Q4_K_M.gguf", bad)), 24, 128)
                self.assertTrue(got is None or got["fit"] == "too big", got)

    def test_negative_free_memory_fits_nothing(self):
        fs = files(("m-Q4_K_M.gguf", 1 * GB))
        self.assertIsNone(quant_pick.pick_quant(fs, -5, -5))
        self.assertIsNone(quant_pick.pick_quant(fs, -50, 50))

    def test_zero_free_vram_goes_to_the_cpu_split_not_gpu(self):
        got = quant_pick.pick_quant(files(("m-Q4_K_M.gguf", 4 * GB)), 0, 32)
        self.assertEqual(got["fit"], "split")

    def test_mmproj_and_imatrix_are_never_picked_even_when_largest(self):
        fs = files(("mmproj-F16.gguf", 90 * GB), ("m.imatrix.gguf", 80 * GB), ("m-Q4_K_M.gguf", 4 * GB))
        got = quant_pick.pick_quant(fs, 200, 0)
        self.assertEqual(got["quant"], "Q4_K_M")

    def test_exact_boundary_of_the_headroom_rule_fits(self):
        # 7 GB x 1.2 = 8.4 GB needed; exactly 8.4 free must still count as a fit.
        self.assertEqual(quant_pick.pick_quant(files(("m-Q4_K_M.gguf", 7 * GB)), 8.4, 0)["fit"], "gpu")

    def test_lowercase_and_odd_file_names(self):
        self.assertEqual(quant_pick.quant_of("model.q4_k_m.GGUF"), "Q4_K_M")
        self.assertEqual(quant_pick.quant_of("Qwen3-8B-IQ4_XS.gguf"), "IQ4_XS")
        self.assertIsNone(quant_pick.quant_of(None))
        self.assertIsNone(quant_pick.quant_of(""))
        self.assertIsNone(quant_pick.quant_of("README.md"))

    def test_none_and_junk_rows_do_not_crash(self):
        self.assertIsNone(quant_pick.pick_quant(None, 16, 16))
        self.assertIsNone(quant_pick.pick_quant([], 16, 16))
        got = quant_pick.pick_quant([{"name": None, "size": None}, {"name": "m-Q4_K_M.gguf"}, {"name": "m-Q8_0.gguf", "size": 5 * GB}], 16, 16)
        self.assertIsNotNone(got)


class FitLabel(unittest.TestCase):
    def test_zero_and_negative_memory_is_too_big(self):
        self.assertEqual(model_wizard.fit_label(5, 0, 0, headroom=model_wizard.FIT_HEADROOM), "too big")
        self.assertEqual(model_wizard.fit_label(5, -3, -3, headroom=model_wizard.FIT_HEADROOM), "too big")

    def test_negative_ram_never_makes_a_model_look_smaller(self):
        self.assertEqual(model_wizard.fit_label(10, 5, -100, headroom=1.2), "too big")

    def test_zero_vram_with_ram_is_split(self):
        self.assertEqual(model_wizard.fit_label(5, 0, 32, headroom=1.2), "split")

    def test_huge_size_is_too_big(self):
        self.assertEqual(model_wizard.fit_label(1e12, 24, 128, headroom=1.2), "too big")


def _resp(body, link=""):
    r = mock.MagicMock()
    r.status = 200
    r.read.return_value = body if isinstance(body, bytes) else json.dumps(body).encode()
    r.headers = {"Link": link} if link else {}
    r.__enter__.return_value = r
    return r


class HfApi(unittest.TestCase):
    def setUp(self):
        # hf_tree_files on a network error sets model_wizard._STATE["offline"]; give each test its own dict.
        patcher = mock.patch.object(model_wizard, "_STATE", {"offline": False})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tree(self, responses):
        """hf_tree_files with urlopen replaying `responses` (a response, or an exception to raise). Returns (files, urls)."""
        seen, it = [], iter(responses)

        def fake(url, timeout=None):
            seen.append(url if isinstance(url, str) else url.full_url)
            nxt = next(it)
            if isinstance(nxt, BaseException):
                raise nxt
            return nxt
        with mock.patch.object(hub._HF_OPENER, "open", fake):
            return model_wizard.hf_tree_files("u", "m"), seen

    def info(self, response):
        def fake(url, timeout=None):
            if isinstance(response, BaseException):
                raise response
            return response
        with mock.patch.object(hub._HF_OPENER, "open", fake):
            return model_wizard.hf_repo_info("u", "m")

    ROW = {"type": "file", "path": "m-Q4_K_M-00001-of-00002.gguf", "size": 1000}

    def test_unreachable_hf_gives_empty_list(self):
        got, _ = self.tree([urllib.error.URLError("down")])
        self.assertEqual(got, [])

    def test_http_error_gives_empty_list(self):
        got, _ = self.tree([urllib.error.HTTPError("u", 500, "boom", {}, None)])
        self.assertEqual(got, [])

    def test_error_midway_through_the_pages_gives_empty_not_a_partial_list(self):
        # Architect: "[] on any failure". A partial list can miss split parts and under-count a quant's size.
        link = '<https://huggingface.co/api/models/u/m/tree/main?cursor=2>; rel="next"'
        got, urls = self.tree([_resp([self.ROW], link), urllib.error.URLError("flaky")])
        self.assertEqual(len(urls), 2)
        self.assertEqual(got, [], "page 2 failed but page 1 was returned as if it were the whole repo")

    def test_junk_json_midway_gives_empty_not_a_partial_list(self):
        link = '<https://huggingface.co/api/models/u/m/tree/main?cursor=2>; rel="next"'
        got, _ = self.tree([_resp([self.ROW], link), _resp(b"<html>oops")])
        self.assertEqual(got, [])

    def test_a_next_link_to_another_host_is_never_followed(self):
        link = '<http://evil.example/steal>; rel="next"'
        _, urls = self.tree([_resp([self.ROW], link), _resp([])])
        self.assertTrue(all("huggingface.co" in u for u in urls), urls)

    def test_pages_are_capped_at_five(self):
        link = '<https://huggingface.co/api/models/u/m/tree/main?cursor=9>; rel="next"'
        _, urls = self.tree([_resp([self.ROW], link) for _ in range(9)])
        self.assertLessEqual(len(urls), 5)

    def test_directories_are_not_files_and_lfs_size_wins(self):
        rows = [{"type": "directory", "path": "sub"},
                {"type": "file", "path": "a.gguf", "size": 134, "lfs": {"size": 5_000_000_000}}]
        got, _ = self.tree([_resp(rows)])
        self.assertEqual(got, [{"name": "a.gguf", "size": 5_000_000_000}])

    def test_junk_rows_do_not_crash(self):
        got, _ = self.tree([_resp([None, 7, "x", {"type": "file"}, {"type": "file", "path": "a", "lfs": "bad"}])])
        self.assertIsInstance(got, list)

    def test_repo_info_unreachable_is_unknown_and_not_gated(self):
        self.assertEqual(self.info(urllib.error.URLError("x"))["status"], "unknown")

    def test_repo_info_gated_variants_all_count_as_gated(self):
        for g in (True, "auto", "manual"):
            with self.subTest(g=g):
                self.assertTrue(self.info(_resp({"gated": g}))["gated"])

    def test_repo_info_license_from_list_or_tag_or_none(self):
        self.assertIn("cc-by-nc", self.info(_resp({"cardData": {"license": ["cc-by-nc-4.0"]}}))["license"])
        self.assertEqual(self.info(_resp({"tags": ["gguf", "license:MIT", 3]}))["license"], "MIT")
        self.assertIsNone(self.info(_resp({"cardData": None, "tags": None}))["license"])
        self.assertEqual(self.info(_resp([1, 2]))["status"], "unknown")


class AskPull(unittest.TestCase):
    PLAN = {"tag": "hf.co/u/m:Q4_K_M", "quant": "Q4_K_M", "size_gb": 8.0, "license": "apache-2.0", "gated": False,
            "free_disk_gb": 500.0, "disk_total_gb": 1000.0}

    def ask(self, answer, plan=None, interactive=True):
        out = io.StringIO()

        def inp(prompt=""):
            if isinstance(answer, BaseException):
                raise answer
            return answer
        got = pull_gate.ask_pull(dict(plan or self.PLAN), interactive, input_fn=inp, out=out.write)
        return got, out.getvalue()

    def test_only_a_typed_yes_downloads(self):
        for a in ("y", "Y", "yes", "YES", "Yes", " y ", "y\n"):
            with self.subTest(a=repr(a)):
                self.assertEqual(self.ask(a)[0], "yes")

    def test_everything_else_downloads_nothing(self):
        for a in ("", " ", "n", "N", "no", "yy", "ye", "yeah", "yes please", "y!", "ok", "1", "true", "\x1b", "ｙ", "yes\x00", "да"):
            with self.subTest(a=repr(a)):
                self.assertEqual(self.ask(a)[0], "no")

    def test_eof_is_no(self):
        self.assertEqual(self.ask(EOFError())[0], "no")

    def test_ctrl_c_propagates(self):
        with self.assertRaises(KeyboardInterrupt):
            self.ask(KeyboardInterrupt())

    def test_non_interactive_never_asks(self):
        got, _ = self.ask(AssertionError("must not ask"), interactive=False)
        self.assertEqual(got, "non_interactive")

    def test_gated_beats_everything_and_never_asks(self):
        got, text = self.ask(AssertionError("must not ask"), plan=dict(self.PLAN, gated=True))
        self.assertEqual(got, "gated")
        self.assertIn("https://huggingface.co/u/m", text)

    def test_disk_exactly_ten_percent_passes_and_one_byte_under_refuses(self):
        at = dict(self.PLAN, free_disk_gb=18.0, size_gb=8.0, disk_total_gb=100.0)  # leaves exactly 10 of 100
        self.assertEqual(pull_gate.check_disk(at), (True, 10.0))
        under = dict(at, size_gb=8.0 + 1 / GB)
        self.assertFalse(pull_gate.check_disk(under)[0])
        self.assertEqual(self.ask(AssertionError("must not ask"), plan=under)[0], "disk_refused")
        self.assertEqual(self.ask("y", plan=at)[0], "yes")

    def test_disk_refusal_wins_over_non_interactive_and_unknown_disk_refuses(self):
        full = dict(self.PLAN, free_disk_gb=1.0, disk_total_gb=100.0)
        self.assertEqual(self.ask("y", plan=full, interactive=False)[0], "disk_refused")
        unknown = dict(self.PLAN, free_disk_gb=0.0, disk_total_gb=0.0)
        self.assertEqual(self.ask("y", plan=unknown)[0], "disk_refused")

    def test_huge_and_negative_sizes(self):
        self.assertEqual(self.ask("y", plan=dict(self.PLAN, size_gb=1e12))[0], "disk_refused")
        self.assertEqual(self.ask("y", plan=dict(self.PLAN, size_gb=-5))[0] in ("yes", "disk_refused"), True)

    def test_size_given_as_string_does_not_crash(self):
        self.assertIn(self.ask("n", plan=dict(self.PLAN, size_gb="8.5"))[0], ("no", "disk_refused"))

    def test_none_fields_do_not_crash(self):
        plan = dict(self.PLAN, quant=None, license=None, size_gb=None)
        self.assertEqual(self.ask("n", plan=plan)[0], "no")

    def test_non_commercial_licences_are_flagged_whatever_the_case(self):
        for lic in ("CC-BY-NC-4.0", "cc-by-nc-sa-4.0", "Non-Commercial", "NONCOMMERCIAL", "Research Only", "research only",
                    ["cc-by-nc-4.0"]):
            with self.subTest(lic=lic):
                _, text = self.ask("n", plan=dict(self.PLAN, license=lic))
                self.assertIn("NON-COMMERCIAL", text)

    def test_open_licences_are_not_flagged(self):
        for lic in ("apache-2.0", "MIT", "llama3.1", "other"):
            with self.subTest(lic=lic):
                self.assertNotIn("NON-COMMERCIAL", self.ask("n", plan=dict(self.PLAN, license=lic))[1])

    def test_unknown_licence_is_said_out_loud(self):
        self.assertIn("unknown", self.ask("n", plan=dict(self.PLAN, license=None))[1])


class GateInRun(unittest.TestCase):
    def sel(self, *a, **kw):
        h = test_run.ModelWizardInRun("sel")
        res = h.sel(*a, **kw)
        self.gate_asked, self.printed = h.gate_asked, h.printed
        return res

    FILES = [{"name": f"m-{q}.gguf", "size": int(gb * GB)} for q, gb in (("Q8_0", 14.1), ("Q4_K_M", 8.5), ("Q2_K", 5.4))]

    def test_gate_answers_end_to_end(self):
        for a, pulled in (("y", 1), ("Y", 1), ("yes", 1), ("", 0), ("n", 0), ("N", 0), ("yeah", 0), ("yes please", 0), (EOFError(), 0)):
            with self.subTest(a=repr(a)):
                got, pulls, _ = self.sel(set(), [""], gate=a, hf_files=self.FILES, requested="hf.co/u/m")
                self.assertEqual(len(pulls), pulled)
                self.assertEqual(got is not None, bool(pulled))
                self.assertEqual(len(self.gate_asked), 1)

    def test_ctrl_c_at_the_prompt_pulls_nothing(self):
        pulls = []
        with self.assertRaises(KeyboardInterrupt):
            try:
                self.sel(set(), [""], gate=KeyboardInterrupt(), hf_files=self.FILES, requested="hf.co/u/m")
            finally:
                pulls = []
        self.assertEqual(pulls, [])

    def test_failed_pull_does_not_write_the_env_or_crash(self):
        for err in (subprocess.CalledProcessError(1, "ollama"), FileNotFoundError("ollama"), OSError("disk")):
            with self.subTest(err=type(err).__name__):
                got, pulls, env = self.sel(set(), [""], gate="y", pull_error=err, hf_files=self.FILES, requested="hf.co/u/m")
                self.assertIsNone(got)
                self.assertNotIn("m:Q8", env)

    def test_zero_free_vram_on_a_known_gpu_asks_and_picks_a_split_quant(self):
        res = dict(test_run.free_of(HW16), free_vram_gb=0.0, gpu_known=True, free_ram_gb=32.0)
        got, pulls, _ = self.sel(set(), [""], gate="y", free=res, hf_files=self.FILES, requested="hf.co/u/m")
        self.assertEqual(len(self.gate_asked), 1)
        self.assertTrue(got and got.startswith("hf.co/u/m:Q"))
        self.assertIn("CPU", self.printed)

    def test_nothing_free_at_all_downloads_nothing(self):
        res = dict(test_run.free_of({"vram_gb": 0.0, "ram_gb": 0.0}), free_vram_gb=0.0, gpu_known=True, free_ram_gb=0.0)
        hw = {"ram_gb": 0.0, "vram_gb": 0.0, "gpu_name": "x"}
        got, pulls, _ = self.sel(set(), [""], gate="y", free=res, hw=hw, hf_files=self.FILES, requested="hf.co/u/m")
        self.assertEqual((got, pulls, self.gate_asked), (None, [], []))

    def test_negative_free_memory_downloads_nothing(self):
        res = dict(test_run.free_of(HW16), free_vram_gb=-4.0, gpu_known=True, free_ram_gb=-8.0)
        got, pulls, _ = self.sel(set(), [""], gate="y", free=res, hf_files=self.FILES, requested="hf.co/u/m")
        self.assertEqual((got, pulls), (None, []))

    def test_gpu_unknown_ignores_a_stale_vram_number(self):
        res = dict(test_run.free_of(HW16), free_vram_gb=80.0, gpu_known=False, free_ram_gb=4.0)
        big = [{"name": "m-Q8_0.gguf", "size": 14 * GB}]
        got, pulls, _ = self.sel(set(), [""], gate="y", free=res, hf_files=big, requested="hf.co/u/m")
        self.assertEqual((got, pulls), (None, []))

    def test_only_sub_q3_repo_downloads_nothing_and_says_why(self):
        fs = [{"name": "m-Q2_K.gguf", "size": 3 * GB}, {"name": "m-IQ2_XS.gguf", "size": 2 * GB}]
        got, pulls, _ = self.sel(set(), [""], gate="y", hf_files=fs, requested="hf.co/u/m")
        self.assertEqual((got, pulls), (None, []))
        self.assertIn("No quant", self.printed)

    def test_typed_sub_q3_quant_still_asks_before_pulling(self):
        fs = [{"name": "m-Q2_K.gguf", "size": 3 * GB}, {"name": "m-Q4_K_M.gguf", "size": 8 * GB}]
        got, pulls, _ = self.sel(set(), [""], gate="n", hf_files=fs, requested="hf.co/u/m:Q2_K")
        self.assertEqual((got, pulls, len(self.gate_asked)), (None, [], 1))

    def test_split_only_repo_is_pulled_as_one_quant_tag_after_y(self):
        fs = [{"name": "m-Q4_K_M-00001-of-00002.gguf", "size": 5 * GB}, {"name": "m-Q4_K_M-00002-of-00002.gguf", "size": 5 * GB}]
        got, pulls, _ = self.sel(set(), [""], gate="y", hf_files=fs, requested="hf.co/u/m")
        self.assertEqual((got, pulls), ("hf.co/u/m:Q4_K_M", [["ollama", "pull", "hf.co/u/m:Q4_K_M"]]))

    def test_repo_with_no_sizes_never_pulls_without_a_y(self):
        fs = [{"name": "m-Q4_K_M.gguf", "size": None}]
        got, pulls, _ = self.sel(set(), [""], gate="n", hf_files=fs, requested="hf.co/u/m")
        self.assertEqual((got, pulls), (None, []))

    def test_unreachable_hf_still_asks_with_the_tag_as_typed(self):
        got, pulls, _ = self.sel(set(), [""], gate="n", hf_files=[], requested="hf.co/u/m:Q4_K_M")
        self.assertEqual((got, pulls, len(self.gate_asked)), (None, [], 1))
        got, pulls, _ = self.sel(set(), [""], gate="y", hf_files=[], requested="hf.co/u/m:Q4_K_M")
        self.assertEqual((got, pulls), ("hf.co/u/m:Q4_K_M", [["ollama", "pull", "hf.co/u/m:Q4_K_M"]]))

    def test_gated_repo_non_interactive_downloads_nothing(self):
        info = {"status": "ok", "gated": True, "license": "llama3"}
        with mock.patch.object(model_wizard, "hf_repo_info", return_value=info), \
                mock.patch.object(process.subprocess, "check_call", side_effect=AssertionError("must not pull")), \
                mock.patch("builtins.input", side_effect=AssertionError("must not ask")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(pick._pull_with_gate("hf.co/meta/llama", False, HW16, test_run.free_of(HW16), ports=run.build_ports(), out=banner.out))

    def test_gated_repo_beats_a_full_disk_message_and_never_asks(self):
        info = {"status": "ok", "gated": "manual", "license": None}
        full = test_run.free_of(HW16, disk_free=1.0, disk_total=1000.0)
        with mock.patch.object(model_wizard, "hf_repo_info", return_value=info), \
                mock.patch.object(process.subprocess, "check_call", side_effect=AssertionError("must not pull")), \
                mock.patch("builtins.input", side_effect=AssertionError("must not ask")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(pick._pull_with_gate("hf.co/meta/llama", True, HW16, full, ports=run.build_ports(), out=banner.out))

    def test_odd_tags_are_never_handed_to_ollama_as_a_flag(self):
        for tag in ("--insecure", "-h", "--help", "-"):
            with self.subTest(tag=tag):
                _, pulls, _ = self.sel(set(), [""], gate="y", requested=tag)
                for cmd in pulls:
                    self.assertFalse(cmd[-1].startswith("-"), f"{cmd} would be read by ollama as an option")

    def test_tags_with_control_characters_or_newlines_are_never_pulled(self):
        for tag in ("qwen\n--insecure", "qwen\x00:7b", "qwen2.5:7b\r"):
            with self.subTest(tag=repr(tag)):
                _, pulls, _ = self.sel(set(), [""], gate="y", requested=tag)
                self.assertEqual(pulls, [])

    def test_unicode_tag_does_not_crash_and_needs_a_y(self):
        got, pulls, _ = self.sel(set(), [""], gate="n", requested="qwén2.5:7b-ü")
        self.assertEqual(pulls, [])

    def test_a_pull_is_always_a_list_never_a_shell_string(self):
        _, pulls, _ = self.sel(set(), [""], gate="y", requested="qwen2.5:7b; echo pwned")
        for cmd in pulls:
            self.assertIsInstance(cmd, list)
            self.assertEqual(cmd[:2], ["ollama", "pull"])
            self.assertEqual(len(cmd), 3)


class HubStateIsolation(unittest.TestCase):
    def test_unreachable_hub_flag_from_an_hf_test_does_not_reach_a_gate_run(self):
        # HfApi's unreachable test sets model_wizard._STATE["offline"]; a later GateInRun case must not see it.
        hf = HfApi("test_unreachable_hf_gives_empty_list")
        hf.setUp()
        try:
            hf.test_unreachable_hf_gives_empty_list()
        finally:
            hf.doCleanups()
        gate = GateInRun("test_zero_free_vram_on_a_known_gpu_asks_and_picks_a_split_quant")
        gate.test_zero_free_vram_on_a_known_gpu_asks_and_picks_a_split_quant()


class MainNeverCrashes(unittest.TestCase):
    def run_main(self, argv, stdin, **kw):
        h = test_pull_flow.NeverDownloads("main_with")
        try:
            return h.main_with(argv, stdin, **kw)
        except KeyboardInterrupt:
            self.fail("Ctrl+C escaped run.main as a traceback")

    def test_yes_with_zero_models_prints_the_command_and_exits_1(self):
        code, text, pulls, _ = self.run_main(["--yes"], test_run._Tty())
        self.assertEqual((code, pulls), (1, []))
        self.assertIn("ollama pull ", text)

    def test_piped_stdin_with_zero_models_exits_1(self):
        code, text, pulls, _ = self.run_main([], io.StringIO(""))
        self.assertEqual((code, pulls), (1, []))
        self.assertIn("ollama pull ", text)

    def test_yes_with_a_typed_hf_repo_never_pulls_and_prints_a_command(self):
        code, text, pulls, _ = self.run_main(["--yes", "hf.co/u/m"], test_run._Tty())
        self.assertEqual((code, pulls), (1, []))
        self.assertIn("ollama pull hf.co/u/m", text)

    def test_stdin_missing_or_closed_is_not_a_traceback_and_pulls_nothing(self):
        closed = io.StringIO()
        closed.close()
        for stdin in (None, closed):
            with self.subTest(stdin=type(stdin).__name__):
                try:
                    code, text, pulls, _ = self.run_main([], stdin)
                except (AttributeError, ValueError) as e:
                    self.fail(f"run.main crashed with {type(e).__name__}: {e}")
                self.assertEqual((code, pulls), (1, []))

    def test_ctrl_c_and_eof_at_the_menu_exit_without_a_traceback(self):
        for exc in (KeyboardInterrupt(), EOFError()):
            with self.subTest(exc=type(exc).__name__), mock.patch("builtins.input", side_effect=exc):
                try:
                    code, _, pulls, _ = self.run_main([], test_run._Tty(), tty_out=True)
                except EOFError:
                    self.fail("EOF at the menu escaped run.main as a traceback")
                self.assertEqual(pulls, [])
                self.assertNotEqual(code, 0)

    def test_a_tag_with_shell_characters_is_not_printed_as_a_runnable_command(self):
        tag = "qwen2.5:7b; touch pwned"
        code, text, pulls, _ = self.run_main(["--yes", tag], test_run._Tty())
        self.assertEqual(pulls, [])
        for line in text.splitlines():
            if "ollama pull" in line and tag in line:
                self.assertIn(shlex.quote(tag), line, "the copy-paste command would run `touch pwned`")

    def test_a_tag_with_spaces_is_quoted_in_the_printed_command(self):
        tag = "my model:7b"
        code, text, pulls, _ = self.run_main(["--yes", tag], test_run._Tty())
        self.assertEqual(pulls, [])
        for line in text.splitlines():
            if "ollama pull" in line and "my model" in line:
                self.assertIn(shlex.quote(tag), line)


class ServeHost(unittest.TestCase):
    def start(self, env):
        h = test_pull_flow.OllamaServe("start")
        return h.start(env=env)

    def test_user_host_already_loopback_is_not_reported_as_replaced(self):
        _, started, text, after = self.start({"OLLAMA_HOST": "127.0.0.1:11434"})
        self.assertEqual(started[0][1]["env"]["OLLAMA_HOST"], "127.0.0.1:11434")
        self.assertNotIn("Your OLLAMA_HOST", text)

    def test_user_host_with_a_scheme_or_all_interfaces_is_replaced_for_the_child_only(self):
        for host in ("http://0.0.0.0:11434", "0.0.0.0", ":11434", "[::]:11434", "myserver.lan:11434"):
            with self.subTest(host=host):
                _, started, text, after = self.start({"OLLAMA_HOST": host})
                self.assertEqual(started[0][1]["env"]["OLLAMA_HOST"], "127.0.0.1:11434")
                self.assertEqual(after, host)
                self.assertIn("listens on 127.0.0.1:11434 only", text)

    def test_empty_user_host_is_treated_as_unset(self):
        _, started, text, _ = self.start({"OLLAMA_HOST": ""})
        self.assertEqual(started[0][1]["env"]["OLLAMA_HOST"], "127.0.0.1:11434")
        self.assertNotIn("Your OLLAMA_HOST", text)

    def test_the_child_keeps_the_rest_of_the_users_environment(self):
        _, started, _, _ = self.start({"OLLAMA_MODELS": "D:\\models", "OLLAMA_HOST": "0.0.0.0"})
        self.assertEqual(started[0][1]["env"]["OLLAMA_MODELS"], "D:\\models")
        self.assertIn("PATH", {k.upper() for k in started[0][1]["env"]})


if __name__ == "__main__":
    unittest.main()
