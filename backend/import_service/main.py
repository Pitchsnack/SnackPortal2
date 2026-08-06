"""import_service composition (Build Phase 5; W1a composed-core seams).

Wires the import coordinator from injected shared-port providers: the RoutedSessionProvider (implemented by
database_router), the LineageEmitPort (implemented by lineage_service), and a DirectoryReadPort transport
client. No service is imported directly (DAG) — only shared ports + this service's own adapters. Liveness is
static and non-disclosing.

W1a adds (a) an optional ``directory_source`` override (default ``GlobalDirectorySource`` — behavior
unchanged; the W1a composed-core journey injects ``StartupDirectorySource`` for the single-record Global→
tenant mapping); (b) ``BoundedImportAuditPolicy`` (the ``BoundedGatewayAuditPolicy`` twin — one bounded
transient retry, reusing the SAME ``audit_id``); (c) ``build_import_audit_sink_from_env`` (the durable
Import-audit sink selector — unset keeps the in-memory no-sink default); and (d)
``build_import_server_from_env`` (host-gate-first served-edge seam — the CP seam idiom). None of these
activates a production import server: the routing session provider and lineage emit port are cross-package and
must be injected by a higher deployment root (import_service must never import database_router / lineage_service
— DAG independence); host/port/audit-sink are read from the environment.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, Optional, Tuple
from urllib.parse import urlsplit

from shared.audit import OperationalAudit, OperationalAuditEvent
from shared.lineage import LineageEmitPort
from shared.session import RoutedSessionProvider

from .adapters.providers.csv_source import CsvSourceAdapter
from .adapters.providers.global_directory_source import GlobalDirectorySource
from .adapters.providers.in_memory_audit_sink import InMemoryAuditSink
from .adapters.providers.json_source import JsonSourceAdapter
from .adapters.providers.startup_directory_source import StartupDirectorySource
from .models import SourceKind
from .ports import DirectoryReadPort, SourceAdapter
from .service import ImportService

if TYPE_CHECKING:  # avoid a top-level transport import (main.py stays import-light while inactive)
    from .adapters.providers.durable_audit_emitter import DurableImportAuditEmitter

SERVICE = "import_service"

# The durable Import-audit sink selector (the Gateway Audit V1a selector idiom). NON-SECRET internal routing
# config — the loopback/internal Control-Plane Import-audit ingest base URL, never a credential. Unset/empty →
# the default in-memory no-sink emitter (there is deliberately NO loopback default — a default would silently
# activate a durable transport); a structurally valid internal http URL → the durable
# ``DurableImportAuditEmitter`` wrapped in the bounded ``BoundedImportAuditPolicy``; anything else → ValueError
# before any socket (fail closed — never a silent fallback from malformed production config).
SP2_IMPORT_AUDIT_SINK_BASE_URL = "SP2_IMPORT_AUDIT_SINK_BASE_URL"

# The Global-directory read base URL — the internal Control-Plane read edge this service reads Global records
# from. NON-SECRET internal routing config (never a credential). Unset/empty → ``None`` from
# ``build_directory_read_from_env`` (the caller must then inject a ``DirectoryReadPort`` explicitly); a
# structurally valid internal http URL → the in-package ``HttpDirectoryRead`` transport client; anything else →
# ValueError before any socket (fail closed — never a silent fallback from malformed production config).
SP2_IMPORT_DIRECTORY_READ_BASE_URL = "SP2_IMPORT_DIRECTORY_READ_BASE_URL"

# The served internal Import-initiate edge bind host — the ACTIVATION selector (the CP seam idiom). Non-secret
# internal config. Unset / empty / whitespace-only → the seam is inactive (returns ``None``); otherwise the
# stripped value must be one of the internal loopback hosts (IC-010 §R).
SP2_IMPORT_HOST = "SP2_IMPORT_HOST"

# The served Import-initiate edge bind port. Consulted ONLY when the host selector is active. Unset / empty /
# whitespace → ``0`` (ephemeral); otherwise a base-10 integer in ``[0, 65535]``; anything else → ``ValueError``
# raised BEFORE the server is built and any socket binds (fail closed).
SP2_IMPORT_PORT = "SP2_IMPORT_PORT"

# The served edge is internal-only and binds loopback hosts exclusively (never portal-reachable).
_IMPORT_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

_AUDIT_EVENT_VERSION = 1


def build_import_service(
    *,
    session_provider: RoutedSessionProvider,
    lineage: LineageEmitPort,
    directory_read: DirectoryReadPort,
    audit: Optional[OperationalAudit] = None,
    directory_source: Optional[SourceAdapter] = None,
    batch_size: int = 2,
    schema_version: str = "1",
) -> ImportService:
    sources = {
        # W1a: the composed-core journey injects StartupDirectorySource (the single-record Global→tenant
        # mapping). Default GlobalDirectorySource keeps every existing composition byte-behavior-unchanged.
        SourceKind.DIRECTORY: directory_source if directory_source is not None else GlobalDirectorySource(directory_read),
        SourceKind.CSV: CsvSourceAdapter(),
        SourceKind.JSON: JsonSourceAdapter(),
    }
    return ImportService(
        session_provider=session_provider,
        lineage=lineage,
        audit=audit or InMemoryAuditSink(),
        sources=sources,
        schema_version=schema_version,
        batch_size=batch_size,
    )


class BoundedImportAuditPolicy(OperationalAudit):
    """W1a fail-closed durable Import-audit policy (the ``BoundedGatewayAuditPolicy`` twin).

    Wraps the durable transport emitter behind the same sink-less ``OperationalAudit`` and owns the two
    fail-closed decisions for every emitted import event:

    * exactly ONE immediate, synchronous, idempotent retry, reusing the SAME ``audit_id`` (maximum two total
      transport calls), and only when the transport failure kind is ``unavailable`` (transient); ``invalid``
      and ``conflict`` are NEVER retried. No retry loop, sleep, queue, outbox, thread, or background machinery.
    * terminal posture: re-raise so the Import boundary fails closed (audit-before-hand-back — the served edge
      maps the raise to 503 ``UNAVAILABLE``; a served import success is never handed back unless its completion
      event is durably confirmed).

    The ``audit_id`` (and ``occurred_at``) are minted ONCE per ``initiate`` in the policy and passed to the
    emitter's ``post`` — so the single retry replays a byte-identical payload (an idempotent ``DUPLICATE_MATCH``
    on the store), never a second row. A ``DUPLICATE_MATCH`` is success inside the wrapped client and never
    reaches this policy's failure path.
    """

    def __init__(self, inner: "DurableImportAuditEmitter", *, transport_error: type[Exception]) -> None:
        self._inner = inner
        self._transport_error = transport_error

    def _retryable(self, failure: Exception) -> bool:
        # Exactly the transient transport kind is retryable; invalid/conflict never.
        return isinstance(failure, self._transport_error) and getattr(failure, "kind", None) == "unavailable"

    def initiate(self, event: OperationalAuditEvent) -> None:
        audit_id = uuid.uuid4().hex
        occurred_at = datetime.now(timezone.utc).isoformat()
        try:
            self._inner.post(event, audit_id=audit_id, event_version=_AUDIT_EVENT_VERSION, occurred_at=occurred_at)
            return
        except Exception as first:
            if not self._retryable(first):
                raise  # invalid/conflict → terminal fail-closed, no retry
        # The single bounded retry: the SAME audit_id + occurred_at (idempotent replay; re-raises on terminal).
        self._inner.post(event, audit_id=audit_id, event_version=_AUDIT_EVENT_VERSION, occurred_at=occurred_at)


def build_import_audit_sink_from_env() -> Optional[OperationalAudit]:
    """The config-selectable durable Import-audit sink seam (W1a; IC-003 Import Audit persistence).

    * ``SP2_IMPORT_AUDIT_SINK_BASE_URL`` unset, or empty/whitespace after stripping → ``None`` — the caller
      keeps the default in-memory no-sink emitter (build_import_service defaults to ``InMemoryAuditSink``).
      There is deliberately NO loopback default — a default would silently activate a durable transport.
    * a structurally valid internal ``http://host[:port]`` value → a ``DurableImportAuditEmitter`` bound to
      that base URL, wrapped in the bounded ``BoundedImportAuditPolicy``. The transport client is lazy:
      construction performs no network I/O.
    * anything else → ``ValueError`` at the composition boundary, raised BEFORE any socket — never a silent
      fallback from malformed production config to the in-memory sink.

    Validation is structural only (``urlsplit`` scheme + netloc; scheme pinned to ``http`` — internal loopback
    transport; TLS termination is deployment scope). No network I/O, no ``control_plane`` import, no database
    access, no secret handling (the base URL is non-secret internal routing config; no SecretRef).
    """
    raw = (os.environ.get(SP2_IMPORT_AUDIT_SINK_BASE_URL) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme != "http" or not parts.netloc:
        raise ValueError(
            f"unsupported {SP2_IMPORT_AUDIT_SINK_BASE_URL}={raw!r}; expected an internal "
            "http://host[:port] Import operational-audit sink base URL (fail closed — no silent fallback)"
        )
    # Lazy relative import (the merged seam shape): the transport client is deferred to selection time.
    from .adapters.providers.durable_audit_emitter import DurableImportAuditEmitter, ImportAuditTransportError

    return BoundedImportAuditPolicy(DurableImportAuditEmitter(raw), transport_error=ImportAuditTransportError)


def build_directory_read_from_env() -> Optional[DirectoryReadPort]:
    """The config-selectable Global-directory read transport seam (the audit-sink selector idiom).

    This is the ONE of import_service's three collaborator ports that CAN be composed inside this
    package: ``HttpDirectoryRead`` is an in-package adapter over the internal Control-Plane read edge, so
    selecting it here imports no sibling service and preserves DAG independence. The routed session provider
    and the lineage emit port remain injection-only (they are implemented by ``database_router`` /
    ``lineage_service`` and cannot be constructed here).

    * ``SP2_IMPORT_DIRECTORY_READ_BASE_URL`` unset, or empty/whitespace after stripping → ``None``; the
      caller must inject a ``DirectoryReadPort`` explicitly.
    * a structurally valid internal ``http://host[:port]`` value → ``HttpDirectoryRead`` bound to it. The
      client is lazy: construction performs no network I/O.
    * anything else → ``ValueError`` at the composition boundary, raised BEFORE any socket — never a silent
      fallback from malformed production config.

    Validation is structural only (``urlsplit`` scheme + netloc; scheme pinned to ``http`` — internal
    transport; TLS termination is deployment scope). No network I/O, no ``control_plane`` import, no database
    access, no secret handling (the base URL is non-secret internal routing config; no SecretRef).
    """
    raw = (os.environ.get(SP2_IMPORT_DIRECTORY_READ_BASE_URL) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme != "http" or not parts.netloc:
        raise ValueError(
            f"unsupported {SP2_IMPORT_DIRECTORY_READ_BASE_URL}={raw!r}; expected an internal "
            "http://host[:port] Global-directory read base URL (fail closed — no silent fallback)"
        )
    # Lazy relative import (the merged seam shape): the transport client is deferred to selection time.
    from .adapters.providers.http_directory_read import HttpDirectoryRead

    return HttpDirectoryRead(raw)


def _import_port_from_env() -> int:
    """Parse ``SP2_IMPORT_PORT`` fail-closed: unset/empty/whitespace → ``0`` (ephemeral); otherwise a base-10
    integer in ``[0, 65535]``, else ``ValueError`` — raised BEFORE the server is built and any socket bind so
    malformed config never opens a listener."""
    raw = (os.environ.get(SP2_IMPORT_PORT) or "").strip()
    if not raw:
        return 0
    try:
        port = int(raw, 10)
    except ValueError:
        raise ValueError(f"invalid {SP2_IMPORT_PORT}={raw!r}; expected an integer in [0, 65535]") from None
    if not (0 <= port <= 65535):
        raise ValueError(f"invalid {SP2_IMPORT_PORT}={raw!r}; port out of range [0, 65535]")
    return port


def build_import_service_from_env(
    *,
    session_provider: Optional[RoutedSessionProvider] = None,
    lineage: Optional[LineageEmitPort] = None,
    directory_read: Optional[DirectoryReadPort] = None,
) -> ImportService:
    """The composed-core Import SERVICE composition — the ONE dependency-construction path.

    Extracted so every startup path — the native ASGI application factory owned by the deployment
    composition root, and the compatibility ``build_import_server_from_env`` seam — builds the
    ``ImportService`` through exactly the same code. Import business semantics, the contract, the
    lineage semantics, the schema, and the route set are untouched by this extraction: it composes
    the SAME ``build_import_service`` call with the SAME ``StartupDirectorySource`` mapping and the
    SAME env-selected durable audit sink that the seam previously built inline.

    Cross-package ports (LOAD-BEARING, DAG): the routing ``session_provider`` (implemented by
    database_router) and the ``lineage`` emit port (implemented by lineage_service) CANNOT be
    constructed inside import_service — the import-linter independence contract forbids importing
    either package. A deployment composition root that may import all three injects them here.

    ``directory_read`` is the one port this package CAN compose for itself: when not injected it is
    selected from the environment via ``build_directory_read_from_env`` (the in-package
    ``HttpDirectoryRead`` adapter over the internal Control-Plane read edge).

    Fail closed: when any of the three ports is still missing after injection + env selection, this
    raises ``ValueError`` — never a partial, in-memory, or silently degraded Import service.
    """
    directory = directory_read if directory_read is not None else build_directory_read_from_env()
    if session_provider is None or lineage is None or directory is None:
        raise ValueError(
            "the composed Import service requires the injected routing session provider and lineage emit"
            f" port, plus a directory read port (injected or selected by {SP2_IMPORT_DIRECTORY_READ_BASE_URL});"
            " a deployment composition root wires the first two, because import_service must not import"
            " database_router / lineage_service — DAG independence. Fail closed — no partial service composed."
        )
    audit = build_import_audit_sink_from_env()
    return build_import_service(
        session_provider=session_provider,
        lineage=lineage,
        directory_read=directory,
        directory_source=StartupDirectorySource(directory),
        audit=audit,
    )


def build_import_server_from_env(
    *,
    session_provider: Optional[RoutedSessionProvider] = None,
    lineage: Optional[LineageEmitPort] = None,
    directory_read: Optional[DirectoryReadPort] = None,
) -> Optional[Tuple[object, str]]:
    """The host-gate-first served Import-initiate edge composition seam (W1a; the CP seam idiom).

    Host-gate-first (the bind HOST is the activation selector):

    * ``SP2_IMPORT_HOST`` unset, or empty/whitespace after stripping → ``None``: the seam is inactive; the
      port and injected ports are NOT consulted, no service is composed, and no socket binds.
    * an active host must be one of ``127.0.0.1`` / ``localhost`` / ``::1`` — the served edge is internal-only;
      any other host → ``ValueError`` BEFORE any socket bind (fail closed).
    * ``SP2_IMPORT_PORT`` unset/empty → ``0`` (ephemeral); otherwise an integer in ``[0, 65535]``; anything
      else → ``ValueError`` BEFORE the server is built and any socket bind.

    Cross-package ports (LOAD-BEARING, DAG): the routing ``session_provider`` (database_router) and ``lineage``
    emit port (lineage_service) — and the ``directory_read`` transport port — CANNOT be composed inside
    import_service (import-linter independence contract). A higher deployment root that may import all three
    services injects them here. When the host is active and any of the three is missing, the seam raises
    ``ValueError`` (fail closed — never a partial or silently-degraded production service). The durable audit
    sink is selected from the environment (``build_import_audit_sink_from_env``; unset → the in-memory
    no-sink default), and the composed-core ``StartupDirectorySource`` is wired over ``directory_read``.

    Side-effect boundary: this seam is DB-inert, network-read-inert, and serve-inert; it is NOT socket-inert —
    when active with all ports injected, ``build_import_server`` binds an ephemeral local socket at
    construction. Callers/tests own the socket lifecycle. Starting the request loop is NEVER done here.
    """
    host = (os.environ.get(SP2_IMPORT_HOST) or "").strip()
    if not host:
        return None
    if host not in _IMPORT_LOOPBACK_HOSTS:
        raise ValueError(
            f"invalid {SP2_IMPORT_HOST}; the served Import-initiate edge is internal-only and"
            f" must bind one of {_IMPORT_LOOPBACK_HOSTS} (fail closed — the configured value is not echoed)"
        )
    port = _import_port_from_env()
    service = build_import_service_from_env(
        session_provider=session_provider,
        lineage=lineage,
        directory_read=directory_read,
    )
    # Lazy relative import keeps import_service/main.py import-light (the serving stack is pulled in when active);
    # build_import_server binds the ephemeral socket.
    from .adapters.providers.http_import_api import build_import_server

    return build_import_server(service, host=host, port=port)


def liveness() -> Dict[str, str]:
    return {"service": SERVICE, "status": "alive", "build_phase": "5"}
