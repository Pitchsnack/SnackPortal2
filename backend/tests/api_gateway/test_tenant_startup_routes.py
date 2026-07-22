"""D-42 CLM Stage B — targeted tenant Startup read/write/isolation/audit tests (default suite; no DB, no socket for the core half).

Covers the gateway core's two CLM tenant Startup routes (GET/PATCH /tenant/startups/<startup_ref>)
with doubles, the gateway-side transport client against a loopback stub edge, the Database-Router
executor over an in-memory routed-session double, and the internal Database-Router edge — the
targeted tenant-read / tenant-write / isolation / audit legs the Stage B START-GATE requires.
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402

from api_gateway.main import build_gateway
from api_gateway.models import AuditAction, InboundRequest
from api_gateway.portal import TenantStartupDetailDTO
from api_gateway.ports import (
    TenantStartupOperationsPort,
    TenantStartupReadRequest,
    TenantStartupUpdateRequest,
)

_REF = "clm-startup-1"
_PATH = f"/tenant/startups/{_REF}"
_DESCRIPTION = "a bounded synthetic description"


class StubTenantStartupOps(TenantStartupOperationsPort):
    """A configurable ``TenantStartupOperationsPort`` double: success / absent / raising."""

    def __init__(self, detail: Optional[TenantStartupDetailDTO] = None, *, raising: bool = False) -> None:
        self.detail = detail
        self.raising = raising
        self.reads: List[TenantStartupReadRequest] = []
        self.updates: List[TenantStartupUpdateRequest] = []

    def read(self, request: TenantStartupReadRequest) -> Optional[TenantStartupDetailDTO]:
        self.reads.append(request)
        if self.raising:
            raise ValueError("transport failure (double)")
        return self.detail

    def update(self, request: TenantStartupUpdateRequest) -> Optional[TenantStartupDetailDTO]:
        self.updates.append(request)
        if self.raising:
            raise ValueError("transport failure (double)")
        if self.detail is None:
            return None
        return TenantStartupDetailDTO(
            record_ref=self.detail.record_ref,
            display_name=self.detail.display_name,
            short_description=request.short_description,
            investment_stage=self.detail.investment_stage,
            lineage_reference=self.detail.lineage_reference,
        )


def _detail(ref: str = _REF) -> TenantStartupDetailDTO:
    return TenantStartupDetailDTO(
        record_ref=ref,
        display_name="CLM Synthetic Co",
        short_description="original description",
        investment_stage="seed",
        lineage_reference="clm-lineage-0001",
    )


def _tenant_gateway(ops: Optional[TenantStartupOperationsPort]):
    """A tenant-token gateway with the CLM port injected. Returns (gateway, router, audit, ops)."""
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    router = D.StubRouterDispatch()
    audit = D.RecordingAuditEmitter()
    gateway = build_gateway(authenticator=authn, router=router, audit=audit, tenant_startup=ops)
    return gateway, authn, router, audit


def _get(path: str = _PATH, *, authorization: str = "tok-t1", headers: Optional[Dict[str, str]] = None) -> InboundRequest:
    return InboundRequest(method="GET", path=path, headers=dict(headers or {}), authorization=authorization)


def _patch(body: Optional[bytes], *, path: str = _PATH, authorization: str = "tok-t1") -> InboundRequest:
    return InboundRequest(method="PATCH", path=path, headers={}, authorization=authorization, patch_body=body)


def _events(audit: D.RecordingAuditEmitter, action: AuditAction):
    return [e for e in audit.events if e.action is action]


# ===========================================================================
# Tenant READ (Day-1 leg)
# ===========================================================================
def test_read_success_composes_detail_dto_and_emits_one_read_event() -> None:
    gateway, _, router, audit = _tenant_gateway(StubTenantStartupOps(_detail()))
    resp = gateway.handle(_get())
    assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
    assert isinstance(resp.portal_dto, TenantStartupDetailDTO)
    assert resp.portal_dto.record_ref == _REF and resp.portal_dto.record_residency == "tenant"
    # Single-route: the CLM path NEVER hands off to the Database Router dispatch wire.
    assert router.handoffs == []
    events = _events(audit, AuditAction.TENANT_STARTUP_READ)
    assert len(events) == 1, "exactly ONE references-only tenant_startup_read event per successful read"
    event = events[0]
    assert event.outcome == "success" and event.actor_ref == "p1"
    assert event.tenant_ref == "t1" and event.record_ref == _REF
    assert event.audit_id and event.occurred_at and event.event_version == 1
    # References only: the event never carries the short_description value.
    for value in (event.actor_ref, event.tenant_ref, event.record_ref, event.outcome, event.correlation_id):
        assert value != "original description"


def test_read_unknown_ref_is_consistent_404_not_found_with_no_dto_and_no_event() -> None:
    gateway, _, _, audit = _tenant_gateway(StubTenantStartupOps(None))
    resp = gateway.handle(_get())
    assert (resp.status, resp.public_code) == (404, "not_found")
    assert resp.portal_dto is None, "no DTO on any denial (IC-010 §V.2)"
    assert _events(audit, AuditAction.TENANT_STARTUP_READ) == [], "a denied request emits no success event"


def test_read_transport_failure_collapses_to_503_unavailable() -> None:
    gateway, _, _, audit = _tenant_gateway(StubTenantStartupOps(raising=True))
    resp = gateway.handle(_get())
    assert (resp.status, resp.public_code) == (503, "unavailable")
    assert resp.portal_dto is None
    assert _events(audit, AuditAction.TENANT_STARTUP_READ) == []


def test_tenantless_principal_is_denied_fail_closed_before_the_port() -> None:
    ops = StubTenantStartupOps(_detail())
    gateway, _, _, audit = _tenant_gateway(ops)
    resp = gateway.handle(_get(authorization="tok-ctl"))
    assert (resp.status, resp.public_code) == (403, "tenant_context_required")
    assert ops.reads == [], "a principal-only (tenantless) context never reaches the tenant data port"
    assert len(_events(audit, AuditAction.ROUTE_DENIED)) == 1


def test_unauthorized_tenant_reuses_existing_route_denied_with_no_data() -> None:
    # The CLM isolation proof: a signed tenant claim naming a tenant the principal is not a
    # member of is denied fail-closed 403 BEFORE any routing (IC-005 CLM), recorded as
    # exactly one gateway-edge RouteDenied event, with no tenant data and no DTO.
    ops = StubTenantStartupOps(_detail())
    authn = D.StubAuthenticator()
    authn.add_token("tok-zeta", principal="p1", tenant="tenant-zeta", role="TENANT_AGENT")
    authn.set_deny_access()
    router = D.StubRouterDispatch()
    audit = D.RecordingAuditEmitter()
    gateway = build_gateway(authenticator=authn, router=router, audit=audit, tenant_startup=ops)
    resp = gateway.handle(_get(authorization="tok-zeta"))
    assert (resp.status, resp.public_code) == (403, "tenant_access_denied")
    assert resp.portal_dto is None and ops.reads == [] and router.handoffs == []
    denied = _events(audit, AuditAction.ROUTE_DENIED)
    assert len(denied) == 1, "exactly one gateway-edge RouteDenied record (the existing class-3 record)"
    assert denied[0].outcome == "rejected"
    assert denied[0].audit_id and denied[0].occurred_at and denied[0].event_version == 1


def test_dual_carrier_straddle_is_denied_before_the_port() -> None:
    ops = StubTenantStartupOps(_detail())
    gateway, _, _, audit = _tenant_gateway(ops)
    request = InboundRequest(method="GET", path=_PATH, host="t2.example.internal", headers={"X-Tenant-Id": "t1"}, authorization="tok-t1")
    resp = gateway.handle(request)
    assert (resp.status, resp.public_code) == (403, "isolation_anomaly")
    assert ops.reads == [], "a straddle attempt never reaches the tenant data port"
    assert len(_events(audit, AuditAction.ISOLATION_ANOMALY)) == 1


def test_port_absent_composition_keeps_the_pre_clm_router_handoff() -> None:
    gateway, _, router, _ = _tenant_gateway(None)
    resp = gateway.handle(_get())
    assert len(router.handoffs) == 1, "with no CLM port, TENANT_OPERATION keeps the pre-CLM handoff unchanged"
    assert resp.portal_dto is None


def test_non_startup_tenant_paths_keep_the_pre_clm_router_handoff() -> None:
    gateway, _, router, _ = _tenant_gateway(StubTenantStartupOps(_detail()))
    resp = gateway.handle(_get(path="/tenant/other"))
    assert len(router.handoffs) == 1, "a non-CLM tenant path keeps the pre-CLM handoff even with the port injected"
    assert resp.portal_dto is None


# ===========================================================================
# Tenant WRITE (Day-2 leg): the bounded single-field update
# ===========================================================================
def test_update_success_writes_sole_field_and_emits_one_update_event() -> None:
    ops = StubTenantStartupOps(_detail())
    gateway, _, router, audit = _tenant_gateway(ops)
    resp = gateway.handle(_patch(json.dumps({"short_description": _DESCRIPTION}).encode("utf-8")))
    assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
    assert isinstance(resp.portal_dto, TenantStartupDetailDTO)
    assert resp.portal_dto.short_description == _DESCRIPTION
    assert len(ops.updates) == 1 and ops.updates[0].short_description == _DESCRIPTION
    assert ops.updates[0].target_tenant_ref == "t1", "the signed active tenant — never a client-supplied selector"
    assert router.handoffs == []
    events = _events(audit, AuditAction.TENANT_STARTUP_UPDATE)
    assert len(events) == 1 and events[0].outcome == "success" and events[0].record_ref == _REF
    # The short_description VALUE never appears in the audit event (IC-010 CLM prohibition).
    for value in (events[0].actor_ref, events[0].tenant_ref, events[0].record_ref, events[0].correlation_id, events[0].outcome):
        assert _DESCRIPTION not in str(value)


def test_update_null_clears_the_sole_field() -> None:
    ops = StubTenantStartupOps(_detail())
    gateway, _, _, _ = _tenant_gateway(ops)
    resp = gateway.handle(_patch(b'{"short_description": null}'))
    assert resp.status == 200
    assert isinstance(resp.portal_dto, TenantStartupDetailDTO) and resp.portal_dto.short_description is None
    assert ops.updates[0].short_description is None


def test_update_rejects_every_malformed_body_fail_closed_with_no_port_call() -> None:
    over_bound = json.dumps({"short_description": "a" * 501}).encode("utf-8")
    for bad in (
        None,  # PATCH with no body
        b"",  # empty body
        b"not-json",
        b"[]",
        b"{}",  # missing the allowlisted field
        b'{"long_description": "x"}',  # unknown field
        b'{"short_description": "x", "extra": 1}',  # extra field
        b'{"short_description": 7}',  # wrong type
        over_bound,  # over the 500-character bound
    ):
        ops = StubTenantStartupOps(_detail())
        gateway, _, _, audit = _tenant_gateway(ops)
        resp = gateway.handle(_patch(bad))
        assert (resp.status, resp.public_code) == (403, "forbidden"), f"malformed body {bad!r} must be rejected fail-closed"
        assert ops.updates == [], "NO partial write: a rejected body never reaches the tenant data port"
        assert _events(audit, AuditAction.TENANT_STARTUP_UPDATE) == [], "a malformed request emits no success event"


def test_update_unknown_ref_is_404_and_writes_nothing() -> None:
    ops = StubTenantStartupOps(None)
    gateway, _, _, audit = _tenant_gateway(ops)
    resp = gateway.handle(_patch(b'{"short_description": "x"}'))
    assert (resp.status, resp.public_code) == (404, "not_found")
    assert _events(audit, AuditAction.TENANT_STARTUP_UPDATE) == []


def test_update_transport_failure_collapses_to_503() -> None:
    gateway, _, _, _ = _tenant_gateway(StubTenantStartupOps(raising=True))
    resp = gateway.handle(_patch(b'{"short_description": "x"}'))
    assert (resp.status, resp.public_code) == (503, "unavailable")


# ===========================================================================
# Audit-before-hand-back (the workspace_memberships_read posture, CLM events)
# ===========================================================================
class _RaisingOnActionEmitter(D.RecordingAuditEmitter):
    def __init__(self, failing: AuditAction) -> None:
        super().__init__()
        self._failing = failing

    def emit(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.action is self._failing:
            raise RuntimeError("durable sink terminally unavailable (double)")
        super().emit(event)


def test_read_success_is_never_handed_back_without_its_durable_event() -> None:
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    audit = _RaisingOnActionEmitter(AuditAction.TENANT_STARTUP_READ)
    gateway = build_gateway(authenticator=authn, router=D.StubRouterDispatch(), audit=audit, tenant_startup=StubTenantStartupOps(_detail()))
    resp = gateway.handle(_get())
    assert (resp.status, resp.public_code) == (503, "unavailable"), "audit-before-hand-back: no unevidenced success"
    assert resp.portal_dto is None


def test_denial_is_never_handed_back_without_its_route_denied_record() -> None:
    # D-42 CLM: RouteDenied is durably homed — a denial whose record cannot persist fails
    # closed (503), never an unevidenced 403 hand-back.
    authn = D.StubAuthenticator()
    authn.add_token("tok-zeta", principal="p1", tenant="tenant-zeta", role="TENANT_AGENT")
    authn.set_deny_access()
    audit = _RaisingOnActionEmitter(AuditAction.ROUTE_DENIED)
    gateway = build_gateway(authenticator=authn, router=D.StubRouterDispatch(), audit=audit, tenant_startup=StubTenantStartupOps(_detail()))
    resp = gateway.handle(_get(authorization="tok-zeta"))
    assert (resp.status, resp.public_code) == (503, "unavailable")


# ===========================================================================
# Gateway-side transport client against a loopback stub edge
# ===========================================================================
class _StubEdgeHandler(BaseHTTPRequestHandler):
    script: List[Tuple[int, bytes]] = []
    requests: List[Tuple[str, Dict[str, Any]]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        type(self).requests.append((self.path, body))
        status, payload = type(self).script.pop(0)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        return


def _stub_edge(script: List[Tuple[int, bytes]]):
    _StubEdgeHandler.script = list(script)
    _StubEdgeHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), _StubEdgeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _record_body(**overrides: object) -> bytes:
    record: Dict[str, object] = {
        "record_ref": _REF,
        "display_name": "CLM Synthetic Co",
        "short_description": "original description",
        "investment_stage": "seed",
        "lineage_reference": "clm-lineage-0001",
    }
    record.update(overrides)
    return json.dumps({"version": 1, "record": record}).encode("utf-8")


def test_client_read_maps_wire_record_to_detail_dto_and_carries_references_only() -> None:
    from api_gateway.adapters.providers.http_tenant_startup import HttpTenantStartupOperations

    server, base = _stub_edge([(200, _record_body())])
    try:
        client = HttpTenantStartupOperations(base)
        detail = client.read(TenantStartupReadRequest(startup_ref=_REF, target_tenant_ref="t1", correlation_id="cid-1", actor_ref="p1"))
    finally:
        server.shutdown()
        server.server_close()
    assert detail == TenantStartupDetailDTO(
        record_ref=_REF,
        display_name="CLM Synthetic Co",
        short_description="original description",
        investment_stage="seed",
        lineage_reference="clm-lineage-0001",
    )
    path, envelope = _StubEdgeHandler.requests[0]
    assert path == "/internal/tenant/startups/read"
    assert set(envelope.keys()) == {"v", "startup_ref", "target_tenant_ref", "correlation_id", "actor_ref"}


def test_client_update_envelope_carries_exactly_the_six_keys() -> None:
    from api_gateway.adapters.providers.http_tenant_startup import HttpTenantStartupOperations

    server, base = _stub_edge([(200, _record_body(short_description="new"))])
    try:
        client = HttpTenantStartupOperations(base)
        detail = client.update(
            TenantStartupUpdateRequest(
                startup_ref=_REF, target_tenant_ref="t1", correlation_id="cid-1", actor_ref="p1", short_description="new"
            )
        )
    finally:
        server.shutdown()
        server.server_close()
    assert detail is not None and detail.short_description == "new"
    path, envelope = _StubEdgeHandler.requests[0]
    assert path == "/internal/tenant/startups/update"
    assert set(envelope.keys()) == {"v", "startup_ref", "target_tenant_ref", "correlation_id", "actor_ref", "short_description"}


def test_client_maps_404_to_none_and_raises_on_everything_else() -> None:
    from api_gateway.adapters.providers.http_tenant_startup import HttpTenantStartupOperations

    request = TenantStartupReadRequest(startup_ref=_REF, target_tenant_ref="t1", correlation_id="cid-1", actor_ref="p1")
    server, base = _stub_edge([(404, json.dumps({"version": 1, "result": "NOT_FOUND"}).encode("utf-8"))])
    try:
        assert HttpTenantStartupOperations(base).read(request) is None
    finally:
        server.shutdown()
        server.server_close()
    for status, payload in (
        (503, json.dumps({"version": 1, "result": "UNAVAILABLE"}).encode("utf-8")),
        (200, b"not-json"),
        (200, json.dumps({"version": 1, "record": {"record_ref": _REF}}).encode("utf-8")),  # wrong record shape
        (200, _record_body(record_ref="a-different-ref")),  # reference mismatch: never trusted
        (200, _record_body(short_description="a" * 501)),  # over-bound content
    ):
        server, base = _stub_edge([(status, payload)])
        try:
            raised = False
            try:
                HttpTenantStartupOperations(base).read(request)
            except Exception:
                raised = True
            assert raised, f"the client must raise on ({status}, {payload[:40]!r}) so the gateway fails closed to 503"
        finally:
            server.shutdown()
            server.server_close()
