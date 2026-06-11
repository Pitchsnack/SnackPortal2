"""Ingress validation floor (D-09): structural/type/sanitization/PII; reject unsafe; safe logging."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from import_service.models import ImportMode, ImportRequest, RawRecord, SourceDescriptor, SourceKind  # noqa: E402
from import_service.validation import ValidationError, validate  # noqa: E402
from doubles import make_service  # noqa: E402


def test_missing_natural_key_rejected() -> None:
    try:
        validate(RawRecord(data={"x": "1"}, source_ref="s"), "record_id")
        assert False, "missing natural key must be rejected"
    except ValidationError:
        pass


def test_pii_is_classified() -> None:
    rec = validate(RawRecord(data={"record_id": "1", "email": "a@b.com", "name": "Bob"}, source_ref="s"), "record_id")
    assert "email" in rec.pii_fields and "name" in rec.pii_fields


def test_control_chars_rejected() -> None:
    try:
        validate(RawRecord(data={"record_id": "1", "x": "bad\x00value"}, source_ref="s"), "record_id")
        assert False, "control characters must be rejected"
    except ValidationError:
        pass


def test_unsupported_type_rejected() -> None:
    try:
        validate(RawRecord(data={"record_id": "1", "x": {"nested": 1}}, source_ref="s"), "record_id")
        assert False, "non-primitive values must be rejected"
    except ValidationError:
        pass


def test_validation_error_is_non_sensitive() -> None:
    try:
        validate(RawRecord(data={"record_id": "1", "x": "leakvalue\x00here"}, source_ref="s"), "record_id")
        assert False, "control chars must be rejected"
    except ValidationError as exc:
        assert "leakvalue" not in str(exc)   # error names the field/reason, never the value


def test_import_rejects_invalid_but_commits_valid_records() -> None:
    svc, provider, _, _, _ = make_service()
    payload = json.dumps([
        {"record_id": "1", "display_name": "A"},
        {"display_name": "B"},                       # missing natural key -> rejected
        {"record_id": "3", "display_name": "C"},
    ])
    req = ImportRequest(
        tenant_id="t1", source=SourceDescriptor(kind=SourceKind.JSON, ref="f", payload=payload),
        mode=ImportMode.ASYNC, operation_key="op1", correlation_id="c", actor_ref="user1",
    )
    status = svc.start_import(req)
    assert status.state == "applied"
    assert status.rejected_count == 1 and status.applied_count == 2
    assert len(provider.tenant_copy_rows("t1")) == 2


if __name__ == "__main__":
    _h.run([
        test_missing_natural_key_rejected,
        test_pii_is_classified,
        test_control_chars_rejected,
        test_unsupported_type_rejected,
        test_validation_error_is_non_sensitive,
        test_import_rejects_invalid_but_commits_valid_records,
    ])
