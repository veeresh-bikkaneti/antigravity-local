"""Copy everything run.py prints into logs/run-<date>.log, so "what did it just say?" has an answer afterwards.

The screen gets the text exactly as printed. The log gets each line with an HH:MM:SS stamp and colour codes removed.
The wrapper hands every other attribute (isatty, encoding, reconfigure) to the real stream, so run.py's
"is this a real terminal?" check still sees the truth. If the log file cannot be opened we just don't log.
"""
import contextlib
import datetime
import os
import re
import sys


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _stamp_line(line):
    """One log line: HH:MM:SS, then the text with colour codes removed. Blank lines stay blank.
    was _stamp: renamed so one name means one thing (ledger._stamp_epoch stamps an epoch)."""
    clean = _ANSI.sub("", line).rstrip("\r")
    if not clean.strip():
        return ""
    return f"{datetime.datetime.now():%H:%M:%S} {clean}"


class _Tee:
    def __init__(self, stream, log):
        self._stream = stream
        self._log = log
        self._partial = ""

    def write(self, text):
        n = self._stream.write(text)  # the screen gets the text exactly as printed
        try:
            self._partial += text
            while "\n" in self._partial:
                line, self._partial = self._partial.split("\n", 1)
                self._log.write(_stamp_line(line) + "\n")
            self._log.flush()
        except Exception:
            pass  # the log is a courtesy; never break the run over it
        return n

    def flush(self):
        try:
            if self._partial:  # a prompt with no newline (input()) still gets its line in the log
                self._log.write(_stamp_line(self._partial) + "\n")
                self._partial = ""
            self._log.flush()
        except Exception:
            pass
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def log_path(log_dir, today=None):
    day = (today or datetime.date.today()).isoformat()
    return os.path.join(log_dir, f"run-{day}.log")


@contextlib.contextmanager
def tee(log_dir, today=None):
    """Mirror stdout and stderr into the day's log file for the duration of the block."""
    log = None
    try:
        os.makedirs(log_dir, exist_ok=True)
        log = open(log_path(log_dir, today), "a", encoding="utf-8")
    except OSError:
        log = None
    if log is None:
        yield None
        return
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _Tee(real_out, log), _Tee(real_err, log)
    try:
        yield log.name
    finally:
        sys.stdout, sys.stderr = real_out, real_err
        log.close()
