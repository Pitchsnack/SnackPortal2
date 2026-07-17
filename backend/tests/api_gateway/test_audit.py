"""Audit (IC-010 §J / AD-1): named emit-set, references-only, single emission, no sink.

B5-BLK-6C-B — this file is also the behavioral owner of the ``workspace_memberships_read``
gateway-edge success-access subclass (IC-002 Audit-Section Extension class 3b): exactly-once
emission per successful self-scoped MembershipsForPrincipal enumeration (empty included),
non-emission on every denial/failure class, the references-only eight-field shape,
actor == subject self-scoping, sole-emitter/single-edge, directory-read audit silence
(Reserved), and the historic-four vs success-action separation.
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.adapters.providers.in_memory_audit_emitter import InMemoryAuditEmitter  # noqa: E402
from api_gateway.models import AuditAction  # noqa: E402
from api_gateway.portal import MembershipEntryDTO, compose_display_ref  # noqa: E402

_SECRET = "tok-t1"
_SUCCESS = AuditAction.WORKSPACE_MEMBERSHIPS_READ


def _events_for(path: str, *, host: str = "", headers=None, authorization=_SECRET):
    gateway, _authn, _router, audit = D.tenant_setup()
    gateway.handle(D.req(path=path, host=host, headers=headers or {}, authorization=authorization, correlation_id="cid-1"))
    return audit.events


def test_emit_set_named_events() -> None:
    assert [e.action for e in _events_for("/tenant/x", headers={"X-Tenant-Id": "t2"})] == [AuditAction.CARRIER_MISMATCH]
    assert [e.action for e in _events_for("/nope", headers={"X-Tenant-Id": "t1"})] == [AuditAction.ROUTE_DENIED]
    assert [e.action for e in _events_for("/tenant/x", host="t2.s.example", headers={"X-Tenant-Id": "t1"})] == [
        AuditAction.ISOLATION_ANOMALY
    ]


def test_carrier_on_control_anomaly_is_emitted() -> None:
    authn = D.StubAuthenticator()
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    audit = D.RecordingAuditEmitter()
    gateway = D.build_gateway(authenticator=authn, router=D.StubRouterDispatch(), audit=audit)
    gateway.handle(D.req(path="/directory/x", headers={"X-Tenant-Id": "t9"}, authorization="tok-ctl"))
    assert [e.action for e in audit.events] == [AuditAction.CARRIER_ON_CONTROL_ANOMALY]


def test_records_are_references_only_no_token_or_pii() -> None:
    events = _events_for("/tenant/x", host="t2.s.example", headers={"X-Tenant-Id": "t1"})  # IsolationAnomaly
    for e in events:
        for value in (e.correlation_id, e.outcome, e.actor_ref, e.tenant_ref, e.carrier_ref):
            assert value != _SECRET  # no bearer token leaks into an audit record
        if e.carrier_ref is not None:
            assert e.carrier_ref.startswith("carrier:") and len(e.carrier_ref) <= 64  # opaque + bounded (IC-005:116)


def test_single_emission_per_anomaly() -> None:
    events = _events_for("/tenant/x", headers={"X-Tenant-Id": "t2"})  # one carrier_mismatch
    keys = [(e.action, e.correlation_id) for e in events]
    assert len(keys) == len(set(keys)) == 1  # exactly one record for the anomaly


def test_default_emitter_is_in_memory_no_sink() -> None:
    emitter = InMemoryAuditEmitter()
    assert emitter.events() == []  # in-process list; no DB/file/external persistence


# --- B5-BLK-6C-B: workspace_memberships_read success-access subclass (IC-002 class 3b) --------
def _members(*tenant_ids: str):
    return tuple(MembershipEntryDTO(tenant_id=t, role="MASTER_AGENT", display_ref=compose_display_ref(t)) for t in tenant_ids)


def _memberships_run(cp, *, query=None, correlation_id="cid-1"):
    """One memberships request through the ACTIVE composition seam (CONTROL principal
    "ops"). Returns (resp, router, audit)."""
    gateway, _authn, router, audit = D.control_read_setup(cp)
    resp = gateway.handle(D.req(path="/memberships", query=query or {}, authorization="tok-ctl", correlation_id=correlation_id))
    return resp, router, audit


def _success_events(audit):
    return [e for e in audit.events if e.action is _SUCCESS]


class _BoomControlPlaneRead(D.StubControlPlaneRead):
    """A test-local port double whose memberships read raises an arbitrary internal
    exception (the class no configured stub mode models)."""

    def memberships_for_principal(self, principal_ref):  # noqa: ANN001
        raise RuntimeError("internal failure (test-local)")


def test_memberships_success_emits_exactly_one_event_regardless_of_cardinality() -> None:
    # 1 / 2 / many memberships -> EXACTLY one event: the audit records the operation,
    # never the number or contents of returned memberships (never zero, never two,
    # never one per membership record, never one per tenant).
    for members in (_members("t1"), _members("t1", "t2"), _members(*(f"t{i}" for i in range(1, 8)))):
        resp, _router, audit = _memberships_run(D.StubControlPlaneRead(memberships=members))
        assert resp.status == 200
        assert len(_success_events(audit)) == 1, f"{len(members)} memberships must emit exactly one event"
        assert len(audit.events) == 1  # no denial/anomaly event accompanies the success


def test_memberships_empty_success_still_emits_exactly_one_event() -> None:
    # A successful EMPTY enumeration is still a successful enumeration -> exactly one.
    resp, _router, audit = _memberships_run(D.StubControlPlaneRead(mode="empty"))
    assert (resp.status, resp.public_code) == (200, "ok")
    assert len(_success_events(audit)) == 1 and len(audit.events) == 1


def test_success_event_required_values_and_contract_field_mapping() -> None:
    # Runtime field -> IC-010 §J / IC-002 class-3b contract shape (the accepted mapping,
    # stated explicitly):
    #   GatewayAuditEvent.audit_id       -> audit_id
    #   GatewayAuditEvent.action         -> action                (== "workspace_memberships_read")
    #   GatewayAuditEvent.actor_ref      -> actor_principal_ref
    #   GatewayAuditEvent.subject_ref    -> subject_principal_ref
    #   GatewayAuditEvent.correlation_id -> correlation_id
    #   GatewayAuditEvent.occurred_at    -> occurred_at
    #   GatewayAuditEvent.outcome        -> outcome               (== "success")
    #   GatewayAuditEvent.event_version  -> event_version         (== 1)
    resp, _router, audit = _memberships_run(D.StubControlPlaneRead(memberships=_members("t1", "t2")))
    assert resp.status == 200
    (event,) = _success_events(audit)
    assert event.action is _SUCCESS and event.action.value == "workspace_memberships_read"
    assert event.outcome == "success"
    assert event.event_version == 1
    assert event.correlation_id == "cid-1"  # the pipeline correlation id (injected header)
    assert isinstance(event.audit_id, str) and event.audit_id
    int(event.audit_id, 16)  # non-empty hex
    assert isinstance(event.occurred_at, str) and event.occurred_at
    parsed = datetime.fromisoformat(event.occurred_at)  # ISO-8601 parseable...
    assert parsed.utcoffset() == timedelta(0)  # ...and UTC
    # Self-scoped: actor == subject == the AUTHENTICATED principal, never a client value.
    assert event.actor_ref == event.subject_ref == "ops"
    assert event.tenant_ref is None and event.carrier_ref is None


def test_success_event_is_references_only_no_membership_content() -> None:
    # The event never carries the returned collection, result tenant ids, role values,
    # display refs, DB identifiers, provider payload, or a secret-shaped value.
    resp, _router, audit = _memberships_run(D.StubControlPlaneRead(memberships=_members("t1", "t2")))
    assert resp.status == 200
    (event,) = _success_events(audit)
    values = [getattr(event, f.name) for f in dataclasses.fields(event)]
    for value in values:
        assert not isinstance(value, (tuple, list, dict, set)), value  # no collection field
    strings = [v for v in values if isinstance(v, str)]
    for forbidden in ("t1", "t2", "MASTER_AGENT", "ref:tenant", "display", "tok-ctl", _SECRET, "eyJ", "postgres", "dsn", "password"):
        for s in strings:
            assert forbidden not in s, (forbidden, s)


def test_client_supplied_subject_never_reaches_the_event() -> None:
    # A client-supplied selector can never override the authenticated principal: the
    # emitted actor/subject stay "ops"; "victim" appears in no field.
    resp, _router, audit = _memberships_run(D.StubControlPlaneRead(memberships=_members("t1")), query={"p": "victim"})
    assert resp.status == 200
    (event,) = _success_events(audit)
    assert event.actor_ref == event.subject_ref == "ops"
    for f in dataclasses.fields(event):
        value = getattr(event, f.name)
        assert not (isinstance(value, str) and "victim" in value), f.name


def test_no_success_event_on_any_denial_or_failure_class() -> None:
    # Non-emission matrix (IC-010 §J): the success count stays ZERO on every denial and
    # failure class; the existing denial/anomaly emission stays exactly as before.
    members = _members("t1")

    # 401 unauthenticated (missing token, then unknown token) — port never reached.
    gateway, _authn, _router, audit = D.control_read_setup(D.StubControlPlaneRead(memberships=members))
    assert gateway.handle(D.req(path="/memberships")).status == 401
    assert gateway.handle(D.req(path="/memberships", authorization="tok-nope")).status == 401
    assert _success_events(audit) == []

    # 403 forbidden (auth denial).
    gateway, authn, _router, audit = D.control_read_setup(D.StubControlPlaneRead(memberships=members))
    authn.set_deny_access()
    assert gateway.handle(D.req(path="/memberships", authorization="tok-ctl")).status == 403
    assert _success_events(audit) == []

    # 403 isolation_anomaly (dual distinct carriers) — the EXISTING IsolationAnomaly only.
    gateway, _authn, _router, audit = D.control_read_setup(
        D.StubControlPlaneRead(memberships=members), token="tok-t1", principal="p1", tenant="t1", role="MASTER_AGENT"
    )
    resp = gateway.handle(D.req(path="/memberships", authorization="tok-t1", host="t1.s.example", headers={"X-Tenant-Id": "t2"}))
    assert (resp.status, resp.public_code) == (403, "isolation_anomaly")
    assert [e.action for e in audit.events] == [AuditAction.ISOLATION_ANOMALY]

    # not found / absent (LW-1: live 404 -> None -> 403) — the EXISTING RouteDenied only.
    gateway, _authn, _router, audit = D.control_read_setup(D.StubControlPlaneRead(mode="absent"))
    assert gateway.handle(D.req(path="/memberships", authorization="tok-ctl")).status == 403
    assert [e.action for e in audit.events] == [AuditAction.ROUTE_DENIED]

    # 503 unavailable / timeout / malformed / internal exception — no event of ANY kind.
    for cp in (
        D.StubControlPlaneRead(mode="unavailable"),
        D.StubControlPlaneRead(mode="timeout"),
        D.StubControlPlaneRead(mode="malformed"),
        _BoomControlPlaneRead(),
    ):
        gateway, _authn, _router, audit = D.control_read_setup(cp)
        resp = gateway.handle(D.req(path="/memberships", authorization="tok-ctl"))
        assert (resp.status, resp.public_code) == (503, "unavailable"), type(cp).__name__
        assert audit.events == [], type(cp).__name__

    # authenticator unavailable (503) — port never reached.
    gateway, authn, _router, audit = D.control_read_setup(D.StubControlPlaneRead(memberships=members))
    authn.set_unavailable()
    assert gateway.handle(D.req(path="/memberships", authorization="tok-ctl")).status == 503
    assert _success_events(audit) == []


def test_directory_read_success_emits_no_audit_event() -> None:
    # Per-read Global Directory access audit is RESERVED (IC-005 / IC-010 §R): startup,
    # investor, and empty directory successes all stay audit-silent; only memberships emits.
    entries = (D.DirectoryEntryDTO(record_ref="rec-1", display_name="Alpha"),)
    for path, cp in (
        ("/directory/startup", D.StubControlPlaneRead(startup_entries=entries)),
        ("/directory/investor", D.StubControlPlaneRead(investor_entries=entries)),
        ("/directory/startup", D.StubControlPlaneRead(mode="empty")),
    ):
        gateway, _authn, _router, audit = D.control_read_setup(cp)
        resp = gateway.handle(D.req(path=path, authorization="tok-ctl"))
        assert resp.status == 200, path
        assert audit.events == [], path


def test_historic_four_denial_actions_unchanged_and_success_action_separate() -> None:
    # The denial/anomaly subset remains EXACTLY the historic four (exact labels); the
    # runtime enum totals five; the success action sits outside that subset and is never
    # classified as a denial, anomaly, or routing action.
    historic = {
        AuditAction.CARRIER_MISMATCH: "CarrierMismatch",
        AuditAction.CARRIER_ON_CONTROL_ANOMALY: "CarrierOnControlAnomaly",
        AuditAction.ROUTE_DENIED: "RouteDenied",
        AuditAction.ISOLATION_ANOMALY: "IsolationAnomaly",
    }
    assert {action: action.value for action in historic} == historic  # exact four, exact labels
    assert len(AuditAction) == 5
    assert set(AuditAction) == set(historic) | {_SUCCESS}
    assert _SUCCESS not in historic
    assert _SUCCESS.value == "workspace_memberships_read"
    assert _SUCCESS.value not in set(historic.values())


def test_sole_emitter_single_recorder_and_zero_router_handoffs() -> None:
    # Single edge (IC-010 §J): ONE injected recorder holds exactly one event; the
    # Control-Plane read port exposes no emit path (so the Control Plane cannot emit);
    # the CONTROL composition branch performs zero router handoffs (no router-side edge).
    cp = D.StubControlPlaneRead(memberships=_members("t1"))
    resp, router, audit = _memberships_run(cp)
    assert resp.status == 200
    assert len(audit.events) == 1 and len(_success_events(audit)) == 1
    assert router.handoffs == []
    assert not hasattr(cp, "emit")


if __name__ == "__main__":
    _h.run(
        [
            test_emit_set_named_events,
            test_carrier_on_control_anomaly_is_emitted,
            test_records_are_references_only_no_token_or_pii,
            test_single_emission_per_anomaly,
            test_default_emitter_is_in_memory_no_sink,
            test_memberships_success_emits_exactly_one_event_regardless_of_cardinality,
            test_memberships_empty_success_still_emits_exactly_one_event,
            test_success_event_required_values_and_contract_field_mapping,
            test_success_event_is_references_only_no_membership_content,
            test_client_supplied_subject_never_reaches_the_event,
            test_no_success_event_on_any_denial_or_failure_class,
            test_directory_read_success_emits_no_audit_event,
            test_historic_four_denial_actions_unchanged_and_success_action_separate,
            test_sole_emitter_single_recorder_and_zero_router_handoffs,
        ]
    )
