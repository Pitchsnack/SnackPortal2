"""DBR-AR-2A behavioral contract — router-edge routing-decision events (PRD DBR-AR-2A §18).

Proves exactly-one in-memory emission per completed or denied ``route()`` invocation —
including the two previously un-audited pre-target denials (``tenant_routing_unavailable``,
``no_active_tenant``) — plus the immutable, versioned, references-only event shape
(IC-002 class 3 — Database Router edge; IC-005 Runtime Operational Audit Emission).
DB-free and network-free: stdlib doubles only. The isolation-anomaly case uses a local
divergent-connection double + pass-through pool double defined in THIS file (the real
pool's own binding check intercepts a misbound connection before the router's D-30 L3
check — PRD readiness MC-9); the shared doubles file is unchanged.
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys
from datetime import datetime
from typing import Callable, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
from _db_doubles import (  # noqa: E402
    FakeAudit,
    FakeConnection,
    FakeConnectionFactory,
    FakeRoutingRead,
    FakeSecretStore,
    make_router,
)

from database_router.adapters.providers.in_memory_audit_sink import InMemoryAuditSink  # noqa: E402
from database_router.cache import RoutingViewCache  # noqa: E402
from database_router.models import (  # noqa: E402
    ROUTING_AUDIT_ACTIONS,
    ROUTING_AUDIT_EVENT_VERSION,
    ROUTING_AUDIT_SOURCE_SERVICE,
    ROUTING_AUDIT_SOURCE_VERSION,
    RoutingAuditEvent,
    RoutingDenied,
    RoutingTarget,
)
from database_router.ports import TenantConnection  # noqa: E402
from database_router.resolver import RoutingResolver  # noqa: E402
from database_router.router import DatabaseRouter  # noqa: E402
from shared.context import RequestContext  # noqa: E402

# The canonical router-edge public-code vocabulary (DBR-AR-2 contract §3). Case 18 pins
# that DBR-AR-2A introduces no new public code beyond this set.
_CANONICAL_CODES = frozenset(
    {
        "not_found",
        "no_active_tenant",
        "not_ready",
        "schema_out_of_range",
        "administratively_disabled",
        "unavailable",
        "control_plane_unavailable",
        "connection_unavailable",
        "tenant_routing_unavailable",
        "routing_isolation_fault",
    }
)

# Closed field enumeration of the router-minted event (case 13): additions — including a
# forbidden field such as recorded_at, a body, a token, or a connection object — fail here.
_EXPECTED_FIELDS = frozenset(
    {
        # inherited from the shared operational-audit shape
        "actor_ref",
        "action",
        "correlation_id",
        "outcome",
        "target_ref",
        # router-minted (required)
        "event_id",
        "event_version",
        "occurred_at",
        "source_service",
        "source_version",
        # references-only (optional)
        "request_ref",
        "resolved_tenant_ref",
        "public_code",
        "error_class",
        "association_store_ref",
        "association_version",
        "lane",
    }
)


def _ctx(
    tenant: Optional[str] = "t1",
    *,
    role: str = "TENANT_ADMIN",
    cid: str = "cid-1",
    principal: str = "principal_ref_1",
    request_id: Optional[str] = "req-1",
) -> RequestContext:
    return RequestContext(correlation_id=cid, request_id=request_id, active_tenant_id=tenant, principal_ref=principal, role=role)


def _wire(configure: Optional[Callable[[FakeRoutingRead], None]] = None):
    read = FakeRoutingRead()
    (configure or (lambda r: r.set_view("t1")))(read)
    audit = FakeAudit()
    factory = FakeConnectionFactory()
    secrets = FakeSecretStore()
    router, _, _, _ = make_router(read=read, secret_store=secrets, factory=factory, audit=audit)
    return router, factory, audit, read, secrets


def _single(audit: FakeAudit) -> RoutingAuditEvent:
    # Case 19 (applied on every path): one call → exactly one outcome event.
    assert len(audit.events) == 1, f"expected exactly one event, got {audit.actions()}"
    event = audit.events[0]
    assert isinstance(event, RoutingAuditEvent)
    return event


def _expect_denial(router: DatabaseRouter, ctx: RequestContext, status: int, code: str, **route_kw) -> RoutingDenied:
    try:
        router.route(ctx, **route_kw)
    except RoutingDenied as denied:
        # Case 20: existing public denial behavior (status + code) is unchanged.
        assert denied.http_status == status and denied.public_code == code
        return denied
    raise AssertionError(f"expected RoutingDenied {code}")


# -- success paths (cases 1, 2, 11, 16) --------------------------------------------------
def test_tenant_success_emits_exactly_one_route_event() -> None:
    router, factory, audit, _, _ = _wire()
    result = router.route(_ctx())
    assert result.target is RoutingTarget.TENANT and result.tenant_id == "t1"  # case 20: return unchanged
    event = _single(audit)
    assert event.action == "Route" and event.outcome == "success" and event.public_code is None
    assert event.target_ref == "t1" and event.resolved_tenant_ref == "t1"
    assert event.association_store_ref == "tenant/t1/db" and event.association_version == "1"
    assert event.lane == "interactive"
    assert event.correlation_id == "cid-1" and event.request_ref == "req-1"  # case 16
    assert factory.opens == [("t1", "1")]


def test_control_success_emits_exactly_one_routecontrol_event() -> None:
    router, factory, audit, _, _ = _wire()
    result = router.route(_ctx(None, role="CONTROL", principal="op_ref"))
    assert result.target is RoutingTarget.CONTROL and result.connection is None  # case 20
    event = _single(audit)
    assert event.action == "RouteControl" and event.outcome == "success"
    assert event.target_ref is None and event.association_store_ref is None and event.lane is None
    assert factory.opens == []


def test_required_fields_and_version_present_on_every_event() -> None:
    # Case 11: minted identity fields on a success and a denial event alike.
    router, _, audit, _, _ = _wire()
    router.route(_ctx())
    _expect_denial(router, _ctx("ghost", cid="cid-2"), 404, "not_found")
    assert len(audit.events) == 2
    for event in audit.events:
        assert isinstance(event, RoutingAuditEvent)
        assert event.event_id and isinstance(event.event_id, str)
        assert event.event_version == ROUTING_AUDIT_EVENT_VERSION == 1
        parsed = datetime.fromisoformat(event.occurred_at)
        assert parsed.tzinfo is not None  # UTC-aware, informational only
        assert event.source_service == ROUTING_AUDIT_SOURCE_SERVICE == "database_router"
        assert event.source_version == ROUTING_AUDIT_SOURCE_VERSION == "4"
        assert event.actor_ref and event.correlation_id
        assert event.action in ROUTING_AUDIT_ACTIONS and event.outcome


# -- canonical denials at the resolve/acquire edge (cases 3-7, 12) ------------------------
def test_unknown_tenant_one_routedenied_not_found_zero_db_open() -> None:
    router, factory, audit, _, _ = _wire(lambda r: r.set_view("t1"))
    _expect_denial(router, _ctx("ghost"), 404, "not_found")
    event = _single(audit)
    assert event.action == "RouteDenied" and event.outcome == "denied:not_found" and event.public_code == "not_found"
    assert factory.opens == []


def test_suspended_tenant_one_routedenied_administratively_disabled_zero_db_open() -> None:
    router, factory, audit, _, _ = _wire(lambda r: r.set_view("t1", lifecycle="Suspended", ready=False))
    _expect_denial(router, _ctx(), 403, "administratively_disabled")
    event = _single(audit)
    assert event.public_code == "administratively_disabled" and factory.opens == []


def test_not_ready_tenant_one_routedenied_not_ready_zero_db_open() -> None:
    router, factory, audit, _, _ = _wire(lambda r: r.set_view("t1", lifecycle="Provisioning", ready=False))
    _expect_denial(router, _ctx(), 503, "not_ready")
    event = _single(audit)
    assert event.public_code == "not_ready" and factory.opens == []


def test_schema_out_of_range_one_routedenied() -> None:
    router, _, audit, _, _ = _wire(lambda r: r.set_view("t1", schema="9"))
    _expect_denial(router, _ctx(), 503, "schema_out_of_range")
    assert _single(audit).public_code == "schema_out_of_range"


def test_connection_unavailable_one_routedenied_and_optional_fields_stay_absent() -> None:
    router, factory, audit, _, secrets = _wire()
    secrets.set_missing("tenant/t1/db")
    _expect_denial(router, _ctx(), 503, "connection_unavailable")
    event = _single(audit)
    assert event.public_code == "connection_unavailable"
    # Case 12: optional fields are absent on denials — never populated, never secret-filled.
    assert event.association_store_ref is None and event.association_version is None
    assert event.error_class is None and event.lane is None and event.resolved_tenant_ref is None
    assert factory.descriptors == []  # the resolved descriptor never existed, let alone leaked


# -- the two previously un-audited early denials (cases 8, 9) -----------------------------
def test_tenant_routing_unavailable_early_denial_one_event_zero_resolution() -> None:
    router, factory, audit, read, secrets = _wire()
    _expect_denial(router, _ctx("t1", role="CONTROL", principal="sys_ref"), 503, "tenant_routing_unavailable", bootstrap_phase0=True)
    event = _single(audit)
    assert event.action == "RouteDenied" and event.outcome == "denied:tenant_routing_unavailable"
    assert event.public_code == "tenant_routing_unavailable" and event.target_ref == "t1"
    # Zero target resolution, zero secret resolution, zero pool/DB activity (pre-target).
    assert read.calls == 0 and secrets.resolved == [] and factory.opens == []


def test_no_active_tenant_early_denial_one_event_zero_resolution() -> None:
    router, factory, audit, read, secrets = _wire()
    _expect_denial(router, _ctx(None, role="TENANT_AGENT"), 403, "no_active_tenant")
    event = _single(audit)
    assert event.action == "RouteDenied" and event.outcome == "denied:no_active_tenant"
    assert event.public_code == "no_active_tenant" and event.target_ref is None
    assert read.calls == 0 and secrets.resolved == [] and factory.opens == []


# -- isolation anomaly (case 10) — local doubles only (shared doubles file unchanged) -----
class _PassThroughPool:
    """Pool double that skips the pool-level binding check so the router's own D-30 L3
    check is reachable (the real pool intercepts a misbound connection first — MC-9)."""

    def __init__(self) -> None:
        self.discarded: List[TenantConnection] = []
        self.released: List[TenantConnection] = []

    def acquire(self, tenant_id: str, association_version: str, open_fn: Callable[[], TenantConnection]) -> TenantConnection:
        return open_fn()

    def discard(self, conn: TenantConnection) -> None:
        self.discarded.append(conn)

    def release(self, conn: TenantConnection) -> None:
        self.released.append(conn)


class _DivergentFactory(FakeConnectionFactory):
    """Mints a connection bound to a DIFFERENT tenant than requested (divergence probe)."""

    def open(self, tenant_id: str, association_version: str, descriptor: str) -> TenantConnection:
        self.opens.append((tenant_id, association_version))
        return FakeConnection("evil-tenant", association_version)


def test_tenant_binding_divergence_one_isolationanomaly_no_route_event() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    cache = RoutingViewCache(ttl_seconds=15.0, clock=lambda: 0.0)
    resolver = RoutingResolver(read, cache, supported_schema_versions=("1",))
    audit = FakeAudit()
    pool = _PassThroughPool()
    router = DatabaseRouter(
        resolver=resolver,
        pool=pool,  # type: ignore[arg-type]
        secret_store=FakeSecretStore(),
        connection_factory=_DivergentFactory(),
        audit=audit,
    )
    _expect_denial(router, _ctx(), 503, "routing_isolation_fault")
    event = _single(audit)  # exactly one event — the anomaly, never a Route or a second denial
    assert event.action == "IsolationAnomaly" and event.outcome == "anomaly:tenant_binding"
    assert event.target_ref == "t1" and event.resolved_tenant_ref == "evil-tenant"
    assert "Route" not in audit.actions() and "RouteDenied" not in audit.actions()
    assert len(pool.discarded) == 1  # the misbound connection never reaches the caller


# -- model shape (cases 13, 14) -----------------------------------------------------------
def test_no_forbidden_field_exists_on_the_event_model() -> None:
    names = {f.name for f in dataclasses.fields(RoutingAuditEvent)}
    assert names == set(_EXPECTED_FIELDS), f"closed field set changed: {sorted(names ^ set(_EXPECTED_FIELDS))}"
    assert "recorded_at" not in names  # store-assigned at persistence time; never router-minted
    for field in dataclasses.fields(RoutingAuditEvent):
        annotation = str(field.type)
        for live_object in ("TenantConnection", "RouteResult", "TenantRoutingView"):
            assert live_object not in annotation, f"live object type {live_object} on event field {field.name}"


def test_event_object_is_immutable() -> None:
    router, _, audit, _, _ = _wire()
    router.route(_ctx())
    event = _single(audit)
    for field_name, value in (("action", "Mutated"), ("event_id", "x"), ("outcome", "tampered")):
        try:
            setattr(event, field_name, value)
        except dataclasses.FrozenInstanceError:
            continue
        raise AssertionError(f"RoutingAuditEvent.{field_name} must be immutable")


# -- sink witnessing (cases 15, 17) — the existing in-memory sink implements the port -----
def test_in_memory_sink_preserves_exact_object_identity_and_order() -> None:
    read = FakeRoutingRead()
    read.set_view("t1")
    read.set_view("t2")
    sink = InMemoryAuditSink()
    factory = FakeConnectionFactory()
    router, _, _, _ = make_router(read=read, secret_store=FakeSecretStore(), factory=factory, audit=sink)
    router.route(_ctx("t1", cid="cid-a"))
    router.route(_ctx("t2", cid="cid-b"))
    events = sink.events()
    assert [e.correlation_id for e in events] == ["cid-a", "cid-b"]  # insertion order preserved
    assert events[0] is sink.events()[0] and events[1] is sink.events()[1]  # exact objects, not copies
    assert all(isinstance(e, RoutingAuditEvent) for e in events)


def test_event_ids_unique_across_separate_route_calls() -> None:
    router, _, audit, _, _ = _wire()
    for n in range(5):
        router.route(_ctx(cid=f"cid-{n}"))
    ids = [e.event_id for e in audit.events if isinstance(e, RoutingAuditEvent)]
    assert len(ids) == 5 and len(set(ids)) == 5


# -- vocabulary and behavior pins (cases 18, 12, 19, 20 sweep) ----------------------------
def test_no_new_public_code_and_no_secret_material_in_any_event() -> None:
    scenarios: List[Callable[[], FakeAudit]] = []

    def _denial_audit(configure: Callable[[FakeRoutingRead], None], tenant: Optional[str], status: int, code: str, **kw) -> FakeAudit:
        router, _, audit, _, secrets = _wire(configure)
        if code == "connection_unavailable":
            secrets.set_missing("tenant/t1/db")
        _expect_denial(router, _ctx(tenant, role=kw.pop("role", "TENANT_ADMIN")), status, code, **kw)
        return audit

    audits = [
        _denial_audit(lambda r: r.set_view("t1"), "ghost", 404, "not_found"),
        _denial_audit(lambda r: r.set_view("t1", lifecycle="Suspended", ready=False), "t1", 403, "administratively_disabled"),
        _denial_audit(lambda r: r.set_view("t1", lifecycle="Provisioning", ready=False), "t1", 503, "not_ready"),
        _denial_audit(lambda r: r.set_view("t1", schema="9"), "t1", 503, "schema_out_of_range"),
        _denial_audit(lambda r: r.set_view("t1"), "t1", 503, "connection_unavailable"),
        _denial_audit(lambda r: r.set_view("t1"), "t1", 503, "tenant_routing_unavailable", role="CONTROL", bootstrap_phase0=True),
        _denial_audit(lambda r: r.set_view("t1"), None, 403, "no_active_tenant", role="TENANT_AGENT"),
    ]
    del scenarios
    success_router, _, success_audit, _, _ = _wire()
    success_router.route(_ctx())
    audits.append(success_audit)
    for audit in audits:
        for event in audit.events:
            assert isinstance(event, RoutingAuditEvent)
            if event.public_code is not None:  # case 18: emitted codes stay canonical
                assert event.public_code in _CANONICAL_CODES, event.public_code
            for value in dataclasses.asdict(event).values():  # case 12: references only
                if isinstance(value, str):
                    assert "descriptor::" not in value, "resolved secret material leaked into an event"
                    assert not value.startswith("eyJ"), "token-shaped value in an event"


def test_one_call_cannot_produce_two_outcome_events_on_any_path() -> None:
    # Case 19 sweep: success, resolve-denial, early denial — one event per invocation each.
    router, _, audit, _, _ = _wire()
    router.route(_ctx(cid="c1"))
    _expect_denial(router, _ctx("ghost", cid="c2"), 404, "not_found")
    _expect_denial(router, _ctx(None, role="TENANT_AGENT", cid="c3"), 403, "no_active_tenant")
    per_correlation = [e.correlation_id for e in audit.events]
    assert per_correlation == ["c1", "c2", "c3"], "each route() call must emit exactly one event, in order"


if __name__ == "__main__":
    _h.run(
        [
            test_tenant_success_emits_exactly_one_route_event,
            test_control_success_emits_exactly_one_routecontrol_event,
            test_required_fields_and_version_present_on_every_event,
            test_unknown_tenant_one_routedenied_not_found_zero_db_open,
            test_suspended_tenant_one_routedenied_administratively_disabled_zero_db_open,
            test_not_ready_tenant_one_routedenied_not_ready_zero_db_open,
            test_schema_out_of_range_one_routedenied,
            test_connection_unavailable_one_routedenied_and_optional_fields_stay_absent,
            test_tenant_routing_unavailable_early_denial_one_event_zero_resolution,
            test_no_active_tenant_early_denial_one_event_zero_resolution,
            test_tenant_binding_divergence_one_isolationanomaly_no_route_event,
            test_no_forbidden_field_exists_on_the_event_model,
            test_event_object_is_immutable,
            test_in_memory_sink_preserves_exact_object_identity_and_order,
            test_event_ids_unique_across_separate_route_calls,
            test_no_new_public_code_and_no_secret_material_in_any_event,
            test_one_call_cannot_produce_two_outcome_events_on_any_path,
        ]
    )
