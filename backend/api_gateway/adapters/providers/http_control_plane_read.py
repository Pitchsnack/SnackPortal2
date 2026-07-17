"""Production ``ControlPlaneReadPort`` over internal HTTP (stdlib urllib) — B5-BLK-6B.

The gateway side of the IC-010 §V typed Control-Plane read seam: a transport CLIENT to
the Control Plane's internal read edge — reached over transport ONLY, never an in-process
import of ``control_plane`` (IC-010 §M; DAG independence). Typed parsing lives HERE: the
raw provider body never crosses the port — the gateway consumes only the IC-009-R1 portal
DTOs (``api_gateway/portal.py``), composed from validated fields.

Denial mapping mirrors the merged auth_router read client (B5-3 LW-1): a live HTTP 404
maps to ``None`` (consistent denial — the gateway maps it to the existing 403), and EVERY
other failure — timeout, connection refusal, oversized, malformed, wrong-shape — raises,
so the gateway collapses it fail-closed to 503 ``unavailable`` (IC-010 §L; no new
``public_code``; no error path downgrades or surfaces internal detail). Lazy construction
(no network I/O until a call); bounded timeout; bounded response size; single attempt (no
retry loop); stdlib urllib only — no vendor SDK, no secret-bearing configuration (the
base URL is non-secret internal routing config).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, List, Optional, Union

from api_gateway.portal import (
    DirectoryEntryDTO,
    GlobalInvestorSummaryDTO,
    GlobalStartupSummaryDTO,
    MembershipEntryDTO,
    WorkspaceMembershipDTO,
    compose_display_ref,
)
from api_gateway.ports import ControlPlaneReadPort

# The two approved directory kinds (IC-009 §C; V2 §3.3 carve-out — startup and investor
# ONLY; live DirectoryKind has no DEAL member). An unapproved kind resolves to None with
# no wire call — the same consistent denial an unknown kind earns from the live edge.
_APPROVED_KINDS = frozenset({"startup", "investor"})


class HttpControlPlaneRead(ControlPlaneReadPort):
    def __init__(self, base_url: str, timeout: float = 2.0, max_response_bytes: int = 256 * 1024) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._max_bytes = max_response_bytes

    def directory(self, kind: str) -> Optional[Union[GlobalStartupSummaryDTO, GlobalInvestorSummaryDTO]]:
        if kind not in _APPROVED_KINDS:
            return None  # unknown/unapproved kind -> consistent denial (no wire call)
        data = self._get("/directory/" + urllib.parse.quote(kind))
        if data is None:
            return None  # live 404 -> consistent denial (LW-1)
        raw_records = data.get("records")
        if not isinstance(raw_records, list):
            raise ValueError("malformed control-plane directory result")
        entries: List[DirectoryEntryDTO] = []
        for item in raw_records:  # Control-Plane order preserved — the gateway never re-sorts
            if not isinstance(item, dict):
                raise ValueError("malformed control-plane directory record")
            record_id = item.get("record_id")
            display_name = item.get("display_name")
            if not isinstance(record_id, str) or not isinstance(display_name, str):
                raise ValueError("malformed control-plane directory record")
            entries.append(DirectoryEntryDTO(record_ref=record_id, display_name=display_name))
        if kind == "startup":
            return GlobalStartupSummaryDTO(records=tuple(entries))
        return GlobalInvestorSummaryDTO(records=tuple(entries))

    def memberships_for_principal(self, principal_ref: str) -> Optional[WorkspaceMembershipDTO]:
        data = self._get("/memberships?p=" + urllib.parse.quote(principal_ref))
        if data is None:
            return None  # read edge absent/unroutable for the path -> consistent denial
        raw_memberships = data.get("memberships")
        if not isinstance(raw_memberships, list):
            raise ValueError("malformed control-plane memberships result")
        entries: List[MembershipEntryDTO] = []
        for item in raw_memberships:
            if not isinstance(item, dict) or set(item.keys()) != {"tenant_id", "role"}:
                raise ValueError("malformed control-plane membership record")
            tenant_id = item["tenant_id"]
            role = item["role"]
            if not isinstance(tenant_id, str) or not isinstance(role, str):
                raise ValueError("malformed control-plane membership record")
            # display_ref is GATEWAY-COMPOSED (derived, never stored; no DDL): the Control
            # Plane returns exactly the {tenant_id, role} reference pair and nothing else.
            entries.append(MembershipEntryDTO(tenant_id=tenant_id, role=role, display_ref=compose_display_ref(tenant_id)))
        return WorkspaceMembershipDTO(memberships=tuple(entries))

    def _get(self, path: str) -> Optional[dict[str, Any]]:
        request = urllib.request.Request(self._base + path, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:  # internal control-plane URL
                raw = resp.read(self._max_bytes + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None  # unknown / not found (consistent denial — LW-1)
            raise  # every other status -> fail closed at the gateway (503 unavailable)
        if len(raw) > self._max_bytes:
            raise ValueError("oversized control-plane response")  # bounded response size
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("malformed control-plane response")
        return payload
