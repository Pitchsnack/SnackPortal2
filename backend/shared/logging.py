"""Structured logging contract (interface only).

Defines the logging port. Implementations MUST redact secrets and PII; only
references, codes, and non-sensitive fields may be logged (D-14, D-09 ingress).
No concrete logger is provided in Build Phase 1.
"""
from __future__ import annotations

from typing import Any, Protocol


class StructuredLogger(Protocol):
    def info(self, message: str, **fields: Any) -> None: ...
    def warning(self, message: str, **fields: Any) -> None: ...
    def error(self, message: str, **fields: Any) -> None: ...

    # Contract: callers and implementations MUST NOT pass secret values, tokens,
    # raw payloads, or PII in `message` or `fields` — references/codes only.
