"""The side scripts must use the model run.py saved to .env next to them, never a hard-coded model.

Each script runs from a copy in its own temp folder, from another working folder, with LOCAL_LLM_MODEL removed
from the environment. That way the answer can only come from the .env beside the script.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ["code_agent.py", "agent_with_workspace.py", "test_local.py"]
MESSAGE = "No model chosen yet. Run python run.py first, or pass --model."


def run_script(script_dir, cwd, name):
    env = {k: v for k, v in os.environ.items() if k != "LOCAL_LLM_MODEL"}
    env["PYTHONUTF8"] = "1"
    return subprocess.run([sys.executable, str(Path(script_dir) / name)], cwd=cwd, env=env,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)


class SideScriptModel(unittest.TestCase):
    def setUp(self):
        self.scripts = tempfile.TemporaryDirectory()
        self.addCleanup(self.scripts.cleanup)
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        for name in SCRIPTS + ["task_report.py"]:
            shutil.copy(ROOT / name, Path(self.scripts.name) / name)

    def test_each_script_exits_2_when_no_model_is_chosen(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                r = run_script(self.scripts.name, self.work.name, name)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(MESSAGE, r.stdout)

    def test_a_env_file_in_the_working_folder_is_ignored(self):
        (Path(self.work.name) / ".env").write_text("LOCAL_LLM_MODEL=from-cwd\n", encoding="utf-8")
        for name in SCRIPTS:
            with self.subTest(script=name):
                r = run_script(self.scripts.name, self.work.name, name)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    @unittest.skipUnless(importlib.util.find_spec("dotenv"), "python-dotenv not installed")
    def test_the_env_file_next_to_the_script_supplies_the_model(self):
        (Path(self.scripts.name) / ".env").write_text("LOCAL_LLM_MODEL=saved-by-run-py\n", encoding="utf-8")
        for name in SCRIPTS:
            with self.subTest(script=name):
                r = run_script(self.scripts.name, self.work.name, name)
                self.assertNotIn(MESSAGE, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
