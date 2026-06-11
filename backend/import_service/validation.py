"""Ingress validation floor (D-09 ingress) — PRD-P5-R2 H.

The mandatory floor applied BEFORE any tenant write: structural + type validation,
injection-safe sanitization, and PII classification. Per-tenant minimize/tokenize is
opt-in and gated by the standing D-08 compliance values (not part of the floor).
Errors are non-sensitive (field name + reason — never field values); no payloads, PII,
or secrets are logged (K5/L). Tenant writes are parameterized via the routed session, so
sanitization is defense-in-depth.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .models import ImportRecord, RawRecord

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE = re.compile(r"\+?\d[\d\s\-]{7,}\d")
_PII_FIELD_NAMES = {"email", "phone", "ssn", "dob", "address", "name", "full_name"}
_MAX_LEN = 10000


class ValidationError(Exception):
    """Non-sensitive validation error (field name + reason; never values)."""


def validate(raw: RawRecord, natural_key_field: str) -> ImportRecord:
    data = raw.data
    # Structural validation: the natural key (per-record idempotency key) must be present.
    if natural_key_field not in data or data[natural_key_field] in (None, ""):
        raise ValidationError(f"missing natural key '{natural_key_field}'")

    fields: Dict[str, Any] = {}
    pii: List[str] = []
    for key, value in data.items():
        # Type validation: only JSON-ish primitives are accepted.
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValidationError(f"unsupported type for field '{key}'")
        if isinstance(value, str):
            if len(value) > _MAX_LEN:
                raise ValidationError(f"field '{key}' exceeds max length")
            # Sanitization: reject control characters (injection-safe).
            if any(ord(c) < 32 and c not in "\t\n\r" for c in value):
                raise ValidationError(f"field '{key}' contains control characters")
        fields[key] = value
        # PII classification (D-09): by field name or value shape.
        if key.lower() in _PII_FIELD_NAMES or (
            isinstance(value, str) and (_EMAIL.search(value) or _PHONE.search(value))
        ):
            pii.append(key)

    return ImportRecord(
        natural_key=str(data[natural_key_field]),
        fields=fields,
        pii_fields=pii,
        source_ref=raw.source_ref,
    )
