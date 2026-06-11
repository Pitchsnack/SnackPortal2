"""Production ControlPlaneReadPort over HTTP (stdlib urllib) — Control Plane Read API.

Transport-only access to Phase-2 control-plane data; NO in-process import of
control_plane (DAG rule 2). Not exercised by the stdlib unit suite (requires a running
control plane); the test suite uses an in-memory read double.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Optional

from auth_router.models import FederationView, Role, TenantStateView
from auth_router.ports import ControlPlaneReadPort


class HttpControlPlaneRead(ControlPlaneReadPort):
    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _get(self, path: str) -> Optional[dict]:
        req = urllib.request.Request(self._base + path, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # internal control-plane URL
            if getattr(resp, "status", 200) == 404:
                return None
            return json.loads(resp.read().decode("utf-8"))

    def get_federation_for_issuer(self, issuer: str) -> Optional[FederationView]:
        data = self._get("/federation?issuer=" + urllib.parse.quote(issuer))
        return FederationView(**data) if data else None

    def get_tenant_state(self, tenant_id: str) -> Optional[TenantStateView]:
        data = self._get("/tenants/" + urllib.parse.quote(tenant_id) + "/state")
        return TenantStateView(**data) if data else None

    def is_member(self, principal_ref: str, tenant_id: str) -> bool:
        data = self._get("/membership?p=" + urllib.parse.quote(principal_ref) + "&t=" + urllib.parse.quote(tenant_id))
        return bool(data and data.get("member"))

    def get_role(self, principal_ref: str, tenant_id: str) -> Optional[Role]:
        data = self._get("/role?p=" + urllib.parse.quote(principal_ref) + "&t=" + urllib.parse.quote(tenant_id))
        if not data or not data.get("role"):
            return None
        return Role(data["role"])
