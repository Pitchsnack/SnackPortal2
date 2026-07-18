"""W1a — served internal Import edge + durable-audit emitter/policy + composition seams (default suite; no DB).

Covers the Import-Service side of the W1a composed-core slice WITHOUT a database:

* the served internal Import edge (``build_import_server`` over ``127.0.0.1`` on a test-owned daemon thread):
  ``POST /internal/import/initiate`` builds the EXACT W1a ``ImportRequest`` (DIRECTORY by reference,
  ``directory_kind="startup"``, SYNC, ``natural_key_field="global_startup_id"``, ``target_table="startups"``)
  and calls ``ImportService.start_import``; the references-only response envelope carries ``replayed``;
  method/path closure (404/405); a malformed request is 400 INVALID; any engine/audit exception collapses to
  503 UNAVAILABLE with no leakage;
* ``StartupDirectorySource`` — the single-record Global→tenant mapping (``record_id -> global_startup_id``,
  ``display_name -> company_name``); an absent record yields nothing;
* ``DurableImportAuditEmitter`` — the exact nine-key references-only wire + minted ``audit_id``, and the
  fail-closed mapping of every ingest answer to a bounded transport-error kind;
* ``BoundedImportAuditPolicy`` — exactly ONE retry for a transient ``unavailable`` failure, reusing the SAME
  ``audit_id``, NEVER for ``invalid`` / ``conflict``;
* the composition seams — ``build_import_server_from_env`` (host-gate-first; loopback-only; injected cross-
  package ports required when active) and ``build_import_audit_sink_from_env`` (unset → the in-memory no-sink
  default; valid → the durable policy; malformed → ValueError), and the default ``build_import_service`` is
  byte-behavior-unchanged (GlobalDirectorySource + InMemoryAuditSink).

Pure stdlib; standalone-runnable: ``python tests/import_service/test_http_import_api.py``.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Iterator, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
import _import_doubles as I  # noqa: E402

from import_service.adapters.providers.durable_audit_emitter import (  # noqa: E402
    DurableImportAuditEmitter,
    ImportAuditTransportError,
    _wire_event,
)
from import_service.adapters.providers.global_directory_source import GlobalDirectorySource  # noqa: E402
from import_service.adapters.providers.http_import_api import _INITIATE_PATH, build_import_server  # noqa: E402
from import_service.adapters.providers.in_memory_audit_sink import InMemoryAuditSink  # noqa: E402
from import_service.adapters.providers.startup_directory_source import StartupDirectorySource  # noqa: E402
from import_service.main import (  # noqa: E402
    SP2_IMPORT_AUDIT_SINK_BASE_URL,
    SP2_IMPORT_HOST,
    BoundedImportAuditPolicy,
    build_import_audit_sink_from_env,
    build_import_server_from_env,
    build_import_service,
)
from import_service.models import ImportMode, ImportStatus, SourceDescriptor, SourceKind  # noqa: E402
from shared.audit import ImportOperationalAuditEvent  # noqa: E402
from shared.lineage import LineageEmitPort  # noqa: E402


def _status(**over: object) -> ImportStatus:
    base: Dict[str, object] = dict(
        import_id="job-1",
        tenant_id="t1",
        state="applied",
        applied_count=1,
        noop_count=0,
        rejected_count=0,
        last_error_summary="",
        correlation_id="cid",
        replayed=False,
    )
    base.update(over)
    return ImportStatus(**base)  # type: ignore[arg-type]


class _RecordingService:
    """Duck-typed ImportService double: records the ImportRequest and returns/raises a canned result."""

    def __init__(self, status: Optional[ImportStatus] = None, error: Optional[BaseException] = None) -> None:
        self.requests: List[Any] = []
        self._status = status
        self._error = error

    def start_import(self, req: Any) -> ImportStatus:
        self.requests.append(req)
        if self._error is not None:
            raise self._error
        return self._status if self._status is not None else _status()


@contextlib.contextmanager
def _serving(service: Any) -> Iterator[str]:
    server, base_url = build_import_server(service)  # type: ignore[arg-type]  (duck-typed double)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()


def _initiate(**over: object) -> Dict[str, object]:
    base: Dict[str, object] = {
        "source_ref": "g1",
        "target_tenant_ref": "t1",
        "operation_key": "op-1",
        "correlation_id": "cid",
        "actor_ref": "p1",
    }
    base.update(over)
    return base


def _post(base: str, body: bytes, path: str = _INITIATE_PATH, method: str = "POST") -> Tuple[int, bytes]:
    req = urllib.request.Request(base + path, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


_REFUSAL_ATTEMPTS = 5


def _refusal_probe(base: str, body: bytes, path: str = _INITIATE_PATH, method: str = "POST") -> Tuple[int, bytes]:
    last: BaseException = AssertionError("unreachable")
    for _attempt in range(_REFUSAL_ATTEMPTS):
        try:
            return _post(base, body, path=path, method=method)
        except (ConnectionAbortedError, ConnectionResetError) as exc:
            last = exc
        except urllib.error.URLError as exc:
            if not isinstance(exc.reason, (ConnectionAbortedError, ConnectionResetError)):
                raise
            last = exc
    raise last


# ===========================================================================
# served internal Import edge
# ===========================================================================
def test_edge_initiate_builds_exact_import_request_and_calls_start_import() -> None:
    service = _RecordingService()
    with _serving(service) as base:
        status, _raw = _post(base, json.dumps(_initiate()).encode())
    assert status == 200
    (req,) = service.requests
    assert req.tenant_id == "t1"
    assert isinstance(req.source, SourceDescriptor)
    assert req.source.kind is SourceKind.DIRECTORY and req.source.ref == "g1" and req.source.directory_kind == "startup"
    assert req.mode is ImportMode.SYNC
    assert req.operation_key == "op-1" and req.correlation_id == "cid" and req.actor_ref == "p1"
    assert req.natural_key_field == "global_startup_id" and req.target_table == "startups"


def test_edge_references_only_response_includes_replayed() -> None:
    service = _RecordingService(_status(state="applied", replayed=True, applied_count=0, noop_count=1, import_id="job-9"))
    with _serving(service) as base:
        status, raw = _post(base, json.dumps(_initiate()).encode())
    assert status == 200
    body = json.loads(raw.decode("utf-8"))
    assert set(body.keys()) == {"version", "outcome"} and body["version"] == 1
    assert body["outcome"] == {"state": "applied", "replayed": True, "applied_count": 0, "noop_count": 1, "import_id": "job-9"}


def test_edge_wrong_path_404_empty() -> None:
    with _serving(_RecordingService()) as base:
        status, raw = _refusal_probe(base, json.dumps(_initiate()).encode(), path="/nope")
    assert status == 404 and raw == b""


def test_edge_wrong_method_405_empty() -> None:
    with _serving(_RecordingService()) as base:
        for method in ("GET", "PUT", "DELETE", "PATCH"):
            status, raw = _refusal_probe(base, b"", method=method)
            assert status == 405 and raw == b"", method


def test_edge_malformed_request_400_no_leak() -> None:
    service = _RecordingService()
    with _serving(service) as base:
        for body in (
            b"not json",
            b"[1,2,3]",
            b"",
            json.dumps({"source_ref": "g1"}).encode(),
            json.dumps(dict(_initiate(), extra="x")).encode(),
        ):
            status, raw = _post(base, body)
            assert status == 400 and json.loads(raw.decode("utf-8")) == {"version": 1, "result": "INVALID"}
    assert service.requests == [], "a malformed request must never reach start_import"


def test_edge_engine_exception_503_no_leak() -> None:
    service = _RecordingService(error=RuntimeError("internal-engine-detail-that-must-never-leak"))
    with _serving(service) as base:
        status, raw = _post(base, json.dumps(_initiate()).encode())
    assert status == 503 and json.loads(raw.decode("utf-8")) == {"version": 1, "result": "UNAVAILABLE"}
    assert b"internal-engine-detail" not in raw


# ===========================================================================
# StartupDirectorySource — single-record mapping
# ===========================================================================
def test_startup_directory_source_maps_single_record() -> None:
    directory = I.FakeDirectoryRead()
    directory.add("startup", "g1", "Acme Inc", industry="ai")
    source = StartupDirectorySource(directory)
    records = list(source.read(SourceDescriptor(kind=SourceKind.DIRECTORY, ref="g1", directory_kind="startup")))
    assert len(records) == 1
    (rec,) = records
    assert rec.data == {"global_startup_id": "g1", "company_name": "Acme Inc"}, "record_id->global_startup_id; display_name->company_name"
    assert rec.source_ref == "global:GlobalStartupDirectory:g1"


def test_startup_directory_source_absent_record_yields_nothing() -> None:
    source = StartupDirectorySource(I.FakeDirectoryRead())
    assert list(source.read(SourceDescriptor(kind=SourceKind.DIRECTORY, ref="missing", directory_kind="startup"))) == []


# ===========================================================================
# DurableImportAuditEmitter — 9-key wire + minting + bounded failures
# ===========================================================================
def _event(**over: object) -> ImportOperationalAuditEvent:
    base: Dict[str, object] = dict(
        actor_ref="p1",
        action="ImportCompleted",
        correlation_id="cid",
        outcome="success",
        target_ref="t1",
        source_ref="global:GlobalStartupDirectory:g1",
    )
    base.update(over)
    return ImportOperationalAuditEvent(**base)  # type: ignore[arg-type]


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

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}", captured
    finally:
        server.shutdown()
        server.server_close()


def test_durable_import_audit_emitter_nine_key_wire_and_minting() -> None:
    with _canned_server(200, "INSERTED") as (base, captured):
        assert DurableImportAuditEmitter(base).initiate(_event()) is None
    envelope = json.loads(captured[0].decode("utf-8"))
    assert set(envelope.keys()) == {"version", "event"} and envelope["version"] == 1
    wire = envelope["event"]
    assert set(wire.keys()) == {
        "audit_id",
        "event_version",
        "occurred_at",
        "correlation_id",
        "action",
        "outcome",
        "actor_ref",
        "target_ref",
        "source_ref",
    }, "exactly the nine references-only import wire keys"
    assert "source_service" not in wire and "id" not in wire and "recorded_at" not in wire
    assert wire["action"] == "ImportCompleted" and wire["outcome"] == "success"
    assert isinstance(wire["audit_id"], str) and len(wire["audit_id"]) == 32, "audit_id is a minted uuid4().hex"
    assert wire["event_version"] == 1 and isinstance(wire["occurred_at"], str) and wire["occurred_at"]


def test_durable_import_audit_emitter_maps_failures_to_bounded_kinds() -> None:
    # _wire_event builds exactly the nine keys for an explicit id (the policy path).
    wire = _wire_event(_event(), audit_id="a" * 32, event_version=1, occurred_at="2026-07-18T00:00:00+00:00")
    assert set(wire.keys()) == {
        "audit_id",
        "event_version",
        "occurred_at",
        "correlation_id",
        "action",
        "outcome",
        "actor_ref",
        "target_ref",
        "source_ref",
    }
    for status, result, kind in ((400, "INVALID", "invalid"), (409, "CONFLICT", "conflict"), (503, "UNAVAILABLE", "unavailable")):
        with _canned_server(status, result) as (base, _c):
            try:
                DurableImportAuditEmitter(base).initiate(_event())
                raise AssertionError(f"{status} must raise")
            except ImportAuditTransportError as exc:
                assert exc.kind == kind and "INVALID" not in str(exc) and "CONFLICT" not in str(exc)
    try:
        DurableImportAuditEmitter("http://127.0.0.1:1", timeout=1.0).initiate(_event())  # refused port
        raise AssertionError("an unreachable edge must raise")
    except ImportAuditTransportError as exc:
        assert exc.kind == "unavailable"


# ===========================================================================
# BoundedImportAuditPolicy — one retry for unavailable; same audit_id; never else
# ===========================================================================
class _CountingEmitter:
    """Records post() calls; raises a bounded transport error for the first ``fail_times`` calls."""

    def __init__(self, *, fail_kind: Optional[str] = None, fail_times: int = 0) -> None:
        self.audit_ids: List[str] = []
        self.calls = 0
        self._fail_kind = fail_kind
        self._fail_times = fail_times

    def post(self, event: ImportOperationalAuditEvent, *, audit_id: str, event_version: int, occurred_at: str) -> None:
        self.calls += 1
        self.audit_ids.append(audit_id)
        if self._fail_kind is not None and self.calls <= self._fail_times:
            raise ImportAuditTransportError(self._fail_kind)


def _policy(inner: Any) -> BoundedImportAuditPolicy:
    return BoundedImportAuditPolicy(inner, transport_error=ImportAuditTransportError)


def test_bounded_import_audit_policy_one_retry_unavailable_same_audit_id() -> None:
    inner = _CountingEmitter(fail_kind="unavailable", fail_times=1)  # first fails, retry succeeds
    _policy(inner).initiate(_event())
    assert inner.calls == 2, "exactly one bounded retry (two total calls) for transient unavailability"
    assert inner.audit_ids[0] == inner.audit_ids[1], "the single retry MUST reuse the same audit_id (idempotent replay)"
    # persistent unavailability re-raises after the bounded retry (fail closed).
    inner2 = _CountingEmitter(fail_kind="unavailable", fail_times=99)
    try:
        _policy(inner2).initiate(_event())
        raise AssertionError("persistent unavailability must re-raise (fail closed)")
    except ImportAuditTransportError as exc:
        assert exc.kind == "unavailable"
    assert inner2.calls == 2, "the retry is bounded to exactly one (no unbounded loop)"


def test_bounded_import_audit_policy_never_retries_invalid_or_conflict() -> None:
    for kind in ("invalid", "conflict"):
        inner = _CountingEmitter(fail_kind=kind, fail_times=99)
        try:
            _policy(inner).initiate(_event())
            raise AssertionError(f"{kind} must re-raise")
        except ImportAuditTransportError as exc:
            assert exc.kind == kind
        assert inner.calls == 1, f"{kind} is terminal — no retry"


# ===========================================================================
# composition seams — build_import_server_from_env + build_import_audit_sink_from_env
# ===========================================================================
class _NoopLineage(LineageEmitPort):
    def emit(self, session: Any, intent: Any) -> None:
        return None


@contextlib.contextmanager
def _env(name: str, value: Optional[str]) -> Iterator[None]:
    saved = os.environ.get(name)
    try:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
        yield
    finally:
        if saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = saved


def test_build_import_server_from_env_selector_matrix() -> None:
    provider, lineage, directory = I.FakeRoutedSessionProvider(), _NoopLineage(), I.FakeDirectoryRead()
    # unset host -> None (host-gate-first; injected ports not consulted).
    for blank in (None, "", "   "):
        with _env(SP2_IMPORT_HOST, blank):
            assert build_import_server_from_env(session_provider=provider, lineage=lineage, directory_read=directory) is None
    # non-loopback host -> ValueError (internal-only).
    with _env(SP2_IMPORT_HOST, "10.0.0.1"):
        try:
            build_import_server_from_env(session_provider=provider, lineage=lineage, directory_read=directory)
            raise AssertionError("a non-loopback host must raise")
        except ValueError:
            pass
    # active host but a missing injected cross-package port -> ValueError (fail closed; DAG).
    with _env(SP2_IMPORT_HOST, "127.0.0.1"):
        try:
            build_import_server_from_env(session_provider=None, lineage=lineage, directory_read=directory)
            raise AssertionError("a missing injected port must raise (no partial service)")
        except ValueError:
            pass
    # active host + all ports injected -> a bound server object (socket bound; caller closes it).
    with _env(SP2_IMPORT_HOST, "127.0.0.1"):
        composed = build_import_server_from_env(session_provider=provider, lineage=lineage, directory_read=directory)
    assert composed is not None
    server, base_url = composed
    assert isinstance(base_url, str) and base_url.startswith("http://127.0.0.1:")
    server.server_close()  # type: ignore[attr-defined]


def test_build_import_audit_sink_from_env_selector_matrix() -> None:
    for blank in (None, "", "   "):
        with _env(SP2_IMPORT_AUDIT_SINK_BASE_URL, blank):
            assert build_import_audit_sink_from_env() is None, "unset keeps the in-memory no-sink default"
    with _env(SP2_IMPORT_AUDIT_SINK_BASE_URL, "http://127.0.0.1:9"):
        sink = build_import_audit_sink_from_env()
    assert isinstance(sink, BoundedImportAuditPolicy), "a valid http URL selects the bounded durable policy"
    for bad in ("ftp://x", "https://x", "notaurl", "http://"):
        with _env(SP2_IMPORT_AUDIT_SINK_BASE_URL, bad):
            try:
                build_import_audit_sink_from_env()
                raise AssertionError(f"malformed {bad!r} must raise ValueError")
            except ValueError:
                pass


def test_build_import_service_default_directory_source_and_sink_unchanged() -> None:
    svc = build_import_service(session_provider=I.FakeRoutedSessionProvider(), lineage=_NoopLineage(), directory_read=I.FakeDirectoryRead())
    assert isinstance(svc._sources[SourceKind.DIRECTORY], GlobalDirectorySource), "default directory source is unchanged"
    assert isinstance(svc._audit, InMemoryAuditSink), "default audit sink is unchanged (in-memory no-sink)"


if __name__ == "__main__":
    _h.run(
        [
            test_edge_initiate_builds_exact_import_request_and_calls_start_import,
            test_edge_references_only_response_includes_replayed,
            test_edge_wrong_path_404_empty,
            test_edge_wrong_method_405_empty,
            test_edge_malformed_request_400_no_leak,
            test_edge_engine_exception_503_no_leak,
            test_startup_directory_source_maps_single_record,
            test_startup_directory_source_absent_record_yields_nothing,
            test_durable_import_audit_emitter_nine_key_wire_and_minting,
            test_durable_import_audit_emitter_maps_failures_to_bounded_kinds,
            test_bounded_import_audit_policy_one_retry_unavailable_same_audit_id,
            test_bounded_import_audit_policy_never_retries_invalid_or_conflict,
            test_build_import_server_from_env_selector_matrix,
            test_build_import_audit_sink_from_env_selector_matrix,
            test_build_import_service_default_directory_source_and_sink_unchanged,
        ]
    )
