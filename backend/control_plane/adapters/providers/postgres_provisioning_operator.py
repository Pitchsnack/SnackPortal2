"""PostgreSQL provisioning operator (D15-ARCH-SPEC-01 §8 Step 2; WP-1/WP-2; D-15; PRD 07D-1).

Control-plane-owned operator that provisions a physically distinct tenant database by
CREATE DATABASE against an admin connection. CONTROLLED NON-PRODUCTION ONLY — intended for
throwaway verification databases; production rollout remains out of scope (PRD-D15-IMPL-01
§8.3, §22.5).

The driver import is confined to this provider zone. Target names are validated as plain
identifiers before being quoted (no injection surface). No credential is logged or returned.

Dual construction (PRD 07D-1; references only, D-14 — the PostgresControlStore precedent): pass a
literal ``admin_dsn=`` connection descriptor (the requires_pg harness path, unchanged) OR
``secrets=`` + ``ref=`` to resolve the admin descriptor from a ``SecretStore`` by reference —
``control/provisioning-admin-dsn`` in the composition root — so no DSN literal transits the
composition root. Construction performs NO I/O and resolves NO secret (lazy); each operation
resolves the descriptor in-memory, connects short-lived, and drops it (never retained). A
missing/unresolvable reference fails closed on the operation (PermissionError / LookupError
propagate; the onboarding orchestrator maps a failed provision to not-Ready).
"""

from __future__ import annotations

import re
from typing import Any, Optional

import psycopg  # type: ignore  # noqa: F401  (driver import confined to this zone)

from control_plane.provisioning import ProvisioningError, ProvisioningOperator, ProvisionResult
from shared.secrets import SecretRef, SecretStore

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


class PostgresProvisioningOperator(ProvisioningOperator):
    def __init__(
        self,
        admin_dsn: Optional[str] = None,
        *,
        secrets: Optional[SecretStore] = None,
        ref: Optional[SecretRef] = None,
        timeout: float = 5.0,
    ) -> None:
        # Lazy: record inputs only; no connection, no secret resolution here (07D-1). Exactly one
        # admin-descriptor source is required — a literal admin_dsn= OR a reference (secrets=, ref=).
        if (admin_dsn is None) == (ref is None):
            raise ValueError("PostgresProvisioningOperator requires exactly one of admin_dsn= or (secrets=, ref=)")
        if ref is not None and secrets is None:
            raise ValueError("PostgresProvisioningOperator ref= requires a SecretStore (secrets=)")
        self._dsn = admin_dsn
        self._secrets = secrets
        self._ref = ref
        self._timeout = timeout

    def _connect(self) -> Any:
        """Resolve the admin descriptor (by reference or literal) and open a short-lived connection.

        Fail-closed: PermissionError (ref not allow-listed), LookupError (unresolved ref), and
        connect errors all propagate — the operation is rejected. The resolved descriptor is
        dropped immediately and never retained on the adapter (D-14)."""
        descriptor: Optional[str] = None
        try:
            if self._ref is not None:
                assert self._secrets is not None  # guaranteed by __init__
                descriptor = self._secrets.resolve(self._ref).material  # in-memory only
            else:
                assert self._dsn is not None  # guaranteed by __init__ (exactly one source)
                descriptor = self._dsn
            return psycopg.connect(descriptor, connect_timeout=int(self._timeout), autocommit=True)
        finally:
            descriptor = None  # never retained on the adapter

    def provision(self, tenant_id: str, *, target: str) -> ProvisionResult:
        self._guard(target)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,))
                if cur.fetchone():
                    return ProvisionResult(target=target, created=False)
                cur.execute(f'CREATE DATABASE "{target}"')  # target validated by _guard
                return ProvisionResult(target=target, created=True)
        finally:
            conn.close()

    def deprovision(self, *, target: str) -> None:
        self._guard(target)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{target}"')  # target validated by _guard
        finally:
            conn.close()

    @staticmethod
    def _guard(target: str) -> None:
        # fullmatch, not match (PRD 07D-2b.2b D-5): with `.match` Python's `$` also matches
        # before ONE trailing newline, so a newline-tailed target would slip past the guard
        # into the quoted CREATE/DROP DATABASE statements. The guard is SHARED by provision()
        # AND deprovision() — defence in depth under the first governed DROP DATABASE caller.
        if not _SAFE_IDENTIFIER.fullmatch(target):
            raise ProvisioningError("unsafe provisioning target identifier")
