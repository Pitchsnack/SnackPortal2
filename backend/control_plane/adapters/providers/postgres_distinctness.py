"""PostgreSQL Physical Distinctness evidence provider (D15-ARCH-SPEC-01 §6.2, §9.3 DV-C1..DV-C4).

Control-plane-owned. Opens a short-lived connection to the database an association resolves
to, gathers the evidence layers the verifier requires, and closes:

* DV-C1 — PostgreSQL cluster system_identifier  (SELECT system_identifier FROM pg_control_system())
* DV-C2 — database-level identity                (current_database() + the database OID)
* DV-C3 — observed provisioning target           (current_database())
* DV-C4 — write-sentinel verification            (write a unique token into a control-owned
                                                   namespace table and read it back)

The credential is resolved in-memory via the SecretStore (D-14) and never returned; the
driver import is confined to this provider zone (Driver Containment Standard). Fails closed:
any error returns None (-> VERIFICATION_INCOMPLETE) and never surfaces a descriptor or
topology. Runs in controlled non-production only. Not exercised by the stdlib unit suite.
"""

from __future__ import annotations

from typing import Optional

import psycopg  # type: ignore  # noqa: F401  (driver import confined to this zone)

from control_plane.distinctness import DistinctnessEvidence, DistinctnessEvidenceProvider, secret_ref_key
from shared.secrets import SecretRef, SecretStore

SYSTEM_ID_QUERY = "SELECT system_identifier::text FROM pg_control_system()"
DB_IDENTITY_QUERY = "SELECT current_database(), (SELECT oid FROM pg_database WHERE datname = current_database())"

# Control-owned sentinel store: a single schema + table; the per-tenant namespace is a VALUE,
# never business data or PII (D15-ARCH-SPEC-01 §6.5).
SENTINEL_SCHEMA_DDL = "CREATE SCHEMA IF NOT EXISTS dv_sentinel"
SENTINEL_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS dv_sentinel.marker "
    "(ns text PRIMARY KEY, token text NOT NULL, written_at timestamptz NOT NULL DEFAULT now())"
)
SENTINEL_WRITE = (
    "INSERT INTO dv_sentinel.marker (ns, token) VALUES (%s, %s) ON CONFLICT (ns) DO UPDATE SET token = EXCLUDED.token, written_at = now()"
)
SENTINEL_READ = "SELECT token FROM dv_sentinel.marker WHERE ns = %s"


class PostgresDistinctnessEvidenceProvider(DistinctnessEvidenceProvider):
    def __init__(self, secret_store: SecretStore, *, timeout: float = 2.0) -> None:
        self._secrets = secret_store
        self._timeout = timeout

    def gather(
        self,
        association_ref: SecretRef,
        *,
        sentinel_token: str,
        sentinel_namespace: str,
    ) -> Optional[DistinctnessEvidence]:
        descriptor: Optional[str] = None
        conn = None
        try:
            descriptor = self._secrets.resolve(association_ref).material  # in-memory only
            conn = psycopg.connect(descriptor, connect_timeout=int(self._timeout))
            with conn.cursor() as cur:
                cur.execute(SYSTEM_ID_QUERY)
                row = cur.fetchone()
                system_identifier = str(row[0]) if row and row[0] is not None else ""

                cur.execute(DB_IDENTITY_QUERY)
                row = cur.fetchone()
                if not row or row[0] is None:
                    return None
                datname = str(row[0])
                db_oid = str(row[1]) if row[1] is not None else ""
                database_identity = f"{datname}:{db_oid}"

                # DV-C4 — write-sentinel: write a unique token and read it back from the
                # intended database only.
                cur.execute(SENTINEL_SCHEMA_DDL)
                cur.execute(SENTINEL_TABLE_DDL)
                cur.execute(SENTINEL_WRITE, (sentinel_namespace, sentinel_token))
                cur.execute(SENTINEL_READ, (sentinel_namespace,))
                read = cur.fetchone()
            conn.commit()
            sentinel_ok = read is not None and read[0] == sentinel_token

            return DistinctnessEvidence(
                system_identifier=system_identifier,
                database_identity=database_identity,
                observed_target=datname,
                secret_ref_key=secret_ref_key(association_ref),
                sentinel_namespace=sentinel_namespace,
                sentinel_token=sentinel_token if sentinel_ok else None,
                sentinel_written=sentinel_ok,
            )
        except Exception:
            # Fail closed; never surface the descriptor or DB topology.
            return None
        finally:
            descriptor = None  # drop the resolved credential reference promptly
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
