"""Structured, append-only runtime logging for background failures."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path


class JsonLineFormatter(logging.Formatter):
    OPERATIONAL_FIELDS = (
        "event",
        "action",
        "duration_ms",
        "error_code",
        "phase",
        "source",
        "session_id",
        "worker_pid",
        "state",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self.OPERATIONAL_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_runtime_logging(path: str | os.PathLike[str]) -> logging.Logger:
    """Configure VoiceFlow's logger once without altering global app logging."""
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    runtime_logger = logging.getLogger("voiceflow")
    runtime_logger.setLevel(logging.INFO)
    runtime_logger.propagate = False
    for handler in runtime_logger.handlers:
        if getattr(handler, "baseFilename", None) == str(destination):
            return runtime_logger
    handler = logging.FileHandler(destination, encoding="utf-8")
    handler.setFormatter(JsonLineFormatter())
    runtime_logger.addHandler(handler)
    return runtime_logger
