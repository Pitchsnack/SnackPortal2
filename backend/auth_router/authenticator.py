"""Authenticator — orchestrates Stage 1 + Stage 2 and emits authentication audit.

Audits successful/failed authentication, tenant switch, carrier mismatch, and
membership/tenant-access failures. Never audits JWT contents, secrets, or credentials.
Internal (platform-issuer) and federated identities use the SAME flow (no special path).
"""
from __future__ import annotations

import base64
import json
from typing import Dict, Optional

from shared.audit import OperationalAudit, OperationalAuditEvent

from .jwt_validation import JwtValidator
from .models import AuthContext, AuthDenied, IssuerConfig, unauthenticated
from .tenant_context import TenantContextResolver


class Authenticator:
    def __init__(
        self,
        validator: JwtValidator,
        resolver: TenantContextResolver,
        audit: OperationalAudit,
        issuers: Dict[str, IssuerConfig],
    ) -> None:
        self._validator = validator
        self._resolver = resolver
        self._audit = audit
        self._issuers = issuers  # issuer string -> IssuerConfig (platform + federated)

    def authenticate(
        self,
        token: str,
        *,
        correlation_id: str,
        carrier_tenant: Optional[str] = None,
        previous_tenant: Optional[str] = None,
    ) -> AuthContext:
        issuer_cfg = self._issuer_for(token)
        if issuer_cfg is None:
            self._deny(correlation_id, None, None, "Authenticate", "unknown_issuer")
            raise unauthenticated("unknown_issuer")

        try:
            claims = self._validator.validate(token, issuer_cfg)
        except AuthDenied as exc:
            self._deny(correlation_id, None, None, "Authenticate", exc.public_code)
            raise

        try:
            ctx = self._resolver.resolve(claims, correlation_id=correlation_id, carrier_tenant=carrier_tenant)
        except AuthDenied as exc:
            action = "CarrierMismatch" if exc.public_code == "carrier_mismatch" else "TenantAccessDenied"
            self._deny(correlation_id, claims.subject, claims.tenant, action, exc.public_code)
            raise

        self._ok(correlation_id, ctx.principal_ref, ctx.active_tenant_id, "Authenticate")
        if previous_tenant and ctx.active_tenant_id and previous_tenant != ctx.active_tenant_id:
            self._ok(correlation_id, ctx.principal_ref, ctx.active_tenant_id, "TenantSwitch")
        return ctx

    def _issuer_for(self, token: str) -> Optional[IssuerConfig]:
        # Read the UNVERIFIED `iss` only to select the keyset; the signature and a
        # second `iss` equality check are enforced by the validator before trust.
        try:
            payload_b64 = token.split(".")[1]
            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)))
            return self._issuers.get(payload.get("iss"))
        except Exception:
            return None

    def _ok(self, cid: str, principal: Optional[str], tenant: Optional[str], action: str) -> None:
        self._audit.initiate(OperationalAuditEvent(
            actor_ref=principal or "<unknown>", action=action,
            correlation_id=cid, outcome="success", target_ref=tenant,
        ))

    def _deny(self, cid: str, principal: Optional[str], tenant: Optional[str], action: str, code: str) -> None:
        self._audit.initiate(OperationalAuditEvent(
            actor_ref=principal or "<unauthenticated>", action=action,
            correlation_id=cid, outcome="denied:" + code, target_ref=tenant,
        ))
