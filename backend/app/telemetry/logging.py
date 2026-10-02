"""Structured JSON logging.

One place to wire logging. Output is single-line JSON so log collectors parse it
directly. It is OpenTelemetry-ready: if a record carries ``trace_id`` / ``span_id``
(or ``otelTraceID`` / ``otelSpanID`` once an OTel logging handler is installed),
they are included automatically — no change needed here.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from logging.config import dictConfig
from typing import Any

from app.core.config import settings

# Attributes present on every stdlib LogRecord; everything else a caller attaches
# via ``logger.info(..., extra={...})`` is treated as a structured field.
_RESERVED: frozenset[str] = frozenset(
    {
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
        "taskName",
    }
)

# Record attributes an OTel logging integration commonly injects.
_TRACE_FIELDS: tuple[tuple[str, str], ...] = (
    ("trace_id", "trace_id"),
    ("span_id", "span_id"),
    ("otelTraceID", "trace_id"),
    ("otelSpanID", "span_id"),
)


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": _dt.datetime.fromtimestamp(record.created, tz=_dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for attr, key in _TRACE_FIELDS:
            value = getattr(record, attr, None)
            if value is not None:
                payload[key] = value

        # User-supplied structured fields (logger.info(..., extra={...})).
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": "app.telemetry.logging.JsonFormatter"}},
            "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
            "root": {"level": settings.log_level.upper(), "handlers": ["console"]},
            "loggers": {
                "uvicorn.access": {"level": "INFO"},
                "sqlalchemy.engine": {"level": "WARNING"},
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
