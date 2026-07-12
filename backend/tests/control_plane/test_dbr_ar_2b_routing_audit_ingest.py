"""DBR-AR-2B — internal routing-audit ingest edge behavioral contract (loopback HTTP; DB-free).

Exercises the uncomposed `build_routing_audit_server` factory end-to-end over
``127.0.0.1`` (single-threaded stdlib server hosted on a test-owned daemon thread — the
established loopback precedent; production stays thread-free, AT-D15T1-10): strict
envelope acceptance/rejection for ``POST /internal/routing-audit/events``, the exact
two-key response envelope for INSERTED / DUPLICATE_MATCH / INVALID / CONFLICT /
UNAVAILABLE, 404/405 empty-body refusals, forbidden-name and secret-shaped-value
defenses, and the no-leak guarantee (no submitted value, exception text, SQL, or
topology ever appears in a response). The store behind the edge is a local test double
implementing `RoutingAuditStorePort` — no database anywhere. Pure stdlib;
standalone-runnable: `python tests/control_plane/test_dbr_ar_2b_routing_audit_ingest.py`.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import sys
import threading
import urllib.error
import urllib.request
from typing import Dict, Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402,F401  (backend + architecture helpers on path)

from control_plane.adapters.providers.http_routing_audit_api import (  # noqa: E402
    _INGEST_PATH,
    build_routing_audit_server,
)
from control_plane.routing_audit import (  # noqa: E402
    RoutingAuditAppendResult,
    RoutingAuditConflictError,
    RoutingAuditInvalidError,
    RoutingAuditRecord,
    RoutingAuditStorePort,
)


class _FakeStore(RoutingAuditStorePort):
    """Scripted store double: behavior in {insert, duplicate, conflict, invalid, boom}."""

    def __init__(self, behavior: str = "insert") -> None:
        self.behavior = behavior
        self.records: List[RoutingAuditRecord] = []

    def append_routing_audit(self, record: RoutingAuditRecord) -> RoutingAuditAppendResult:
        self.records.append(record)
        if self.behavior == "insert":
            return RoutingAuditAppendResult.INSERTED
        if self.behavior == "duplicate":
            return RoutingAuditAppendResult.DUPLICATE_MATCH
        if self.behavior == "conflict":
            raise RoutingAuditConflictError("replayed event_id with a different payload")
        if self.behavior == "invalid":
            raise RoutingAuditInvalidError("record rejected")
        raise RuntimeError("internal-store-detail-that-must-never-leak")


@contextlib.contextmanager
def _serving(store: RoutingAuditStorePort) -> Iterator[str]:
    server, base_url = build_routing_audit_server(store)  # 127.0.0.1, ephemeral port
    thread = threading.Thread(target=server.serve_forever, daemon=True)  # test-owned hosting thread only
    thread.start()
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()


def _request(base: str, body: bytes, path: str = _INGEST_PATH, method: str = "POST") -> Tuple[int, bytes]:
    req = urllib.request.Request(base + path, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


# OBS-1 precedent (see tests/database_router/test_http_dispatch_api.py): a single-threaded stdlib
# HTTP/1.0 server closes the connection immediately after a bodiless 404/405 refusal, before
# reading any request body; on Windows loopback that intermittently surfaces client-side as
# ConnectionAbortedError/ConnectionResetError while reading the response. Bounded retry with a
# fresh connection, used SOLELY for the side-effect-free refusal probes (they never reach the
# store); every other exception propagates unchanged and a persistent abort still fails.
_REFUSAL_PROBE_ATTEMPTS = 5


def _refusal_probe(base: str, body: bytes, path: str = _INGEST_PATH, method: str = "POST") -> Tuple[int, bytes]:
    last: BaseException = AssertionError("unreachable")
    for _attempt in range(_REFUSAL_PROBE_ATTEMPTS):
        try:
            return _request(base, body, path=path, method=method)
        except (ConnectionAbortedError, ConnectionResetError) as exc:
            last = exc
        except urllib.error.URLError as exc:
            if not isinstance(exc.reason, (ConnectionAbortedError, ConnectionResetError)):
                raise
            last = exc
    raise last


def _event(**overrides: object) -> Dict[str, object]:
    base: Dict[str, object] = {
        "event_id": "1f0e6b1a-9b2c-4d3e-8f4a-5b6c7d8e9f0a",
        "event_version": 1,
        "occurred_at": "2026-07-13T10:00:00+00:00",
        "correlation_id": "corr-1",
        "actor_ref": "principal:alice",
        "action": "Route",
        "outcome": "success",
        "source_service": "database_router",
        "source_version": "4",
        "request_ref": "req-1",
        "tenant_ref": "tenant-alpha",
        "resolved_tenant_ref": "tenant-alpha",
        "public_code": None,
        "error_class": None,
        "association_store_ref": "tenant/alpha-db",
        "association_version": "1",
        "lane": "interactive",
    }
    base.update(overrides)
    return base


def _envelope(event: Optional[Dict[str, object]] = None, **top: object) -> bytes:
    payload: Dict[str, object] = {"version": 1, "event": event if event is not None else _event()}
    payload.update(top)
    return json.dumps(payload).encode("utf-8")


def _expect(base: str, body: bytes, status: int, result: str) -> bytes:
    got_status, raw = _request(base, body)
    assert got_status == status, f"expected {status}, got {got_status}: {raw!r}"
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed == {"version": 1, "result": result}, parsed
    return raw


# ---------------------------------------------------------------------------
# Cases 13-15 — accept, idempotent replay, conflict
# ---------------------------------------------------------------------------
def test_case13_valid_insert_envelope_accepted() -> None:
    store = _FakeStore("insert")
    with _serving(store) as base:
        _expect(base, _envelope(), 200, "INSERTED")
    record = store.records[0]
    assert record.tenant_ref == "tenant-alpha" and record.action == "Route"
    assert record.trace_ref is None, "trace_ref is reserved: never populated from the wire in 2B"


def test_case14_exact_duplicate_accepted_idempotently() -> None:
    with _serving(_FakeStore("duplicate")) as base:
        _expect(base, _envelope(), 200, "DUPLICATE_MATCH")


def test_case15_same_id_different_payload_conflict_rejected() -> None:
    store = _FakeStore("conflict")
    with _serving(store) as base:
        _expect(base, _envelope(), 409, "CONFLICT")
    assert len(store.records) == 1


# ---------------------------------------------------------------------------
# Cases 16-18 — path, method, malformed body
# ---------------------------------------------------------------------------
def test_case16_wrong_path_rejected_404_empty() -> None:
    store = _FakeStore("insert")
    with _serving(store) as base:
        for path in (
            "/internal/routing-audit/event",
            "/internal/routing-audit/events/extra",
            "/internal/routing/tenants/t1",
            "/",
            "/internal",
        ):
            status, raw = _refusal_probe(base, _envelope(), path=path)
            assert (status, raw) == (404, b""), path
    assert store.records == [], "a refused path must never reach the store"


def test_case17_wrong_method_rejected_405_empty() -> None:
    store = _FakeStore("insert")
    with _serving(store) as base:
        for method in ("GET", "PUT", "DELETE", "PATCH", "OPTIONS"):
            status, raw = _refusal_probe(base, _envelope(), method=method)
            assert (status, raw) == (405, b""), method
    assert store.records == []


def test_case18_malformed_and_non_object_json_rejected() -> None:
    store = _FakeStore("insert")
    with _serving(store) as base:
        for body in (b"", b"not-json{", b"[1, 2]", b'"string"', b"42", b"null", b"true"):
            _expect(base, body, 400, "INVALID")
    assert store.records == []


# ---------------------------------------------------------------------------
# Cases 19-22 — strict key sets, version, types
# ---------------------------------------------------------------------------
def test_case19_missing_or_extra_top_level_keys_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        _expect(base, json.dumps({"event": _event()}).encode(), 400, "INVALID")  # missing version
        _expect(base, json.dumps({"version": 1}).encode(), 400, "INVALID")  # missing event
        _expect(base, _envelope(extra="x"), 400, "INVALID")  # extra top-level key


def test_case20_missing_or_extra_event_keys_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        missing = _event()
        missing.pop("correlation_id")
        _expect(base, _envelope(missing), 400, "INVALID")
        extra = _event()
        extra["surprise"] = "x"
        _expect(base, _envelope(extra), 400, "INVALID")
        reserved = _event()
        reserved["trace_ref"] = None  # reserved column is NOT a 2B wire key (MC5)
        _expect(base, _envelope(reserved), 400, "INVALID")


def test_case21_unsupported_version_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        for version in (0, 2, "1", None, True):
            _expect(base, _envelope(version=version), 400, "INVALID")
        _expect(base, _envelope(_event(event_version=2)), 400, "INVALID")
        _expect(base, _envelope(_event(event_version=True)), 400, "INVALID")


def test_case22_wrong_field_types_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        _expect(base, _envelope(_event(actor_ref=7)), 400, "INVALID")
        _expect(base, _envelope(_event(correlation_id=None)), 400, "INVALID")
        _expect(base, _envelope(_event(event_version="1")), 400, "INVALID")
        _expect(base, _envelope(_event(lane=1)), 400, "INVALID")
        _expect(base, _envelope(_event(event_id="")), 400, "INVALID")
        _expect(base, _envelope({"...": "not the shape"}), 400, "INVALID")
        _expect(base, json.dumps({"version": 1, "event": [1]}).encode(), 400, "INVALID")


# ---------------------------------------------------------------------------
# Cases 23-26 — vocabulary, combinations, forbidden names, secret shapes
# ---------------------------------------------------------------------------
def test_case23_unknown_action_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        for action in ("Publish", "route", "DispatchCompleted", "DispatchFailed", "AuditSinkFailed", ""):
            _expect(base, _envelope(_event(action=action)), 400, "INVALID")


def test_case24_invalid_action_outcome_public_code_combinations_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        _expect(base, _envelope(_event(action="Route", outcome="denied:not_found", public_code="not_found")), 400, "INVALID")
        _expect(base, _envelope(_event(action="Route", outcome="success", public_code="not_found")), 400, "INVALID")
        _expect(base, _envelope(_event(action="RouteDenied", outcome="success")), 400, "INVALID")
        _expect(base, _envelope(_event(action="RouteDenied", outcome="denied:bogus_code", public_code="bogus_code")), 400, "INVALID")
        _expect(base, _envelope(_event(action="RouteDenied", outcome="denied:not_found", public_code="not_ready")), 400, "INVALID")
        _expect(base, _envelope(_event(action="IsolationAnomaly", outcome="anomaly:other")), 400, "INVALID")
        _expect(
            base, _envelope(_event(action="IsolationAnomaly", outcome="anomaly:tenant_binding", public_code="not_found")), 400, "INVALID"
        )
        _expect(base, _envelope(_event(error_class="secret_resolution")), 400, "INVALID")  # error_class without connection_unavailable
        _expect(
            base,
            _envelope(
                _event(
                    action="RouteDenied", outcome="denied:connection_unavailable", public_code="connection_unavailable", error_class="disk"
                )
            ),
            400,
            "INVALID",
        )
        _expect(base, _envelope(_event(lane="warp")), 400, "INVALID")
        _expect(base, _envelope(_event(source_service="api_gateway")), 400, "INVALID")
        # And the valid shapes of each family are accepted (combination checks are not over-strict):
        _expect(
            base,
            _envelope(
                _event(
                    action="RouteControl",
                    tenant_ref=None,
                    resolved_tenant_ref=None,
                    association_store_ref=None,
                    association_version=None,
                    lane=None,
                )
            ),
            200,
            "INSERTED",
        )
        _expect(
            base,
            _envelope(
                _event(
                    action="RouteDenied", outcome="denied:connection_unavailable", public_code="connection_unavailable", error_class="pool"
                )
            ),
            200,
            "INSERTED",
        )
        _expect(
            base,
            _envelope(_event(action="IsolationAnomaly", outcome="anomaly:tenant_binding", resolved_tenant_ref="tenant-beta")),
            200,
            "INSERTED",
        )


def test_case25_forbidden_field_name_rejected() -> None:
    with _serving(_FakeStore("insert")) as base:
        for name in (
            "recorded_at",
            "store_id",
            "id",
            "dsn",
            "password",
            "token",
            "jwt",
            "request_body",
            "response_body",
            "hostname",
            "connection",
            "payload",
        ):
            bad = _event()
            bad[name] = "x"
            _expect(base, _envelope(bad), 400, "INVALID")


def test_case26_token_or_credential_shaped_value_rejected() -> None:
    # Probe values are CONSTRUCTED at runtime so no secret-shaped literal enters the
    # committed test text (secret-hygiene guards + gitleaks scan every tracked file).
    with _serving(_FakeStore("insert")) as base:
        shaped = (
            "ey" + "J" + "0" * 12 + ".x.y",  # JWT-shaped prefix
            "-" * 5 + "BEGIN FAKE KEY" + "-" * 5,  # PEM-shaped marker
            "AK" + "IA" + "EXAMPLEONLY",  # cloud-key-shaped prefix
            "gh" + "p_" + "x" * 12,  # token-shaped prefix
            "xo" + "x" + "b-1-1",  # token-shaped prefix
            "scheme" + "://" + "host/db",  # DSN/URL-shaped value
        )
        for value in shaped:
            _expect(base, _envelope(_event(request_ref=value)), 400, "INVALID")
        _expect(base, _envelope(_event(tenant_ref="t" * 513)), 400, "INVALID")  # overlength reference field


# ---------------------------------------------------------------------------
# Cases 27-28 — bounded internal failure; zero leakage
# ---------------------------------------------------------------------------
def test_case27_internal_store_failure_collapses_to_bounded_response() -> None:
    with _serving(_FakeStore("boom")) as base:
        raw = _expect(base, _envelope(), 503, "UNAVAILABLE")
        assert b"internal-store-detail" not in raw and b"RuntimeError" not in raw and b"Traceback" not in raw
    with _serving(_FakeStore("invalid")) as base:
        _expect(base, _envelope(), 400, "INVALID")


def test_case28_no_response_leaks_payload_or_exception_text() -> None:
    probe = "leak-probe-7d1f"
    with _serving(_FakeStore("boom")) as base:
        _status, raw = _request(base, _envelope(_event(actor_ref=probe)))
        assert probe.encode() not in raw
        assert set(json.loads(raw.decode("utf-8")).keys()) == {"version", "result"}
    with _serving(_FakeStore("insert")) as base:
        bad = _event()
        bad["surprise"] = probe
        _status, raw = _request(base, _envelope(bad))
        assert probe.encode() not in raw, "a rejected envelope must never be echoed"
        for token in (b"control_routing_audit", b"INSERT", b"SELECT", b"psycopg", b"127.0.0.1", b"Traceback"):
            assert token not in raw, token


if __name__ == "__main__":
    _h.run(
        [
            test_case13_valid_insert_envelope_accepted,
            test_case14_exact_duplicate_accepted_idempotently,
            test_case15_same_id_different_payload_conflict_rejected,
            test_case16_wrong_path_rejected_404_empty,
            test_case17_wrong_method_rejected_405_empty,
            test_case18_malformed_and_non_object_json_rejected,
            test_case19_missing_or_extra_top_level_keys_rejected,
            test_case20_missing_or_extra_event_keys_rejected,
            test_case21_unsupported_version_rejected,
            test_case22_wrong_field_types_rejected,
            test_case23_unknown_action_rejected,
            test_case24_invalid_action_outcome_public_code_combinations_rejected,
            test_case25_forbidden_field_name_rejected,
            test_case26_token_or_credential_shaped_value_rejected,
            test_case27_internal_store_failure_collapses_to_bounded_response,
            test_case28_no_response_leaks_payload_or_exception_text,
        ]
    )
