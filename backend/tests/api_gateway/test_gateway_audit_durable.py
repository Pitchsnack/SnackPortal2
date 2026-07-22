"""Gateway Audit V1a — durable-audit behavioral contract (default suite; no PostgreSQL).

Covers the gateway-side durable operational-audit slice end to end WITHOUT a database:

* the ``DurableAuditEmitter`` transport client — exact ten-key references-only wire shape, and the
  fail-closed mapping of every ingest answer (INSERTED / DUPLICATE_MATCH success; 400/409/503 and an
  unreachable edge → bounded ``DurableAuditTransportError``), exercised against a canned loopback
  server (no control_plane import);
* the ``BoundedGatewayAuditPolicy`` — exactly ONE retry for a transient ``unavailable`` failure
  (maximum two transport calls), NEVER for ``invalid`` / ``conflict``, and terminal re-raise;
* the gateway success edge — ``Gateway.handle`` emits exactly one durable success event; a terminally
  unavailable durable sink collapses to the typed ``503 unavailable`` (audit-before-hand-back, fail
  closed) and never a served 200; non-emission on every denial/failure class and directory-read
  silence are preserved;
* the ``build_audit_emitter_from_env`` selector — unset → None (default in-memory no-sink emitter);
  valid http → the durable policy; malformed → ValueError BEFORE any socket; real durable mode never
  silently falls back to ``InMemoryAuditEmitter``; the default non-durable composition is unchanged;
  and the gateway never receives a database driver or a Control-DB descriptor.

Pure stdlib; standalone-runnable: ``python tests/api_gateway/test_gateway_audit_durable.py``.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _gateway_doubles as D  # noqa: E402
import _h  # noqa: E402

from api_gateway.adapters.providers.durable_audit_emitter import (  # noqa: E402
    DurableAuditEmitter,
    DurableAuditTransportError,
    _wire_event,
)
from api_gateway.adapters.providers.in_memory_audit_emitter import InMemoryAuditEmitter  # noqa: E402
from api_gateway.main import (  # noqa: E402
    GW_AUDIT_SINK_BASE_URL_ENV,
    BoundedGatewayAuditPolicy,
    ClmDurableAuditPartition,
    build_audit_emitter_from_env,
    build_gateway,
)
from api_gateway.models import AuditAction, GatewayAuditEvent  # noqa: E402
from api_gateway.portal import MembershipEntryDTO, compose_display_ref  # noqa: E402
from api_gateway.ports import AuditEmitterPort  # noqa: E402

_SUCCESS = AuditAction.WORKSPACE_MEMBERSHIPS_READ

_EVENT = GatewayAuditEvent(
    action=_SUCCESS,
    correlation_id="cid-1",
    outcome="success",
    actor_ref="ops",
    subject_ref="ops",
    audit_id="0123456789abcdef0123456789abcdef",
    occurred_at="2026-07-18T10:00:00+00:00",
    event_version=1,
)


# --- a canned loopback ingest server (self-contained; no control_plane import) --------------------
@contextlib.contextmanager
def _canned_server(status: int, result: Optional[str]) -> Iterator[Tuple[str, List[bytes]]]:
    captured: List[bytes] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            captured.append(self.rfile.read(length) if length > 0 else b"")
            body = b"" if result is None else json.dumps({"version": 1, "result": result}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            return

    import threading

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}", captured
    finally:
        server.shutdown()
        server.server_close()


# --- counting AuditEmitterPort doubles ------------------------------------------------------------
class _CountingEmitter(AuditEmitterPort):
    """Records emits; raises a bounded transport error for the first ``fail_times`` calls."""

    def __init__(self, *, fail_kind: Optional[str] = None, fail_times: int = 0) -> None:
        self.events: List[GatewayAuditEvent] = []
        self.calls = 0
        self._fail_kind = fail_kind
        self._fail_times = fail_times

    def emit(self, event: GatewayAuditEvent) -> None:
        self.calls += 1
        self.events.append(event)
        if self._fail_kind is not None and self.calls <= self._fail_times:
            raise DurableAuditTransportError(self._fail_kind)


def _members(*tenant_ids: str):
    return tuple(MembershipEntryDTO(tenant_id=t, role="MASTER_AGENT", display_ref=compose_display_ref(t)) for t in tenant_ids)


def _gateway_with_audit(cp, audit: AuditEmitterPort):
    """A CONTROL-principal gateway with the read seam active and a custom audit emitter injected."""
    authn = D.StubAuthenticator()
    authn.add_token("tok-ctl", principal="ops", tenant=None, role="CONTROL")
    gateway = build_gateway(authenticator=authn, router=D.StubRouterDispatch(), control_read=cp, audit=audit)
    return gateway


def _memberships_req():
    return D.req(path="/memberships", authorization="tok-ctl", correlation_id="cid-1")


# ===========================================================================
# DurableAuditEmitter — wire shape + response mapping
# ===========================================================================
def test_emitter_wire_event_is_exactly_ten_references_only_keys() -> None:
    # D-42 CLM: the wire gains exactly ONE key — record_ref (a reference only) — for a
    # total of eleven approved references-only keys.
    wire = _wire_event(_EVENT)
    assert set(wire.keys()) == {
        "audit_id",
        "event_version",
        "occurred_at",
        "correlation_id",
        "action",
        "outcome",
        "actor_ref",
        "subject_ref",
        "tenant_ref",
        "carrier_ref",
        "record_ref",
    }
    assert wire["action"] == "workspace_memberships_read"  # the AuditAction enum's string value
    assert wire["outcome"] == "success" and wire["actor_ref"] == wire["subject_ref"] == "ops"
    assert "source_service" not in wire and "id" not in wire and "recorded_at" not in wire


def test_emitter_maps_success_results_to_none() -> None:
    for result in ("INSERTED", "DUPLICATE_MATCH"):
        with _canned_server(200, result) as (base, captured):
            assert DurableAuditEmitter(base).emit(_EVENT) is None  # both are idempotent success
        envelope = json.loads(captured[0].decode("utf-8"))
        assert envelope == {"version": 1, "event": _wire_event(_EVENT)}


def test_emitter_maps_failures_to_bounded_transport_error() -> None:
    for status, result, kind in ((400, "INVALID", "invalid"), (409, "CONFLICT", "conflict"), (503, "UNAVAILABLE", "unavailable")):
        with _canned_server(status, result) as (base, _captured):
            try:
                DurableAuditEmitter(base).emit(_EVENT)
                raise AssertionError(f"{status} must raise")
            except DurableAuditTransportError as exc:
                assert exc.kind == kind
                assert "INVALID" not in str(exc) and "CONFLICT" not in str(exc)  # no server body leaks


def test_emitter_unreachable_edge_is_unavailable() -> None:
    try:
        DurableAuditEmitter("http://127.0.0.1:1", timeout=1.0).emit(_EVENT)  # refused port
        raise AssertionError("an unreachable edge must raise")
    except DurableAuditTransportError as exc:
        assert exc.kind == "unavailable"


def test_emitter_rejects_non_two_key_or_unknown_result() -> None:
    with _canned_server(200, None) as (base, _c):  # empty body
        try:
            DurableAuditEmitter(base).emit(_EVENT)
            raise AssertionError("an empty 200 body must raise")
        except DurableAuditTransportError as exc:
            assert exc.kind == "invalid"


def test_emitter_holds_no_database_driver_or_descriptor() -> None:
    import api_gateway.adapters.providers.durable_audit_emitter as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8").lower()
    for banned in ("psycopg", "sqlalchemy", "asyncpg", "dsn", "postgresql://", "connect("):
        assert banned not in src, f"the gateway durable emitter must not reference {banned!r} (no DB driver / descriptor)"
    emitter = DurableAuditEmitter("http://127.0.0.1:0")
    assert not hasattr(emitter, "_dsn") and not hasattr(emitter, "_conn")


# ===========================================================================
# BoundedGatewayAuditPolicy — exactly one retry for unavailable; never else
# ===========================================================================
def _policy(inner: AuditEmitterPort) -> BoundedGatewayAuditPolicy:
    return BoundedGatewayAuditPolicy(inner, transport_error=DurableAuditTransportError)


def test_policy_success_is_one_call_no_retry() -> None:
    inner = _CountingEmitter()
    _policy(inner).emit(_EVENT)
    assert inner.calls == 1


def test_policy_retries_once_for_transient_unavailable() -> None:
    inner = _CountingEmitter(fail_kind="unavailable", fail_times=1)  # first fails, retry succeeds
    _policy(inner).emit(_EVENT)
    assert inner.calls == 2, "exactly one bounded retry (two total calls) for transient unavailability"


def test_policy_reraises_after_the_single_retry_for_persistent_unavailable() -> None:
    inner = _CountingEmitter(fail_kind="unavailable", fail_times=99)
    try:
        _policy(inner).emit(_EVENT)
        raise AssertionError("persistent unavailability must re-raise (fail closed)")
    except DurableAuditTransportError as exc:
        assert exc.kind == "unavailable"
    assert inner.calls == 2, "the retry is bounded to exactly one (no unbounded retry loop)"


def test_policy_never_retries_invalid_or_conflict() -> None:
    for kind in ("invalid", "conflict"):
        inner = _CountingEmitter(fail_kind=kind, fail_times=99)
        try:
            _policy(inner).emit(_EVENT)
            raise AssertionError(f"{kind} must re-raise")
        except DurableAuditTransportError as exc:
            assert exc.kind == kind
        assert inner.calls == 1, f"{kind} is terminal — no retry"


# ===========================================================================
# Gateway success edge — one durable event; fail closed 503; non-emission
# ===========================================================================
def _success_events(emitter: _CountingEmitter):
    return [e for e in emitter.events if e.action is _SUCCESS]


def test_gateway_success_emits_exactly_one_durable_event() -> None:
    for members in (_members("t1"), (), _members("t1", "t2")):  # non-empty, empty, many
        emitter = _CountingEmitter()
        gateway = _gateway_with_audit(
            D.StubControlPlaneRead(memberships=members) if members else D.StubControlPlaneRead(mode="empty"), _policy(emitter)
        )
        resp = gateway.handle(_memberships_req())
        assert resp.status == 200
        assert len(_success_events(emitter)) == 1, "exactly one durable event per success (empty included)"
        (event,) = _success_events(emitter)
        assert event.outcome == "success" and event.event_version == 1
        assert event.actor_ref == event.subject_ref == "ops"


def test_gateway_fails_closed_503_when_durable_sink_terminally_unavailable() -> None:
    emitter = _CountingEmitter(fail_kind="unavailable", fail_times=99)
    gateway = _gateway_with_audit(D.StubControlPlaneRead(memberships=_members("t1")), _policy(emitter))
    resp = gateway.handle(_memberships_req())
    assert (resp.status, resp.public_code) == (503, "unavailable"), "a served success is never handed back without durable persistence"
    assert emitter.calls == 2, "audit-before-hand-back with exactly one bounded retry, then fail closed"


def test_gateway_serves_200_when_transient_failure_recovers_on_retry() -> None:
    emitter = _CountingEmitter(fail_kind="unavailable", fail_times=1)
    gateway = _gateway_with_audit(D.StubControlPlaneRead(memberships=_members("t1")), _policy(emitter))
    resp = gateway.handle(_memberships_req())
    assert resp.status == 200 and emitter.calls == 2


def test_gateway_no_durable_event_on_denial_or_failure_or_directory() -> None:
    # Denial (unknown membership -> 403) and failure (503) classes emit ZERO durable events.
    for cp, expected in ((D.StubControlPlaneRead(mode="absent"), 403), (D.StubControlPlaneRead(mode="unavailable"), 503)):
        emitter = _CountingEmitter()
        gateway = _gateway_with_audit(cp, _policy(emitter))
        assert gateway.handle(_memberships_req()).status == expected
        assert _success_events(emitter) == []
    # Directory reads are audit-silent (Reserved): zero durable events.
    emitter = _CountingEmitter()
    entries = (D.DirectoryEntryDTO(record_ref="rec-1", display_name="Alpha"),)
    gateway = _gateway_with_audit(D.StubControlPlaneRead(startup_entries=entries), _policy(emitter))
    assert gateway.handle(D.req(path="/directory/startup", authorization="tok-ctl")).status == 200
    assert emitter.events == []


# ===========================================================================
# build_audit_emitter_from_env — selection, fail-closed, no silent fallback
# ===========================================================================
@contextlib.contextmanager
def _env(value: Optional[str]) -> Iterator[None]:
    saved = os.environ.get(GW_AUDIT_SINK_BASE_URL_ENV)
    try:
        if value is None:
            os.environ.pop(GW_AUDIT_SINK_BASE_URL_ENV, None)
        else:
            os.environ[GW_AUDIT_SINK_BASE_URL_ENV] = value
        yield
    finally:
        if saved is None:
            os.environ.pop(GW_AUDIT_SINK_BASE_URL_ENV, None)
        else:
            os.environ[GW_AUDIT_SINK_BASE_URL_ENV] = saved


def test_selector_unset_returns_none() -> None:
    for blank in (None, "", "   "):
        with _env(blank):
            assert build_audit_emitter_from_env() is None, "unset/blank keeps the default in-memory no-sink emitter"


def test_selector_valid_url_selects_the_durable_policy() -> None:
    # D-42 CLM: the selector now wraps the bounded durable policy in the CLM action
    # partition — the four CLM-homed classes go durable; every other class keeps the
    # in-memory no-sink emitter (no wider audit expansion).
    with _env("http://127.0.0.1:9"):
        selected = build_audit_emitter_from_env()
    assert isinstance(selected, ClmDurableAuditPartition), "a valid http URL selects the CLM-partitioned durable policy"
    assert not isinstance(selected, InMemoryAuditEmitter), "real durable mode must never be the in-memory emitter"
    assert isinstance(selected._durable, BoundedGatewayAuditPolicy), "the durable half is the bounded fail-closed policy"
    assert isinstance(selected._durable._inner, DurableAuditEmitter)
    assert isinstance(selected._in_memory, InMemoryAuditEmitter), "the un-homed classes keep the in-memory no-sink emitter"


def test_selector_malformed_raises_before_any_socket() -> None:
    for bad in ("ftp://x", "https://x", "notaurl", "http://"):
        with _env(bad):
            try:
                build_audit_emitter_from_env()
                raise AssertionError(f"malformed {bad!r} must raise ValueError (fail closed — no silent fallback)")
            except ValueError:
                pass


def test_default_non_durable_composition_is_unchanged() -> None:
    # build_gateway with no audit (and audit=None) keeps the in-memory no-sink default (AD-1 Option A).
    gw_default = build_gateway(authenticator=D.StubAuthenticator(), router=D.StubRouterDispatch())
    gw_none = build_gateway(authenticator=D.StubAuthenticator(), router=D.StubRouterDispatch(), audit=None)
    assert isinstance(gw_default._audit, InMemoryAuditEmitter) and isinstance(gw_none._audit, InMemoryAuditEmitter)


if __name__ == "__main__":
    _h.run(
        [
            test_emitter_wire_event_is_exactly_ten_references_only_keys,
            test_emitter_maps_success_results_to_none,
            test_emitter_maps_failures_to_bounded_transport_error,
            test_emitter_unreachable_edge_is_unavailable,
            test_emitter_rejects_non_two_key_or_unknown_result,
            test_emitter_holds_no_database_driver_or_descriptor,
            test_policy_success_is_one_call_no_retry,
            test_policy_retries_once_for_transient_unavailable,
            test_policy_reraises_after_the_single_retry_for_persistent_unavailable,
            test_policy_never_retries_invalid_or_conflict,
            test_gateway_success_emits_exactly_one_durable_event,
            test_gateway_fails_closed_503_when_durable_sink_terminally_unavailable,
            test_gateway_serves_200_when_transient_failure_recovers_on_retry,
            test_gateway_no_durable_event_on_denial_or_failure_or_directory,
            test_selector_unset_returns_none,
            test_selector_valid_url_selects_the_durable_policy,
            test_selector_malformed_raises_before_any_socket,
            test_default_non_durable_composition_is_unchanged,
        ]
    )
