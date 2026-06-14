"""D15 Physical Distinctness — live-PostgreSQL evidence (standalone-only; SNACKPORTAL_TEST_DSN).

Proves against a real cluster that PostgreSQL `system_identifier` is CLUSTER-scoped (identical
across databases — hence insufficient alone, DV-AC9) while database-level identity (datname +
OID) differentiates; that two distinct tenant databases verify; and that a tenant association
pointed at the Control Database is caught (DV-C7A). Provisions throwaway verification databases
and drops them afterward (controlled non-production only).

Run: set SNACKPORTAL_TEST_DSN to an admin DSN with CREATE/DROP DATABASE rights, then
`python tests/control_plane/requires_pg/test_pg_distinctness.py`.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

from control_plane.adapters.providers.postgres_distinctness import PostgresDistinctnessEvidenceProvider  # noqa: E402
from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator  # noqa: E402
from control_plane.distinctness import DistinctnessResult, PhysicalDistinctnessVerifier  # noqa: E402
from shared.secrets import SecretRef, SecretStore, SecretValue  # noqa: E402

T1 = "sp2_dvtest_t1"
T2 = "sp2_dvtest_t2"


class MapSecretStore(SecretStore):
    """Maps a secret reference store_ref directly to a DSN (test-only)."""

    def __init__(self, mapping: dict) -> None:
        self._m = mapping

    def resolve(self, ref: SecretRef) -> SecretValue:
        return SecretValue(self._m[ref.store_ref])

    def current_version(self, store_ref: str) -> str:
        return "1"


def test_real_distinctness(admin_dsn: str) -> None:
    operator = PostgresProvisioningOperator(admin_dsn)
    operator.provision("t1", target=T1)
    operator.provision("t2", target=T2)
    try:
        secrets = MapSecretStore(
            {
                "t1_secret": _pg.swap_db(admin_dsn, T1),
                "t2_secret": _pg.swap_db(admin_dsn, T2),
                "control_secret": admin_dsn,
            }
        )
        provider = PostgresDistinctnessEvidenceProvider(secrets)
        ev1 = provider.gather(SecretRef("t1_secret", "1"), sentinel_token="tok1", sentinel_namespace="dv_sentinel_t1")
        ev2 = provider.gather(SecretRef("t2_secret", "1"), sentinel_token="tok2", sentinel_namespace="dv_sentinel_t2")
        evc = provider.gather(SecretRef("control_secret", "1"), sentinel_token="tokc", sentinel_namespace="dv_sentinel_control")

        assert ev1 and ev2 and evc, "evidence gather must succeed against live PG"
        assert ev1.system_identifier == ev2.system_identifier == evc.system_identifier, "system_identifier is cluster-scoped (DV-AC9)"
        assert len({ev1.database_identity, ev2.database_identity, evc.database_identity}) == 3, "database-level identity differentiates"
        assert ev1.sentinel_written and ev2.sentinel_written, "write-sentinel must be proven"

        verifier = PhysicalDistinctnessVerifier()
        out1 = verifier.verify("t1", ev1, intended_target=T1, control_db=evc, inventory={"t2": ev2})
        assert out1.result is DistinctnessResult.VERIFIED, f"distinct tenant must verify: {out1.reason}"

        # A tenant association pointed at the Control DB must be caught (tenant-vs-Control-DB).
        ev_mis = provider.gather(SecretRef("control_secret", "1"), sentinel_token="tokx", sentinel_namespace="dv_sentinel_t1")
        out_mis = verifier.verify("t1", ev_mis, intended_target=T1, control_db=evc, inventory={})
        assert out_mis.result is DistinctnessResult.ISOLATION_ANOMALY, "tenant pointed at Control DB must be an IsolationAnomaly"
    finally:
        operator.deprovision(target=T1)
        operator.deprovision(target=T2)


if __name__ == "__main__":
    _pg.run([test_real_distinctness])
