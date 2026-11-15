"""Copy everything run.py prints into logs/run-<date>.log, so "what did it just say?" has an answer afterwards.

The wrapper hands every other attribute (isatty, encoding, reconfigure) to the real stream, so run.py's
"is this a real terminal?" check still sees the truth. If the log file cannot be opened we just don't log.
"""
import contextlib
import datetime
import os
import sys


class _Tee:
    def __init__(self, stream, log):
        self._stream = stream
        self._log = log

    def write(self, text):
        n = self._stream.write(text)
        try:
            self._log.write(text)
            self._log.flush()
        except Exception:
            pass  # the log is a courtesy; never break the run over it
        return n

    def flush(self):
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
