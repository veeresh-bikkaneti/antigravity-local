"""run.bat must switch the console to UTF-8 before anything prints, so emojis render in plain cmd.exe."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.name == "nt", "run.bat is Windows only")
class RunBat(unittest.TestCase):
    def test_header_switches_to_utf8_before_anything_runs(self):
        # Run the real header of run.bat (everything before the first REM step), then probe the result.
        lines = (ROOT / "run.bat").read_text(encoding="utf-8").splitlines()
        header = lines[: next(i for i, l in enumerate(lines) if l.startswith("REM 1."))]
        with tempfile.TemporaryDirectory() as d:
            probe = Path(d) / "probe.bat"
            probe.write_text("\r\n".join(header + ["chcp", "echo PYTHONUTF8=%PYTHONUTF8%", ""]), encoding="ascii")
            env = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
            out = subprocess.run(["cmd", "/c", str(probe)], capture_output=True, text=True, env=env, timeout=60).stdout
        self.assertIn("65001", out)
        self.assertIn("PYTHONUTF8=1", out)

    def test_bat_files_are_forced_to_crlf(self):
        self.assertIn("*.bat text eol=crlf", (ROOT / ".gitattributes").read_text())


if __name__ == "__main__":
    unittest.main()
