"""B5-BLK-6B — IC-010 §V portal response composition: behavior + adapter + denial matrix.

Owns (per the 6B execution PRD §16): adapter parsing; 404/unavailable/timeout/malformed
behavior; handler composition; per-category success; EVERY denial path (``portal_dto is
None`` on all of them); MembershipsForPrincipal self-scoping (the authenticated principal
only — a client-supplied selector is never read); the mandatory rollback/default proof
(seam unset ⇒ pre-6B behavior, ``portal_dto is None``); and the behavioral mutation
detectors (denial-to-success, DTO-on-denial, import-reported-complete, missing-auth
pipeline order, client-supplied principal, seam-on-by-default).

Adapter legs run against a REAL loopback HTTP server (a canned control-plane read edge,
plus the REAL ``control_plane`` read edge end-to-end) — best-effort with the established
OSError self-skip; the stub-backed legs carry the assertions regardless of sockets.
Stdlib-only; no database; runnable standalone:
python tests/api_gateway/test_portal_response_composition.py
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.adapters.providers.http_control_plane_read import HttpControlPlaneRead  # noqa: E402
from api_gateway.main import (  # noqa: E402
    GW_CONTROL_READ_BASE_URL_ENV,
    build_control_plane_read_from_env,
    build_gateway,
)
from api_gateway.models import AuditAction, DispatchCategory, RouteOutcome  # noqa: E402
from api_gateway.portal import (  # noqa: E402
    DirectoryEntryDTO,
    GlobalInvestorSummaryDTO,
    GlobalStartupSummaryDTO,
    ImportInitiationDTO,
    MembershipEntryDTO,
    WorkspaceMembershipDTO,
    compose_display_ref,
)
from api_gateway.ports import RouterDispatchPort  # noqa: E402
from shared.context import RequestContext  # noqa: E402

_ENTRIES = (DirectoryEntryDTO(record_ref="rec-1", display_name="Alpha"), DirectoryEntryDTO(record_ref="rec-2", display_name="Beta"))
_MEMBERS = (
    MembershipEntryDTO(tenant_id="t1", role="MASTER_AGENT", display_ref=compose_display_ref("t1")),
    MembershipEntryDTO(tenant_id="t2", role="MASTER_AGENT", display_ref=compose_display_ref("t2")),
)


class _DenyRouter(RouterDispatchPort):
    """A router double returning a caller-supplied denial outcome (still records handoffs)."""

    def __init__(self, outcome: RouteOutcome) -> None:
        self._outcome = outcome
        self.handoffs: list = []

    def dispatch(self, context: RequestContext, decision) -> RouteOutcome:  # noqa: ANN001
        self.handoffs.append((context, decision))
        return self._outcome


# --- per-category success (the composition seam ACTIVE) --------------------------------------------
def test_directory_read_success_composes_startup_page_in_cp_order() -> None:
    cp = D.StubControlPlaneRead(startup_entries=_ENTRIES)
    gateway, _authn, router, audit = D.control_read_setup(cp)
    resp = gateway.handle(D.req(path="/directory/startup", authorization="tok-ctl"))
    assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
    assert resp.category is DispatchCategory.GLOBAL_DIRECTORY_READ
    assert isinstance(resp.portal_dto, GlobalStartupSummaryDTO)
    # Control-Plane order preserved — the gateway never re-sorts (IC-010 §B).
    assert tuple(e.record_ref for e in resp.portal_dto.records) == ("rec-1", "rec-2")
    assert (resp.portal_dto.record_origin, resp.portal_dto.record_residency) == ("global", "global")
    assert resp.portal_dto.record_type == "GlobalStartupDirectory"
    assert router.handoffs == []  # the CONTROL read is composed from the read port, not routed
    assert audit.events == []  # a clean composed read emits no anomaly (no new audit event)


def test_directory_read_success_composes_investor_page() -> None:
    cp = D.StubControlPlaneRead(investor_entries=_ENTRIES)
    gateway, _authn, _router, _audit = D.control_read_setup(cp)
    resp = gateway.handle(D.req(path="/directory/investor", authorization="tok-ctl"))
    assert isinstance(resp.portal_dto, GlobalInvestorSummaryDTO)
    assert resp.portal_dto.record_type == "GlobalInvestorDirectory"
    assert cp.directory_kinds == ["investor"]


def test_directory_read_empty_directory_is_success_with_empty_sequence() -> None:
    gateway, _authn, _router, _audit = D.control_read_setup(D.StubControlPlaneRead(mode="empty"))
    resp = gateway.handle(D.req(path="/directory/startup", authorization="tok-ctl"))
    assert (resp.status, resp.public_code) == (200, "ok")
    assert isinstance(resp.portal_dto, GlobalStartupSummaryDTO) and resp.portal_dto.records == ()


def test_memberships_success_composes_membership_dto_with_display_refs() -> None:
    cp = D.StubControlPlaneRead(memberships=_MEMBERS)
    gateway, _authn, router, audit = D.control_read_setup(cp)
    resp = gateway.handle(D.req(path="/memberships", authorization="tok-ctl"))
    assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
    assert resp.category is DispatchCategory.MEMBERSHIPS_FOR_PRINCIPAL
    assert isinstance(resp.portal_dto, WorkspaceMembershipDTO)
    assert tuple(m.tenant_id for m in resp.portal_dto.memberships) == ("t1", "t2")
    # display_ref is gateway-composed in the pinned deterministic format (derived, not stored).
    assert resp.portal_dto.memberships[0].display_ref == "ref:tenant/t1/display"
    assert router.handoffs == []
    # B5-BLK-6C-B: the successful self-scoped enumeration emits EXACTLY ONE
    # workspace_memberships_read success-access event (IC-010 §J; IC-002 class 3b).
    assert [e.action for e in audit.events] == [AuditAction.WORKSPACE_MEMBERSHIPS_READ]


def test_memberships_empty_is_success_with_present_dto_and_empty_tuple() -> None:
    # An empty membership set is a lawful success: 200 + a PRESENT DTO with an empty tuple —
    # never an error, never None (IC-002 semantics; a principal may hold zero memberships).
    gateway, _authn, _router, audit = D.control_read_setup(D.StubControlPlaneRead(mode="empty"))
    resp = gateway.handle(D.req(path="/memberships", authorization="tok-ctl"))
    assert (resp.status, resp.public_code) == (200, "ok")
    assert isinstance(resp.portal_dto, WorkspaceMembershipDTO) and resp.portal_dto.memberships == ()
    # B5-BLK-6C-B: a successful EMPTY enumeration is still a successful enumeration and
    # emits exactly one success event — never zero (IC-002 class 3b).
    assert [e.action for e in audit.events] == [AuditAction.WORKSPACE_MEMBERSHIPS_READ]


def test_import_initiation_success_composes_accepted_envelope_only() -> None:
    cp = D.StubControlPlaneRead()
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    router = D.StubRouterDispatch()
    gateway = build_gateway(authenticator=authn, router=router, control_read=cp, audit=D.RecordingAuditEmitter())
    resp = gateway.handle(D.req(method="POST", path="/import/global-startup/rec-9", authorization="tok-t1"))
    assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
    assert resp.category is DispatchCategory.IMPORT_INITIATION
    assert isinstance(resp.portal_dto, ImportInitiationDTO)
    # The envelope states ONLY that initiation was accepted — never completion, never a
    # job/lineage/idempotency identifier (nothing was created; no import was executed).
    assert resp.portal_dto.initiation == "accepted"
    assert resp.portal_dto.source_ref == "global-startup/rec-9"  # gateway-validated request reference
    assert resp.portal_dto.target_tenant_ref == "t1"  # the single dispatch-decision tenant reference
    assert len(router.handoffs) == 1  # the dispatch itself still went through the router


def test_tenant_operation_returns_no_dto_even_with_seam_active() -> None:
    cp = D.StubControlPlaneRead(startup_entries=_ENTRIES, memberships=_MEMBERS)
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    router = D.StubRouterDispatch()
    gateway = build_gateway(authenticator=authn, router=router, control_read=cp, audit=D.RecordingAuditEmitter())
    resp = gateway.handle(D.req(method="POST", path="/tenant/deals", authorization="tok-t1"))
    assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
    assert resp.category is DispatchCategory.TENANT_OPERATION
    assert resp.portal_dto is None  # dispatch/denial semantics only — no tenant business DTO
    assert len(router.handoffs) == 1 and cp.directory_kinds == [] and cp.principals == []


# --- self-scoping (mutation detector: client-supplied membership principal) ------------------------
def test_memberships_principal_is_authenticated_ref_never_client_supplied() -> None:
    cp = D.StubControlPlaneRead(memberships=_MEMBERS)
    gateway, _authn, _router, _audit = D.control_read_setup(cp, principal="ops")
    # A client-supplied selector rides the query AND a prohibited workspace-ish channel;
    # the gateway must bind the port call to the AUTHENTICATED principal exclusively.
    resp = gateway.handle(D.req(path="/memberships", query={"p": "victim"}, authorization="tok-ctl"))
    assert resp.status == 200
    assert cp.principals == ["ops"], cp.principals  # never "victim"


def test_memberships_self_scoping_holds_for_tenant_scoped_principals_too() -> None:
    cp = D.StubControlPlaneRead(memberships=_MEMBERS)
    gateway, _authn, _router, _audit = D.control_read_setup(cp, token="tok-ma", principal="agent-9", tenant="t1", role="MASTER_AGENT")
    resp = gateway.handle(D.req(path="/memberships", query={"p": "someone-else"}, authorization="tok-ma", host="t1.snackportal.example"))
    assert resp.status == 200
    assert cp.principals == ["agent-9"]


# --- failure semantics (CP unavailable / timeout / malformed / not found) --------------------------
def test_cp_unavailable_maps_to_503_unavailable_no_dto() -> None:
    gateway, _authn, _router, _audit = D.control_read_setup(D.StubControlPlaneRead(mode="unavailable"))
    for path in ("/directory/startup", "/memberships"):
        resp = gateway.handle(D.req(path=path, authorization="tok-ctl"))
        assert (resp.status, resp.public_code) == (503, "unavailable")
        assert resp.portal_dto is None and resp.dispatched is False


def test_cp_timeout_maps_to_503_unavailable_no_dto() -> None:
    gateway, _authn, _router, _audit = D.control_read_setup(D.StubControlPlaneRead(mode="timeout"))
    resp = gateway.handle(D.req(path="/directory/investor", authorization="tok-ctl"))
    assert (resp.status, resp.public_code) == (503, "unavailable") and resp.portal_dto is None


def test_cp_malformed_result_maps_to_503_unavailable_no_dto() -> None:
    gateway, _authn, _router, _audit = D.control_read_setup(D.StubControlPlaneRead(mode="malformed"))
    for path in ("/directory/startup", "/memberships"):
        resp = gateway.handle(D.req(path=path, authorization="tok-ctl"))
        assert (resp.status, resp.public_code) == (503, "unavailable") and resp.portal_dto is None


def test_unknown_directory_kind_is_existing_consistent_403_denial() -> None:
    gateway, _authn, _router, audit = D.control_read_setup(D.StubControlPlaneRead(startup_entries=_ENTRIES))
    for path in ("/directory/deal", "/directory", "/directory/startup/rec-1"):
        resp = gateway.handle(D.req(path=path, authorization="tok-ctl"))
        assert (resp.status, resp.public_code) == (403, "forbidden"), path
        assert resp.portal_dto is None
    # The consistent denial is audited with the EXISTING RouteDenied action — no new class.
    assert {e.action.value for e in audit.events} == {"RouteDenied"}


def test_cp_read_port_absent_result_is_consistent_403_denial() -> None:
    gateway, _authn, _router, audit = D.control_read_setup(D.StubControlPlaneRead(mode="absent"))
    resp = gateway.handle(D.req(path="/memberships", authorization="tok-ctl"))
    assert (resp.status, resp.public_code) == (403, "forbidden") and resp.portal_dto is None
    assert [e.action.value for e in audit.events] == ["RouteDenied"]


# --- every denial path returns portal_dto is None (mutation detectors 9/10/13) --------------------
def test_no_dto_on_any_denial_path() -> None:
    cp = D.StubControlPlaneRead(startup_entries=_ENTRIES, memberships=_MEMBERS)

    # unauthenticated (missing token) — and the port is NEVER reached (pipeline order).
    gateway, _authn, _router, _audit = D.control_read_setup(cp)
    resp = gateway.handle(D.req(path="/directory/startup"))
    assert (resp.status, resp.public_code) == (401, "unauthenticated") and resp.portal_dto is None
    resp = gateway.handle(D.req(path="/memberships", authorization="tok-nope"))
    assert (resp.status, resp.public_code) == (401, "unauthenticated") and resp.portal_dto is None
    assert cp.directory_kinds == [] and cp.principals == []  # authentication precedes composition

    # authorization denial (auth router says no).
    gateway, authn, _router, _audit = D.control_read_setup(cp, token="tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    authn.set_deny_access()
    resp = gateway.handle(D.req(path="/tenant/x", authorization="tok-t1"))
    assert resp.status == 403 and resp.portal_dto is None

    # carrier mismatch.
    gateway, _authn, _router, _audit = D.control_read_setup(cp, token="tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    resp = gateway.handle(D.req(path="/tenant/x", authorization="tok-t1", headers={"X-Tenant-Id": "t2"}))
    assert (resp.status, resp.public_code) == (403, "carrier_mismatch") and resp.portal_dto is None

    # tenant straddle (dual distinct carriers) — 403 isolation_anomaly, no DTO.
    gateway, _authn, _router, audit = D.control_read_setup(cp, token="tok-t1", principal="p1", tenant="t1", role="MASTER_AGENT")
    resp = gateway.handle(D.req(path="/tenant/x", authorization="tok-t1", host="t1.snackportal.example", headers={"X-Tenant-Id": "t2"}))
    assert (resp.status, resp.public_code) == (403, "isolation_anomaly") and resp.portal_dto is None
    assert [e.action.value for e in audit.events] == ["IsolationAnomaly"]

    # unknown route (fail-closed classifier).
    gateway, _authn, _router, _audit = D.control_read_setup(cp)
    resp = gateway.handle(D.req(path="/shared/deals", authorization="tok-ctl"))
    assert (resp.status, resp.public_code) == (403, "unknown_route") and resp.portal_dto is None

    # tenant operation without a tenant context (control-scope claim on a tenant path).
    resp = gateway.handle(D.req(method="POST", path="/tenant/x", authorization="tok-ctl"))
    assert (resp.status, resp.public_code) == (403, "tenant_context_required") and resp.portal_dto is None

    # authenticator unavailable.
    gateway, authn, _router, _audit = D.control_read_setup(cp)
    authn.set_unavailable()
    resp = gateway.handle(D.req(path="/memberships", authorization="tok-ctl"))
    assert (resp.status, resp.public_code) == (503, "unavailable") and resp.portal_dto is None


def test_routing_denial_preserved_and_no_dto_on_import_rejection() -> None:
    # Import-initiation rejection: the router's outcome (status/public_code) is preserved
    # UNCHANGED and no DTO is attached — a denial is never converted into success.
    cp = D.StubControlPlaneRead()
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    for outcome in (
        RouteOutcome(status=403, public_code="forbidden", dispatched=False),
        RouteOutcome(status=404, public_code="not_found", dispatched=False),
        RouteOutcome(status=503, public_code="unavailable", dispatched=False),
        RouteOutcome(status=503, public_code="not_ready", dispatched=True),  # dispatched but NOT successful
    ):
        router = _DenyRouter(outcome)
        gateway = build_gateway(authenticator=authn, router=router, control_read=cp, audit=D.RecordingAuditEmitter())
        resp = gateway.handle(D.req(method="POST", path="/import/global-startup/rec-9", authorization="tok-t1"))
        assert (resp.status, resp.public_code, resp.dispatched) == (outcome.status, outcome.public_code, outcome.dispatched)
        assert resp.portal_dto is None, outcome


# --- rollback/default proof (mutation detector 19: the seam must be OFF by default) ----------------
def test_rollback_default_preserves_pre_6b_behavior_and_none_dto() -> None:
    # With NO control_read injected (the default), every category continues through the
    # RouterDispatchPort exactly as pre-6B and portal_dto is None on every result.
    authn = D.StubAuthenticator()
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    router = D.StubRouterDispatch()
    gateway = D.build_gateway(authenticator=authn, router=router, audit=D.RecordingAuditEmitter())
    for method, path, token in (
        ("GET", "/directory/startup", "tok-ctl"),
        ("GET", "/memberships", "tok-ctl"),
        ("POST", "/import/global-startup/rec-9", "tok-t1"),
        ("POST", "/tenant/deals", "tok-t1"),
    ):
        resp = gateway.handle(D.req(method=method, path=path, authorization=token))
        assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True), path
        assert resp.portal_dto is None, path
    assert len(router.handoffs) == 4  # ALL FOUR categories routed — none composed


def test_env_selector_unset_or_empty_is_none_and_invalid_fails_before_socket() -> None:
    import os

    old = os.environ.pop(GW_CONTROL_READ_BASE_URL_ENV, None)
    try:
        assert build_control_plane_read_from_env() is None  # unset -> None (seam OFF)
        os.environ[GW_CONTROL_READ_BASE_URL_ENV] = "   "
        assert build_control_plane_read_from_env() is None  # empty/whitespace -> None
        for bad in ("https://cp.internal", "cp.internal:8080", "ftp://x", "http://"):
            os.environ[GW_CONTROL_READ_BASE_URL_ENV] = bad
            raised = False
            try:
                build_control_plane_read_from_env()
            except ValueError:
                raised = True
            assert raised, f"{bad!r} must raise ValueError before any socket"
        # A structurally valid internal http URL selects the LAZY transport client — the
        # construction performs no network I/O (the host is not even resolvable).
        os.environ[GW_CONTROL_READ_BASE_URL_ENV] = "http://sp2-nonexistent-cp.internal:19"
        port = build_control_plane_read_from_env()
        assert isinstance(port, HttpControlPlaneRead)
    finally:
        if old is None:
            os.environ.pop(GW_CONTROL_READ_BASE_URL_ENV, None)
        else:
            os.environ[GW_CONTROL_READ_BASE_URL_ENV] = old


# --- adapter parsing over a REAL loopback wire (best-effort; OSError self-skip) --------------------
class _CannedCpHandler(BaseHTTPRequestHandler):
    """A canned control-plane read edge: per-path fixtures + failure behaviors.

    Records every request (hit count + raw path) so the B5-BLK-6C-C pagination-limitation leg can
    prove the adapter sends no cursor/limit and never follows a served ``next_cursor``.
    """

    behavior = "ok"  # ok | malformed | wrongshape | slow | boom | cursor
    hits = 0
    request_paths: list = []

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        type(self).hits += 1
        type(self).request_paths.append(self.path)
        if self.behavior == "cursor":
            body = {"records": [{"record_id": "rec-1", "display_name": "Alpha"}], "next_cursor": "100"}
            self._send(200, json.dumps(body).encode("utf-8"))
            return
        if self.behavior == "slow":
            time.sleep(0.4)
        if self.behavior == "boom":
            self._send(500, b'{"error":"internal"}')
            return
        if self.behavior == "malformed":
            self._send(200, b"this is not json")
            return
        if self.behavior == "wrongshape":
            self._send(200, json.dumps({"records": "nope"}).encode("utf-8"))
            return
        if self.path.startswith("/directory/startup"):
            body = {
                "records": [
                    {"directory": "GlobalStartupDirectory", "record_id": "rec-1", "display_name": "Alpha", "attributes": {}},
                    {"directory": "GlobalStartupDirectory", "record_id": "rec-2", "display_name": "Beta", "attributes": {}},
                ],
                "next_cursor": None,
            }
            self._send(200, json.dumps(body).encode("utf-8"))
            return
        if self.path.startswith("/memberships?p=u1"):
            body = {"memberships": [{"tenant_id": "t1", "role": "TENANT_ADMIN"}, {"tenant_id": "t2", "role": "MASTER_AGENT"}]}
            self._send(200, json.dumps(body).encode("utf-8"))
            return
        self._send(404, b'{"error":"not_found"}')

    def _send(self, status: int, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        return


def _canned_server() -> Optional[Tuple[HTTPServer, str]]:
    try:
        server = HTTPServer(("127.0.0.1", 0), _CannedCpHandler)
    except OSError:
        return None  # binding unavailable; transport check skipped
    host, port = server.server_address[0], server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{port}"


def test_adapter_parses_typed_dtos_and_maps_404_to_none_over_real_wire() -> None:
    started = _canned_server()
    if started is None:
        return
    server, base = started
    try:
        _CannedCpHandler.behavior = "ok"
        client = HttpControlPlaneRead(base, timeout=2.0)
        page = client.directory("startup")
        assert isinstance(page, GlobalStartupSummaryDTO)
        assert tuple(e.record_ref for e in page.records) == ("rec-1", "rec-2")  # CP order preserved
        assert page.records[0].display_name == "Alpha"
        members = client.memberships_for_principal("u1")
        assert isinstance(members, WorkspaceMembershipDTO)
        assert tuple(m.tenant_id for m in members.memberships) == ("t1", "t2")
        assert members.memberships[0].display_ref == "ref:tenant/t1/display"  # gateway-composed
        # Unapproved kind: refused adapter-side with NO wire call; unknown principal path -> 404 -> None.
        assert client.directory("deal") is None
        assert client.memberships_for_principal("ghost") is None  # canned edge 404s unknown paths
    except OSError:
        return  # loopback networking blocked; transport check skipped
    finally:
        server.shutdown()
        server.server_close()


def test_adapter_raises_on_500_malformed_wrongshape_and_timeout() -> None:
    started = _canned_server()
    if started is None:
        return
    server, base = started
    try:
        for behavior, timeout in (("boom", 2.0), ("malformed", 2.0), ("wrongshape", 2.0), ("slow", 0.05)):
            _CannedCpHandler.behavior = behavior
            client = HttpControlPlaneRead(base, timeout=timeout)
            raised = False
            try:
                client.directory("startup")
            except Exception:
                raised = True  # the gateway collapses this fail-closed to 503 unavailable
            assert raised, f"behavior {behavior!r} must raise (fail closed), never return a value"
    except OSError:
        return
    finally:
        _CannedCpHandler.behavior = "ok"
        server.shutdown()
        server.server_close()


# --- B5-BLK-6C-C residual companions (D9 / D11 / D15 / D16) ----------------------------------------
def test_client_supplied_kind_query_is_never_read() -> None:
    # B5-BLK-6C-C (D9): the directory kind is a PATH-derived operation parameter; a client-supplied
    # query value can never select the kind, reach an unsupported provider path, or alter the taxonomy.
    cp = D.StubControlPlaneRead(startup_entries=_ENTRIES)
    gateway, _authn, _router, _audit = D.control_read_setup(cp)
    resp = gateway.handle(D.req(path="/directory/startup", query={"kind": "deal"}, authorization="tok-ctl"))
    assert (resp.status, resp.public_code) == (200, "ok")
    assert isinstance(resp.portal_dto, GlobalStartupSummaryDTO)
    assert cp.directory_kinds == ["startup"], cp.directory_kinds  # never the client-supplied "deal"


def test_composed_portal_dto_instances_carry_exact_field_sets() -> None:
    # B5-BLK-6C-C (D15 companion): the INSTANCES the gateway composes — not only the classes —
    # carry exactly the approved field sets (references only; no extra field can ride a response).
    cp = D.StubControlPlaneRead(startup_entries=_ENTRIES, investor_entries=_ENTRIES, memberships=_MEMBERS)
    gateway, _authn, _router, _audit = D.control_read_setup(cp)
    startup = gateway.handle(D.req(path="/directory/startup", authorization="tok-ctl")).portal_dto
    investor = gateway.handle(D.req(path="/directory/investor", authorization="tok-ctl")).portal_dto
    members = gateway.handle(D.req(path="/memberships", authorization="tok-ctl")).portal_dto
    assert startup is not None and investor is not None and members is not None
    directory_fields = {"records", "record_origin", "record_residency", "record_type"}
    assert {f.name for f in dataclasses.fields(startup)} == directory_fields
    assert {f.name for f in dataclasses.fields(investor)} == directory_fields
    assert {f.name for f in dataclasses.fields(members)} == {"memberships"}
    assert all({f.name for f in dataclasses.fields(e)} == {"record_ref", "display_name"} for e in startup.records)
    assert all({f.name for f in dataclasses.fields(m)} == {"tenant_id", "role", "display_ref"} for m in members.memberships)
    authn = D.StubAuthenticator()
    authn.add_token("tok-t1", principal="p1", tenant="t1", role="TENANT_AGENT")
    gateway = D.build_gateway(authenticator=authn, router=D.StubRouterDispatch(), control_read=cp, audit=D.RecordingAuditEmitter())
    imported = gateway.handle(D.req(method="POST", path="/import/global-startup/rec-9", authorization="tok-t1")).portal_dto
    assert imported is not None
    assert {f.name for f in dataclasses.fields(imported)} == {"source_ref", "target_tenant_ref", "initiation"}


def test_adapter_sends_no_cursor_and_never_follows_next_cursor_single_page() -> None:
    # B5-BLK-6C-C (D16): ONE directory page only — the adapter sends no cursor/limit and a served
    # next_cursor is ignored (exactly one provider request). Pagination support is NOT claimed.
    started = _canned_server()
    if started is None:
        return
    server, base = started
    try:
        _CannedCpHandler.behavior = "cursor"
        _CannedCpHandler.hits = 0
        _CannedCpHandler.request_paths.clear()
        client = HttpControlPlaneRead(base, timeout=2.0)
        page = client.directory("startup")
        assert isinstance(page, GlobalStartupSummaryDTO)
        assert tuple(e.record_ref for e in page.records) == ("rec-1",)  # the single served page only
        assert _CannedCpHandler.hits == 1, "a served next_cursor must NEVER trigger a follow-up request"
        assert _CannedCpHandler.request_paths == ["/directory/startup"], "no cursor/limit query may be sent"
    except OSError:
        return  # loopback networking blocked; transport check skipped
    finally:
        _CannedCpHandler.behavior = "ok"
        server.shutdown()
        server.server_close()


def test_oversized_response_maps_to_503_unavailable_no_dto() -> None:
    # B5-BLK-6C-C (D11): a response larger than the bounded size raises adapter-side and the
    # gateway collapses it fail-closed to 503 unavailable with no DTO and no success audit event.
    started = _canned_server()
    if started is None:
        return
    server, base = started
    try:
        _CannedCpHandler.behavior = "ok"
        client = HttpControlPlaneRead(base, timeout=2.0, max_response_bytes=8)
        raised = False
        try:
            client.directory("startup")
        except ValueError:
            raised = True
        assert raised, "an oversized response must raise (fail closed), never return a value"
        gateway, _authn, _router, audit = D.control_read_setup(client, principal="u1")
        resp = gateway.handle(D.req(path="/memberships", authorization="tok-ctl"))
        assert (resp.status, resp.public_code) == (503, "unavailable") and resp.portal_dto is None
        assert audit.events == []  # no success event on the oversized failure path
    except OSError:
        return  # loopback networking blocked; transport check skipped
    finally:
        server.shutdown()
        server.server_close()


def test_end_to_end_real_cp_read_edge_through_real_gateway() -> None:
    # The strongest in-slice composition proof: the REAL control_plane read edge (in-memory
    # store) → the REAL HttpControlPlaneRead adapter → the REAL gateway pipeline.
    from control_plane.adapters.providers.http_read_api import make_server
    from control_plane.adapters.providers.in_memory_store import InMemoryControlStore
    from control_plane.main import ControlPlane
    from control_plane.records import DirectoryKind, DirectoryRecord, MembershipRecord, Role

    store = InMemoryControlStore()
    store.put_directory_record(DirectoryRecord(directory=DirectoryKind.STARTUP, record_id="g1", display_name="S1", attributes={}))
    store.put_directory_record(DirectoryRecord(directory=DirectoryKind.STARTUP, record_id="g2", display_name="S2", attributes={}))
    store.put_membership(MembershipRecord(principal_ref="ops", tenant_id="t1", role=Role.MASTER_AGENT))
    try:
        server, base = make_server(ControlPlane(store=store), "127.0.0.1", 0)
    except OSError:
        return  # binding unavailable; transport check skipped
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        gateway, _authn, router, audit = D.control_read_setup(HttpControlPlaneRead(base, timeout=2.0))
        resp = gateway.handle(D.req(path="/directory/startup", authorization="tok-ctl"))
        assert (resp.status, resp.public_code, resp.dispatched) == (200, "ok", True)
        assert isinstance(resp.portal_dto, GlobalStartupSummaryDTO)
        assert tuple(e.record_ref for e in resp.portal_dto.records) == ("g1", "g2")
        assert audit.events == []  # the directory leg contributes ZERO events (§R Reserved)
        resp = gateway.handle(D.req(path="/memberships", authorization="tok-ctl"))
        assert isinstance(resp.portal_dto, WorkspaceMembershipDTO)
        assert tuple((m.tenant_id, m.role, m.display_ref) for m in resp.portal_dto.memberships) == (
            ("t1", "MASTER_AGENT", "ref:tenant/t1/display"),
        )
        assert router.handoffs == []  # composed, not routed
        # B5-BLK-6C-B: exactly ONE event total — directory leg 0 + memberships leg 1.
        assert [e.action for e in audit.events] == [AuditAction.WORKSPACE_MEMBERSHIPS_READ]
    except OSError:
        return  # loopback networking blocked; transport check skipped
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    _h.run(
        [
            test_directory_read_success_composes_startup_page_in_cp_order,
            test_directory_read_success_composes_investor_page,
            test_directory_read_empty_directory_is_success_with_empty_sequence,
            test_memberships_success_composes_membership_dto_with_display_refs,
            test_memberships_empty_is_success_with_present_dto_and_empty_tuple,
            test_import_initiation_success_composes_accepted_envelope_only,
            test_tenant_operation_returns_no_dto_even_with_seam_active,
            test_memberships_principal_is_authenticated_ref_never_client_supplied,
            test_memberships_self_scoping_holds_for_tenant_scoped_principals_too,
            test_cp_unavailable_maps_to_503_unavailable_no_dto,
            test_cp_timeout_maps_to_503_unavailable_no_dto,
            test_cp_malformed_result_maps_to_503_unavailable_no_dto,
            test_unknown_directory_kind_is_existing_consistent_403_denial,
            test_cp_read_port_absent_result_is_consistent_403_denial,
            test_no_dto_on_any_denial_path,
            test_routing_denial_preserved_and_no_dto_on_import_rejection,
            test_rollback_default_preserves_pre_6b_behavior_and_none_dto,
            test_env_selector_unset_or_empty_is_none_and_invalid_fails_before_socket,
            test_adapter_parses_typed_dtos_and_maps_404_to_none_over_real_wire,
            test_adapter_raises_on_500_malformed_wrongshape_and_timeout,
            test_client_supplied_kind_query_is_never_read,
            test_composed_portal_dto_instances_carry_exact_field_sets,
            test_adapter_sends_no_cursor_and_never_follows_next_cursor_single_page,
            test_oversized_response_maps_to_503_unavailable_no_dto,
            test_end_to_end_real_cp_read_edge_through_real_gateway,
        ]
    )
