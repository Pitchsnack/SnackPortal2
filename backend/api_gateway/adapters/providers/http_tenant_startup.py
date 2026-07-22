"""Production ``TenantStartupOperationsPort`` over internal HTTP (stdlib urllib) — D-42 CLM Stage B.

The gateway side of the CLM tenant Startup data seam (IC-010 CLM section): a transport CLIENT
to the Database Router's internal tenant Startup operations edge — reached over transport ONLY,
never an in-process import of ``database_router`` (IC-010 §M; DAG independence). Typed parsing
lives HERE: the raw provider body never crosses the port — the gateway consumes only the adopted
``TenantStartupDetailDTO`` (IC-009 CLM section), composed from validated fields. The gateway
never resolves a database (§X): the Database Router side selects exactly one physical tenant
database from the signed active tenant this client forwards by reference.

Denial mapping mirrors the merged Control-Plane read client (B5-3 LW-1): a live HTTP 404 maps to
``None`` (the consistent IC-002 not-found semantic — the gateway maps it to the existing
``not_found`` denial), and EVERY other failure — timeout, connection refusal, oversized,
malformed, wrong-shape, over-bound field — raises, so the gateway collapses it fail-closed to
503 ``unavailable`` (IC-010 §L; no new ``public_code``; no error path surfaces internal detail).
References + the two bounded nullable content fields only: no tenant row, DB handle/name/DSN,
credential, secret, or router internals ever cross this client. Lazy construction (no network
I/O until a call); bounded timeout; bounded response size; single attempt (no retry loop);
stdlib urllib only — no vendor SDK, no secret-bearing configuration (the base URL is non-secret
internal routing config).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from api_gateway.portal import (
    TENANT_STARTUP_SHORT_DESCRIPTION_MAX_CHARS,
    TenantStartupDetailDTO,
)
from api_gateway.ports import (
    TenantStartupOperationsPort,
    TenantStartupReadRequest,
    TenantStartupUpdateRequest,
)

_READ_PATH = "/internal/tenant/startups/read"
_UPDATE_PATH = "/internal/tenant/startups/update"
_ENVELOPE_VERSION = 1
_MAX_REF_BYTES = 512  # IC-010 CLM: every reference field is length-bounded (1..512 UTF-8 bytes)
_MAX_LABEL_CHARS = 200  # bounded label (investment_stage) — defensive response bound

# Exactly the five bounded record keys the internal edge returns; the D-37 §10 provenance
# triple is DTO-owned constants (record_origin/record_residency/record_type) and never wire.
_RECORD_KEYS = frozenset({"record_ref", "display_name", "short_description", "investment_stage", "lineage_reference"})


def _checked_ref(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > _MAX_REF_BYTES:
        raise ValueError(f"malformed tenant startup record field: {field}")
    return value


def _checked_nullable(value: object, field: str, max_chars: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > max_chars:
        raise ValueError(f"malformed tenant startup record field: {field}")
    return value


class HttpTenantStartupOperations(TenantStartupOperationsPort):
    """HTTP client for the internal Database-Router tenant Startup operations edge."""

    def __init__(self, base_url: str, timeout: float = 5.0, max_response_bytes: int = 64 * 1024) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._max_bytes = max_response_bytes

    def read(self, request: TenantStartupReadRequest) -> Optional[TenantStartupDetailDTO]:
        envelope: Dict[str, object] = {
            "v": _ENVELOPE_VERSION,
            "startup_ref": request.startup_ref,
            "target_tenant_ref": request.target_tenant_ref,
            "correlation_id": request.correlation_id,
            "actor_ref": request.actor_ref,
        }
        return self._call(_READ_PATH, envelope, request.startup_ref)

    def update(self, request: TenantStartupUpdateRequest) -> Optional[TenantStartupDetailDTO]:
        envelope: Dict[str, object] = {
            "v": _ENVELOPE_VERSION,
            "startup_ref": request.startup_ref,
            "target_tenant_ref": request.target_tenant_ref,
            "correlation_id": request.correlation_id,
            "actor_ref": request.actor_ref,
            "short_description": request.short_description,
        }
        return self._call(_UPDATE_PATH, envelope, request.startup_ref)

    def _call(self, path: str, envelope: Dict[str, object], startup_ref: str) -> Optional[TenantStartupDetailDTO]:
        payload = json.dumps(envelope).encode("utf-8")
        http_request = urllib.request.Request(
            self._base + path,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self._timeout) as resp:  # internal database-router URL
                status = int(resp.status)
                raw = resp.read(self._max_bytes + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None  # unknown <startup_ref> within the bound tenant DB (consistent IC-002 not-found)
            raise  # every other status -> fail closed at the gateway (503 unavailable)
        if status != 200 or len(raw) > self._max_bytes:
            raise ValueError("malformed or oversized tenant startup response")
        body = json.loads(raw.decode("utf-8"))
        if not isinstance(body, dict) or set(body.keys()) != {"version", "record"}:
            raise ValueError("malformed tenant startup response envelope")
        version = body["version"]
        if isinstance(version, bool) or version != _ENVELOPE_VERSION:
            raise ValueError("unsupported tenant startup response version")
        record: Any = body["record"]
        if not isinstance(record, dict) or set(record.keys()) != set(_RECORD_KEYS):
            raise ValueError("malformed tenant startup record shape")
        record_ref = _checked_ref(record["record_ref"], "record_ref")
        if record_ref != startup_ref:
            # The record reference MUST be the reference the route addressed (IC-009 CLM);
            # a divergent echo is a protocol violation, never trusted.
            raise ValueError("tenant startup record reference mismatch")
        return TenantStartupDetailDTO(
            record_ref=record_ref,
            display_name=_checked_ref(record["display_name"], "display_name"),
            short_description=_checked_nullable(
                record["short_description"], "short_description", TENANT_STARTUP_SHORT_DESCRIPTION_MAX_CHARS
            ),
            investment_stage=_checked_nullable(record["investment_stage"], "investment_stage", _MAX_LABEL_CHARS),
            lineage_reference=_checked_nullable(record["lineage_reference"], "lineage_reference", _MAX_REF_BYTES),
        )
