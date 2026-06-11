"""Schema compatibility framework — Control-DB schema (D-12).

Detect-only: never migrates, never modifies schema. Out-of-range or migration-pending
fails safe to global not-ready. Tenant schema checks are out of scope (Build Phase 4,
D-17).
"""
from __future__ import annotations

from typing import Optional

from shared.health import GlobalReadiness

from .records import SchemaCompatState


class SchemaCompatibilityChecker:
    def __init__(self, supported_min: int, supported_max: int) -> None:
        self._min = supported_min
        self._max = supported_max

    def check(self, observed_version: Optional[int], *, migration_pending: bool = False) -> SchemaCompatState:
        if observed_version is None:
            return SchemaCompatState.FAIL  # could not determine the schema version
        if migration_pending:
            return SchemaCompatState.MIGRATION_REQUIRED  # detect only — never auto-migrate (D-12)
        if observed_version < self._min or observed_version > self._max:
            return SchemaCompatState.VERSION_MISMATCH
        return SchemaCompatState.PASS

    @staticmethod
    def to_readiness(state: SchemaCompatState) -> GlobalReadiness:
        return GlobalReadiness.READY if state is SchemaCompatState.PASS else GlobalReadiness.NOT_READY
