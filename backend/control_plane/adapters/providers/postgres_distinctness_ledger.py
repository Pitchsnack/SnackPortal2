"""Durable Control-DB Physical Distinctness Ledger (PRD 06 B-2; D15-ARCH-SPEC-01 §9.2 input 8).

A persistent implementation of the control-plane ``DistinctnessLedger`` ABC
(``control_plane/distinctness.py``), backing the per-tenant distinctness-evidence inventory
with a Control-Database table (``control_distinctness_ledger``; DDL:
``infrastructure/db/control/001_distinctness_ledger.sql``) so the inventory survives
control-plane restart and is shared across nodes — unlike the default
``InMemoryDistinctnessLedger`` (per-instance, lost on restart).

Semantics match the ABC the readiness gate already relies on (``provisioning.py``): upsert the
LATEST evidence per tenant (``record_evidence``), return the inventory minus the subject tenant
(``evidence_excluding``), and drop a tenant's evidence (``remove``). It is an *inventory*, not an
audit-history sink. The gate is unchanged: the durable ledger is selected via the gate's existing
``ledger=`` parameter (composition root), so IC-002 states, the D-15 audit vocabulary, and
IC-010 §P are untouched.

References only (D-14; IC-001 Global Audit Representation Rule): the persisted row carries
identity/comparison keys and a non-sensitive secret-store *reference* key — never a credential,
DSN, raw secret value, JWT/API key, PII, or business payload. The Control-DB connection
descriptor is resolved in-memory from the ``SecretStore`` at each operation and is never
retained on this object.

Lazy-connect (Driver Containment Standard; follows the ``postgres_probe`` model, NOT
``postgres_store``): construction opens NO connection — ``__init__`` only stores the
secret-store reference. Each operation resolves the descriptor, opens a short-lived connection,
acts, and closes. Consequently ``ControlPlane()`` construction performs no live database I/O for
any ledger selection. The database driver import is confined to this provider zone. Runs in
controlled non-production only; the live record/read exercise against a real Control DB is B-4,
not B-2 — the stdlib unit suite does not exercise this adapter.

Fail-closed: ``evidence_excluding`` NEVER substitutes a partial or empty inventory on error — an
empty inventory would hide a tenant-vs-tenant collision (fail-OPEN). On any failure it lets the
error propagate so the readiness gate aborts before Ready (fail-closed). The adapter never
surfaces the descriptor or database topology.

Freshness (DB2-2): each recorded row carries ``recorded_at`` (UTC ISO-8601, set at record time
via ``now_iso()``). A freshness/staleness policy MAY be enforced as a later additive,
opt-in composition step; it must never relax an existing fail-closed denial. B-2 records the
timestamp and does not enforce a staleness window.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

import psycopg  # type: ignore  # noqa: F401  (driver import confined to this zone)

from control_plane._util import now_iso
from control_plane.distinctness import DistinctnessCollisionError, DistinctnessEvidence, DistinctnessLedger
from shared.secrets import SecretRef, SecretStore

# Control-plane-owned ledger table (Control Database). DDL is an additive, reference-only
# artifact under infrastructure/db/control/ (created, not applied — applying is B-4).
LEDGER_TABLE = "control_distinctness_ledger"

_UPSERT = (
    f"INSERT INTO {LEDGER_TABLE} "
    "(tenant_id, system_identifier, database_identity, observed_target, secret_ref_key, "
    "sentinel_namespace, sentinel_token, sentinel_written, recorded_at) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (tenant_id) DO UPDATE SET "
    "system_identifier = EXCLUDED.system_identifier, "
    "database_identity = EXCLUDED.database_identity, "
    "observed_target = EXCLUDED.observed_target, "
    "secret_ref_key = EXCLUDED.secret_ref_key, "
    "sentinel_namespace = EXCLUDED.sentinel_namespace, "
    "sentinel_token = EXCLUDED.sentinel_token, "
    "sentinel_written = EXCLUDED.sentinel_written, "
    "recorded_at = EXCLUDED.recorded_at"
)
_SELECT_EXCLUDING = (
    "SELECT tenant_id, system_identifier, database_identity, observed_target, secret_ref_key, "
    f"sentinel_namespace, sentinel_token, sentinel_written FROM {LEDGER_TABLE} WHERE tenant_id <> %s"
)
_DELETE = f"DELETE FROM {LEDGER_TABLE} WHERE tenant_id = %s"

# SQLSTATE for the driver's unique-violation error class (PRD 07D-2c). The 008 unique
# fingerprint constraint on (system_identifier, database_identity) — reference-only DDL under
# infrastructure/db/control/, applied by the live exercise, never by this adapter — rejects a
# row that would leave two DISTINCT tenants on one physical database.
_UNIQUE_VIOLATION_SQLSTATE = "23505"


class PostgresDistinctnessLedger(DistinctnessLedger):
    """Control-DB-backed durable distinctness ledger (lazy-connect, references-only)."""

    def __init__(self, secret_store: SecretStore, control_db_ref: SecretRef, *, timeout: float = 2.0) -> None:
        # control_db_ref is a non-sensitive secret-store reference (store_ref/version), never the
        # secret value (D-14). No connection is opened here — lazy-connect per operation.
        self._secrets = secret_store
        self._control_db_ref = control_db_ref
        self._timeout = timeout

    def _connect(self) -> Any:
        """Resolve the Control-DB descriptor and open a short-lived connection (lazy).

        The descriptor is resolved in-memory at call time and dropped immediately; it is never
        stored on the adapter (D-14)."""
        descriptor: Optional[str] = None
        try:
            descriptor = self._secrets.resolve(self._control_db_ref).material  # in-memory only
            return psycopg.connect(descriptor, connect_timeout=int(self._timeout))
        finally:
            descriptor = None  # drop the resolved descriptor promptly (never retained)

    def record_evidence(self, tenant_id: str, evidence: DistinctnessEvidence) -> None:
        conn = self._connect()
        try:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        _UPSERT,
                        (
                            tenant_id,
                            evidence.system_identifier,
                            evidence.database_identity,
                            evidence.observed_target,
                            evidence.secret_ref_key,
                            evidence.sentinel_namespace,
                            evidence.sentinel_token,
                            evidence.sentinel_written,
                            now_iso(),
                        ),
                    )
            except Exception as exc:
                # PRD 07D-2c: map ONLY the unique-violation SQLSTATE onto the typed domain
                # refusal. Same-tenant writes resolve via the (tenant_id) conflict arbiter and
                # never reach this path, so a 23505 here is the losing side of a cross-tenant
                # fingerprint race (008 unique fingerprint constraint). Every other error keeps
                # propagating unchanged — the documented fail-closed-by-raise contract below is
                # untouched. Detection is by the driver-standard `sqlstate` attribute (no
                # driver-typed exception classes leak into the domain).
                if getattr(exc, "sqlstate", None) == _UNIQUE_VIOLATION_SQLSTATE:
                    raise DistinctnessCollisionError("distinctness fingerprint already recorded for another tenant") from exc
                raise
            conn.commit()
        finally:
            conn.close()

    def evidence_excluding(self, tenant_id: str) -> Mapping[str, DistinctnessEvidence]:
        # Fail-closed: any connection/query error propagates so the gate aborts before Ready.
        # NEVER swallow an error and return a partial/empty inventory — that would hide a
        # tenant-vs-tenant collision (fail-open).
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(_SELECT_EXCLUDING, (tenant_id,))
                rows = cur.fetchall()
        finally:
            conn.close()
        inventory: Dict[str, DistinctnessEvidence] = {}
        for r in rows:
            inventory[str(r[0])] = DistinctnessEvidence(
                system_identifier=str(r[1]),
                database_identity=str(r[2]),
                observed_target=str(r[3]),
                secret_ref_key=str(r[4]),
                sentinel_namespace=str(r[5]),
                sentinel_token=(str(r[6]) if r[6] is not None else None),
                sentinel_written=bool(r[7]),
            )
        return inventory

    def remove(self, tenant_id: str) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(_DELETE, (tenant_id,))
            conn.commit()
        finally:
            conn.close()
