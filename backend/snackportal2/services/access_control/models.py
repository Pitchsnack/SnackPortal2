"""Access Control Service wire models (IC-014 §4).

Every field is a reference, a code, or an enumeration — never a payload. The decision
inputs are exhaustive and closed: a cookie, a query-string parameter, portal state, a
workspace label, a body field claiming identity or tenancy, a database identifier, a DSN,
a token, or tenant business data has nowhere to go in these shapes, which is the cheapest
possible enforcement of "prohibited as a decision input".
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ...shared.errors import ErrorCode
from ...shared.operations import BffOperation
from ...shared.security import RequestContext
from ...shared.types import DatabaseDomain
from .policy import Decision


class AccessDecisionRequest(BaseModel):
    """Ask whether one principal may perform one enumerated operation."""

    context: RequestContext = Field(
        description="The canonical RequestContext, built by the BFF exclusively from AuthContext (IC-013 §7)."
    )
    operation: BffOperation = Field(
        description="The enumerated BFF operation being attempted. An operation outside the surface is denied."
    )
    record_ref: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Opaque reference to the target record, where the operation names one. Never field content.",
    )
    owner_agent_ref: Optional[str] = Field(
        default=None,
        max_length=256,
        description="The record's single human owner reference (IC-008). An input only; ownership never grants.",
    )
    owner_ai_agent_ref: Optional[str] = Field(
        default=None,
        max_length=256,
        description="The record's single current AI owner reference. MUST be null pre-IC-006; populated is an error, never a grant.",
    )


class AccessDecisionResponse(BaseModel):
    """Allowed or Denied, and nothing that would disclose why."""

    decision: Decision = Field(description="The authorization result. Exactly two values exist; there is no third.")
    denial_code: Optional[ErrorCode] = Field(
        default=None,
        description="Canonical public denial code when denied, null when allowed. Never a reason, rule, or internal detail.",
    )
    resolved_domain: Optional[DatabaseDomain] = Field(
        default=None,
        description="The single lawful database domain when allowed, null when denied. Never a database name or DSN.",
    )


__all__ = ["AccessDecisionRequest", "AccessDecisionResponse"]
