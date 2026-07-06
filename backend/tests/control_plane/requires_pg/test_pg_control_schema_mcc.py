"""MCC Control-DB registry schema — live-PostgreSQL proof (standalone-only; SNACKPORTAL_TEST_DSN).

The MCC live exercise for the created-not-applied Control-DB registry DDL
(infrastructure/db/control/004_control_tenants.sql, 005_control_memberships.sql,
006_control_federation.sql, 007_control_directory.sql — the wired-but-previously-DDL-less tables
postgres_store.py already targets). Against a real non-production PostgreSQL it pins the reviewed
DDL by git blob (Option P; MCC exec-auth V2 §15), applies control 001-007 inside a throwaway
scratch SCHEMA, and proves: table/column shapes and the all-text typing rule (created_at /
updated_at / expected_schema_version are text, NOT timestamptz / integer — MCC exec-auth V2 §9),
PK/conflict behavior, tenant_type DEFAULT + CHECK + the control_internal singleton, attributes
JSONB, NO cross-table FKs, idempotent re-apply, and — the wired-store proof — that the UNMODIFIED
PostgresControlStore now works against the new DDL for put_tenant/get_tenant, put_membership,
put_federation, and directory READS (AC-30/AC-31).

EXPECTED-FAILURE PROBE (MCC-AR-1). put_directory_record binds a plain Python dict for
`attributes`; psycopg 3 has no default dumper for dict, so the WRITE raises at the driver layer
before any SQL reaches PostgreSQL. That is a pre-existing runtime adapter defect independent of
this DDL (reads are unaffected: psycopg 3 natively loads jsonb -> dict). This harness asserts the
defect's CURRENT failure mode as documentation — follow-up "MCC-AR-1 — PostgresControlStore
Directory JSONB Adapter Fix" (wrap with psycopg Jsonb(...)) is deferred with the tenant_type
runtime plumbing and is NOT fixed here (MCC exec-auth V2 §13). When MCC-AR-1 lands, the probe
below FAILS (the write succeeds) and must be consciously updated in that PRD.

ISOLATION & SAFETY. Everything runs in a uniquely-named scratch schema
`sp2_mcc_control_schema_scratch` created at start and DROP SCHEMA ... CASCADE'd in a finally — it
never touches `public` or any real table, and never CREATE/DROP DATABASE. The DDL files in the
repo are never modified (read + blob-pinned only). 001-003 are applied first as prerequisites of
the 001-007 sequence (their blobs are pinned by their own harnesses and the static blob-pin
guard); 004-007 are pinned HERE under _REVIEWED_004_BLOB.._REVIEWED_007_BLOB, cross-checked by
tests/architecture/test_b7c1_control_audit_ddl_blob_pins.py in lockstep.

DRIVER CONTAINMENT. This file imports NO database driver. It reaches PostgreSQL only through the
control-plane adapter `PostgresControlStore` (whose psycopg import lives in the sanctioned
provider zone) via `store._conn`. Expected-error cases use AUTOCOMMIT isolation (each statement
is its own transaction; a rejected statement leaves the connection immediately usable).

SECRET HYGIENE (D-14). SNACKPORTAL_TEST_DSN is used by NAME only; its value is never printed,
logged, or written. Stored rows are asserted to contain no DSN/password substring.

DEFAULT SUITE / CI. IGNORED by the default test run (pyproject addopts
`--ignore=tests/control_plane/requires_pg`) and NOT wired into any .github workflow run-set (MCC
exec-auth V2 §16.3) — manual/local only. Run it by populating SNACKPORTAL_TEST_DSN (a
non-production admin DSN permitted to CREATE/DROP SCHEMA) and invoking:
  python backend/tests/control_plane/requires_pg/test_pg_control_schema_mcc.py
With SNACKPORTAL_TEST_DSN unset (or psycopg absent) it clean-skips (exit 0).
"""

from __future__ import annotations

import hashlib
import pathlib
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run())

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # backend on path

from control_plane._util import now_iso  # noqa: E402
from control_plane.adapters.providers.postgres_store import PostgresControlStore  # noqa: E402
from control_plane.records import (  # noqa: E402
    DirectoryKind,
    DirectoryRecord,
    FederationConfig,
    MembershipRecord,
    Role,
    TenantLifecycleState,
    TenantRecord,
)
from shared.secrets import SecretRef  # noqa: E402

_SCHEMA = "sp2_mcc_control_schema_scratch"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL_ORDER = [  # applied 001 -> 009 (001-003 prerequisites; 004-007 the MCC registry DDL; 009 the 07D-2e CAS version column)
    "001_distinctness_ledger.sql",
    "002_provisioning_audit.sql",
    "003_provisioning_audit_append_only.sql",
    "004_control_tenants.sql",
    "005_control_memberships.sql",
    "006_control_federation.sql",
    "007_control_directory.sql",
    "009_control_tenants_cas_version.sql",
]

# Reviewed MCC DDL blobs (full LF-normalized git-blob SHA-1; Option P — MCC exec-auth V2 §15). The applied
# bytes MUST equal these reviewed blobs; a mismatch STOPs the exercise (do not "fix" DDL here). The static
# guard test_b7c1_control_audit_ddl_blob_pins.py cross-checks these pins against the current DDL in CI.
_REVIEWED_004_BLOB = "8194408e62f08533e649612981f10089b8a3b1b0"
_REVIEWED_005_BLOB = "a0df9ec58b6825aa298b1b9656cc0028d9831c14"
_REVIEWED_006_BLOB = "c929af89da85ec7614b716bdb40af611da9613f2"
_REVIEWED_007_BLOB = "aa6066a7398cfb81e8e96067927023c3f11bb391"
# PRD 07D-2e: the control_tenants CAS version column (R-2c-LWW closure) — same lockstep pattern.
_REVIEWED_009_BLOB = "64f8227e829d446a74efeb3784e06b0e28f47549"
_MCC_PINS = [
    ("004_control_tenants.sql", _REVIEWED_004_BLOB),
    ("005_control_memberships.sql", _REVIEWED_005_BLOB),
    ("006_control_federation.sql", _REVIEWED_006_BLOB),
    ("007_control_directory.sql", _REVIEWED_007_BLOB),
    ("009_control_tenants_cas_version.sql", _REVIEWED_009_BLOB),
]

# The exact table set 001-007 creates — proves NO tenant-business / agents / sharing / global_* tables.
_EXPECTED_TABLES = {
    "control_distinctness_ledger",
    "control_audit",
    "control_tenants",
    "control_memberships",
    "control_federation",
    "control_directory",
}

_TENANTS_COLS = [
    "tenant_id",
    "organization_ref",
    "lifecycle_state",
    "expected_schema_version",
    "assoc_store_ref",
    "assoc_version",
    "federation_config_ref",
    "created_at",
    "updated_at",
    "tenant_type",
    "version",  # PRD 07D-2e (009): bigint CAS write-version — the ONE non-text column
]
_MEMBERSHIPS_COLS = ["principal_ref", "tenant_id", "role"]
_FEDERATION_COLS = ["tenant_id", "oidc_issuer", "oidc_audience", "jwks_ref", "claim_to_tenant_rule"]
_DIRECTORY_COLS = ["directory", "record_id", "display_name", "attributes"]


# --- helpers (stdlib only; driver reached solely via PostgresControlStore._conn) -----------------
def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _store(dsn: str, *, autocommit: bool = False) -> PostgresControlStore:
    """A control-plane store whose session search_path is the scratch schema ONLY (so a missing
    table fails closed instead of resolving public)."""
    s = PostgresControlStore(dsn)
    if autocommit:
        s._conn.autocommit = True
    with s._conn.cursor() as cur:
        cur.execute(f"SET search_path TO {_SCHEMA}")
    if not autocommit:
        s._conn.commit()
    return s


def _raises(conn, sql: str, params=()) -> bool:
    """True iff `sql` raised. Autocommit isolation: a rejected statement is its own aborted
    single-statement transaction, so the connection stays usable for the next statement."""
    try:
        conn.execute(sql, params)
        return False
    except Exception:
        return True


def _scalar(conn, sql: str, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _columns(conn, table: str):
    """(name, data_type, is_nullable, is_identity, column_default) per column, ordinal order."""
    return conn.execute(
        "SELECT column_name, data_type, is_nullable, is_identity, column_default "
        "FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (_SCHEMA, table),
    ).fetchall()


def _pk_columns(conn, table: str):
    return [
        r[0]
        for r in conn.execute(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
            "AND tc.table_schema=kcu.table_schema WHERE tc.table_schema=%s AND tc.table_name=%s "
            "AND tc.constraint_type='PRIMARY KEY' ORDER BY kcu.ordinal_position",
            (_SCHEMA, table),
        ).fetchall()
    ]


def _tenant(tid: str, org: str = "org-ref-1", created: str | None = None, updated: str | None = None) -> TenantRecord:
    ts = now_iso()
    return TenantRecord(
        tenant_id=tid,
        organization_ref=org,
        lifecycle_state=TenantLifecycleState.REGISTERED,
        expected_schema_version="v1",  # deliberately NON-numeric: proves text (not integer) typing
        database_association_ref=SecretRef(store_ref="tenant/mcc-assoc-ref", version="1"),
        federation_config_ref="fed-ref-1",
        created_at=created or ts,
        updated_at=updated or ts,
    )


# --- the exercise -------------------------------------------------------------------------------
def test_mcc_live_pg_control_schema(admin_dsn: str) -> None:
    # C1 — PostgreSQL version gate (>= 11; consistent with the B-7A control harness)
    boot = _store(admin_dsn, autocommit=True)
    conn = boot._conn
    server_num = int(_scalar(conn, "SELECT current_setting('server_version_num')"))
    assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num}) — NOT READY (environment)"
    print(f"PASS: C1 version gate (server_version_num={server_num} >= 110000)")

    # fresh scratch schema (drop any leftover from a prior crashed run — scratch-only reset)
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        cur.execute(f"CREATE SCHEMA {_SCHEMA}")
        cur.execute(f"SET search_path TO {_SCHEMA}")
    # Adapter stores opened during checks are tracked so the finally can close them BEFORE the schema
    # drop — an orphaned idle-in-transaction session would otherwise block DROP SCHEMA ... CASCADE forever.
    _opened: list[PostgresControlStore] = []
    try:
        # C2 — table-absent precondition for all four MCC tables
        for t in ("control_tenants", "control_memberships", "control_federation", "control_directory"):
            assert _scalar(conn, f"SELECT to_regclass('{t}')") is None, f"{t} must be ABSENT before apply"
        print("PASS: C2 table-absent precondition (all four MCC tables NULL in scratch schema)")

        # C3 — DDL blob pins (Option P): applied 004-007 bytes == reviewed blobs
        for name, reviewed in _MCC_PINS:
            got = _git_blob_sha1(_CONTROL / name)
            assert got == reviewed, f"{name} blob {got} != reviewed {reviewed} — STOP (do not fix DDL in this harness)"
        print("PASS: C3 DDL blob pins (004-007 match reviewed blobs)")

        # C4 — apply 001 -> 007 in order (read from the repo files; never modified); exact table set
        for name in _DDL_ORDER:
            with conn.cursor() as cur:
                cur.execute((_CONTROL / name).read_text(encoding="utf-8"))
        tables = {
            r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s", (_SCHEMA,)).fetchall()
        }
        assert tables == _EXPECTED_TABLES, f"scratch table set {sorted(tables)} != expected {sorted(_EXPECTED_TABLES)}"
        print(f"PASS: C4 DDL apply 001-007 (exact table set = {len(_EXPECTED_TABLES)} control_* tables; no business/agents/global tables)")

        # C5 — control_tenants shape: columns/order, text typing (version bigint — PRD 07D-2e),
        # NOT NULL, tenant_type default, version default 0, PK, no identity/id
        cols = _columns(conn, "control_tenants")
        names = [c[0] for c in cols]
        assert names == _TENANTS_COLS, f"control_tenants columns {names} != {_TENANTS_COLS}"
        for cname, dtype, nullable, identity, _default in cols:
            want = "bigint" if cname == "version" else "text"  # 07D-2e: version is the ONE non-text column
            assert dtype == want, f"control_tenants.{cname} must be {want}; got {dtype}"
            assert nullable == "NO", f"control_tenants.{cname} must be NOT NULL"
            assert identity == "NO", f"control_tenants.{cname} must not be IDENTITY"
        meta = {c[0]: c for c in cols}
        assert "timestamp" not in meta["created_at"][1] and "timestamp" not in meta["updated_at"][1], (
            "created_at/updated_at must be text, NOT timestamptz (unmodified-adapter str round-trip)"
        )
        assert meta["expected_schema_version"][1] == "text", "expected_schema_version must be text, NOT integer"
        assert "customer" in (meta["tenant_type"][4] or ""), f"tenant_type default must be 'customer'; got {meta['tenant_type'][4]!r}"
        assert "0" in (meta["version"][4] or ""), f"version default must be 0 (PRD 07D-2e); got {meta['version'][4]!r}"
        assert _pk_columns(conn, "control_tenants") == ["tenant_id"], "control_tenants PK must be (tenant_id)"
        assert "id" not in names, "no surrogate id column (natural keys only)"
        idx = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname=%s AND tablename='control_tenants'", (_SCHEMA,)
            ).fetchall()
        }
        singleton = idx.get("ux_control_tenants_single_control_internal", "")
        assert singleton and "control_internal" in singleton and "WHERE" in singleton, (
            f"partial unique singleton index missing/wrong: {sorted(idx)}"
        )
        print(
            "PASS: C5 control_tenants shape (10 text cols + version bigint DEFAULT 0, all NOT NULL, "
            "DEFAULT 'customer', PK(tenant_id), singleton partial index)"
        )

        # C6 — control_memberships / control_federation / control_directory shapes
        for table, expected_cols, pk in (
            ("control_memberships", _MEMBERSHIPS_COLS, ["principal_ref", "tenant_id"]),
            ("control_federation", _FEDERATION_COLS, ["tenant_id"]),
            ("control_directory", _DIRECTORY_COLS, ["directory", "record_id"]),
        ):
            cols = _columns(conn, table)
            names = [c[0] for c in cols]
            assert names == expected_cols, f"{table} columns {names} != {expected_cols}"
            for cname, dtype, nullable, identity, _default in cols:
                want = "jsonb" if (table, cname) == ("control_directory", "attributes") else "text"
                assert dtype == want, f"{table}.{cname} must be {want}; got {dtype}"
                assert nullable == "NO", f"{table}.{cname} must be NOT NULL"
                assert identity == "NO", f"{table}.{cname} must not be IDENTITY"
            assert _pk_columns(conn, table) == pk, f"{table} PK must be {pk}"
        print("PASS: C6 memberships/federation/directory shapes (text + jsonb attributes; PKs match wired conflict targets)")

        # C7 — NO cross-table FK on any of the four MCC tables (exec-auth V2 §11)
        for t in ("control_tenants", "control_memberships", "control_federation", "control_directory"):
            fks = _scalar(conn, "SELECT count(*) FROM pg_constraint WHERE conrelid = %s::regclass AND contype='f'", (f"{_SCHEMA}.{t}",))
            assert fks == 0, f"{t} must have NO foreign keys; got {fks}"
        print("PASS: C7 no cross-table FKs (all four tables; store-parity pin)")

        # C8 — tenant_type behavior (direct SQL; adapter is tenant_type-agnostic by design in MCC)
        conn.execute(
            "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version,"
            " assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at)"
            " VALUES ('mcc-default-t','org','Registered','v1','ref','1','fed', %s, %s)",
            (now_iso(), now_iso()),
        )
        assert _scalar(conn, "SELECT tenant_type FROM control_tenants WHERE tenant_id='mcc-default-t'") == "customer", (
            "tenant_type DEFAULT must yield 'customer' when the INSERT omits it (the unmodified-adapter path)"
        )
        assert _raises(
            conn,
            "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version,"
            " assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at, tenant_type)"
            " VALUES ('mcc-bogus-t','org','Registered','v1','ref','1','fed', %s, %s, 'bogus')",
            (now_iso(), now_iso()),
        ), "tenant_type CHECK must reject values outside ('customer','control_internal')"
        conn.execute(
            "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version,"
            " assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at, tenant_type)"
            " VALUES ('mcc-control-internal','org-control','Registered','v1','ref','1','fed', %s, %s, 'control_internal')",
            (now_iso(), now_iso()),
        )
        assert _raises(
            conn,
            "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version,"
            " assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at, tenant_type)"
            " VALUES ('mcc-control-internal-2','org','Registered','v1','ref','1','fed', %s, %s, 'control_internal')",
            (now_iso(), now_iso()),
        ), "a SECOND control_internal row must be rejected by the singleton partial unique index"
        n_ci = _scalar(conn, "SELECT count(*) FROM control_tenants WHERE tenant_type='control_internal'")
        assert n_ci == 1, f"exactly one control_internal row must exist; got {n_ci}"
        conn.execute(
            "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version,"
            " assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at)"
            " VALUES ('mcc-customer-2','org2','Registered','v1','ref','1','fed', %s, %s)",
            (now_iso(), now_iso()),
        )
        assert _scalar(conn, "SELECT count(*) FROM control_tenants WHERE tenant_type='customer'") >= 2, (
            "multiple customer tenants must be allowed"
        )
        print(
            "PASS: C8 tenant_type (DEFAULT 'customer'; CHECK rejects invalid; control_internal singleton enforced; multiple customers OK)"
        )

        # C9 — PK/duplicate rejection (direct SQL; plain duplicate INSERTs without ON CONFLICT must raise)
        conn.execute("INSERT INTO control_memberships (principal_ref, tenant_id, role) VALUES ('p1','mcc-default-t','CONTROL')")
        assert _raises(
            conn, "INSERT INTO control_memberships (principal_ref, tenant_id, role) VALUES ('p1','mcc-default-t','TENANT_AGENT')"
        ), "duplicate (principal_ref, tenant_id) must be rejected by the composite PK"
        conn.execute(
            "INSERT INTO control_federation (tenant_id, oidc_issuer, oidc_audience, jwks_ref, claim_to_tenant_rule)"
            " VALUES ('mcc-default-t','iss','aud','jwks-ref','rule')"
        )
        assert _raises(
            conn,
            "INSERT INTO control_federation (tenant_id, oidc_issuer, oidc_audience, jwks_ref, claim_to_tenant_rule)"
            " VALUES ('mcc-default-t','iss2','aud2','jwks-ref2','rule2')",
        ), "duplicate control_federation tenant_id must be rejected by the PK"
        conn.execute(
            "INSERT INTO control_directory (directory, record_id, display_name, attributes)"
            " VALUES ('GlobalStartupDirectory','dup-1','Dup', '{}'::jsonb)"
        )
        assert _raises(
            conn,
            "INSERT INTO control_directory (directory, record_id, display_name, attributes)"
            " VALUES ('GlobalStartupDirectory','dup-1','Dup2', '{}'::jsonb)",
        ), "duplicate (directory, record_id) must be rejected by the composite PK"
        print("PASS: C9 PK/duplicate rejection (memberships composite, federation single, directory composite)")

        # C10 — UNMODIFIED adapter proof (AC-30): tenant round-trip + upsert; membership; federation
        store = _store(admin_dsn)  # real adapter path (non-autocommit; put_* commit)
        _opened.append(store)
        t1 = _tenant("mcc-adapter-t1")
        store.put_tenant(t1)
        got = store.get_tenant("mcc-adapter-t1")
        assert got is not None, "get_tenant must read back the row the unmodified adapter wrote"
        assert got == t1, f"TenantRecord round-trip mismatch: {got!r} != {t1!r}"
        for fname in ("expected_schema_version", "created_at", "updated_at"):
            assert isinstance(getattr(got, fname), str), f"TenantRecord.{fname} must round-trip as str (text typing proof)"
        assert got.lifecycle_state is TenantLifecycleState.REGISTERED and got.database_association_ref == SecretRef(
            "tenant/mcc-assoc-ref", "1"
        )
        assert _scalar(conn, "SELECT tenant_type FROM control_tenants WHERE tenant_id='mcc-adapter-t1'") == "customer", (
            "the unmodified adapter INSERT (omitting tenant_type) must land tenant_type='customer' via the DDL default"
        )
        # The adapter's DO UPDATE deliberately does NOT touch created_at, so the upsert record must share
        # t1's created_at — the round-trip equality below then also PROVES created_at is preserved.
        t1b = _tenant("mcc-adapter-t1", org="org-ref-1-updated", created=t1.created_at, updated=now_iso())
        store.put_tenant(t1b)  # ON CONFLICT (tenant_id) DO UPDATE path
        again = store.get_tenant("mcc-adapter-t1")
        assert again == t1b and _scalar(conn, "SELECT count(*) FROM control_tenants WHERE tenant_id='mcc-adapter-t1'") == 1, (
            "put_tenant upsert must update in place (1 row, new values, created_at preserved)"
        )
        assert "mcc-adapter-t1" in store.list_tenant_ids(), "list_tenant_ids must include the adapter-written tenant"
        store.put_membership(MembershipRecord(principal_ref="mcc-p1", tenant_id="mcc-adapter-t1", role=Role.TENANT_ADMIN))
        store.put_membership(MembershipRecord(principal_ref="mcc-p1", tenant_id="mcc-adapter-t1", role=Role.TENANT_AGENT))  # upsert
        ms = store.list_memberships(principal_ref="mcc-p1", tenant_id="mcc-adapter-t1")
        assert len(ms) == 1 and ms[0].role is Role.TENANT_AGENT, f"membership upsert round-trip failed: {ms!r}"
        fed = FederationConfig(
            tenant_id="mcc-adapter-t1",
            oidc_issuer="https://iss.example",
            oidc_audience="aud",
            jwks_ref="jwks-ref",
            claim_to_tenant_rule="rule",
        )
        store.put_federation(fed)
        fed2 = FederationConfig(
            tenant_id="mcc-adapter-t1",
            oidc_issuer="https://iss2.example",
            oidc_audience="aud2",
            jwks_ref="jwks-ref2",
            claim_to_tenant_rule="rule2",
        )
        store.put_federation(fed2)  # upsert
        gotfed = store.get_federation("mcc-adapter-t1")
        assert gotfed == fed2, f"federation upsert round-trip failed: {gotfed!r}"
        store._conn.close()
        print("PASS: C10 unmodified-adapter proof (tenant str round-trip + DEFAULT tenant_type; tenant/membership/federation upserts)")

        # C11 — directory READ proof (AC-31): direct-SQL seed with VALID DirectoryKind values, adapter reads
        conn.execute(
            "INSERT INTO control_directory (directory, record_id, display_name, attributes)"
            " VALUES ('GlobalStartupDirectory','mcc-gs-1','MCC Startup One', '{\"sector\": \"fintech\", \"stage\": \"seed\"}'::jsonb)"
        )
        conn.execute(
            "INSERT INTO control_directory (directory, record_id, display_name, attributes)"
            " VALUES ('GlobalInvestorDirectory','mcc-gi-1','MCC Investor One', '{}'::jsonb)"
        )
        reader = _store(admin_dsn)
        _opened.append(reader)
        rec = reader.get_directory_record(DirectoryKind.STARTUP, "mcc-gs-1")
        assert rec is not None and rec.display_name == "MCC Startup One", f"adapter directory read failed: {rec!r}"
        assert rec.attributes == {"sector": "fintech", "stage": "seed"}, f"jsonb -> dict read must round-trip: {rec.attributes!r}"
        assert rec.directory is DirectoryKind.STARTUP
        inv = reader.list_directory(DirectoryKind.INVESTOR)
        assert [r.record_id for r in inv] == ["mcc-gi-1"] and inv[0].attributes == {}, f"list_directory(INVESTOR) mismatch: {inv!r}"
        reader._conn.close()
        print("PASS: C11 directory READ proof (direct-SQL seed; unmodified adapter get_directory_record + list_directory; jsonb->dict)")

        # C12 — EXPECTED-FAILURE probe (MCC-AR-1): put_directory_record dict->jsonb write defect.
        # psycopg 3 has no default dumper for dict; the write raises CLIENT-SIDE before any SQL is sent.
        # NOT a DDL defect — do NOT fix here. When MCC-AR-1 (Jsonb(...) wrap) lands, this probe FAILS and
        # must be consciously updated in that PRD.
        probe = _store(admin_dsn)
        _opened.append(probe)
        n_dir_before = _scalar(conn, "SELECT count(*) FROM control_directory")
        probe_raised, probe_msg = False, ""
        try:
            probe.put_directory_record(
                DirectoryRecord(directory=DirectoryKind.STARTUP, record_id="mcc-ar1-probe", display_name="Probe", attributes={"k": "v"})
            )
        except Exception as exc:  # driver-layer adaptation error (no SQL reached the server)
            probe_raised, probe_msg = True, str(exc)
        probe._conn.close()
        assert probe_raised, (
            "put_directory_record with dict attributes must CURRENTLY fail (MCC-AR-1 open); if it passes, MCC-AR-1 landed: update probe"
        )
        assert "adapt" in probe_msg.lower(), f"expected the dict-adaptation driver error, got a different failure: {probe_msg}"
        assert _scalar(conn, "SELECT count(*) FROM control_directory") == n_dir_before, (
            "the failed write must leave NO row (client-side failure; nothing sent)"
        )
        print("PASS: C12 expected-failure probe (put_directory_record dict->jsonb raises at driver; no row written; MCC-AR-1)")

        # C13 — idempotency PROVEN: re-apply 004-007; rows preserved; CHECK + singleton still enforcing
        rows_before = {
            t: _scalar(conn, f"SELECT count(*) FROM {t}")
            for t in ("control_tenants", "control_memberships", "control_federation", "control_directory")
        }
        for name in _DDL_ORDER[3:]:
            with conn.cursor() as cur:
                cur.execute((_CONTROL / name).read_text(encoding="utf-8"))  # CREATE ... IF NOT EXISTS — must not error
        for t, n in rows_before.items():
            assert _scalar(conn, f"SELECT count(*) FROM {t}") == n, f"re-applying DDL must preserve {t} rows"
        assert _raises(
            conn,
            "INSERT INTO control_tenants (tenant_id, organization_ref, lifecycle_state, expected_schema_version,"
            " assoc_store_ref, assoc_version, federation_config_ref, created_at, updated_at, tenant_type)"
            " VALUES ('mcc-ci-again','org','Registered','v1','ref','1','fed', %s, %s, 'control_internal')",
            (now_iso(), now_iso()),
        ), "after re-apply, the control_internal singleton must still enforce"
        print("PASS: C13 idempotency (re-apply 004-007 clean; rows preserved; singleton still enforcing)")

        # C14 — secret hygiene (D-14): no DSN/password substring in any stored cell of the four tables
        p = urlsplit(admin_dsn)
        leak = [s for s in (admin_dsn, p.password or "") if s]
        for t in ("control_tenants", "control_memberships", "control_federation", "control_directory"):
            for row in conn.execute(f"SELECT * FROM {t}").fetchall():
                for cell in row:
                    for secret in leak:
                        assert secret not in str(cell), f"stored cell in {t} must not contain the DSN/password (references-only)"
        print("PASS: C14 secret hygiene (no DSN/password substring in any stored cell)")

        print("ALL MCC CHECKS PASSED")
    finally:
        # cleanup: close any adapter store left open by a failed check FIRST (an orphaned
        # idle-in-transaction session would block the DROP SCHEMA below), then drop the scratch
        # schema (DROP SCHEMA CASCADE; never DELETE/TRUNCATE); scratch-only.
        for s in _opened:
            try:
                if s._conn_cache is not None:  # lazy cache only — never open a NEW connection here
                    s._conn_cache.close()
            except Exception:
                pass  # already closed / already broken — cleanup must not mask the real failure
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        conn.close()


if __name__ == "__main__":
    _pg.run([test_mcc_live_pg_control_schema])
