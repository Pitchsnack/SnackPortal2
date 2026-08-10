"""Test doubles for the Gateway-free MVP public edges.

The doubles sit at exactly two places, and deliberately nowhere else:

* **the database** — two PHYSICALLY DISTINCT in-memory tenant stores behind a real
  ``RoutedSessionProvider``. Distinct dicts stand in for distinct physical databases, and the
  provider records every ``(tenant_id, principal_ref)`` it was asked to open. That recording is
  the strongest available detector: a cross-tenant breach shows up as an opened ACME session
  under a ZETA principal even when the HTTP status would look innocent;
* **the identity provider** — a fake IC-005 ``PrincipalAuthenticatorPort`` that reproduces the
  real Auth Router's Stage-1 + Stage-2 decision shape (bearer -> claims; carrier match-or-reject;
  membership + readiness check; the consistent forbidden denial) without JWT or crypto.

Everything between those two points is the REAL runtime under test: the real shared
``PublicBoundary`` kernel, the real shared transport gate, the real ``TenantStartupOperations``
executor, the real owner-resident DTO composition, and the real FastAPI applications served over
a real loopback socket.
"""

from __future__ import annotations

import http.client
import json
import threading
from typing import Any, Dict, List, Optional, Tuple

from shared.public_edge import (
    EdgeAuditEvent,
    EdgeAuditPort,
    PrincipalAuthenticatorPort,
    PublicBoundary,
    TrustedPrincipal,
    carrier_mismatch,
    forbidden,
    unauthenticated,
    unavailable,
)
from shared.session import Lane, RoutedSessionProvider, RoutedTenantSession

ACME = "t-acme"
ZETA = "t-zeta"
ACME_REF = "gs-acme-1"
ZETA_REF = "gs-zeta-1"
ACME_SECRET_NAME = "ACME Confidential Holdings"
ZETA_SECRET_NAME = "ZETA Private Partners"

# Bearer credentials the fake identity provider recognizes. Opaque strings, never real tokens.
ACME_BEARER = "acme-principal-token"
ZETA_BEARER = "zeta-principal-token"
CONTROL_BEARER = "control-principal-token"
STRANGER_BEARER = "non-member-principal-token"

ACME_PRINCIPAL = "p-acme"
ZETA_PRINCIPAL = "p-zeta"
CONTROL_PRINCIPAL = "p-control"
STRANGER_PRINCIPAL = "p-stranger"

_CLAIMS: Dict[str, Tuple[str, Optional[str], Optional[str]]] = {
    # bearer -> (principal_ref, signed active tenant claim or None for CONTROL, role)
    ACME_BEARER: (ACME_PRINCIPAL, ACME, "TENANT_AGENT"),
    ZETA_BEARER: (ZETA_PRINCIPAL, ZETA, "TENANT_AGENT"),
    CONTROL_BEARER: (CONTROL_PRINCIPAL, None, None),
    STRANGER_BEARER: (STRANGER_PRINCIPAL, ACME, "TENANT_AGENT"),
}

# The Control-Plane membership table the fake Auth Router consults (Stage 2). The stranger holds
# a signed ACME claim but NO membership row, which is how a revoked or forged claim behaves.
_MEMBERSHIPS: Dict[str, Tuple[str, ...]] = {
    ACME_PRINCIPAL: (ACME,),
    ZETA_PRINCIPAL: (ZETA,),
    CONTROL_PRINCIPAL: (),
    STRANGER_PRINCIPAL: (),
}


# --------------------------------------------------------------------------------------------
# The two-tenant data plane
# --------------------------------------------------------------------------------------------


class _Session(RoutedTenantSession):
    """One tenant, one store, caller-controlled transaction — the real session vocabulary."""

    def __init__(self, tenant_id: str, store: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
        self._tenant_id = tenant_id
        self._store = store
        self._staged: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def begin(self) -> None:
        self._staged = {table: {key: dict(row) for key, row in rows.items()} for table, rows in self._store.items()}

    def _live(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        return self._staged if self._staged is not None else self._store

    def commit(self) -> None:
        if self._staged is not None:
            self._store.clear()
            self._store.update(self._staged)
            self._staged = None

    def rollback(self) -> None:
        self._staged = None

    def close(self) -> None:
        self._staged = None

    def upsert(self, table: str, key: Dict[str, Any], row: Dict[str, Any]) -> bool:
        rows = self._live().setdefault(table, {})
        ref = str(next(iter(key.values())))
        changed = rows.get(ref) != row
        rows[ref] = dict(row)
        return changed

    def append(self, table: str, row: Dict[str, Any]) -> None:
        rows = self._live().setdefault(table, {})
        rows[str(len(rows))] = dict(row)

    def update(self, table: str, key: Dict[str, Any], assignments: Dict[str, Any]) -> None:
        rows = self._live().setdefault(table, {})
        ref = str(next(iter(key.values())))
        if ref in rows:
            rows[ref].update(assignments)

    def get(self, table: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = self._live().get(table, {})
        row = rows.get(str(next(iter(key.values()))))
        return dict(row) if row is not None else None

    def latest(self, table: str, where: Dict[str, Any], order_by: str) -> Optional[Dict[str, Any]]:
        rows = [row for row in self._live().get(table, {}).values() if all(row.get(k) == v for k, v in where.items())]
        if not rows:
            return None
        return dict(max(rows, key=lambda row: row.get(order_by, 0)))


class TwoTenantProvider(RoutedSessionProvider):
    """Two physically distinct stores; records every session it is asked to open.

    ``opened`` is the isolation oracle: a Gateway-free architecture is safe only if a ZETA
    principal never causes ``(ACME, ...)`` to appear here — regardless of what the caller put
    in a header, a body, or a path.
    """

    def __init__(self) -> None:
        self._stores: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {
            ACME: {
                "startups": {
                    ACME_REF: {
                        "global_startup_id": ACME_REF,
                        "company_name": ACME_SECRET_NAME,
                        "short_description": "acme-private",
                        "investment_stage": "seed",
                    }
                },
                "lineage": {},
            },
            ZETA: {
                "startups": {
                    ZETA_REF: {
                        "global_startup_id": ZETA_REF,
                        "company_name": ZETA_SECRET_NAME,
                        "short_description": "zeta-private",
                        "investment_stage": "series-a",
                    }
                },
                "lineage": {},
            },
        }
        self.opened: List[Tuple[str, Optional[str]]] = []
        self.fail_with: Optional[Exception] = None

    def store(self, tenant_id: str) -> Dict[str, Dict[str, Any]]:
        return self._stores[tenant_id]["startups"]

    def open_session(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        principal_ref: Optional[str] = None,
        lane: Lane = Lane.BULK,
    ) -> RoutedTenantSession:
        self.opened.append((tenant_id, principal_ref))
        if self.fail_with is not None:
            raise self.fail_with
        if tenant_id not in self._stores:
            raise LookupError("no such tenant association")
        return _Session(tenant_id, self._stores[tenant_id])


# --------------------------------------------------------------------------------------------
# The identity provider double (the IC-005 Auth Router's decision shape, without crypto)
# --------------------------------------------------------------------------------------------


class FakeAuthRouter(PrincipalAuthenticatorPort):
    """Reproduces Stage 1 (bearer -> claims) and Stage 2 (carrier match, membership, readiness).

    Denial vocabulary matches the real router exactly: 401 ``unauthenticated`` for a missing or
    unknown bearer; 403 ``carrier_mismatch`` when an asserted carrier disagrees with the signed
    claim; 403 ``forbidden`` for an unknown tenant AND for a non-member alike (the consistent
    denial that leaks no tenant existence); 503 ``unavailable`` when the control plane is down.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[Optional[str], Tuple[str, ...]]] = []
        self.control_plane_down = False
        self.not_ready_tenants: Tuple[str, ...] = ()

    def authenticate(self, authorization: Optional[str], carriers: Any, correlation_id: str) -> TrustedPrincipal:
        carrier_list = tuple(carriers)
        self.calls.append((authorization, carrier_list))
        if not isinstance(authorization, str):
            raise unauthenticated()
        scheme, sep, credential = authorization.partition(" ")
        if sep != " " or scheme.lower() != "bearer" or not credential or credential.startswith(" "):
            raise unauthenticated()
        claims = _CLAIMS.get(credential)
        if claims is None:
            raise unauthenticated()
        principal_ref, active, role = claims
        if active is None:
            # Tenantless CONTROL principal: a carrier is claim-only and never a selector.
            return TrustedPrincipal(correlation_id=correlation_id, principal_ref=principal_ref, active_tenant_id=None, role=None)
        distinct = []
        for carrier in carrier_list:
            if carrier not in distinct:
                distinct.append(carrier)
        if len(distinct) > 1:
            raise carrier_mismatch()
        if distinct and distinct[0] != active:
            raise carrier_mismatch()
        if self.control_plane_down:
            raise unavailable()
        if active not in _MEMBERSHIPS.get(principal_ref, ()):
            raise forbidden()  # unknown tenant and non-member are indistinguishable
        if active in self.not_ready_tenants:
            raise forbidden()
        return TrustedPrincipal(correlation_id=correlation_id, principal_ref=principal_ref, active_tenant_id=active, role=role)


class RecordingAudit(EdgeAuditPort):
    """Records emitted events; ``fail_with`` makes the sink terminally unavailable."""

    def __init__(self) -> None:
        self.events: List[EdgeAuditEvent] = []
        self.fail_with: Optional[Exception] = None

    def emit(self, event: EdgeAuditEvent) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.events.append(event)

    def actions(self) -> List[str]:
        return [event.action for event in self.events]


def build_boundary() -> Tuple[PublicBoundary, FakeAuthRouter, RecordingAudit]:
    """The REAL shared kernel over the two doubles."""
    auth = FakeAuthRouter()
    audit = RecordingAudit()
    return PublicBoundary(authenticator=auth, audit=audit), auth, audit


# --------------------------------------------------------------------------------------------
# Loopback hosting — the edges are exercised over a real socket, never via a test client
# --------------------------------------------------------------------------------------------


class HostedEdge:
    """A composed edge served on an ephemeral loopback port for the lifetime of a ``with``."""

    def __init__(self, server: Any, base_url: str) -> None:
        self._server = server
        self.base_url = base_url
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)

    def __enter__(self) -> "HostedEdge":
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server.server_close()

    @property
    def port(self) -> int:
        return int(self.base_url.rsplit(":", 1)[1])

    def request(
        self,
        method: str,
        target: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
    ) -> Tuple[int, bytes, Dict[str, str]]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, target, body=body, headers=headers or {})
            response = conn.getresponse()
            payload = response.read()
            return response.status, payload, {k.lower(): v for k, v in response.getheaders()}
        finally:
            conn.close()


def bearer(credential: str) -> Dict[str, str]:
    return {"Authorization": "Bearer " + credential}


def decode(payload: bytes) -> Any:
    return json.loads(payload.decode("utf-8"))
