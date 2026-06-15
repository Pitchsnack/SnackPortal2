"""PostgreSQL provisioning operator (D15-ARCH-SPEC-01 §8 Step 2; WP-1/WP-2; D-15).

Control-plane-owned operator that provisions a physically distinct tenant database by
CREATE DATABASE against an admin connection. CONTROLLED NON-PRODUCTION ONLY — intended for
throwaway verification databases; production rollout / live tenant onboarding remain out of
scope (PRD-D15-IMPL-01 §8.3, §22.5).

The driver import is confined to this provider zone. Target names are validated as plain
identifiers before being quoted (no injection surface). The admin descriptor is supplied by
the composition root; no credential is logged or returned.
"""

from __future__ import annotations

import re

import psycopg  # type: ignore  # noqa: F401  (driver import confined to this zone)

from control_plane.provisioning import ProvisioningError, ProvisioningOperator, ProvisionResult

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


class PostgresProvisioningOperator(ProvisioningOperator):
    def __init__(self, admin_dsn: str, *, timeout: float = 5.0) -> None:
        self._dsn = admin_dsn
        self._timeout = timeout

    def provision(self, tenant_id: str, *, target: str) -> ProvisionResult:
        self._guard(target)
        conn = psycopg.connect(self._dsn, connect_timeout=int(self._timeout), autocommit=True)
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
        conn = psycopg.connect(self._dsn, connect_timeout=int(self._timeout), autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{target}"')  # target validated by _guard
        finally:
            conn.close()

    @staticmethod
    def _guard(target: str) -> None:
        if not _SAFE_IDENTIFIER.match(target):
            raise ProvisioningError("unsafe provisioning target identifier")
