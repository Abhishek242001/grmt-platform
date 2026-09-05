import logging
import logging.handlers
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging() -> None:
    """Configure root logger once. Never log secrets, tokens, or password fields —
    callers are responsible for keeping sensitive values out of log messages."""
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    if root.handlers:
        return  # avoid duplicate handlers when uvicorn --reload re-imports this module

    formatter = logging.Formatter(_LOG_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        settings.log_file, maxBytes=5_000_000, backupCount=3
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
