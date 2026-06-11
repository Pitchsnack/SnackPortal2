"""Production ControlPlaneRoutingReadPort over HTTP (stdlib urllib).

Transport-only access to the control-plane routing-read endpoint; NO in-process
import of control_plane (DAG rule). Not exercised by the stdlib unit suite (requires
a running control plane); the suite uses an in-memory routing-read double. Returns
None on 404 (consistent denial) and raises on transport failure so callers fail closed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from database_router.models import TenantRoutingView
from database_router.ports import ControlPlaneRoutingReadPort
from shared.secrets import SecretRef


class HttpRoutingRead(ControlPlaneRoutingReadPort):
    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def get_routing_view(self, tenant_id: str) -> Optional[TenantRoutingView]:
        path = "/internal/routing/tenants/" + urllib.parse.quote(tenant_id)
        req = urllib.request.Request(self._base + path, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # internal control-plane URL
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None  # unknown / unauthorized-to-know (consistent denial)
            raise  # other statuses -> fail closed
        ref = data["database_association_ref"]
        return TenantRoutingView(
            tenant_id=data["tenant_id"],
            lifecycle_state=data["lifecycle_state"],
            ready=bool(data["ready"]),
            database_association_ref=SecretRef(store_ref=ref["store_ref"], version=ref["version"]),
            expected_schema_version=data["expected_schema_version"],
        )
