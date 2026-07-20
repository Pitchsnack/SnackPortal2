"""Controlled rollback rehearsal — composed-core Control Plane + Database Router — DISPOSABLE live-PostgreSQL proof (standalone-only).

The MANUAL_ONLY, operator-run, human-START-GATED rehearsal harness that proves the B5-BLK-8 rollback
MECHANISM — returning a durable/activated composition to the deferred (in-memory) default whose
construction performs no I/O — against a disposable, physically distinct three-database topology, driven
entirely IN-PROCESS through the real composition root. There is NO Gateway, NO Auth, NO served HTTP edge,
and NO port (composed-core): the Database Router reads the durable Control Plane through a harness-local
in-process ``ControlPlaneRoutingReadPort`` bridge, so the durable plane is genuinely load-bearing without
any listening process. This harness hosts no server, opens no HTTP client connection, loads no crypto
material, and sets only Control-Plane composition selectors (never a gateway / auth / database-router /
import served-edge selector).

Phases S0..S9 + finally (R-A disposal) + S-final (single-final-write):

    S0  control 001-009 blob-pin STOP-before-connect (LF-normalized git-blob SHA-1; never "fix" the DDL here)
    S1  three disposable, physically distinct databases created fresh with a safe current_database() readback:
          sp2_rollback_control / sp2_rollback_target / sp2_rollback_adjacent
    S2  control 001-009 applied to the disposable Control DB ONLY (never 010-013 routing/gateway op-audit,
        never 014-015 import op-audit, never any audit-store DDL)
    S3  the 14-file tenant template (provisioning 001-003 + lineage 001-003 + tenant 001-008) applied to each
        disposable tenant DB via the REAL applicator; scratch SecretRef material outside the repository
    S4  a SecretRef-only registry seed (the registry stores NO raw DSN) + synthetic target/adjacent startups;
        BEFORE_DATA_DIGEST captured for both
    S5  the durable/activated ControlPlane() (SP2_CP_CONTROL_STORE=postgres — RULE 2; the live side stays
        in-memory) fronted by an in-process Database Router (the portless composed-core plane)
    S6  the single routed proof: one request -> one active tenant -> one database (the target pool key is the
        only pool key; the adjacent physical DB is never opened)
    S7  the preferred gate §7 secret-resolution failure trigger — a synthetic Ready tenant ``gamma`` whose
        SecretRef is deliberately unresolvable: the Router fails closed, no connection opens, the target pool
        key remains the only pool key, and a references-only failure record is captured (D-14; the documented
        fallback trigger is distinctness regression)
    S8  the composition rollback — the four SP2_CP_* selectors are unset and a fresh ControlPlane() composes
        the deferred in-memory default (in-memory store + provisioning operator + distinctness ledger) whose
        construction performs no I/O (the recorder observes ``calls == []``; NO exception-type assertion is
        made)
    S9  AFTER_DATA_DIGEST captured for both tenants; before == after (D-24 non-destructive) and the adjacent
        tenant proven untouched (D-30 per-tenant isolation); the 22-field rollback record and its
        references-only evidence entries are completed IN MEMORY — the single authoritative JSON is NOT
        written here (see S-final)
    finally / R-A  disposal of the COMPLETE disposable topology (pg_terminate_backend + DROP DATABASE IF
        EXISTS for each of the three), asserting the retained disposable datname census == 0
    S-final  reached ONLY when S0-S9 AND the finally disposal both succeed (any assertion — including
        ``retained == 0`` — re-raises through the finally and skips this step): DISPOSAL_ASSERTION and
        FINAL_VERDICT are finalized to PASS (retained=0) / ROLLBACK-PROVEN-LOCAL and the single
        references-only JSON evidence bundle is written EXACTLY ONCE OUTSIDE the repository, so a failed run
        or a failed disposal can never retain a false-PASS record

ISOLATION & SAFETY. Everything runs in the rehearsal-owned scratch databases sp2_rollback_control /
sp2_rollback_target / sp2_rollback_adjacent created from the SNACKPORTAL_TEST_DSN admin connection at start
and DROPPED in a ``finally``. The DSN must point ONLY at a disposable, non-production instance; it must NEVER
point at production, shared staging, the standing Control database, or any tenant database. The repo DDL
files are read + blob-pinned only, never modified. No standing SnackPortal2 database is named, read, or
touched by this file. The rehearsal never runs a destructive statement against a tenant table and never
deletes tenant business data (D-24); the only DROP DATABASE targets are the three disposable names above.

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN reaches the rehearsal only through the ``_pg`` runner; no
descriptor value is printed, logged, committed, or recorded. Tenant DSNs live only in a rehearsal-owned
scratch secret directory (deleted in ``finally``) resolved in-memory by the REAL EnvTenantSecretStore; the
Control-store DSN travels by SecretRef through the REAL EnvReferenceSecretStore binding. The registry rows
carry SecretRef {store_ref, version} only. The evidence bundle is references only and is substring-scanned
for secret shapes before it is written.

DRIVER CONTAINMENT. This file imports NO database driver, NO jwt, and NO cryptography at any scope.
PostgreSQL is reached only through the sanctioned provider adapters, imported lazily inside the exercise so
the module clean-skips without psycopg.

MANUAL_ONLY / START-GATE. This rehearsal is deliberately MANUAL_ONLY, operator-run, and disposable: an
explicit human START-GATE (Dan) is required before any execution, per
infrastructure/runbooks/controlled_rollback_rehearsal.md. It is registered as a justified MANUAL_ONLY
exception in tests/architecture/test_live_pg_workflow_runset_completeness.py; the automatic live-pg workflow
loop is unchanged and never runs this file.

DEFAULT SUITE. IGNORED by the default test run (pyproject addopts ``--ignore=tests/control_plane/requires_pg``).
Run it standalone against a disposable instance:
  python backend/tests/control_plane/requires_pg/test_pg_controlled_rollback_rehearsal.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0, no DB touched).

NO OVERCLAIM. This rehearsal is DISPOSABLE-ONLY and proves a LOCAL rollback mechanism: it does not touch the
retained standing topology, does not execute a rollback against production, does not prove a
production-scoped rollback (the later B5-BLK-8C stage), and closes no blocker. B5-BLK-8 remains OPEN; the
live blocker census remains 7 of 9 OPEN; Production remains NOT READY / DO-NOT-ACTIVATE.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run()/swap_db())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

# The three rehearsal-owned scratch databases: created and dropped by THIS file only. Collision-free vs every
# standing Control/tenant database name and every sibling harness scratch family (R-A disposal target set).
_ROLLBACK_CTL = "sp2_rollback_control"
_ROLLBACK_TARGET = "sp2_rollback_target"
_ROLLBACK_ADJACENT = "sp2_rollback_adjacent"
_ROLLBACK_DBS = (_ROLLBACK_CTL, _ROLLBACK_TARGET, _ROLLBACK_ADJACENT)

# The exact synthetic contract (references only; no personal or production data).
_TARGET = "target"  # tenant id (registry + secret ref)
_ADJACENT = "adjacent"  # tenant id (registry + secret ref) — proven untouched (D-30)
_GAMMA = "gamma"  # registered Ready, DELIBERATELY unresolvable SecretRef (the §7 secret-resolution trigger)
_FIXED_TS = "2026-07-20T00:00:00+00:00"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"

# STOP-before-connect blob pins for control 001-009 — rehearsal-specific name (NOT _REVIEWED_*_BLOB) so the
# control-DDL pin-completeness meta-guard's _REVIEWED_[A-Z0-9]+_BLOB sweep does not enrol them (the
# served-write _REHEARSAL_BLOB_* precedent). A mismatch STOPS the exercise BEFORE any connection is opened.
_ROLLBACK_BLOB_001 = "30956ff1e85e8dab1c9f55cbfc121ee9212f3ca0"
_ROLLBACK_BLOB_002 = "887d0cbce636b7a4610272b584ad0aea61eb2294"
_ROLLBACK_BLOB_003 = "c787c5372c511dc1975d337cdfe871d2d849a2c4"
_ROLLBACK_BLOB_004 = "8194408e62f08533e649612981f10089b8a3b1b0"
_ROLLBACK_BLOB_005 = "a0df9ec58b6825aa298b1b9656cc0028d9831c14"
_ROLLBACK_BLOB_006 = "c929af89da85ec7614b716bdb40af611da9613f2"
_ROLLBACK_BLOB_007 = "aa6066a7398cfb81e8e96067927023c3f11bb391"
_ROLLBACK_BLOB_008 = "c510ebbaa881e3fc325dbb8ee8bf49b114e522ab"
_ROLLBACK_BLOB_009 = "64f8227e829d446a74efeb3784e06b0e28f47549"
_CONTROL_DDL = (
    ("001_distinctness_ledger.sql", _ROLLBACK_BLOB_001),
    ("002_provisioning_audit.sql", _ROLLBACK_BLOB_002),
    ("003_provisioning_audit_append_only.sql", _ROLLBACK_BLOB_003),
    ("004_control_tenants.sql", _ROLLBACK_BLOB_004),
    ("005_control_memberships.sql", _ROLLBACK_BLOB_005),
    ("006_control_federation.sql", _ROLLBACK_BLOB_006),
    ("007_control_directory.sql", _ROLLBACK_BLOB_007),
    ("008_distinctness_fingerprint_unique.sql", _ROLLBACK_BLOB_008),
    ("009_control_tenants_cas_version.sql", _ROLLBACK_BLOB_009),
)

# The pinned environment-touch census (the composed-core plane is SMALL: only the ControlPlane selectors +
# the control-store secret + the tenant secret dir). No served-edge selectors — the composed-core plane has
# none. Every key is set/unset through _EnvPatch (fail closed) and restored in ``finally``.
_ENV_TOUCHED_KEYS = (
    "SP2_CP_CONTROL_STORE",
    "SP2_CP_CONTROL_STORE_DSN_REF",
    "SP2_CP_PROVISIONING_ADAPTER",
    "SP2_CP_TENANT_SCHEMA_APPLICATOR",
    "SP2_CP_DISTINCTNESS_LEDGER",
    "SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1",
    "SNACKPORTAL_TENANT_SECRET_DIR",
)

# The exact 19-key DBR-AR-2E evidence-entry shape (references only; ORDER is authoritative).
_EVIDENCE_KEYS = (
    "evidence_id",
    "requirement_id",
    "blocker_id",
    "title",
    "status",
    "source_type",
    "source_path_or_url",
    "source_commit",
    "source_tree",
    "source_blob_or_hash",
    "environment",
    "database_identity",
    "captured_at",
    "verified_at",
    "verifier",
    "reproducibility",
    "sensitivity",
    "retention",
    "notes",
)

# The exact 22 references-only rollback-record fields (the 8A template shape).
_ROLLBACK_FIELDS = (
    "EXECUTION_ID",
    "EXECUTION_DATE",
    "OPERATOR",
    "ENVIRONMENT_CLASS",
    "BASELINE_MAIN_SHA",
    "ACTIVATION_MODE",
    "ROLLBACK_TRIGGER",
    "ROLLBACK_PLAN_REF",
    "PRE_ROLLBACK_STATE_REF",
    "POST_ROLLBACK_STATE_REF",
    "TENANT_SCOPE",
    "ADJACENT_TENANT_SCOPE",
    "BEFORE_DATA_DIGEST",
    "AFTER_DATA_DIGEST",
    "ISOLATION_ASSERTION",
    "NON_DESTRUCTIVE_ASSERTION",
    "FAILURE_RECORD_REF",
    "AUDIT_RECORD_REF",
    "SECRET_REFERENCE_ONLY_ASSERTION",
    "DEFERRED_COMPOSITION_ASSERTION",
    "DISPOSAL_ASSERTION",
    "FINAL_VERDICT",
)

# Secret/PII shape detectors (BUILT from low-entropy fragments — never a contiguous shape here).
_DSN_MARKER = "postgresql" + "://"
_JWT_MARKER = "ey" + "J"
_KEY_MARKER = "-----" + "BEGIN"


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _verify_rollback_blob_pins() -> None:
    """Resolve the committed control 001-009 blob IDs and STOP before connecting or applying SQL if any
    diverges from the rehearsal pin (pure file I/O — no DB, no socket). Never "fix" the DDL in place."""
    for name, pinned in _CONTROL_DDL:
        actual = _git_blob_sha1(_CONTROL / name)
        assert actual == pinned, f"control {name} blob {actual} != pinned {pinned} — STOP before connect/apply (do not fix DDL here)"
    print(f"PASS: S0 control 001-009 blob pins verified BEFORE any connection ({len(_CONTROL_DDL)} files)")


def _scalar(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _digest(conn: Any) -> str:
    """A references-only sha256 over the ordered synthetic projection (non-secret business identities only)."""
    rows = conn.execute("SELECT global_startup_id, company_name FROM startups ORDER BY global_startup_id").fetchall()
    return hashlib.sha256(repr([tuple(r) for r in rows]).encode("utf-8")).hexdigest()


class _EnvPatch:
    """Set/unset environment keys with the prior value recorded; ``restore()`` runs in ``finally``. Only keys
    in the pinned ``_ENV_TOUCHED_KEYS`` census may pass through here (fail closed)."""

    def __init__(self) -> None:
        self._saved: Dict[str, Optional[str]] = {}

    def set(self, key: str, value: Optional[str]) -> None:
        assert key in _ENV_TOUCHED_KEYS, f"environment key {key!r} is outside the pinned touch census — refused"
        if key not in self._saved:
            self._saved[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def restore(self) -> None:
        for key, prior in self._saved.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
        self._saved.clear()


def _evidence_entry(evidence_id: str, **overrides: str) -> Dict[str, str]:
    """Build one references-only DBR-AR-2E entry with the exact 19 keys (defaults, then overrides)."""
    base: Dict[str, str] = {
        "evidence_id": evidence_id,
        "requirement_id": "B5-BLK-8B",
        "blocker_id": "B5-BLK-8",
        "title": "",
        "status": "PASS",
        "source_type": "harness",
        "source_path_or_url": "tests/control_plane/requires_pg/test_pg_controlled_rollback_rehearsal.py",
        "source_commit": "ref:live-main-at-run",
        "source_tree": "ref:live-tree-at-run",
        "source_blob_or_hash": "ref:phase-print",
        "environment": "disposable",
        "database_identity": "ref:sp2_rollback_* (disposable)",
        "captured_at": _FIXED_TS,
        "verified_at": _FIXED_TS,
        "verifier": "rollback-rehearsal-harness",
        "reproducibility": "manual-start-gated",
        "sensitivity": "references-only",
        "retention": "retain-all (IC-001 default)",
        "notes": "",
    }
    for key, value in overrides.items():
        assert key in base, f"unknown evidence key {key!r}"
        base[key] = value
    assert tuple(base.keys()) == _EVIDENCE_KEYS, "evidence entry must carry the exact 19-key DBR-AR-2E shape in order"
    return base


def _record_failure(evidence: List[Dict[str, str]], *, trigger: str, reason_ref: str) -> str:
    """Append the references-only §7 failure entry (never a secret value) and return its ref:evidence#... anchor."""
    assert not reason_ref.lower().startswith(_DSN_MARKER), "the failure reason must be a reference, never a descriptor value"
    evidence.append(
        _evidence_entry(
            "EV-RBK-FAILURE-01",
            title="secret-resolution-failure §7 trigger",
            notes=f"trigger={trigger}; reason={reason_ref}; no tenant connection opened; references only (D-14)",
        )
    )
    return "ref:evidence#EV-RBK-FAILURE-01"


def _write_evidence_bundle(path: pathlib.Path, record: Dict[str, str], evidence: List[Dict[str, str]]) -> None:
    """Serialize the single authoritative references-only JSON document, after fail-closed validation:
    (a) all 22 record fields present + non-empty; (b) every ref:evidence#<id> resolves to an evidence_id;
    (c) every cell passes the secret-shape substring scan. A printed line alone is NOT sufficient evidence."""
    assert not path.resolve().is_relative_to(_REPO_ROOT), "the evidence bundle must be written OUTSIDE the repository"
    for field in _ROLLBACK_FIELDS:
        assert field in record and str(record[field]).strip(), f"the rollback record must carry a non-empty {field}"
    ids = {entry["evidence_id"] for entry in evidence}
    for field, value in record.items():
        if str(value).startswith("ref:evidence#"):
            anchor = str(value).split("ref:evidence#", 1)[1]
            assert anchor in ids, f"{field} anchor {anchor!r} does not resolve to an evidence entry"
    for entry in evidence:
        assert tuple(entry.keys()) == _EVIDENCE_KEYS, "every evidence entry must carry the exact 19-key shape in order"
    index = {
        "schema": "b5-blk8b-rollback-rehearsal-evidence-index",
        "schema_version": 1,
        "prd": "PRD SnackPortal2 B5-BLK-8B Disposable Rollback Rehearsal",
        "authorization": "Dan START-GATE (8B execution)",
        "baseline_commit": os.environ.get("SP2_ROLLBACK_BASELINE_COMMIT") or "ref:live-main-at-run",
        "baseline_tree": os.environ.get("SP2_ROLLBACK_BASELINE_TREE") or "ref:live-tree-at-run",
        "outcome": "REMAIN NOT READY / DO-NOT-ACTIVATE",
        "blocker_census": 9,
        "blockers_open": 7,
        "blockers_closed": 2,
        "dbr_ar_2_status": "N/A (8B closes zero blockers)",
        "generated_on": _FIXED_TS[:10],
        "rollback_record": record,
        "evidence": evidence,
    }
    blob = json.dumps(index, indent=2, sort_keys=False)
    lowered = blob.lower()
    assert _DSN_MARKER not in lowered, "a DSN-shaped value must never appear in the evidence bundle"
    assert _JWT_MARKER.lower() not in lowered, "a token-shaped value must never appear in the evidence bundle"
    assert _KEY_MARKER.lower() not in lowered, "key material must never appear in the evidence bundle"
    path.write_text(blob, encoding="utf-8")


# --- the exercise ---------------------------------------------------------------------------------
def test_pg_controlled_rollback_rehearsal(admin_dsn: str) -> None:
    # PROOF S0 — control 001-009 blob pins verified BEFORE any connection or SQL (STOP rule).
    _verify_rollback_blob_pins()

    # Lazy provider/composition imports: psycopg stays confined to the sanctioned zone; the module clean-skips
    # without it. Tests may import any package (lint-imports governs production packages only). NO Gateway,
    # NO Auth, NO served edge, NO crypto, NO socket — composed-core only.
    from control_plane.adapters.providers import postgres_distinctness_ledger as ledger_mod
    from control_plane.adapters.providers.in_memory_store import InMemoryControlStore
    from control_plane.adapters.providers.postgres_store import PostgresControlStore
    from control_plane.adapters.providers.postgres_tenant_schema_applicator import PostgresTenantSchemaApplicator
    from control_plane.distinctness import InMemoryDistinctnessLedger
    from control_plane.main import ControlPlane
    from control_plane.provisioning import InMemoryProvisioningOperator
    from control_plane.read_api import ControlPlaneReadService
    from database_router.adapters.providers.env_tenant_secret_store import EnvTenantSecretStore
    from database_router.adapters.providers.in_memory_audit_sink import InMemoryAuditSink
    from database_router.adapters.providers.psycopg_connection import PsycopgConnectionFactory
    from database_router.cache import RoutingViewCache
    from database_router.models import RoutingDenied, TenantRoutingView
    from database_router.pool import ConnectionPoolManager
    from database_router.ports import ControlPlaneRoutingReadPort
    from database_router.resolver import RoutingResolver
    from database_router.router import DatabaseRouter
    from database_router.session_provider import PgRoutedSessionProvider
    from shared.secrets import SecretRef
    from shared.session import Lane

    # The portless composed-core bridge: the Database Router reads the durable Control Plane IN-PROCESS through
    # its own unit of work (no served read edge, no socket). Mirrors HttpRoutingRead's dict -> TenantRoutingView
    # mapping exactly, but sources the dict from ControlPlaneReadService(PostgresControlStore) in-process.
    class _InProcessRoutingRead(ControlPlaneRoutingReadPort):
        def __init__(self, control_plane: ControlPlane) -> None:
            self._cp = control_plane

        def get_routing_view(self, tenant_id: str) -> Optional[TenantRoutingView]:
            with self._cp.control_store_unit_of_work() as store:
                data = ControlPlaneReadService(store).routing_view(tenant_id)
            if data is None:
                return None
            ref = data["database_association_ref"]
            return TenantRoutingView(
                tenant_id=data["tenant_id"],
                lifecycle_state=data["lifecycle_state"],
                ready=bool(data["ready"]),
                database_association_ref=SecretRef(store_ref=ref["store_ref"], version=ref["version"]),
                expected_schema_version=data["expected_schema_version"],
            )

    # Admin connection (autocommit: CREATE/DROP DATABASE are non-transactional), via the sanctioned adapter.
    admin = PostgresControlStore(admin_dsn)._conn
    admin.autocommit = True
    server_num = int(_scalar(admin, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num})"

    env = _EnvPatch()
    ctl_conn = target_conn = adjacent_conn = None
    secret_dir: Optional[str] = None

    try:
        # PROOF S1 — three disposable, physically distinct databases, lifecycle-owned by THIS run.
        for name in _ROLLBACK_DBS:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
            admin.execute(f'CREATE DATABASE "{name}"')
        ctl_dsn = _pg.swap_db(admin_dsn, _ROLLBACK_CTL)
        target_dsn = _pg.swap_db(admin_dsn, _ROLLBACK_TARGET)
        adjacent_dsn = _pg.swap_db(admin_dsn, _ROLLBACK_ADJACENT)
        ctl_conn = PostgresControlStore(ctl_dsn)._conn
        ctl_conn.autocommit = True
        target_conn = PostgresControlStore(target_dsn)._conn
        target_conn.autocommit = True
        adjacent_conn = PostgresControlStore(adjacent_dsn)._conn
        adjacent_conn.autocommit = True
        identities = {
            _scalar(ctl_conn, "SELECT current_database()"),
            _scalar(target_conn, "SELECT current_database()"),
            _scalar(adjacent_conn, "SELECT current_database()"),
        }
        assert identities == set(_ROLLBACK_DBS), f"safe identity readback must show three distinct physical databases: {identities}"
        print(f"PASS: S1 three disposable physically distinct databases created fresh ({', '.join(_ROLLBACK_DBS)})")

        # PROOF S2 — control DDL on the disposable Control DB ONLY: 001-009 in order, each exactly once; NO
        # 010-013 (routing/gateway op-audit), NO 014-015 (import op-audit), NO audit-store DDL.
        with ctl_conn.cursor() as cur:
            for name, _pinned in _CONTROL_DDL:
                cur.execute((_CONTROL / name).read_text(encoding="utf-8"))
        assert _scalar(ctl_conn, "SELECT to_regclass('control_tenants')") is not None, "control_tenants must exist after apply"
        assert _scalar(ctl_conn, "SELECT to_regclass('control_routing_audit')") is None, "010-013 must NOT be applied by this rehearsal"
        assert _scalar(ctl_conn, "SELECT to_regclass('control_import_audit')") is None, "014-015 must NOT be applied by this rehearsal"
        print("PASS: S2 control 001-009 applied to the disposable Control DB only (010-015 absent)")

        # PROOF S3 — rehearsal-owned scratch secret directory (SecretRef-only transport) + the 14-file tenant
        # template applied to BOTH disposable tenant DBs via the REAL applicator. gamma gets NO secret file.
        secret_dir = tempfile.mkdtemp(prefix="sp2_rollback_secrets_")
        for tenant_id, tenant_dsn in ((_TARGET, target_dsn), (_ADJACENT, adjacent_dsn)):
            ref_dir = pathlib.Path(secret_dir) / "tenant" / tenant_id
            ref_dir.mkdir(parents=True)
            (ref_dir / "dsn@1").write_text(tenant_dsn, encoding="utf-8")
        env.set("SNACKPORTAL_TENANT_SECRET_DIR", secret_dir)
        tenant_secrets = EnvTenantSecretStore()
        applicator = PostgresTenantSchemaApplicator(tenant_secrets)
        applicator.apply_schema(_TARGET, target=_ROLLBACK_TARGET, association_ref=SecretRef(store_ref=f"tenant/{_TARGET}/dsn", version="1"))
        applicator.apply_schema(
            _ADJACENT, target=_ROLLBACK_ADJACENT, association_ref=SecretRef(store_ref=f"tenant/{_ADJACENT}/dsn", version="1")
        )
        for tconn in (target_conn, adjacent_conn):
            assert _scalar(tconn, "SELECT to_regclass('startups')") is not None, "startups must exist after the 14-file tenant template"
        print("PASS: S3 14-file tenant template applied to both disposable tenant DBs (real applicator)")

        # PROOF S4 — SecretRef-only registry seed (target/adjacent/gamma Ready; the registry stores NO raw DSN)
        # + synthetic target/adjacent startups; BEFORE_DATA_DIGEST captured for both.
        for tenant_id in (_TARGET, _ADJACENT, _GAMMA):
            ctl_conn.execute(
                "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version,"
                " assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at)"
                " VALUES (%s, 'rollback_org', 'Ready', '1', %s, '1', 'rollback_fed', %s, %s)",
                (tenant_id, f"tenant/{tenant_id}/dsn", _FIXED_TS, _FIXED_TS),
            )
        for tenant_id in (_TARGET, _ADJACENT):
            ctl_conn.execute(
                "INSERT INTO control_memberships (principal_ref, tenant_id, role) VALUES (%s, %s, 'TENANT_AGENT')",
                ("rollback_agent", tenant_id),
            )
        for row in ctl_conn.execute("SELECT * FROM control_tenants").fetchall():
            for cell in row:
                assert "postgresql" not in str(cell), "the registry must never store a raw DSN (SecretRef only)"
        for tconn, tag in ((target_conn, "target"), (adjacent_conn, "adjacent")):
            for suffix in ("1", "2"):
                tconn.execute(
                    "INSERT INTO startups (global_startup_id, company_name) VALUES (%s, %s)",
                    (f"rbk-{tag}-{suffix}", f"Rollback Synthetic {tag} {suffix}"),
                )
        before_target = _digest(target_conn)
        before_adjacent = _digest(adjacent_conn)
        print("PASS: S4 SecretRef-only registry + synthetic startups seeded; BEFORE_DATA_DIGEST captured (target + adjacent)")

        # PROOF S5 — compose the durable/activated plane (RULE 2: control-store-standalone postgres; the live
        # side stays in-memory) fronted by the in-process Database Router (the portless composed-core bridge).
        env.set("SP2_CP_PROVISIONING_ADAPTER", None)
        env.set("SP2_CP_TENANT_SCHEMA_APPLICATOR", None)
        env.set("SP2_CP_DISTINCTNESS_LEDGER", None)
        env.set("SP2_CP_CONTROL_STORE_DSN_REF", None)  # default control/control-store-dsn (reference only)
        env.set("SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1", ctl_dsn)  # in-memory reference material
        env.set("SP2_CP_CONTROL_STORE", "postgres")  # control-store-standalone postgres (sanctioned RULE 2)
        cp = ControlPlane()
        assert isinstance(cp.store, PostgresControlStore), "S5: RULE 2 must select the durable Control store (live side in-memory)"
        routing_read = _InProcessRoutingRead(cp)
        resolver = RoutingResolver(routing_read, RoutingViewCache(ttl_seconds=60.0, clock=lambda: 0.0), supported_schema_versions=("1",))
        request_pool = ConnectionPoolManager(max_per_tenant=5, idle_timeout_seconds=60.0, clock=lambda: 0.0)
        bulk_pool = ConnectionPoolManager(max_per_tenant=5, idle_timeout_seconds=60.0, clock=lambda: 0.0)
        audit = InMemoryAuditSink()
        router = DatabaseRouter(
            resolver=resolver,
            pool=request_pool,
            bulk_pool=bulk_pool,
            secret_store=tenant_secrets,
            connection_factory=PsycopgConnectionFactory(),
            audit=audit,
        )
        provider = PgRoutedSessionProvider(router)
        print("PASS: S5 durable/activated ControlPlane() + in-process Database Router composed (composed-core; no ports)")

        # PROOF S6 — the single routed proof: one request -> one active tenant -> one database.
        session = provider.open_session(tenant_id=_TARGET, correlation_id="corr-rollback-0001", lane=Lane.BULK)
        try:
            rows = session.page("startups", {}, order_by="global_startup_id", limit=10)
            assert len(rows) == 2, f"S6: the routed target connection must read exactly the two seeded startups: {len(rows)}"
        finally:
            session.close()
        assert bulk_pool.pool_keys() == [(_TARGET, "1")], f"S6: exactly one routed pool key (target) is allowed: {bulk_pool.pool_keys()}"
        assert request_pool.pool_keys() == [], f"S6: the interactive pool must be empty (single BULK route): {request_pool.pool_keys()}"
        for event in audit.events():
            assert _ADJACENT not in str(event.target_ref or "") and _ADJACENT not in str(event.resolved_tenant_ref or ""), (
                f"S6: no routing-audit event may reference the adjacent tenant: {event}"
            )
        assert _digest(adjacent_conn) == before_adjacent, "S6: the adjacent physical DB must be untouched by the target route (D-30)"
        print("PASS: S6 single routed proof (one request -> one active tenant -> one database; adjacent untouched)")

        # PROOF S7 — the preferred gate §7 secret-resolution failure trigger: a synthetic Ready tenant whose
        # SecretRef is deliberately unresolvable. The Router fails closed, no connection opens, and the target
        # pool key remains the only pool key. A references-only failure record is captured (never a secret).
        evidence: List[Dict[str, str]] = []
        evidence.append(
            _evidence_entry(
                "EV-RBK-PLAN-01",
                title="rollback plan",
                source_type="runbook",
                source_path_or_url="infrastructure/runbooks/controlled_rollback_rehearsal.md#rollback",
                notes="composition rollback to the deferred in-memory default; references only",
            )
        )
        evidence.append(
            _evidence_entry(
                "EV-RBK-PRE-01",
                title="pre-rollback state",
                notes="transient durable-composition simulation (SP2_CP_CONTROL_STORE=postgres, RULE 2); disposable; NOT production",
            )
        )
        denied_status: Optional[int] = None
        try:
            provider.open_session(tenant_id=_GAMMA, correlation_id="corr-rollback-gamma", lane=Lane.BULK)
        except RoutingDenied as denied:
            denied_status = denied.http_status
        assert denied_status == 503, f"S7: an unresolvable tenant SecretRef must fail closed (503 unavailable): {denied_status}"
        assert bulk_pool.pool_keys() == [(_TARGET, "1")], f"S7: the failed trigger must open NO new pool key: {bulk_pool.pool_keys()}"
        failure_ref = _record_failure(evidence, trigger="secret_resolution_failure", reason_ref="ref:gamma-secret-unresolved")
        print("PASS: S7 secret-resolution failure trigger fails closed (503; no connection opened; references-only failure record)")

        # PROOF S8 — the composition rollback: unset the four SP2_CP_* selectors, then a fresh ControlPlane()
        # composes the deferred in-memory default (in-memory store + operator + ledger) whose construction
        # performs no I/O. A recorder over the shared driver module proves ``calls == []`` — NO exception-type
        # assertion is made (no fail-closed exception-type requirement; the live fail-closed type is ValueError).
        calls: List[Tuple[Any, Any]] = []
        _orig_connect = ledger_mod.psycopg.connect
        ledger_mod.psycopg.connect = lambda *a, **k: calls.append((a, k))  # type: ignore[assignment]
        try:
            env.set("SP2_CP_CONTROL_STORE", None)
            env.set("SP2_CP_PROVISIONING_ADAPTER", None)
            env.set("SP2_CP_TENANT_SCHEMA_APPLICATOR", None)
            env.set("SP2_CP_DISTINCTNESS_LEDGER", None)
            cp2 = ControlPlane()
            assert isinstance(cp2.store, InMemoryControlStore), "S8: the rolled-back store must be the in-memory default"
            assert isinstance(cp2.operator, InMemoryProvisioningOperator), "S8: the rolled-back operator must be in-memory"
            assert isinstance(cp2.provisioning._ledger, InMemoryDistinctnessLedger), "S8: the rolled-back ledger must be in-memory"
            assert calls == [], "S8: the deferred in-memory composition construction must perform no I/O (calls == [])"
        finally:
            ledger_mod.psycopg.connect = _orig_connect
        evidence.append(
            _evidence_entry(
                "EV-RBK-POST-01",
                title="post-rollback state",
                notes="re-composed in-memory default; construction performs no I/O",
            )
        )
        print("PASS: S8 composition rollback to the deferred in-memory default (in-memory adapters; construction performs no I/O)")

        # PROOF S9 — AFTER_DATA_DIGEST for both tenants; before == after (D-24 non-destructive); adjacent
        # untouched (D-30); complete the 22-field rollback record + references-only evidence IN MEMORY. The
        # single authoritative JSON is finalized only AFTER the finally disposal succeeds (see S-final).
        after_target = _digest(target_conn)
        after_adjacent = _digest(adjacent_conn)
        assert after_target == before_target, "S9: the target tenant data must be unchanged (before == after; D-24 non-destructive)"
        assert after_adjacent == before_adjacent, "S9: the adjacent tenant data must be unchanged (D-30 per-tenant isolation)"
        evidence.append(
            _evidence_entry(
                "EV-RBK-AUDIT-01",
                title="audit record",
                notes="references-only; no durable sink (deployment-era 8C/8D); disposable",
            )
        )
        record: Dict[str, str] = {
            "EXECUTION_ID": f"rollback-rehearsal-{os.getpid()}",
            "EXECUTION_DATE": _FIXED_TS[:10],
            "OPERATOR": os.environ.get("SP2_ROLLBACK_OPERATOR") or "operator (references only)",
            "ENVIRONMENT_CLASS": "local",
            "BASELINE_MAIN_SHA": os.environ.get("SP2_ROLLBACK_BASELINE_COMMIT") or "ref:live-main-at-run",
            "ACTIVATION_MODE": "deferred-in-memory",
            "ROLLBACK_TRIGGER": "secret_resolution_failure",
            "ROLLBACK_PLAN_REF": "ref:evidence#EV-RBK-PLAN-01",
            "PRE_ROLLBACK_STATE_REF": "ref:evidence#EV-RBK-PRE-01",
            "POST_ROLLBACK_STATE_REF": "ref:evidence#EV-RBK-POST-01",
            "TENANT_SCOPE": _TARGET,
            "ADJACENT_TENANT_SCOPE": _ADJACENT,
            "BEFORE_DATA_DIGEST": before_target,
            "AFTER_DATA_DIGEST": after_target,
            "ISOLATION_ASSERTION": "PASS",
            "NON_DESTRUCTIVE_ASSERTION": "PASS",
            "FAILURE_RECORD_REF": failure_ref,
            "AUDIT_RECORD_REF": "ref:evidence#EV-RBK-AUDIT-01",
            "SECRET_REFERENCE_ONLY_ASSERTION": "PASS",
            "DEFERRED_COMPOSITION_ASSERTION": "PASS",
        }
        print(
            "PASS: S9 before == after (D-24); adjacent untouched (D-30); 22-field record completed in memory"
            " (authoritative JSON deferred to S-final)"
        )
    finally:
        # PROOF finally / R-A — disposal of the COMPLETE disposable topology (after success OR failure).
        # Pool-held connections are severed by pg_terminate_backend before each DROP DATABASE. This is R-A
        # disposal (teardown of the disposable topology), distinct from the S8 composition rollback.
        for conn in (ctl_conn, target_conn, adjacent_conn):
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        env.restore()
        if secret_dir is not None:
            shutil.rmtree(secret_dir, ignore_errors=True)  # scratch SecretRef material never outlives the run
        retained = 0
        for name in _ROLLBACK_DBS:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
            retained += int(_scalar(admin, "SELECT count(*) FROM pg_database WHERE datname = %s", (name,)))
        print(f"PASS: finally R-A disposal of the complete disposable topology (retained disposable datname count = {retained})")
        admin.close()
        assert retained == 0, "R-A: every disposable rollback database must be removed after the run"

    # PROOF S-final — SINGLE-FINAL-WRITE. Reached ONLY when S0-S9 AND the finally R-A disposal both succeed:
    # any S0-S9 assertion or any disposal failure (including ``retained == 0`` above) re-raises through the
    # finally and this block never runs. Only now are the disposal/verdict verdicts finalized and the single
    # authoritative references-only JSON written EXACTLY ONCE, OUTSIDE the repository — so a failed run or a
    # failed disposal can never retain a false-PASS record.
    record["DISPOSAL_ASSERTION"] = "PASS (retained=0)"
    record["FINAL_VERDICT"] = "ROLLBACK-PROVEN-LOCAL"
    evidence_dir = tempfile.mkdtemp(prefix="sp2_rollback_evidence_")  # OUTSIDE the repository (system temp)
    bundle_path = pathlib.Path(evidence_dir) / f"b5_blk8b_rollback_rehearsal_evidence_{record['EXECUTION_ID']}.json"
    _write_evidence_bundle(bundle_path, record, evidence)
    assert bundle_path.is_file() and not bundle_path.resolve().is_relative_to(_REPO_ROOT), (
        "S-final: the single authoritative references-only evidence bundle must exist OUTSIDE the repository"
    )
    print(f"PASS: S-final single references-only evidence bundle written AFTER disposal ({bundle_path.name})")


if __name__ == "__main__":
    _pg.run([test_pg_controlled_rollback_rehearsal])
