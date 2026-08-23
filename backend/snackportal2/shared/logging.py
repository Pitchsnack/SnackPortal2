"""Structured, references-only logging.

Logs inherit the references-only discipline that governs audit (IC-013 §10, §21.1 E-5.4):
a log line MUST NOT record a token, credential, DSN, secret, PII, or tenant business
content. That is enforced here rather than trusted to call sites — :func:`log_event`
drops any field whose key matches a prohibited name and refuses any value that is not a
scalar reference, so a caller cannot leak a payload by passing one.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Mapping, Optional

from .correlation import current_correlation_id

# Field names that may never appear in a log record. Matched as substrings, case-folded,
# so ``tenant_dsn``, ``authorization_header`` and ``refresh_token`` are all caught.
_PROHIBITED_FIELD_FRAGMENTS = (
    "authorization",
    "credential",
    "dsn",
    "email",
    "name",
    "password",
    "payload",
    "pii",
    "secret",
    "session",
    "token",
)

# ``*_ref`` fields are the sanctioned reference vocabulary and are allowed even though
# some of them (``display_ref``) contain the substring "name"-adjacent tokens.
_ALWAYS_ALLOWED = frozenset(
    {
        "actor_ref",
        "carrier_ref",
        "correlation_id",
        "principal_ref",
        "record_ref",
        "service",
        "subject_ref",
        "tenant_ref",
    }
)


class _JsonFormatter(logging.Formatter):
    """Render each record as one compact JSON object on a single line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "level": record.levelname,
            "service": getattr(record, "sp2_service", "unknown"),
            "event": record.getMessage(),
        }
        correlation_id = getattr(record, "sp2_correlation_id", "")
        if correlation_id:
            payload["correlation_id"] = correlation_id
        fields = getattr(record, "sp2_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_logging(service: str, level: int = logging.INFO) -> logging.Logger:
    """Return the service logger, installing the JSON handler exactly once.

    Writes to stderr. Uvicorn's own access logging stays **off** by default (IC-013
    §21.1 E-5); enabling it is a per-environment deployment decision, not a code change.
    """
    logger = logging.getLogger("snackportal2." + service)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    return logger


def _is_permitted(key: str, value: Any) -> bool:
    """A field survives only if its name is not prohibited and its value is a scalar."""
    if not isinstance(value, (str, int, float, bool)) and value is not None:
        return False
    if key in _ALWAYS_ALLOWED:
        return True
    folded = key.casefold()
    return not any(fragment in folded for fragment in _PROHIBITED_FIELD_FRAGMENTS)


def redact(fields: Mapping[str, Any]) -> Dict[str, Any]:
    """Drop every prohibited or non-scalar field. Exposed so tests can assert on it."""
    return {key: value for key, value in fields.items() if _is_permitted(key, value)}


def log_event(
    logger: logging.Logger,
    event: str,
    service: str,
    *,
    level: int = logging.INFO,
    correlation_id: Optional[str] = None,
    **fields: Any,
) -> None:
    """Emit one structured, redacted event bound to the current correlation id."""
    logger.log(
        level,
        event,
        extra={
            "sp2_service": service,
            "sp2_correlation_id": correlation_id if correlation_id is not None else current_correlation_id(),
            "sp2_fields": redact(fields),
        },
    )


__all__ = ["configure_logging", "log_event", "redact"]
