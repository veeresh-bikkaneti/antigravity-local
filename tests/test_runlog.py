"""Everything printed during a run also lands in logs/run-<date>.log, and the terminal check still works."""
import datetime
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import runlog  # noqa: E402


class _Tty(io.StringIO):
    def isatty(self):
        return True


class Tee(unittest.TestCase):
    def run_block(self, out, text, today=None):
        real = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as d:
                log_dir = os.path.join(d, "logs")
                with runlog.tee(log_dir, today) as path:
                    print(text)
                    seen_tty = sys.stdout.isatty()
                written = open(path, encoding="utf-8").read() if path else None
                return written, seen_tty, os.path.basename(path or "")
        finally:
            sys.stdout, sys.stderr = real

    def test_lines_land_in_log_and_on_screen(self):
        out = io.StringIO()
        written, _, _ = self.run_block(out, "🧠 [3/4] picking")
        self.assertEqual(out.getvalue(), "🧠 [3/4] picking\n")
        self.assertRegex(written, r"^\d{2}:\d{2}:\d{2} .* \[3/4\] picking\n$")  # the log is stamped; the screen is not

    def test_log_strips_colour_codes_and_the_screen_keeps_them(self):
        out = io.StringIO()
        written, _, _ = self.run_block(out, "\x1b[31mred\x1b[0m text")
        self.assertEqual(out.getvalue(), "\x1b[31mred\x1b[0m text\n")
        self.assertNotIn("\x1b", written)
        self.assertIn("red text", written)

    def test_a_prompt_without_a_newline_still_reaches_the_log(self):
        out = io.StringIO()
        real = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as d:
                with runlog.tee(os.path.join(d, "logs"), datetime.date(2026, 11, 15)) as path:
                    sys.stdout.write("Show the command? [y/N] ")
                    sys.stdout.flush()
                written = open(path, encoding="utf-8").read()
        finally:
            sys.stdout, sys.stderr = real
        self.assertIn("Show the command? [y/N] ", written)

    def test_isatty_is_delegated_to_the_real_stream(self):
        self.assertTrue(self.run_block(_Tty(), "x")[1])
        self.assertFalse(self.run_block(io.StringIO(), "x")[1])

    def test_file_is_named_for_the_day(self):
        _, _, name = self.run_block(io.StringIO(), "x", today=datetime.date(2026, 11, 14))
        self.assertEqual(name, "run-2026-11-14.log")

    def test_streams_are_restored(self):
        before = sys.stdout
        self.run_block(io.StringIO(), "x")
        self.assertIs(sys.stdout, before)

    def test_unwritable_log_dir_does_not_break_the_run(self):
        with tempfile.NamedTemporaryFile() as blocker:  # a file where the folder should be
            out = io.StringIO()
            real = sys.stdout
            sys.stdout = out
            try:
                with runlog.tee(os.path.join(blocker.name, "logs")) as path:
                    print("still printed")
            finally:
                sys.stdout = real
        self.assertIsNone(path)
        self.assertEqual(out.getvalue(), "still printed\n")


if __name__ == "__main__":
    unittest.main()
