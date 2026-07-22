"""CLM tenant Startup bounded read/update executor (D-42 Stage B; IC-010 CLM section).

The Database-Router-side data half of the CLM tenant Startup seam: given references only
(the signed active tenant, the opaque ``<startup_ref>``), it opens EXACTLY ONE routed
tenant session (registry-authoritative routing, readiness + schema gating, per-tenant
credential by reference — ``RoutedSessionProvider``; D-07: the Database Router alone
resolves the physical database) and executes the bounded read or the bounded single-field
update there. One request → one tenant → one physical tenant database (IC-010 §K/§O).

Bounded by construction (IC-010 CLM): the read projects the five bounded record fields;
the update writes the SOLE CLM-mutable field ``short_description`` (a UTF-8 string of at
most 500 characters, or None to clear) through the session's tabular vocabulary inside one
caller-owned transaction — validation precedes any write and a failed transaction rolls
back, so there is NO partial write. ``lineage_reference`` resolves from the tenant-resident
lineage chain (IC-004): the latest lineage row addressing the record, or None when the
record was never imported. No create, no delete, no sharing, no media, no general edit
capability exists here.

References + the two bounded nullable content fields only: no DSN, credential, secret,
pool internals, or physical database identity ever leaves this module. Driver-free by
placement (vendor containment): tenant data is reached ONLY through the injected
``RoutedSessionProvider`` port — this module imports no database driver.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from shared.session import Lane, RoutedSessionProvider, RoutedTenantSession

# The tenant business table + reference column (the W1a import target shape: startups are
# keyed by the tenant-resident global_startup_id soft reference — tenant DDL 003/008).
_STARTUPS_TABLE = "startups"
_REF_COLUMN = "global_startup_id"
_LINEAGE_TABLE = "lineage"

# IC-010 CLM bounds (defense-in-depth: the gateway validated these fail-closed already).
_MAX_REF_BYTES = 512
_MAX_SHORT_DESCRIPTION_CHARS = 500


@dataclass(frozen=True)
class TenantStartupRecord:
    """The references + bounded-content projection of one tenant-resident Startup row.

    Exactly the five wire fields of the CLM record (the D-37 §10 provenance triple is
    composed gateway-side and never crosses the internal wire). Never a raw row, tenant
    business payload beyond these fields, PII, secret, or database identity.
    """

    record_ref: str
    display_name: str
    short_description: Optional[str]
    investment_stage: Optional[str]
    lineage_reference: Optional[str]


def _checked_ref(value: str, field: str) -> str:
    if not value or len(value.encode("utf-8")) > _MAX_REF_BYTES:
        raise ValueError(f"tenant startup {field} must be a bounded non-empty reference")
    return value


class TenantStartupOperations:
    """The bounded CLM executor over ONE routed tenant session per operation."""

    def __init__(self, provider: RoutedSessionProvider) -> None:
        self._provider = provider

    def read(self, *, tenant_ref: str, startup_ref: str, correlation_id: str, actor_ref: str) -> Optional[TenantStartupRecord]:
        """One bounded tenant Startup read. ``None`` = unknown ``startup_ref`` within the
        bound tenant database (the consistent IC-002 not-found semantic — no existence
        detail beyond the caller's own tenant is ever derivable here)."""
        _checked_ref(tenant_ref, "tenant_ref")
        _checked_ref(startup_ref, "startup_ref")
        session = self._provider.open_session(
            tenant_id=tenant_ref, correlation_id=correlation_id, principal_ref=actor_ref, lane=Lane.INTERACTIVE
        )
        try:
            session.begin()
            row = session.get(_STARTUPS_TABLE, {_REF_COLUMN: startup_ref})
            lineage_ref = self._lineage_reference(session, tenant_ref, startup_ref) if row is not None else None
            session.commit()
        except Exception:
            self._abandon(session)
            raise
        finally:
            session.close()
        if row is None:
            return None
        return self._record(startup_ref, row, lineage_ref)

    def update(
        self,
        *,
        tenant_ref: str,
        startup_ref: str,
        short_description: Optional[str],
        correlation_id: str,
        actor_ref: str,
    ) -> Optional[TenantStartupRecord]:
        """The bounded single-field update (IC-010 CLM): write ``short_description`` — the
        sole CLM-mutable field — atomically, re-read within the same transaction as the
        persistence witness, and commit; any failure rolls the transaction back (NO partial
        write). ``None`` = unknown ``startup_ref`` (nothing was written)."""
        _checked_ref(tenant_ref, "tenant_ref")
        _checked_ref(startup_ref, "startup_ref")
        if short_description is not None and len(short_description) > _MAX_SHORT_DESCRIPTION_CHARS:
            raise ValueError("short_description exceeds the 500-character bound")
        session = self._provider.open_session(
            tenant_id=tenant_ref, correlation_id=correlation_id, principal_ref=actor_ref, lane=Lane.INTERACTIVE
        )
        try:
            session.begin()
            existing = session.get(_STARTUPS_TABLE, {_REF_COLUMN: startup_ref})
            if existing is None:
                # Unknown record: end the transaction WITHOUT writing anything.
                session.rollback()
                return None
            # Exactly the one allowlisted column via the narrow bounded UPDATE verb (CLM
            # D-42): a WHERE-keyed SET of short_description ONLY — no other column is
            # touched. The existence check above guarantees a matching row, and the
            # single-statement write inside this one transaction admits no partial state.
            session.update(_STARTUPS_TABLE, {_REF_COLUMN: startup_ref}, {"short_description": short_description})
            reread = session.get(_STARTUPS_TABLE, {_REF_COLUMN: startup_ref})
            if reread is None or reread.get("short_description") != short_description:
                raise ValueError("tenant startup update persistence witness failed")
            lineage_ref = self._lineage_reference(session, tenant_ref, startup_ref)
            session.commit()
        except Exception:
            self._abandon(session)
            raise
        finally:
            session.close()
        return self._record(startup_ref, reread, lineage_ref)

    @staticmethod
    def _lineage_reference(session: RoutedTenantSession, tenant_ref: str, startup_ref: str) -> Optional[str]:
        # IC-004: the latest tenant-resident lineage row addressing this record (the W1a
        # target shape `<tenant>:startups:<ref>`), or None when the record was never
        # imported. A reference only — never chain material or payload.
        target_ref = f"{tenant_ref}:{_STARTUPS_TABLE}:{startup_ref}"
        row = session.latest(_LINEAGE_TABLE, {"target_ref": target_ref}, "seq")
        if row is None:
            return None
        lineage_id = row.get("lineage_id")
        return lineage_id if isinstance(lineage_id, str) and lineage_id else None

    @staticmethod
    def _abandon(session: RoutedTenantSession) -> None:
        # Fail-closed transaction abandonment: NO partial write may survive an error.
        try:
            session.rollback()
        except Exception:
            pass  # the original error is the signal; close() still returns the connection

    @staticmethod
    def _record(startup_ref: str, row: Dict[str, Any], lineage_ref: Optional[str]) -> TenantStartupRecord:
        display_name = row.get("company_name")
        if not isinstance(display_name, str) or not display_name:
            raise ValueError("tenant startup row carries no display name")
        short_description = row.get("short_description")
        investment_stage = row.get("investment_stage")
        return TenantStartupRecord(
            record_ref=startup_ref,
            display_name=display_name,
            short_description=short_description if isinstance(short_description, str) else None,
            investment_stage=investment_stage if isinstance(investment_stage, str) else None,
            lineage_reference=lineage_ref,
        )
