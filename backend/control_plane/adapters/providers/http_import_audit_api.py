"""Internal Control-Plane Import operational-audit ingest edge (stdlib http.server) — W1a durable Import Audit.

Exposes ONE internal-only surface, ``POST /internal/import-audit/events``, which MUST remain internal-only
and MUST NEVER be portal-reachable or registered as a public / frontend ingress. It binds ``127.0.0.1`` by
default and runs on a plain single-threaded stdlib HTTP server (no threading / asyncio / concurrency
machinery here — the AT-D15T1-10 precedent).

Wire contract (W1a). The request envelope is exactly ``{version, event}`` with ``version`` exactly ``1`` and
``event`` exactly the nine approved references-only Import-event keys (``source_service`` / ``id`` /
``recorded_at`` are NEVER wire keys — ``source_service`` is the store-side producer constant
``import_service``, and ``id`` / ``recorded_at`` are DB-assigned). Validation is STRICT and fail closed:
wrong path 404 empty; non-POST 405 empty; anything malformed, mis-keyed, mis-typed, out-of-vocabulary,
over-length, secret/token/DSN-shaped, or carrying a forbidden field name answers
``400 {"version": 1, "result": "INVALID"}``. W1a persists the whole Import-operational-audit class — the five
actions the Import Service emits — with the exact action/outcome combination pinned per action (the
routing-edge combination-rule precedent):

    ImportRequested | ImportStarted | ImportResumed -> outcome == "success"
    ImportCompleted                                 -> outcome in {"success", "replayed"}
    ImportFailed                                    -> outcome == "error:<bounded-suffix>"

Accepted events answer ``200 INSERTED`` / ``200 DUPLICATE_MATCH`` (both success — idempotent replay); a
same-ID/different-payload replay answers ``409 CONFLICT``; any internal store failure collapses to
``503 UNAVAILABLE``. Responses are the fixed two-key envelope only: no SQL, table detail, Control-DB identity,
hostname, topology, exception text, stack trace, credential state, or stored event content ever crosses this
edge, and no stdlib HTML error body is ever emitted.

Uncomposed until env-selected: ``build_import_audit_server`` CONSTRUCTS the server bound to an
``ImportAuditStorePort`` and returns it with its base URL — it does not start the request loop, and this
module deliberately has no blocking runnable entrypoint (the composition seam lives in ``control_plane/
main.py``). Tests host it on a loopback port.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Tuple, cast

from control_plane.import_audit import (
    IMPORT_AUDIT_SOURCE_SERVICE,
    ImportAuditConflictError,
    ImportAuditInvalidError,
    ImportAuditRecord,
    ImportAuditStorePort,
)

_INGEST_PATH = "/internal/import-audit/events"
_ENVELOPE_VERSION = 1
_EVENT_VERSION = 1  # W1a accepts exactly event_version 1 (additive evolution by contract amendment)

_TOP_LEVEL_KEYS = frozenset({"version", "event"})

# Exactly the nine approved references-only Import-event wire keys (all always present on import events).
_EVENT_KEYS = frozenset(
    {
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
)

# Defense-in-depth beyond the exact-key-set check: these names are rejected BY NAME so a future allowlist
# edit can never silently admit a store-assigned, producer-constant, or forbidden-data field.
# ``source_service`` is a store-side constant and must never arrive on the wire.
_FORBIDDEN_EVENT_KEYS = frozenset(
    {
        "id",
        "recorded_at",
        "source_service",
        "dsn",
        "password",
        "passwd",
        "secret",
        "token",
        "jwt",
        "bearer_token",
        "authorization",
        "request_body",
        "response_body",
        "body",
        "payload",
        "records",
        "record",
        "rows",
        "fields",
        "database",
        "db_name",
        "hostname",
        "topology",
        "connection",
    }
)

# The exact five Import-operational-audit actions, and the pinned action/outcome combination (per action).
_ACTIONS_SUCCESS_ONLY = frozenset({"ImportRequested", "ImportStarted", "ImportResumed"})
_ACTION_COMPLETED = "ImportCompleted"
_COMPLETED_OUTCOMES = frozenset({"success", "replayed"})
_ACTION_FAILED = "ImportFailed"
_ERROR_PREFIX = "error:"
_SUCCESS_OUTCOME = "success"
_ALL_ACTIONS = _ACTIONS_SUCCESS_ONLY | {_ACTION_COMPLETED, _ACTION_FAILED}

# Secret/token/DSN-shaped value markers: any string value containing one is rejected.
_SECRET_SHAPES = ("eyJ", "-----BEGIN", "AKIA", "ghp_", "xox", "://")
_MAX_REF_LENGTH = 512  # uniform reference-field cap


class _IngestValidationError(Exception):
    """A malformed/invalid ingest envelope — mapped fail-closed to 400 INVALID."""


def _checked_string(value: object) -> str:
    if not isinstance(value, str):
        raise _IngestValidationError("event field must be a string")
    if len(value) > _MAX_REF_LENGTH:
        raise _IngestValidationError("event field exceeds the reference length cap")
    for marker in _SECRET_SHAPES:
        if marker in value:
            raise _IngestValidationError("event field carries a secret/token/DSN-shaped value")
    return value


def _required_string(event: Dict[str, Any], key: str) -> str:
    value = _checked_string(event[key])
    if not value:
        raise _IngestValidationError("required event field must be non-empty")
    return value


def _parse_record(raw: bytes) -> ImportAuditRecord:
    """Strictly validate one wire envelope and translate it to the Control-Plane-local record."""
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise _IngestValidationError("body is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope.keys()) != set(_TOP_LEVEL_KEYS):
        raise _IngestValidationError("request keys must be exactly {version, event}")
    version = envelope["version"]
    if isinstance(version, bool) or version != _ENVELOPE_VERSION:
        raise _IngestValidationError("unsupported envelope version")
    event = envelope["event"]
    if not isinstance(event, dict):
        raise _IngestValidationError("event must be an object")
    present = set(event.keys())
    forbidden = present & _FORBIDDEN_EVENT_KEYS
    if forbidden:
        raise _IngestValidationError("event carries a forbidden field name")
    if present != set(_EVENT_KEYS):
        raise _IngestValidationError("event keys must be exactly the nine approved fields")

    event_version = event["event_version"]
    if isinstance(event_version, bool) or not isinstance(event_version, int) or event_version != _EVENT_VERSION:
        raise _IngestValidationError("unsupported event_version")

    action = _required_string(event, "action")
    if action not in _ALL_ACTIONS:
        raise _IngestValidationError("unsupported action (not an Import-operational-audit action)")
    outcome = _required_string(event, "outcome")
    _check_action_outcome(action, outcome)

    return ImportAuditRecord(
        audit_id=_required_string(event, "audit_id"),
        event_version=event_version,
        occurred_at=_required_string(event, "occurred_at"),
        correlation_id=_required_string(event, "correlation_id"),
        action=action,
        outcome=outcome,
        source_service=IMPORT_AUDIT_SOURCE_SERVICE,  # store-side producer constant — never from the wire
        actor_ref=_required_string(event, "actor_ref"),
        target_ref=_required_string(event, "target_ref"),
        source_ref=_required_string(event, "source_ref"),
    )


def _check_action_outcome(action: str, outcome: str) -> None:
    """Pin the exact per-action outcome vocabulary (fail closed on any other combination)."""
    if action in _ACTIONS_SUCCESS_ONLY:
        if outcome != _SUCCESS_OUTCOME:
            raise _IngestValidationError("invalid action/outcome combination")
        return
    if action == _ACTION_COMPLETED:
        if outcome not in _COMPLETED_OUTCOMES:
            raise _IngestValidationError("invalid action/outcome combination")
        return
    # _ACTION_FAILED: outcome must be exactly "error:<bounded-suffix>" (suffix non-empty, no whitespace).
    if not outcome.startswith(_ERROR_PREFIX):
        raise _IngestValidationError("invalid action/outcome combination")
    suffix = outcome[len(_ERROR_PREFIX) :]
    if not suffix or any(c.isspace() for c in suffix):
        raise _IngestValidationError("invalid action/outcome combination")


def _make_handler(store: ImportAuditStorePort) -> "type[BaseHTTPRequestHandler]":
    class _IngestHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            if self.path != _INGEST_PATH:
                self._respond_empty(404)  # wrong path: refused, no store call
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b""
                record = _parse_record(raw)
            except Exception:
                # Malformed/invalid envelope -> fixed 400 INVALID (no detail, no echo).
                self._respond_result(400, "INVALID")
                return
            try:
                result = store.append_import_audit(record)
            except ImportAuditConflictError:
                self._respond_result(409, "CONFLICT")
                return
            except ImportAuditInvalidError:
                self._respond_result(400, "INVALID")
                return
            except Exception:
                # Internal store failure collapses to a bounded response: no exception text, SQL,
                # topology, or credential state may leak through this edge.
                self._respond_result(503, "UNAVAILABLE")
                return
            self._respond_result(200, result.value)

        def _method_not_allowed(self) -> None:
            # POST-only edge: every non-POST method is refused 405 with an EMPTY body.
            self._respond_empty(405)

        # Refuse (not handle) other methods without ever reaching the stdlib HTML error path.
        do_GET = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed

        def _respond_empty(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _respond_result(self, status: int, result: str) -> None:
            payload = json.dumps({"version": _ENVELOPE_VERSION, "result": result}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:  # silence default stderr logging
            return

    return _IngestHandler


def build_import_audit_server(store: ImportAuditStorePort, host: str = "127.0.0.1", port: int = 0) -> Tuple[HTTPServer, str]:
    """Construct the internal Import operational-audit ingest server bound to an ``ImportAuditStorePort``.

    ``port=0`` binds an ephemeral port. This factory CONSTRUCTS the plain single-threaded server only —
    starting and stopping the request loop is the caller's responsibility (tests host it on loopback;
    production composition is the ``control_plane/main.py`` seam). Returns ``(server, base_url)``.
    """
    server = HTTPServer((host, port), _make_handler(store))
    bound_host, bound_port = cast(str, server.server_address[0]), server.server_address[1]
    return server, f"http://{bound_host}:{bound_port}"
