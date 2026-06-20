"""Readiness/liveness/version are minimally-disclosing (IC-010 §S)."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from api_gateway import readiness  # noqa: E402

_ALLOWED_KEYS = {"service", "status", "state", "build_phase"}
# A field value must never disclose a database, tenant, host, or topology identifier.
_FORBIDDEN_SUBSTRINGS = ("postgres", "database", "tenant", "dsn", "://", "host", "topology", "schema")


def _assert_minimal(payload: dict) -> None:
    assert set(payload.keys()) <= _ALLOWED_KEYS, f"unexpected disclosing keys: {payload.keys()}"
    for value in payload.values():
        low = str(value).lower()
        for bad in _FORBIDDEN_SUBSTRINGS:
            assert bad not in low, f"readiness payload discloses {bad!r}: {payload}"


def test_liveness_minimal() -> None:
    _assert_minimal(readiness.liveness())


def test_readiness_minimal() -> None:
    _assert_minimal(readiness.readiness())


def test_version_minimal() -> None:
    _assert_minimal(readiness.version())


if __name__ == "__main__":
    _h.run([test_liveness_minimal, test_readiness_minimal, test_version_minimal])
