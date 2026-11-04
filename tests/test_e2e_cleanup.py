"""e2e.stop must kill the whole process tree (run.py on Windows runs venv python as a child)."""
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e  # noqa: E402

CHAIN = ("import subprocess,sys;"
         "subprocess.call([sys.executable,'-c','import os,time;print(os.getpid(),flush=True);time.sleep(120)'])")


def alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


@unittest.skipUnless(os.name == "nt", "POSIX run.py uses execv, so there is no child chain to orphan")
class StopKillsTree(unittest.TestCase):
    def test_stop_kills_grandchild(self):
        p = subprocess.Popen([sys.executable, "-c", CHAIN], stdout=subprocess.PIPE, text=True)
        child = int(p.stdout.readline())
        self.addCleanup(lambda: subprocess.run(["taskkill", "/F", "/PID", str(child)], capture_output=True))
        e2e.stop(p)
        time.sleep(1)
        self.assertFalse(alive(child), "grandchild still running after stop()")


if __name__ == "__main__":
    unittest.main()
