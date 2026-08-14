"""Minimal structured logging without sensitive business payloads."""

import json
import logging
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("event", "service", "environment", "release_sha"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_logging(level: str) -> None:
    """Install a process-level JSON log handler once."""

    root = logging.getLogger()
    root.setLevel(level.upper())
    if any(getattr(handler, "_seekandscore_handler", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler._seekandscore_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
