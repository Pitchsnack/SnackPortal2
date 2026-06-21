"""Durable Distinctness Ledger — live-PostgreSQL exercise (standalone-only; SNACKPORTAL_TEST_DSN).

The B-4 live exercise for the PRD 06 B-2 durable ledger: against a real Control database it
applies the additive ledger DDL (infrastructure/db/control/001_distinctness_ledger.sql), then
proves the durable `PostgresDistinctnessLedger` record_evidence / evidence_excluding / remove
behave as the gate requires — latest-per-tenant upsert, inventory-minus-self, drop — and
reconstruct reference-only `DistinctnessEvidence` faithfully. Applies and drops a throwaway
ledger table (controlled non-production only); the database driver stays confined to the adapter
(no `psycopg` import here — Driver Containment Standard).

This file is IGNORED by the default test run (pyproject `addopts --ignore=tests/control_plane/
requires_pg`); B-2 runs no live PostgreSQL. Run it in B-4:
set SNACKPORTAL_TEST_DSN to an admin DSN for a non-production Control database, then
`python tests/control_plane/requires_pg/test_pg_distinctness_ledger.py`.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import replace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

from control_plane.adapters.providers.postgres_distinctness_ledger import PostgresDistinctnessLedger  # noqa: E402
from control_plane.distinctness import DistinctnessEvidence  # noqa: E402
from shared.secrets import SecretRef, SecretStore, SecretValue  # noqa: E402

_DDL = pathlib.Path(__file__).resolve().parents[4] / "infrastructure" / "db" / "control" / "001_distinctness_ledger.sql"
_CONTROL_REF = SecretRef(store_ref="control_secret", version="1")


class MapSecretStore(SecretStore):
    """Maps a secret reference store_ref directly to a DSN (test-only)."""

    def __init__(self, mapping: dict) -> None:
        self._m = mapping

    def resolve(self, ref: SecretRef) -> SecretValue:
        return SecretValue(self._m[ref.store_ref])

    def current_version(self, store_ref: str) -> str:
        return "1"


def _evidence(tenant_id: str) -> DistinctnessEvidence:
    return DistinctnessEvidence(
        system_identifier="sp2_nonprod_control_cluster",
        database_identity=f"{tenant_id}:42",
        observed_target=f"sp2_tenant_{tenant_id}",
        secret_ref_key=f"sp2_tenant_{tenant_id}",
        sentinel_namespace=f"dv_sentinel_{tenant_id}",
        sentinel_token=f"tok_{tenant_id}",
        sentinel_written=True,
    )


def _exec(ledger: PostgresDistinctnessLedger, statement: str) -> None:
    conn = ledger._connect()  # driver confined to the adapter
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
        conn.commit()
    finally:
        conn.close()


def test_durable_ledger_roundtrip(admin_dsn: str) -> None:
    secrets = MapSecretStore({"control_secret": admin_dsn})
    ledger = PostgresDistinctnessLedger(secrets, _CONTROL_REF)
    _exec(ledger, _DDL.read_text(encoding="utf-8"))  # apply the additive DDL (B-4 only)
    try:
        _exec(ledger, "DELETE FROM control_distinctness_ledger")  # clean slate

        ledger.record_evidence("t1", _evidence("t1"))
        ledger.record_evidence("t2", _evidence("t2"))

        inv = ledger.evidence_excluding("t1")
        assert set(inv.keys()) == {"t2"}, f"inventory-minus-self must exclude the subject: {set(inv.keys())}"
        assert inv["t2"].database_identity == "t2:42", "reference-only evidence must reconstruct faithfully"
        assert inv["t2"].sentinel_written is True and inv["t2"].sentinel_token == "tok_t2"

        # upsert-latest (one row per tenant)
        ledger.record_evidence("t2", replace(_evidence("t2"), database_identity="t2:99"))
        assert ledger.evidence_excluding("t1")["t2"].database_identity == "t2:99", "record_evidence must upsert latest"

        ledger.remove("t2")
        assert set(ledger.evidence_excluding("t1").keys()) == set(), "remove must drop the tenant's evidence"
    finally:
        _exec(ledger, "DROP TABLE IF EXISTS control_distinctness_ledger")  # throwaway cleanup


if __name__ == "__main__":
    _pg.run([test_durable_ledger_roundtrip])
