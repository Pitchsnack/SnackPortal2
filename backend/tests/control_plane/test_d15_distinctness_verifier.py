"""D15 Physical Distinctness Verifier — pure-logic conformance (D15-ARCH-SPEC-01 §9; §13).

Covers DV-C1..DV-C9 + DV-C7A and acceptance criteria DV-AC9..DV-AC16D: both distinctness
legs (tenant-vs-tenant AND tenant-vs-Control-DB), system_identifier-alone insufficiency,
write-sentinel requirement, misroute detection, and fail-closed routing eligibility.
Standalone-runnable: `python tests/control_plane/test_d15_distinctness_verifier.py`.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.distinctness import (  # noqa: E402
    REASON_CONTROL_DB_COLLISION,
    REASON_MISROUTED_TARGET,
    REASON_SYSTEM_ID_ONLY,
    REASON_TENANT_COLLISION,
    DistinctnessEvidence,
    DistinctnessResult,
    PhysicalDistinctnessVerifier,
)

CONTROL = DistinctnessEvidence(
    system_identifier="cluster-A",
    database_identity="sp2_control:1",
    observed_target="sp2_control",
    secret_ref_key="control_secret",
    sentinel_namespace="dv_sentinel_control",
    sentinel_token=None,
    sentinel_written=True,
)


def _ev(**kw: object) -> DistinctnessEvidence:
    base = dict(
        system_identifier="cluster-A",
        database_identity="sp2_tenant_t1:1001",
        observed_target="sp2_tenant_t1",
        secret_ref_key="tenant_t1_secret",
        sentinel_namespace="dv_sentinel_t1",
        sentinel_token="sentok-1",
        sentinel_written=True,
    )
    base.update(kw)
    return DistinctnessEvidence(**base)  # type: ignore[arg-type]


def _verify(candidate, *, intended="sp2_tenant_t1", inventory=None):
    return PhysicalDistinctnessVerifier().verify("t1", candidate, intended_target=intended, control_db=CONTROL, inventory=inventory or {})


def test_verified_when_physically_distinct() -> None:
    out = _verify(_ev())
    assert out.result is DistinctnessResult.VERIFIED, out.reason
    assert out.routable is True, "VERIFIED must be routing-eligible"


def test_same_cluster_different_database_is_ok() -> None:
    # DV-AC9: system_identifier alone is insufficient — same cluster, different database
    # identity is DISTINCT and must pass.
    out = _verify(
        _ev(system_identifier="cluster-A", database_identity="sp2_tenant_t1:1001"),
        inventory={
            "t2": _ev(
                system_identifier="cluster-A",
                database_identity="sp2_tenant_t2:2002",
                observed_target="sp2_tenant_t2",
                secret_ref_key="tenant_t2_secret",
                sentinel_namespace="dv_sentinel_t2",
                sentinel_token="sentok-9",
            )
        },
    )
    assert out.result is DistinctnessResult.VERIFIED, out.reason


def test_system_identifier_alone_insufficient() -> None:
    # DV-AC9: with no database-level identity, distinctness cannot be proven.
    out = _verify(_ev(database_identity=""))
    assert out.result is DistinctnessResult.VERIFICATION_INCOMPLETE
    assert out.reason == REASON_SYSTEM_ID_ONLY
    assert out.routable is False


def test_same_database_collision_is_anomaly() -> None:
    # DV-C5/C6 / DV-AC12/13/15/16: two tenants sharing the (system_id, db identity) fingerprint.
    other = _ev(
        observed_target="sp2_tenant_t2", secret_ref_key="tenant_t2_secret", sentinel_namespace="dv_sentinel_t2", sentinel_token="sentok-2"
    )
    out = _verify(_ev(), inventory={"t2": other})  # same fingerprint as candidate
    assert out.result is DistinctnessResult.ISOLATION_ANOMALY
    assert out.reason == REASON_TENANT_COLLISION
    assert out.routable is False


def test_misrouted_target_is_anomaly() -> None:
    # DV-C3/C7 / DV-AC14: the database reached is not the intended target.
    out = _verify(_ev(observed_target="sp2_tenant_OTHER"))
    assert out.result is DistinctnessResult.ISOLATION_ANOMALY
    assert out.reason == REASON_MISROUTED_TARGET


def test_control_db_fingerprint_collision_is_anomaly() -> None:
    # DV-C7A / DV-AC16B/C: tenant resolves to the Control DB's physical database.
    out = _verify(_ev(system_identifier="cluster-A", database_identity="sp2_control:1", observed_target="sp2_tenant_t1"))
    assert out.result is DistinctnessResult.ISOLATION_ANOMALY
    assert out.reason == REASON_CONTROL_DB_COLLISION


def test_control_db_secret_reference_collision_is_anomaly() -> None:
    # DV-C7A secret-reference vector (the R2 X-1 amendment): tenant's secret reference
    # equals the Control DB's secret reference -> it would reach the Control DB.
    out = _verify(_ev(secret_ref_key="control_secret"))
    assert out.result is DistinctnessResult.ISOLATION_ANOMALY
    assert out.reason == REASON_CONTROL_DB_COLLISION


def test_control_db_sentinel_namespace_collision_is_anomaly() -> None:
    # DV-C7A sentinel-namespace vector.
    out = _verify(_ev(sentinel_namespace="dv_sentinel_control"))
    assert out.result is DistinctnessResult.ISOLATION_ANOMALY
    assert out.reason == REASON_CONTROL_DB_COLLISION


def test_sentinel_not_written_is_incomplete() -> None:
    # DV-C4: write-sentinel verification is required.
    out = _verify(_ev(sentinel_written=False, sentinel_token=None))
    assert out.result is DistinctnessResult.VERIFICATION_INCOMPLETE
    assert out.routable is False


def test_no_evidence_is_incomplete() -> None:
    # Result C: verification could not complete (no evidence gathered).
    out = _verify(None)
    assert out.result is DistinctnessResult.VERIFICATION_INCOMPLETE
    assert out.routable is False


if __name__ == "__main__":
    _h.run(
        [
            test_verified_when_physically_distinct,
            test_same_cluster_different_database_is_ok,
            test_system_identifier_alone_insufficient,
            test_same_database_collision_is_anomaly,
            test_misrouted_target_is_anomaly,
            test_control_db_fingerprint_collision_is_anomaly,
            test_control_db_secret_reference_collision_is_anomaly,
            test_control_db_sentinel_namespace_collision_is_anomaly,
            test_sentinel_not_written_is_incomplete,
            test_no_evidence_is_incomplete,
        ]
    )
