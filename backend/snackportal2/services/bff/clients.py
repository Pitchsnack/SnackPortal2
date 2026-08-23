"""HTTP clients for the services the BFF orchestrates, and the fail-closed defaults.

Each client speaks to exactly one internal service over its published contract and maps the
response onto a BFF-local shape (``ports.py``). Nothing here imports another service's
implementation.

**Unconfigured means closed.** With no service URLs configured, the defaults deny: nobody
authenticates, nothing is authorized, no tenant resolves, no domain service answers, and audit
is dropped rather than silently believed. A BFF that starts without its dependencies is inert,
not permissive.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional

from ...shared.errors import AppError, ErrorCode, tenant_unavailable
from ...shared.operations import BffOperation
from ...shared.security import AuthContext, RequestContext
from ...shared.types import DatabaseDomain, PlatformRole
from .ports import AuthenticationResult, AuthorizationResult, CarrierVerdict, RoutedTenant

ENV_AUTHENTICATION_URL = "SP2_BFF_AUTHENTICATION_URL"
ENV_ACCESS_CONTROL_URL = "SP2_BFF_ACCESS_CONTROL_URL"
ENV_DATABASE_ROUTER_URL = "SP2_BFF_DATABASE_ROUTER_URL"
ENV_CONTROL_PLANE_URL = "SP2_BFF_CONTROL_PLANE_URL"
ENV_AUDIT_URL = "SP2_BFF_AUDIT_URL"
ENV_SERVICE_CREDENTIAL = "SP2_BFF_SERVICE_CREDENTIAL"
ENV_BASE_DOMAIN = "SP2_BFF_BASE_DOMAIN"

#: One URL per tenant-resident domain service the BFF orchestrates.
ENV_DOMAIN_URLS: Mapping[str, str] = {
    "startups": "SP2_BFF_STARTUPS_URL",
    "investors": "SP2_BFF_INVESTORS_URL",
    "deals": "SP2_BFF_DEALS_URL",
    "import_service": "SP2_BFF_IMPORT_SERVICE_URL",
    "lineage": "SP2_BFF_LINEAGE_URL",
    "sharing": "SP2_BFF_SHARING_URL",
    "contacts": "SP2_BFF_CONTACTS_URL",
}

TIMEOUT_SECONDS = 5.0


def _headers(credential: str) -> Dict[str, str]:
    return {"Authorization": "Bearer " + credential}


def _propagate(status_code: int, body: Mapping[str, Any]) -> AppError:
    """Re-raise a downstream canonical denial unchanged.

    Re-coding it here would let "not ready" quietly become "not found", and those are different
    facts about a tenant that a caller answers differently.
    """
    code = str(body.get("code", "tenant_unavailable"))
    try:
        return AppError(status_code, ErrorCode(code))
    except ValueError:
        return tenant_unavailable()


# --- Fail-closed defaults ---------------------------------------------------------------

class DenyAllAuthentication:
    """No Authentication Service configured, so no principal is ever established."""

    def authenticate(self, credential: str, carrier: Optional[str], correlation_id: str) -> Optional[AuthenticationResult]:
        del credential, carrier, correlation_id
        return None


class DenyAllAccessControl:
    """No Access Control Service configured, so every decision is Denied (IC-014 §8.2)."""

    def decide(
        self, context: RequestContext, operation: BffOperation, record_ref: Optional[str] = None
    ) -> AuthorizationResult:
        del context, operation, record_ref
        return AuthorizationResult(allowed=False, denial_code="access_denied", resolved_domain=None)


class UnavailableRouting:
    """No Database Router configured. Nothing resolves, and nothing falls back."""

    def resolve(self, context: RequestContext) -> RoutedTenant:
        del context
        raise tenant_unavailable()


class UnavailableControlRead:
    """No Control Plane configured. Control-resident reads answer with nothing."""

    def list_memberships(self, principal_ref: str) -> List[Dict[str, str]]:
        del principal_ref
        raise tenant_unavailable()

    def list_directory(self, directory: str) -> List[Dict[str, str]]:
        del directory
        raise tenant_unavailable()

    def get_directory_record(self, directory: str, record_ref: str) -> Optional[Dict[str, str]]:
        del directory, record_ref
        raise tenant_unavailable()


class UnavailableDomainService:
    """No URL configured for this domain service, so its operations are unavailable."""

    def call(self, path: str, payload: Dict[str, Any]) -> Any:
        del path, payload
        raise tenant_unavailable()


class DroppingAudit:
    """No Audit Service configured, so events are dropped — visibly, never silently.

    Dropping is the honest default. Buffering in memory and calling it audited produces a system
    that believes it has an audit trail it does not have, and that belief is worse than the
    missing trail.
    """

    def __init__(self) -> None:
        self.dropped = 0

    def emit(
        self,
        action: str,
        outcome: str,
        correlation_id: str,
        actor_ref: str,
        subject_ref: Optional[str] = None,
        tenant_ref: Optional[str] = None,
        record_ref: Optional[str] = None,
        carrier_ref: Optional[str] = None,
    ) -> None:
        del action, outcome, correlation_id, actor_ref, subject_ref, tenant_ref, record_ref, carrier_ref
        self.dropped += 1


# --- HTTP clients -------------------------------------------------------------------------

class HttpAuthentication:
    """Calls the Authentication Service (IC-005)."""

    def __init__(self, base_url: str, credential: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential

    def authenticate(self, credential: str, carrier: Optional[str], correlation_id: str) -> Optional[AuthenticationResult]:
        import httpx

        try:
            response = httpx.post(
                self._base_url + "/authenticate",
                headers=_headers(self._credential),
                json={"credential": credential, "tenant_carrier": carrier},
                timeout=TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                return None
            body = response.json()
            return AuthenticationResult(
                auth_context=AuthContext(
                    correlation_id=correlation_id,
                    principal_ref=body["principal_ref"],
                    role=PlatformRole(body["role"]),
                    active_tenant_ref=body.get("active_tenant_ref"),
                ),
                carrier_verdict=CarrierVerdict(body["carrier_check"]),
            )
        except Exception:
            return None


class HttpAccessControl:
    """Calls the Access Control Service (IC-014). Never evaluates a rule locally."""

    def __init__(self, base_url: str, credential: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential

    def decide(
        self, context: RequestContext, operation: BffOperation, record_ref: Optional[str] = None
    ) -> AuthorizationResult:
        import httpx

        try:
            response = httpx.post(
                self._base_url + "/decisions",
                headers=_headers(self._credential),
                json={
                    "context": context.model_dump(mode="json"),
                    "operation": operation.value,
                    "record_ref": record_ref,
                },
                timeout=TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                return AuthorizationResult(allowed=False, denial_code="access_denied", resolved_domain=None)
            body = response.json()
            if body.get("decision") != "allowed":
                return AuthorizationResult(allowed=False, denial_code=body.get("denial_code"), resolved_domain=None)
            domain = body.get("resolved_domain")
            return AuthorizationResult(
                allowed=True,
                denial_code=None,
                resolved_domain=DatabaseDomain(domain) if domain else None,
            )
        except Exception:
            # An unreachable authorizer is one of the named Denied conditions (IC-014 §8.2).
            return AuthorizationResult(allowed=False, denial_code="access_denied", resolved_domain=None)


class HttpTenantRouting:
    """Calls the Database Router's resolution surface. The BFF never chooses a database itself."""

    def __init__(self, base_url: str, credential: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential

    def resolve(self, context: RequestContext) -> RoutedTenant:
        import httpx

        try:
            response = httpx.post(
                self._base_url + "/internal/routing/resolve",
                headers=_headers(self._credential),
                json={"context": context.model_dump(mode="json")},
                timeout=TIMEOUT_SECONDS,
            )
        except Exception:
            raise tenant_unavailable() from None
        if response.status_code >= 400:
            raise _propagate(response.status_code, response.json() if response.content else {})
        body = response.json()
        return RoutedTenant(tenant_ref=str(body["tenant_ref"]), target_ref=str(body["target_ref"]))


class HttpControlRead:
    """Reads Control-resident data: memberships and the global directories."""

    def __init__(self, base_url: str, credential: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential

    def _get(self, path: str) -> Any:
        import httpx

        try:
            response = httpx.get(self._base_url + path, headers=_headers(self._credential), timeout=TIMEOUT_SECONDS)
        except Exception:
            raise tenant_unavailable() from None
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise _propagate(response.status_code, response.json() if response.content else {})
        return response.json()

    def list_memberships(self, principal_ref: str) -> List[Dict[str, str]]:
        body = self._get("/internal/memberships/" + principal_ref)
        if body is None:
            return []
        return [dict(entry) for entry in body.get("memberships", [])]

    def list_directory(self, directory: str) -> List[Dict[str, str]]:
        body = self._get("/internal/directories/" + directory + "/records")
        if body is None:
            return []
        return [dict(entry) for entry in body.get("records", [])]

    def get_directory_record(self, directory: str, record_ref: str) -> Optional[Dict[str, str]]:
        body = self._get("/internal/directories/" + directory + "/records/" + record_ref)
        if body is None:
            return None
        return {str(key): str(value) for key, value in body.items() if not isinstance(value, dict)}


class HttpDomainService:
    """Invokes one operation on one tenant-resident domain service."""

    def __init__(self, base_url: str, credential: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential

    def call(self, path: str, payload: Dict[str, Any]) -> Any:
        import httpx

        try:
            response = httpx.post(
                self._base_url + path, headers=_headers(self._credential), json=payload, timeout=TIMEOUT_SECONDS
            )
        except Exception:
            raise tenant_unavailable() from None
        if response.status_code >= 400:
            raise _propagate(response.status_code, response.json() if response.content else {})
        return response.json()


class HttpAudit:
    """Emits ingress-edge audit to the Audit Service. The BFF is the sole emitter."""

    def __init__(self, base_url: str, credential: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential

    def emit(
        self,
        action: str,
        outcome: str,
        correlation_id: str,
        actor_ref: str,
        subject_ref: Optional[str] = None,
        tenant_ref: Optional[str] = None,
        record_ref: Optional[str] = None,
        carrier_ref: Optional[str] = None,
    ) -> None:
        import httpx

        try:
            httpx.post(
                self._base_url + "/audit/events",
                headers=_headers(self._credential),
                json={
                    "action": action,
                    "outcome": outcome,
                    "correlation_id": correlation_id,
                    "actor_ref": actor_ref,
                    "subject_ref": subject_ref,
                    "tenant_ref": tenant_ref,
                    "record_ref": record_ref,
                    "carrier_ref": carrier_ref,
                },
                timeout=TIMEOUT_SECONDS,
            )
        except Exception:
            # An audit failure must not convert a correct denial into a served request. The
            # denial still stands; the lost event is a monitoring concern, not a reason to let
            # the request through.
            return


def build_components(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Compose the BFF's dependencies from configuration, fail-closed by omission."""
    source: Mapping[str, str] = os.environ if env is None else env
    credential = source.get(ENV_SERVICE_CREDENTIAL, "").strip()

    def url(name: str) -> str:
        value = source.get(name, "").strip()
        return value if value.startswith(("http://", "https://")) and credential else ""

    auth_url = url(ENV_AUTHENTICATION_URL)
    ac_url = url(ENV_ACCESS_CONTROL_URL)
    router_url = url(ENV_DATABASE_ROUTER_URL)
    cp_url = url(ENV_CONTROL_PLANE_URL)
    audit_url = url(ENV_AUDIT_URL)

    domains: Dict[str, Any] = {}
    for service_key, variable in ENV_DOMAIN_URLS.items():
        service_url = url(variable)
        domains[service_key] = HttpDomainService(service_url, credential) if service_url else UnavailableDomainService()

    return {
        "authentication": HttpAuthentication(auth_url, credential) if auth_url else DenyAllAuthentication(),
        "access_control": HttpAccessControl(ac_url, credential) if ac_url else DenyAllAccessControl(),
        "routing": HttpTenantRouting(router_url, credential) if router_url else UnavailableRouting(),
        "control_read": HttpControlRead(cp_url, credential) if cp_url else UnavailableControlRead(),
        "audit": HttpAudit(audit_url, credential) if audit_url else DroppingAudit(),
        "domains": domains,
        "base_domain": source.get(ENV_BASE_DOMAIN, "").strip(),
    }


__all__ = [
    "ENV_ACCESS_CONTROL_URL",
    "ENV_AUDIT_URL",
    "ENV_AUTHENTICATION_URL",
    "ENV_BASE_DOMAIN",
    "ENV_CONTROL_PLANE_URL",
    "ENV_DATABASE_ROUTER_URL",
    "ENV_DOMAIN_URLS",
    "ENV_SERVICE_CREDENTIAL",
    "DenyAllAccessControl",
    "DenyAllAuthentication",
    "DroppingAudit",
    "HttpAccessControl",
    "HttpAudit",
    "HttpAuthentication",
    "HttpControlRead",
    "HttpDomainService",
    "HttpTenantRouting",
    "UnavailableControlRead",
    "UnavailableDomainService",
    "UnavailableRouting",
    "build_components",
]
