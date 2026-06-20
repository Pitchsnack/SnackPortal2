"""RequestContext construction — EXCLUSIVELY from AuthContext (IC-010 §G/§T; D-33 §4.6).

The gateway builds the canonical ``shared.context.RequestContext`` from the
Authenticator's output ONLY. ``active_tenant_id`` is the signed active-tenant claim;
NO inbound tenant/workspace parameter (a carrier beyond the match check, header, cookie,
query, host, body, or workspace value) may set it or reach the router. The context
carries references only — never a token/secret. This realizes IC-010 §W / D-33 §10
criterion 6 (load-bearing).
"""

from __future__ import annotations

from shared.context import RequestContext

from .models import AuthResult


def build_request_context(auth: AuthResult) -> RequestContext:
    """Construct the router-handoff context from AuthResult fields ONLY (no request input).

    Note: ``workspace_type`` is a presentation-layer label (IC-010 §F) and is deliberately
    NOT a field of the router-input RequestContext — it is never a routing selector.
    """
    return RequestContext(
        correlation_id=auth.correlation_id,
        request_id=auth.correlation_id,
        active_tenant_id=auth.active_tenant_id,
        principal_ref=auth.principal_ref,
        role=auth.role,
    )
