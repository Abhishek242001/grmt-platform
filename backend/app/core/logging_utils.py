"""
log.txt logger — implements the exact format specified in development_rule.md §3:

    [YYYY-MM-DD HH:MM:SS UTC] [LEVEL] [service] [req-id] message

Plain text, one event per line, copy-paste friendly. Multi-line tracebacks are
fenced with ---BEGIN TRACE--- / ---END TRACE--- so a whole error can be
selected and pasted cleanly. Never logs passwords, raw JWTs, full PDF content,
or full API keys — see development_rule.md §3.3.
"""
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()
_lock = threading.Lock()

_LOG_PATH = Path(settings.log_file_path)
_MAX_BYTES = 20 * 1024 * 1024  # 20MB, per development_rule.md §3.4
_MAX_ROTATED = 3


def _rotate_if_needed():
    if _LOG_PATH.exists() and _LOG_PATH.stat().st_size > _MAX_BYTES:
        for i in range(_MAX_ROTATED - 1, 0, -1):
            src = _LOG_PATH.with_suffix(f".txt.{i}") if i > 1 else _LOG_PATH.with_suffix(".txt.1")
            dst = _LOG_PATH.with_suffix(f".txt.{i + 1}")
            if src.exists():
                src.rename(dst)
        _LOG_PATH.rename(_LOG_PATH.with_suffix(".txt.1"))


def _write(level: str, service: str, req_id: str, message: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] [{level}] [{service}] [{req_id}] {message}\n"
    with _lock:
        try:
            _rotate_if_needed()
            _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass  # never let logging failures break a request
    # also echo to stdout so `uvicorn` console output matches log.txt during dev
    sys.stdout.write(line)


class ServiceLogger:
    """Usage: log = ServiceLogger('backend'); log.info(req_id, 'message')"""

    def __init__(self, service: str):
        self.service = service

    def info(self, req_id: str, message: str):
        _write("INFO", self.service, req_id, message)

    def warn(self, req_id: str, message: str):
        _write("WARN", self.service, req_id, message)

    def error(self, req_id: str, message: str, exc: Exception | None = None):
        _write("ERROR", self.service, req_id, message)
        if exc is not None:
            trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            with _lock:
                with open(_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write("---BEGIN TRACE---\n")
                    f.write(trace)
                    f.write("---END TRACE---\n")


log = ServiceLogger("backend")
