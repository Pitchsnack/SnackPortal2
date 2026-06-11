"""Readiness (three-state, disclosure-safe) + schema compatibility (detect-only)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.readiness import ReadinessFramework  # noqa: E402
from control_plane.records import SchemaCompatState  # noqa: E402
from control_plane.schema_compat import SchemaCompatibilityChecker  # noqa: E402
from shared.health import GlobalReadiness  # noqa: E402


def test_three_readiness_states() -> None:
    r = ReadinessFramework()
    assert r.evaluate(phase1_active=False, control_store_reachable=True, schema_pass=True).state is GlobalReadiness.NOT_READY
    assert r.evaluate(phase1_active=True, control_store_reachable=True, schema_pass=True).state is GlobalReadiness.READY
    assert r.evaluate(phase1_active=True, control_store_reachable=True, schema_pass=True, degraded=True).state is GlobalReadiness.DEGRADED


def test_readiness_report_discloses_nothing_sensitive() -> None:
    r = ReadinessFramework()
    for rep in (
        r.evaluate(phase1_active=False, control_store_reachable=True, schema_pass=True),
        r.evaluate(phase1_active=True, control_store_reachable=True, schema_pass=True, degraded=True),
    ):
        low = rep.detail.lower()
        for leak in ("tenant", "database", "secret", "dsn", "host"):
            assert leak not in low


def test_schema_states_and_readiness_mapping() -> None:
    c = SchemaCompatibilityChecker(1, 1)
    assert c.check(1) is SchemaCompatState.PASS
    assert c.check(2) is SchemaCompatState.VERSION_MISMATCH
    assert c.check(None) is SchemaCompatState.FAIL
    assert c.check(1, migration_pending=True) is SchemaCompatState.MIGRATION_REQUIRED
    assert c.to_readiness(SchemaCompatState.PASS) is GlobalReadiness.READY
    for s in (SchemaCompatState.FAIL, SchemaCompatState.VERSION_MISMATCH, SchemaCompatState.MIGRATION_REQUIRED):
        assert c.to_readiness(s) is GlobalReadiness.NOT_READY


if __name__ == "__main__":
    _h.run([
        test_three_readiness_states,
        test_readiness_report_discloses_nothing_sensitive,
        test_schema_states_and_readiness_mapping,
    ])
