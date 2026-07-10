"""Control Plane Read API (Build Phase 4; PRD-P4-R2 B; closes O-2/R-P4-01).

Transport-agnostic read service over the ControlStore, plus a path/query dispatcher
the HTTP provider (and tests) call. Serves the internal **routing** read used by the
Database Router (`TenantRoutingView`, carrying the association *reference* and the
expected schema version) and the auth-facing tenant-state / membership / role reads.

Disclosure-safe (Governance §I): unknown tenants return 404 (consistent denial — no
existence leak); **no credentials are ever returned** (the association is a
{store_ref, version} reference, never the secret value). The routing read model is
distinct from tenant-state so the auth path never receives the association reference
(least disclosure). The routing endpoint is internal/control-plane-scoped.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from .federation import FederationStore
from .ports import ControlStore
from .records import DirectoryKind, DirectoryRecord, TenantLifecycleState

_DIR_ALIAS = {"startup": DirectoryKind.STARTUP, "investor": DirectoryKind.INVESTOR}
_MAX_PAGE = 200


class ControlPlaneReadService:
    def __init__(self, store: ControlStore) -> None:
        self._store = store
        self._federation = FederationStore(store)

    def tenant_state(self, tenant_id: str) -> Optional[dict[str, Any]]:
        rec = self._store.get_tenant(tenant_id)
        if rec is None:
            return None
        return {
            "tenant_id": rec.tenant_id,
            "lifecycle_state": rec.lifecycle_state.value,
            "ready": rec.lifecycle_state is TenantLifecycleState.READY,
        }

    def routing_view(self, tenant_id: str) -> Optional[dict[str, Any]]:
        rec = self._store.get_tenant(tenant_id)
        if rec is None:
            return None
        return {
            "tenant_id": rec.tenant_id,
            "lifecycle_state": rec.lifecycle_state.value,
            "ready": rec.lifecycle_state is TenantLifecycleState.READY,
            "database_association_ref": {
                "store_ref": rec.database_association_ref.store_ref,
                "version": rec.database_association_ref.version,
            },  # reference only — NEVER credentials (D-14)
            "expected_schema_version": rec.expected_schema_version,
        }

    def is_member(self, principal_ref: str, tenant_id: str) -> dict[str, Any]:
        members = self._store.list_memberships(principal_ref=principal_ref, tenant_id=tenant_id)
        return {"member": len(members) > 0}

    def get_role(self, principal_ref: str, tenant_id: str) -> Optional[dict[str, Any]]:
        members = self._store.list_memberships(principal_ref=principal_ref, tenant_id=tenant_id)
        if not members:
            return None
        return {"role": members[0].role.value}

    def federation_for_issuer(self, issuer: str) -> Optional[dict[str, Any]]:
        """Resolve an OIDC issuer to its per-tenant federation config (B5-3 LW-2).

        The federation read contract is keyed by tenant (``FederationStore.get(tenant_id)``),
        so the issuer is resolved through the EXISTING port surface only: enumerate
        ``list_tenant_ids()`` in sorted order (deterministic when two tenants share an
        issuer — first match wins) and read each config through the existing
        ``FederationStore`` (the ``directory_page`` enumeration precedent). The response
        carries exactly the five ``FederationConfig`` fields — the shape the auth-router
        client (``HttpControlPlaneRead.get_federation_for_issuer``) already decodes as
        ``FederationView``. ``jwks_ref`` is a REFERENCE (public-key location, never key
        material inline) — no credential crosses this read (Governance §I).
        """
        for tenant_id in sorted(self._store.list_tenant_ids()):
            config = self._federation.get(tenant_id)
            if config is not None and config.oidc_issuer == issuer:
                return {
                    "tenant_id": config.tenant_id,
                    "oidc_issuer": config.oidc_issuer,
                    "oidc_audience": config.oidc_audience,
                    "jwks_ref": config.jwks_ref,
                    "claim_to_tenant_rule": config.claim_to_tenant_rule,
                }
        return None

    # --- Global Discovery Platform reads (D-31; PRD-P5-R2 E) -----------------
    # Global reference data only; NEVER tenant-owned records.
    def directory_record(self, kind_alias: str, record_id: str) -> Optional[dict[str, Any]]:
        kind = _DIR_ALIAS.get(kind_alias)
        if kind is None:
            return None
        rec = self._store.get_directory_record(kind, record_id)
        if rec is None:
            return None
        return self._directory_view(rec)

    def directory_page(self, kind_alias: str, cursor: str, limit: int) -> Optional[dict[str, Any]]:
        kind = _DIR_ALIAS.get(kind_alias)
        if kind is None:
            return None
        limit = max(1, min(limit, _MAX_PAGE))
        records = sorted(self._store.list_directory(kind), key=lambda r: r.record_id)
        offset = int(cursor) if (cursor or "").isdigit() else 0
        page = records[offset : offset + limit]
        next_cursor = str(offset + limit) if offset + limit < len(records) else None
        return {"records": [self._directory_view(r) for r in page], "next_cursor": next_cursor}

    @staticmethod
    def _directory_view(rec: DirectoryRecord) -> dict[str, Any]:
        return {
            "directory": rec.directory.value,
            "record_id": rec.record_id,
            "display_name": rec.display_name,
            "attributes": dict(rec.attributes),  # non-sensitive global reference data
        }


_NOT_FOUND: Tuple[int, dict[str, Any]] = (404, {"error": "not_found"})


class ControlPlaneReadDispatcher:
    """Maps (method, request_target) -> (http_status, body). Transport-neutral."""

    def __init__(self, service: ControlPlaneReadService) -> None:
        self._svc = service

    def handle(self, method: str, request_target: str) -> Tuple[int, Optional[dict[str, Any]]]:
        if method != "GET":
            return (405, {"error": "method_not_allowed"})
        parts = urlsplit(request_target)
        path = parts.path
        query = parse_qs(parts.query)
        segments = [s for s in path.split("/") if s != ""]

        # /internal/routing/tenants/{tenant_id}
        if segments[:3] == ["internal", "routing", "tenants"] and len(segments) == 4:
            body = self._svc.routing_view(segments[3])
            return (200, body) if body is not None else _NOT_FOUND

        # /tenants/{tenant_id}/state
        if len(segments) == 3 and segments[0] == "tenants" and segments[2] == "state":
            body = self._svc.tenant_state(segments[1])
            return (200, body) if body is not None else _NOT_FOUND

        # /membership?p=&t=
        if segments == ["membership"]:
            p = (query.get("p") or [""])[0]
            t = (query.get("t") or [""])[0]
            return (200, self._svc.is_member(p, t))

        # /role?p=&t=
        if segments == ["role"]:
            p = (query.get("p") or [""])[0]
            t = (query.get("t") or [""])[0]
            body = self._svc.get_role(p, t)
            return (200, body) if body is not None else _NOT_FOUND

        # /directory/{kind}/{record_id}
        if len(segments) == 3 and segments[0] == "directory":
            body = self._svc.directory_record(segments[1], segments[2])
            return (200, body) if body is not None else _NOT_FOUND

        # /directory/{kind}?cursor=&limit=
        if len(segments) == 2 and segments[0] == "directory":
            cursor = (query.get("cursor") or [""])[0]
            limit_raw = (query.get("limit") or ["100"])[0]
            limit = int(limit_raw) if limit_raw.isdigit() else 100
            body = self._svc.directory_page(segments[1], cursor, limit)
            return (200, body) if body is not None else _NOT_FOUND

        # /federation?issuer=<urlencoded issuer> (B5-3 LW-2 — the read half of the existing
        # HttpControlPlaneRead.get_federation_for_issuer client pair). Parsed with
        # keep_blank_values so "missing", "empty", and "duplicate" are each visible and all
        # rejected with a deterministic 400 (exactly ONE non-empty issuer value is required);
        # parse_qs percent-decodes the client's urllib.parse.quote()d issuer.
        if segments == ["federation"]:
            issuers = parse_qs(parts.query, keep_blank_values=True).get("issuer")
            if issuers is None or len(issuers) != 1 or not issuers[0]:
                return (400, {"error": "invalid_issuer"})
            body = self._svc.federation_for_issuer(issuers[0])
            return (200, body) if body is not None else _NOT_FOUND

        return _NOT_FOUND
