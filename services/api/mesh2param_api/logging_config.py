from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """One-line structured service logs with correlation fields."""

    def format(self, record: logging.LogRecord) -> str:
        document: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "requestId": getattr(record, "request_id", None),
            "projectId": getattr(record, "project_id", None),
            "jobId": getattr(record, "job_id", None),
            "phase": getattr(record, "phase", None),
        }
        if record.exc_info:
            document["traceback"] = self.formatException(record.exc_info)
        internal_traceback = getattr(record, "traceback", None)
        if internal_traceback:
            document["traceback"] = internal_traceback
        return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def configure_service_logging(level: str) -> None:
    logger = logging.getLogger("mesh2param_api")
    logger.setLevel(level)
    if not any(getattr(handler, "mesh2param_json", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler.mesh2param_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.propagate = False


__all__ = ["JsonFormatter", "configure_service_logging"]
