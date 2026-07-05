"""D15 provisioning verification gate — service-level conformance (D15-ARCH-SPEC-01 §8/§9/§13).

Fail-closed readiness (WP-10): Ready ONLY when reachability + schema + Physical Distinctness
all pass. Re-association triggers router cache invalidation + re-verification (WP-11).
Reference-only operational audit (WP-12). Both distinctness legs enforced.
Standalone-runnable: `python tests/control_plane/test_d15_provisioning_gate.py`.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
from _d15_doubles import (  # noqa: E402
    FakeEvidenceProvider,
    FakeProbe,
    build_service,
    register_tenant,
    tenant_evidence,
)

from control_plane import events  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.distinctness import DistinctnessResult, InMemoryDistinctnessLedger  # noqa: E402
from control_plane.records import TenantLifecycleState  # noqa: E402
from control_plane.router_signal import RecordingRouterInvalidation  # noqa: E402
from shared.secrets import SecretRef  # noqa: E402


def _actions(store: InMemoryControlStore) -> list:
    return [r.action for r in store.list_audit()]


def test_gate_reaches_ready_only_when_all_pass() -> None:
    store = InMemoryControlStore()
    register_tenant(store, "t1", store_ref="t1_secret")
    svc = build_service(store, FakeEvidenceProvider({"t1_secret": tenant_evidence("t1")}))

    out = svc.verify("t1", actor="ops_ref", correlation_id="c1")

    assert out.result is DistinctnessResult.VERIFIED, out.reason
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.READY
    acts = _actions(store)
    assert events.DISTINCTNESS_VERIFICATION_STARTED in acts
    assert events.DISTINCTNESS_VERIFICATION_PASSED in acts
    assert events.ROUTING_ENABLED in acts


def test_unreachable_is_not_ready() -> None:
    store = InMemoryControlStore()
    register_tenant(store, "t1", store_ref="t1_secret")
    svc = build_service(
        store, FakeEvidenceProvider({"t1_secret": tenant_evidence("t1")}), probe=FakeProbe(reachable=False, observed_schema_version=None)
    )

    out = svc.verify("t1", actor="ops_ref", correlation_id="c1")

    assert out.result is DistinctnessResult.VERIFICATION_INCOMPLETE
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.FAILED
    assert events.VERIFICATION_INCOMPLETE in _actions(store)


def test_schema_mismatch_is_not_ready() -> None:
    store = InMemoryControlStore()
    register_tenant(store, "t1", store_ref="t1_secret", schema="1")
    svc = build_service(
        store, FakeEvidenceProvider({"t1_secret": tenant_evidence("t1")}), probe=FakeProbe(reachable=True, observed_schema_version="2")
    )

    out = svc.verify("t1", actor="ops_ref", correlation_id="c1")

    assert out.result is DistinctnessResult.VERIFICATION_FAILED
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.FAILED


def test_tenant_collision_fails_closed_and_keeps_first_ready() -> None:
    store = InMemoryControlStore()
    register_tenant(store, "t1", store_ref="t1_secret")
    register_tenant(store, "t2", store_ref="t2_secret")
    shared_db_identity = "sp2_shared:9999"
    provider = FakeEvidenceProvider(
        {
            "t1_secret": tenant_evidence("t1", database_identity=shared_db_identity),
            # t2 reaches its own intended target but collides on the physical fingerprint.
            "t2_secret": tenant_evidence("t2", database_identity=shared_db_identity, observed_target="sp2_tenant_t2"),
        }
    )
    svc = build_service(store, provider)

    first = svc.verify("t1", actor="ops_ref", correlation_id="c1")
    second = svc.verify("t2", actor="ops_ref", correlation_id="c2")

    assert first.result is DistinctnessResult.VERIFIED
    assert second.result is DistinctnessResult.ISOLATION_ANOMALY
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.READY, "first tenant stays Ready"
    # PRD 07D-2b.2a (Dan-authorized characterization update): isolation-class anomalies now
    # quarantine automatically at classification time (amended IC-002) — was FAILED.
    assert store.get_tenant("t2").lifecycle_state is TenantLifecycleState.QUARANTINED, "colliding tenant quarantines"
    assert events.ISOLATION_ANOMALY in _actions(store)


def test_secret_reference_control_collision_pre_check() -> None:
    # DV-C7A secret-reference vector at the registry level: a tenant pointed at the Control
    # DB's secret reference is rejected before any evidence gather.
    store = InMemoryControlStore()
    register_tenant(store, "t1", store_ref="control_secret")  # == CONTROL_EVIDENCE.secret_ref_key
    svc = build_service(store, FakeEvidenceProvider({}))  # empty: gather must NOT be needed

    out = svc.verify("t1", actor="ops_ref", correlation_id="c1")

    assert out.result is DistinctnessResult.ISOLATION_ANOMALY
    # PRD 07D-2b.2a (Dan-authorized characterization update): anomaly -> QUARANTINED, was FAILED.
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.QUARANTINED
    assert events.ISOLATION_ANOMALY in _actions(store)


def test_reassociate_invalidates_router_and_reverifies() -> None:
    store = InMemoryControlStore()
    register_tenant(store, "t1", store_ref="t1_secret")
    provider = FakeEvidenceProvider(
        {
            "t1_secret": tenant_evidence("t1", database_identity="sp2_tenant_t1:1001"),
            "t1_secret_v2": tenant_evidence("t1", database_identity="sp2_tenant_t1:2002"),  # relocated DB
        }
    )
    router = RecordingRouterInvalidation()
    svc = build_service(store, provider, router=router)

    svc.verify("t1", actor="ops_ref", correlation_id="c1")
    out = svc.reassociate("t1", new_association_ref=SecretRef("t1_secret_v2", "2"), actor="ops_ref", correlation_id="c2")

    assert out.result is DistinctnessResult.VERIFIED, out.reason
    assert store.get_tenant("t1").lifecycle_state is TenantLifecycleState.READY
    assert store.get_tenant("t1").database_association_ref.store_ref == "t1_secret_v2"
    assert ("t1", "c2") in router.signals, "router invalidation must be signalled on re-association"
    acts = _actions(store)
    assert events.DATABASE_ASSOCIATED in acts
    assert events.ROUTER_CACHE_INVALIDATED in acts


def test_disable_routing_signals_and_drops_evidence() -> None:
    store = InMemoryControlStore()
    register_tenant(store, "t1", store_ref="t1_secret")
    ledger = InMemoryDistinctnessLedger()
    router = RecordingRouterInvalidation()
    svc = build_service(store, FakeEvidenceProvider({"t1_secret": tenant_evidence("t1")}), router=router, ledger=ledger)

    svc.verify("t1", actor="ops_ref", correlation_id="c1")
    assert "t1" in dict(ledger.evidence_excluding("__none__")), "verified tenant recorded in ledger"

    svc.disable_routing("t1", actor="ops_ref", correlation_id="c2")

    assert "t1" not in dict(ledger.evidence_excluding("__none__")), "evidence dropped on routing disable"
    assert ("t1", "c2") in router.signals
    acts = _actions(store)
    assert events.ROUTING_DISABLED in acts
    assert events.ROUTER_CACHE_INVALIDATED in acts


def test_audit_records_are_reference_only() -> None:
    store = InMemoryControlStore()
    register_tenant(store, "t1", store_ref="t1_secret")
    svc = build_service(store, FakeEvidenceProvider({"t1_secret": tenant_evidence("t1")}))
    svc.verify("t1", actor="ops_ref", correlation_id="c1")

    for r in store.list_audit():
        # Reference-only by construction: actor/tenant are references, never names/emails/PII.
        assert "@" not in r.actor, "actor must be a reference, not an email"
        assert r.tenant_id is None or "@" not in r.tenant_id, "tenant must be a reference"
        assert r.action and isinstance(r.action, str)
        assert r.correlation_id == "c1"


if __name__ == "__main__":
    _h.run(
        [
            test_gate_reaches_ready_only_when_all_pass,
            test_unreachable_is_not_ready,
            test_schema_mismatch_is_not_ready,
            test_tenant_collision_fails_closed_and_keeps_first_ready,
            test_secret_reference_control_collision_pre_check,
            test_reassociate_invalidates_router_and_reverifies,
            test_disable_routing_signals_and_drops_evidence,
            test_audit_records_are_reference_only,
        ]
    )
