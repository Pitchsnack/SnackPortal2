"""Endpoint dispatch taxonomy + isolation (IC-010 §X/§Q/§K).

Dispatch is by request path/operation ONLY (consumes no tenant/workspace/ownership
selector — IC-010 §X; the route is never a client-controlled routing channel). Each
request resolves to EXACTLY ONE §Q category → one DatabaseDomain → one database
(§K/§O). A MASTER_AGENT multi-membership fan-out is structurally impossible: there is
one signed active tenant and no API to address a second (IC-009 P.4). Import Initiation
is a single Tenant-DB write (IR-09), never a Control-read-joined-to-tenant-write straddle.
"""

from __future__ import annotations

from shared.context import RequestContext

from .models import DatabaseDomain, DispatchCategory, DispatchDecision, InboundRequest

_CONTROL_CATEGORIES = (DispatchCategory.GLOBAL_DIRECTORY_READ, DispatchCategory.MEMBERSHIPS_FOR_PRINCIPAL)


class DispatchError(Exception):
    """A dispatch/isolation breach. ``isolation_anomaly`` marks a §K straddle attempt."""

    def __init__(self, public_code: str, *, isolation_anomaly: bool = False) -> None:
        super().__init__(public_code)
        self.public_code = public_code
        self.isolation_anomaly = isolation_anomaly


def category_domain(category: DispatchCategory) -> DatabaseDomain:
    """The single DatabaseDomain a §Q category resolves to (CONTROL or TENANT — never both)."""
    if category in _CONTROL_CATEGORIES:
        return DatabaseDomain.CONTROL
    return DatabaseDomain.TENANT


def default_classifier(request: InboundRequest) -> DispatchCategory:
    """Classify a request into one §Q category by PATH/OPERATION ONLY (IC-010 §X).

    Consumes no header/carrier/cookie/query/workspace value — the dispatch decision never
    varies with a client-supplied tenant/workspace/ownership value. An unknown route is a
    fail-closed denial.
    """
    path = request.path
    if path == "/tenant" or path.startswith("/tenant/"):
        return DispatchCategory.TENANT_OPERATION
    if path == "/directory" or path.startswith("/directory/"):
        return DispatchCategory.GLOBAL_DIRECTORY_READ
    if path == "/memberships" or path.startswith("/memberships/"):
        return DispatchCategory.MEMBERSHIPS_FOR_PRINCIPAL
    if path == "/import" or path.startswith("/import/"):
        return DispatchCategory.IMPORT_INITIATION
    raise DispatchError("unknown_route")


def decide(category: DispatchCategory, context: RequestContext) -> DispatchDecision:
    """Resolve the single dispatch decision; enforce one request → one category → one DB.

    A TENANT-domain category binds to the single signed active tenant; a CONTROL category
    must not target a tenant. A tenant operation under a tenantless (control-scope) claim
    is a fail-closed denial — not a straddle.
    """
    domain = category_domain(category)
    if domain is DatabaseDomain.TENANT:
        if context.active_tenant_id is None:
            raise DispatchError("tenant_context_required")
        return DispatchDecision(category=category, domain=domain, target_tenant_id=context.active_tenant_id)
    return DispatchDecision(category=category, domain=domain, target_tenant_id=None)


def assert_single_database(decision: DispatchDecision) -> None:
    """IC-010 §K/§O: the decision targets the Control DB OR exactly one tenant DB — never
    both/none. A violation is an IsolationAnomaly (defensive; ``decide`` never yields one)."""
    if decision.domain is DatabaseDomain.TENANT and decision.target_tenant_id is None:
        raise DispatchError("isolation_anomaly", isolation_anomaly=True)
    if decision.domain is DatabaseDomain.CONTROL and decision.target_tenant_id is not None:
        raise DispatchError("isolation_anomaly", isolation_anomaly=True)
