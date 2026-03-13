from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Formats log records into JSON for structured ingestion."""

    _reserved = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._reserved and not key.startswith("_")
        }
        if extras:
            payload["context"] = extras

        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info))

        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    selected_level = (level or os.getenv("CIPHERFORGE_LOG_LEVEL", "INFO")).upper()
    root = logging.getLogger()
    root.setLevel(selected_level)
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

