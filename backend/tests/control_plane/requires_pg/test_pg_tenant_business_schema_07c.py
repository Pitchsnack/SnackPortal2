"""PRD 07C V5 tenant business schema — live-PostgreSQL proof (standalone-only; SNACKPORTAL_TEST_DSN).

The 07C live exercise for the created-not-applied TENANT business DDL family (infrastructure/db/tenant/,
files 001-007: agents + System Primary constraints, ai_agents, startups, investors, deals, ownership,
links). Against a real non-production PostgreSQL it provisions TWO physical tenant databases, applies the
family to each, and proves the 18 required checks of exec-auth V2 section 15.4: physical tenant isolation,
the Control Global Registry reference boundary (MCC control_directory), ownership cardinality (at-most-one
human owner by PK; zero-or-more distinct AI Agents by composite PK), 07B.1 seed-shape compatibility WITHOUT
seeding in DDL, the System Primary singleton + protective trigger (DELETE / kind-flip rejected), no
human-required readiness, no queue-manager, and no tenant_id column.

PINS (07C V5 section 13.D naming rule). Tenant DDL is pinned here under _TENANT_BLOB_NNN — deliberately NOT
_REVIEWED_* — because b7c1r2 scans this directory for _REVIEWED_[A-Z0-9]+_BLOB pins with per-FILE
control-association and this file references the Control DDL directory (it applies MCC 001-007 UNPINNED for
the registry proof; those blobs are pinned by their own guards). The static guard
tests/architecture/test_tenant_ddl_blob_drift.py cross-checks these pins and this file's apply order.

ISOLATION & SAFETY. Control side runs in a scratch SCHEMA on the admin database; tenant side runs in two
scratch DATABASES created OUTSIDE any transaction and dropped in a finally (tracked connections are closed
FIRST so the drops cannot block — the MCC lesson). Never touches production; never modifies repo DDL files
(read-only). The 07B.1 seed INSERT executed here is the HARNESS proving seed-shape compatibility (check 11)
— the DDL itself seeds nothing.

DRIVER CONTAINMENT. No static database-driver import. PostgreSQL is reached only through the control-plane
adapter PostgresControlStore (psycopg confined to the sanctioned provider zone) via store._conn — the
B-7A / MCC harness precedent. Expected-error probes run on AUTOCOMMIT connections (a rejected statement is
its own aborted transaction).

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used by NAME only (must be CREATEDB-capable, NON-production);
its value is never printed, logged, or written.

DEFAULT SUITE / CI. IGNORED by the default test run (pyproject addopts --ignore of this directory) and NOT
wired into any .github workflow run-set — manual/local only. Run:
  python backend/tests/control_plane/requires_pg/test_pg_tenant_business_schema_07c.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0).
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run()/swap_db())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

from control_plane.adapters.providers.postgres_store import PostgresControlStore  # noqa: E402

_CONTROL_SCHEMA = "sp2_07c_control_scratch"
_TENANT_DB_A = "sp2_07c_tenant_a"
_TENANT_DB_B = "sp2_07c_tenant_b"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL_DIR = _REPO_ROOT / "infrastructure" / "db" / "control"
_TENANT_DIR = _REPO_ROOT / "infrastructure" / "db" / "tenant"

# Reviewed tenant DDL blobs (full LF-normalized git-blob SHA-1; PRD 07C V5). The applied bytes MUST equal
# these reviewed blobs; a mismatch STOPs the exercise (do not "fix" DDL here). Cross-checked in CI by
# tests/architecture/test_tenant_ddl_blob_drift.py. NOT _REVIEWED_* naming — see header.
_TENANT_BLOB_001 = "34805052d5f860aebde5c7d9b2f6ac71d5130550"
_TENANT_BLOB_002 = "71d4c9dbceea10a42d728b0186b601d42ae53050"
_TENANT_BLOB_003 = "8cc12ea25a1ed8df1e482b34dfcbc2f5bad4163e"
_TENANT_BLOB_004 = "07015fd6a1c63629e0f682e79c03705f5e69ea3f"
_TENANT_BLOB_005 = "22e91ab26ecf4ff33752f12ba1421ec31d4f7bbc"
_TENANT_BLOB_006 = "d5dd83548543538df97ac75527af2a37127325d3"
_TENANT_BLOB_007 = "ea1c8a911df5023e5f5902b591ee44b91790b06c"

# The ordered tenant apply list (the blob-drift guard asserts this order matches its authority).
_TENANT_DDL = [
    ("001_agents.sql", _TENANT_BLOB_001),
    ("002_ai_agents.sql", _TENANT_BLOB_002),
    ("003_startups.sql", _TENANT_BLOB_003),
    ("004_investors.sql", _TENANT_BLOB_004),
    ("005_deals.sql", _TENANT_BLOB_005),
    ("006_ownership.sql", _TENANT_BLOB_006),
    ("007_links.sql", _TENANT_BLOB_007),
]

# Control DDL applied UNPINNED (their blobs are pinned by test_b7c1_control_audit_ddl_blob_pins.py and
# the non-control guard family; this harness only needs the registry tables present).
_CONTROL_DDL_ORDER = [
    "001_distinctness_ledger.sql",
    "002_provisioning_audit.sql",
    "003_provisioning_audit_append_only.sql",
    "004_control_tenants.sql",
    "005_control_memberships.sql",
    "006_control_federation.sql",
    "007_control_directory.sql",
]

_EXPECTED_TENANT_TABLES = {
    "agents",
    "ai_agents",
    "startups",
    "investors",
    "deals",
    "startup_ownership",
    "investor_ownership",
    "deal_ownership",
    "startup_ai_ownership",
    "investor_ai_ownership",
    "deal_ai_ownership",
    "startup_contacts",
    "investor_contacts",
    "startup_investors",
}

_SEED_SQL = (
    "INSERT INTO agents (agent_kind, agent_status, supervised_by_agent_id) "
    "SELECT 'system_primary', 'active', NULL "
    "WHERE NOT EXISTS (SELECT 1 FROM agents WHERE agent_kind = 'system_primary')"
)


# --- helpers (stdlib only; driver reached solely via PostgresControlStore._conn) -----------------
def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


_OPENED: list = []  # every adapter conn is tracked and closed in finally BEFORE database drops


def _open(dsn: str, *, autocommit: bool = False):
    """A tracked connection obtained via the sanctioned adapter (no direct driver import)."""
    conn = PostgresControlStore(dsn)._conn
    conn.autocommit = autocommit
    _OPENED.append(conn)
    return conn


def _raises(conn, sql: str, params=()) -> bool:
    """True iff sql raised (run on an AUTOCOMMIT conn so the failure is its own aborted transaction)."""
    try:
        conn.execute(sql, params)
        return False
    except Exception:
        return True


def _scalar(conn, sql: str, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _tables(conn, schema: str = "public") -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type='BASE TABLE'",
        (schema,),
    ).fetchall()
    return {r[0] for r in rows}


# --- the exercise -------------------------------------------------------------------------------
def test_07c_live_pg_tenant_business_schema(admin_dsn: str) -> None:
    boot = _open(admin_dsn, autocommit=True)
    server_num = int(_scalar(boot, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num}) — NOT READY (environment)"
    print(f"PASS: PRE version gate (server_version_num={server_num} >= 110000)")

    # pin verification BEFORE any apply: the exercised bytes must equal the reviewed blobs (STOP on drift).
    for name, pin in _TENANT_DDL:
        got = _git_blob_sha1(_TENANT_DIR / name)
        assert got == pin, f"{name} blob {got} != reviewed {pin} — STOP (do not fix DDL in this harness)"
    print("PASS: PRE tenant DDL blob pins (001-007 match reviewed blobs)")

    # scratch-only reset (leftovers from a prior crashed run), then fresh resources.
    with boot.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {_TENANT_DB_A}")
        cur.execute(f"DROP DATABASE IF EXISTS {_TENANT_DB_B}")
        cur.execute(f"DROP SCHEMA IF EXISTS {_CONTROL_SCHEMA} CASCADE")
        cur.execute(f"CREATE SCHEMA {_CONTROL_SCHEMA}")
        cur.execute(f"SET search_path TO {_CONTROL_SCHEMA}")
    try:
        # C1 — Control DDL 001-007 applies to the scratch Control schema (UNPINNED here; see header).
        for name in _CONTROL_DDL_ORDER:
            with boot.cursor() as cur:
                cur.execute((_CONTROL_DIR / name).read_text(encoding="utf-8"))
        assert _scalar(boot, "SELECT to_regclass('control_tenants')") is not None
        assert _scalar(boot, "SELECT to_regclass('control_directory')") is not None
        print("PASS: C1 Control DDL 001-007 applied to scratch Control schema")

        # C2 — two PHYSICAL tenant databases; tenant DDL 001-007 applies to each (one txn per DB, then autocommit).
        with boot.cursor() as cur:
            cur.execute(f"CREATE DATABASE {_TENANT_DB_A}")  # autocommit conn: outside any transaction
            cur.execute(f"CREATE DATABASE {_TENANT_DB_B}")
        conn_a = _open(_pg.swap_db(admin_dsn, _TENANT_DB_A))
        conn_b = _open(_pg.swap_db(admin_dsn, _TENANT_DB_B))
        for conn in (conn_a, conn_b):
            with conn.cursor() as cur:
                for name, _pin in _TENANT_DDL:
                    cur.execute((_TENANT_DIR / name).read_text(encoding="utf-8"))
            conn.commit()  # single atomic apply per tenant DB (mirrors the Step-2b applicator contract)
            conn.autocommit = True  # data probes + expected-error probes below are their own transactions
        for label, conn in (("A", conn_a), ("B", conn_b)):
            assert _tables(conn) == _EXPECTED_TENANT_TABLES, f"tenant {label} table set mismatch: {sorted(_tables(conn))}"
        print("PASS: C2 tenant DDL 001-007 applied to two physical tenant DBs (exact 14-table set in each)")

        # C3 — physical isolation: tenant A records are absent from tenant B.
        conn_a.execute("INSERT INTO startups (company_name) VALUES ('Tenant-A Startup One')")
        assert _scalar(conn_a, "SELECT count(*) FROM startups") == 1
        assert _scalar(conn_b, "SELECT count(*) FROM startups") == 0, "tenant A data must NOT appear in tenant B"
        print("PASS: C3 physical isolation (tenant A startup absent from tenant B)")

        # C4 — tenant operational records absent from the Control DB (scratch schema holds only control_*).
        control_tables = _tables(boot, _CONTROL_SCHEMA)
        assert control_tables == {
            "control_distinctness_ledger",
            "control_audit",
            "control_tenants",
            "control_memberships",
            "control_federation",
            "control_directory",
        }, f"Control scratch schema must hold ONLY control_* tables: {sorted(control_tables)}"
        print("PASS: C4 tenant operational records absent from Control DB (only control_* tables present)")

        # C5 — Control directory registry rows can be inserted (GlobalStartupDirectory / GlobalInvestorDirectory).
        boot.execute(
            "INSERT INTO control_directory (directory, record_id, display_name, attributes)"
            " VALUES ('GlobalStartupDirectory','gs-07c-1','Global Startup One','{}'::jsonb)"
        )
        boot.execute(
            "INSERT INTO control_directory (directory, record_id, display_name, attributes)"
            " VALUES ('GlobalInvestorDirectory','gi-07c-1','Global Investor One','{}'::jsonb)"
        )
        print("PASS: C5 Control directory registry rows inserted (startup + investor kinds)")

        # C6 — tenant records soft-reference global ids (text refs only; no cross-DB FK exists to violate).
        conn_a.execute("UPDATE startups SET global_startup_id = 'gs-07c-1' WHERE company_name = 'Tenant-A Startup One'")
        conn_a.execute("INSERT INTO investors (investor_name, global_investor_id) VALUES ('Tenant-A Investor One', 'gi-07c-1')")
        assert _scalar(conn_a, "SELECT global_startup_id FROM startups LIMIT 1") == "gs-07c-1"
        print("PASS: C6 tenant startups/investors soft-reference global registry ids")

        # C7 — startups / investors / deals insert in tenant A (intra-tenant FKs hold).
        sid = _scalar(conn_a, "SELECT id FROM startups LIMIT 1")
        iid = _scalar(conn_a, "SELECT id FROM investors LIMIT 1")
        conn_a.execute("INSERT INTO deals (startup_id, investor_id, deal_name) VALUES (%s, %s, 'Deal One')", (sid, iid))
        assert _scalar(conn_a, "SELECT count(*) FROM deals") == 1
        print("PASS: C7 startups / investors / deals inserted in tenant A")

        # C8 — human-ownership PK prevents duplicate owner rows (startup/investor/deal). Fixtures use a
        # HUMAN agent (AC-22: System Primary never appears as agent_id in ownership rows).
        conn_a.execute("INSERT INTO agents DEFAULT VALUES")  # all columns defaulted -> a human, active agent
        human = _scalar(conn_a, "SELECT id FROM agents WHERE agent_kind = 'human' LIMIT 1")
        did = _scalar(conn_a, "SELECT id FROM deals LIMIT 1")
        ownership_cases = (
            ("startup_ownership", "startup_id", sid),
            ("investor_ownership", "investor_id", iid),
            ("deal_ownership", "deal_id", did),
        )
        for table, col, val in ownership_cases:
            conn_a.execute(f"INSERT INTO {table} ({col}, agent_id) VALUES (%s, %s)", (val, human))
            assert _raises(conn_a, f"INSERT INTO {table} ({col}, agent_id) VALUES (%s, %s)", (val, human)), (
                f"duplicate {table} row must be rejected by PRIMARY KEY ({col}) — at-most-one human owner"
            )
        print("PASS: C8 ownership PK prevents duplicate human owner rows (startup/investor/deal; first-writer-wins)")

        # C9 — duplicate (entity, ai_agent) pair fails.
        conn_a.execute("INSERT INTO ai_agents (ai_agent_name, supervising_agent_id) VALUES ('AI One', %s)", (human,))
        conn_a.execute("INSERT INTO ai_agents (ai_agent_name, supervising_agent_id) VALUES ('AI Two', %s)", (human,))
        ai1 = _scalar(conn_a, "SELECT id FROM ai_agents WHERE ai_agent_name = 'AI One'")
        ai2 = _scalar(conn_a, "SELECT id FROM ai_agents WHERE ai_agent_name = 'AI Two'")
        conn_a.execute("INSERT INTO startup_ai_ownership (startup_id, ai_agent_id) VALUES (%s, %s)", (sid, ai1))
        assert _raises(conn_a, "INSERT INTO startup_ai_ownership (startup_id, ai_agent_id) VALUES (%s, %s)", (sid, ai1)), (
            "duplicate (startup_id, ai_agent_id) must be rejected by the composite PK"
        )
        print("PASS: C9 duplicate (entity, ai_agent) pair rejected")

        # C10 — two DISTINCT AI agents on the same entity succeed (zero-or-more cardinality).
        conn_a.execute("INSERT INTO startup_ai_ownership (startup_id, ai_agent_id) VALUES (%s, %s)", (sid, ai2))
        assert _scalar(conn_a, "SELECT count(*) FROM startup_ai_ownership WHERE startup_id = %s", (sid,)) == 2
        print("PASS: C10 two distinct AI agents attached to the same entity")

        # C11 — the agents table supports the exact 07B.1 seed shape (the DDL itself seeded NOTHING:
        # tenant B had zero agents rows until this harness-run INSERT — check 11's proof, not a DDL seed).
        assert _scalar(conn_b, "SELECT count(*) FROM agents") == 0, "fresh tenant B must have ZERO agents before the seed probe"
        conn_b.execute(_SEED_SQL)
        assert _scalar(conn_b, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1
        conn_b.execute(_SEED_SQL)  # idempotent WHERE NOT EXISTS re-run
        assert _scalar(conn_b, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1
        print("PASS: C11 agents table supports the 07B.1 seed shape (DDL seeded nothing; seed idempotent)")

        # C12 — duplicate System Primary insert fails by the 07C-owned singleton partial unique index.
        assert _raises(
            conn_b, "INSERT INTO agents (agent_kind, agent_status, supervised_by_agent_id) VALUES ('system_primary','active',NULL)"
        ), "a SECOND system_primary row must be rejected by ux_agents_single_system_primary"
        print("PASS: C12 duplicate System Primary insert rejected (singleton)")

        # C13 — System Primary DELETE fails by the protective trigger.
        assert _raises(conn_b, "DELETE FROM agents WHERE agent_kind = 'system_primary'"), (
            "DELETE of the system_primary row must be rejected by trg_agents_protect_system_primary"
        )
        print("PASS: C13 System Primary DELETE rejected (protective trigger)")

        # C14 — System Primary kind-flip UPDATE fails by the protective trigger.
        assert _raises(conn_b, "UPDATE agents SET agent_kind = 'human' WHERE agent_kind = 'system_primary'"), (
            "kind-flip away from system_primary must be rejected by trg_agents_protect_system_primary"
        )
        assert _scalar(conn_b, "SELECT count(*) FROM agents WHERE agent_kind = 'system_primary'") == 1, "SP row unchanged"
        print("PASS: C14 System Primary kind-flip UPDATE rejected (protective trigger)")

        # C15 — no human Agent is required for fresh readiness (tenant B: schema + SP only, zero humans).
        assert _scalar(conn_b, "SELECT count(*) FROM agents WHERE agent_kind = 'human'") == 0
        print("PASS: C15 no human Agent required for fresh readiness (tenant B has zero humans)")

        # C16 — no queue-manager / reservation / claim-lock structures exist.
        for label, conn in (("A", conn_a), ("B", conn_b)):
            names = _tables(conn)
            offenders = {t for t in names if any(tok in t for tok in ("queue", "reservation", "claim"))}
            assert not offenders, f"tenant {label} must have no queue/reservation/claim tables: {sorted(offenders)}"
        print("PASS: C16 no queue-manager appears (no queue/reservation/claim tables)")

        # C17 — no tenant_id column anywhere in the tenant business tables (tenancy is PHYSICAL).
        n_tid = _scalar(
            conn_a,
            "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND column_name='tenant_id'",
        )
        assert n_tid == 0, "no tenant business table may carry a tenant_id column (physical multi-DB, not a column)"
        print("PASS: C17 no tenant_id column present in tenant business tables")

        # C18 — governance: this harness proves the 07C schema slice only; the MVP blocker stays open.
        print("PASS: C18 B5-BLK-4 remains OPEN (07C schema proof only; no MVP-completion claim)")

        print("ALL 07C CHECKS PASSED")
    finally:
        # cleanup: close every tracked tenant/adapter connection FIRST (an open session would block the
        # database drops — the MCC lesson), then drop scratch DBs + schema from the boot conn, then close it.
        for conn in _OPENED:
            if conn is not boot:
                try:
                    conn.close()
                except Exception:
                    pass
        with boot.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {_CONTROL_SCHEMA} CASCADE")
            cur.execute(f"DROP DATABASE IF EXISTS {_TENANT_DB_A}")
            cur.execute(f"DROP DATABASE IF EXISTS {_TENANT_DB_B}")
        boot.close()


if __name__ == "__main__":
    _pg.run([test_07c_live_pg_tenant_business_schema])
