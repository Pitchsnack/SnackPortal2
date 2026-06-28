"""Provisioning DDL templates — live-PostgreSQL coverage (standalone-only; SNACKPORTAL_TEST_DSN).

PRD 06 ATR-4 — Provisioning DDL Live Harness Coverage. The three provisioning templates in
``infrastructure/db/provisioning/`` are today applied by NO runtime code and NO test: the
``PostgresProvisioningOperator`` only ``CREATE``/``DROP DATABASE``; the distinctness provider applies
its OWN embedded sentinel DDL (``postgres_distinctness.py``), not ``002``; the probe only READS
``schema_version``. This harness closes that gap on the test side: against a real, disposable cluster
it pins each template by git blob and proves it applies cleanly, is idempotent, and satisfies the
runtime's BEHAVIORAL expectations.

WHAT EACH TEMPLATE IS (and where it lands):

* ``001_tenant_database.sql`` — a tenant-DB table (``schema_version``). The control-plane probe reads
  ``SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1`` (D-17). Applied to a SCRATCH
  DATABASE here.
* ``002_distinctness_sentinel.sql`` — a tenant-DB schema + table (``dv_sentinel.marker``). The
  distinctness verifier writes a unique token (``INSERT … ON CONFLICT (ns) …``) and reads it back.
  Applied to the SAME SCRATCH DATABASE (002 hard-codes the literal ``dv_sentinel`` schema, so a scratch
  *schema* would not isolate it — a scratch *database* does).
* ``003_provisioning_role.sql`` — a CLUSTER-level role (``sp2_provisioner``: ``NOLOGIN`` + ``CREATEDB``).
  Roles are cluster-scoped, not database-scoped, so this is applied against the admin connection and the
  role is ``DROP``ed at start and in ``finally``. AT-2 (PRD 06) asserts the full **least-privilege** vector
  — CREATEDB on, and ``rolsuper``/``rolcreaterole``/``rolreplication``/``rolbypassrls``/``rolcanlogin`` all
  OFF — so a privilege-escalation edit to ``003`` (e.g. an added SUPERUSER) fails closed.

ISOLATION & SAFETY. 001/002 run inside a uniquely-named scratch DATABASE
(``sp2_atr4_prov_scratch``) created and ``DROP DATABASE IF EXISTS``'d (autocommit) — it never touches a
real database. 003's cluster role ``sp2_provisioner`` is ``DROP``ed at start and in ``finally``. The
``.sql`` files in the repo are never modified (read + git-blob-pinned only). The DSN must be a
superuser/admin connection permitted to ``CREATE``/``DROP DATABASE`` and ``CREATE``/``DROP ROLE``
(003 needs ``CREATEROLE``); the ephemeral CI service runs as the ``postgres`` superuser under trust auth.

INDEPENDENCE. The three templates are independent (001/002 are database-scoped; 003 is a cluster role);
each is asserted to apply cleanly + idempotently on its own — no ordered dependency is claimed (the
README "apply in order" is a convention, not a dependency).

DRIVER CONTAINMENT. This file imports NO database driver statically. It reaches psycopg only through a
runtime ``importlib.import_module("psycopg")`` after a DSN check — so the default-suite
``tests/architecture/test_vendor_and_db_containment.py`` (which AST-scans for static driver imports) is
not tripped.

BLOB PINS. The applied bytes MUST equal the reviewed-and-merged blobs (LF-normalized git-blob SHA-1);
a mismatch FAILs the harness (do not "fix" the DDL here). The pin variables are named
``_PROVISIONING_DDL_SHA_00N`` (NOT ``_REVIEWED_*_BLOB``) so the Control-DB-only B-7C-1R2 pin-completeness
meta-guard (``test_b7c1r2_control_ddl_pin_completeness.py``) is not tripped — provisioning DDL is a
distinct, db/provisioning-scoped concern.

SECRET HYGIENE (D-14). ``SNACKPORTAL_TEST_DSN`` is used by NAME only; its value is never printed or
stored. 003's role is ``NOLOGIN`` (no password is created); no row written here holds a DSN/secret.

DEFAULT SUITE. IGNORED by the default test run (pyproject ``addopts
--ignore=tests/control_plane/requires_pg``). Run it for the ATR-4 exercise by populating
``SNACKPORTAL_TEST_DSN`` (a non-production admin DSN) in the environment and invoking:
  python backend/tests/control_plane/requires_pg/test_pg_provisioning_ddl.py
With ``SNACKPORTAL_TEST_DSN`` unset (or psycopg absent) it clean-skips (exit 0).

BOUNDARY. ATR-4 proves the templates APPLY + are IDEMPOTENT + behave as the runtime expects on ONE
ephemeral cluster. It does NOT activate runtime provisioning, does NOT wire the ``postgres`` adapter,
does NOT exercise the Database Router, and does NOT prove tenant physical multi-DB routing/isolation
(that needs >=2 distinct clusters — what ``test_b3a_multi_database_topology.py`` is for). B5-BLK-4
remains OPEN; the Physical Multi-Database MVP remains mandatory.
"""

from __future__ import annotations

import hashlib
import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _pg  # noqa: E402  (standalone live-PG runner: SNACKPORTAL_TEST_DSN, available()/run())

_PROVISIONING = pathlib.Path(__file__).resolve().parents[4] / "infrastructure" / "db" / "provisioning"
_DDL_001 = _PROVISIONING / "001_tenant_database.sql"
_DDL_002 = _PROVISIONING / "002_distinctness_sentinel.sql"
_DDL_003 = _PROVISIONING / "003_provisioning_role.sql"

# Reviewed-and-merged provisioning DDL blobs (full LF-normalized git-blob SHA-1; PRD 06 ATR-4). The
# applied bytes MUST equal these; a mismatch STOPs the exercise (do not "fix" DDL here). NOT named
# _REVIEWED_*_BLOB on purpose (that pattern is the Control-DB-only b7c1r2 meta-guard's subject; these
# are db/provisioning-scoped).
_PROVISIONING_DDL_SHA_001 = "d3073e82a6b9b5dc3bc9774201c6932c956a6897"
_PROVISIONING_DDL_SHA_002 = "04b1401de262320e140d79f5133051f41ff92693"
_PROVISIONING_DDL_SHA_003 = "2564826cc2d00b63b2edf0c7f88fc2c88bcc853b"

_SCRATCH_DB = "sp2_atr4_prov_scratch"
_PROV_ROLE = "sp2_provisioner"

# Behavioral parity strings (the EXACT runtime ops; written inline rather than imported from the
# provider modules, so this stays behavioral and not coupled to the provider's embedded DDL constants).
_SCHEMA_VERSION_PROBE = "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"  # postgres_probe
_SENTINEL_NS = "atr4_probe_ns"
_SENTINEL_TOKEN = "atr4_probe_token"  # not a secret — a deterministic round-trip marker
_SENTINEL_WRITE = (
    "INSERT INTO dv_sentinel.marker (ns, token) VALUES (%s, %s) ON CONFLICT (ns) DO UPDATE SET token = EXCLUDED.token, written_at = now()"
)
_SENTINEL_READ = "SELECT token FROM dv_sentinel.marker WHERE ns = %s"


# --- helpers (stdlib only; driver reached solely via importlib.import_module) --------------------
def _psycopg():
    """The database driver, located at call time (no static import — Driver Containment Standard)."""
    return importlib.import_module("psycopg")


def _git_blob_sha1(path: pathlib.Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")  # autocrlf normalization (the git blob is LF)
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _scalar(conn, sql: str, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _apply(conn, ddl_path: pathlib.Path) -> None:
    """Apply a template's full text (read + never modified) in a single statement batch."""
    with conn.cursor() as cur:
        cur.execute(ddl_path.read_text(encoding="utf-8"))


def _assert_blob(ddl_path: pathlib.Path, expected: str) -> None:
    actual = _git_blob_sha1(ddl_path)
    assert actual == expected, f"{ddl_path.name} blob {actual} != reviewed {expected} — STOP (do not fix DDL in ATR-4)"


# AT-2 (PRD 06) — sp2_provisioner least-privilege vector. The role needs ONLY CREATEDB; every elevated
# attribute must be OFF. Asserting the NEGATIVE attributes (not just the positive ones) is what catches a
# privilege-escalation edit to 003_provisioning_role.sql (e.g. an added SUPERUSER/CREATEROLE).
_LEAST_PRIV_QUERY = (
    "SELECT rolcreatedb, rolcanlogin, rolsuper, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname = %s"
)
_LEAST_PRIV_LABELS = ("rolcreatedb", "rolcanlogin", "rolsuper", "rolcreaterole", "rolreplication", "rolbypassrls")
_EXPECTED_ROLE_ATTRS = (True, False, False, False, False, False)  # CREATEDB only; no super/createrole/replication/bypassrls


def _assert_least_privilege(attrs) -> None:
    actual = tuple(attrs)
    assert actual == _EXPECTED_ROLE_ATTRS, (
        "sp2_provisioner least-privilege violated: "
        + ", ".join(f"{label}={value!r}" for label, value in zip(_LEAST_PRIV_LABELS, actual))
        + f"; expected {dict(zip(_LEAST_PRIV_LABELS, _EXPECTED_ROLE_ATTRS))}"
    )


# --- the exercise --------------------------------------------------------------------------------
def test_provisioning_001_002_tenant_db(admin_dsn: str) -> None:
    """001 (schema_version) + 002 (dv_sentinel.marker) applied to a SCRATCH DATABASE; behavioral +
    idempotent + non-vacuous. These are the two tenant-DB templates."""
    psycopg = _psycopg()

    # blob pins (applied bytes == reviewed blobs) — before any apply
    _assert_blob(_DDL_001, _PROVISIONING_DDL_SHA_001)
    _assert_blob(_DDL_002, _PROVISIONING_DDL_SHA_002)
    print(f"PASS: 001/002 blob pins (001={_PROVISIONING_DDL_SHA_001[:12]}…, 002={_PROVISIONING_DDL_SHA_002[:12]}…)")

    admin = psycopg.connect(admin_dsn)
    admin.autocommit = True  # CREATE/DROP DATABASE cannot run inside a transaction block
    try:
        server_num = int(_scalar(admin, "SELECT current_setting('server_version_num')"))
        assert server_num >= 110000, f"PostgreSQL >= 11 required (server_version_num={server_num}) — NOT READY (environment)"
        print(f"PASS: version gate (server_version_num={server_num} >= 110000)")

        # fresh scratch DATABASE (drop any leftover from a prior crashed run first)
        admin.execute(f"DROP DATABASE IF EXISTS {_SCRATCH_DB}")
        admin.execute(f"CREATE DATABASE {_SCRATCH_DB}")
        scratch = psycopg.connect(_pg.swap_db(admin_dsn, _SCRATCH_DB))
        scratch.autocommit = True
        try:
            # non-vacuity precondition: a fresh DB has neither object (so a no-op cannot masquerade as PASS)
            assert _scalar(scratch, "SELECT to_regclass('schema_version')") is None, "schema_version must be ABSENT before apply"
            assert _scalar(scratch, "SELECT to_regclass('dv_sentinel.marker')") is None, "dv_sentinel.marker must be ABSENT before apply"
            print("PASS: non-vacuity precondition (schema_version + dv_sentinel.marker ABSENT in fresh scratch DB)")

            # apply 001 then 002 (independent; order here is incidental, not a dependency)
            _apply(scratch, _DDL_001)
            _apply(scratch, _DDL_002)
            assert _scalar(scratch, "SELECT to_regclass('schema_version')") is not None, "schema_version must exist after apply"
            assert _scalar(scratch, "SELECT to_regclass('dv_sentinel.marker')") is not None, "dv_sentinel.marker must exist after apply"
            print("PASS: 001/002 apply (schema_version + dv_sentinel.marker created cleanly)")

            # behavioral 001 — the EXACT control-plane probe query returns the seeded version '1'
            observed = _scalar(scratch, _SCHEMA_VERSION_PROBE)
            assert str(observed) == "1", f"probe query must observe seeded version '1'; got {observed!r}"
            print("PASS: 001 behavioral (probe 'SELECT version … ORDER BY applied_at DESC LIMIT 1' == '1')")

            # behavioral 002 — the EXACT verifier write/readback round-trips through dv_sentinel.marker
            scratch.execute(_SENTINEL_WRITE, (_SENTINEL_NS, _SENTINEL_TOKEN))
            readback = _scalar(scratch, _SENTINEL_READ, (_SENTINEL_NS,))
            assert readback == _SENTINEL_TOKEN, f"sentinel write/readback must round-trip; got {readback!r}"
            print("PASS: 002 behavioral (INSERT … ON CONFLICT (ns) … write + readback round-trips)")

            # idempotency — re-apply both; no error, and no data drift (001's seed is WHERE-NOT-EXISTS-guarded,
            # 002's CREATE … IF NOT EXISTS is a no-op), so counts are unchanged
            sv_count = _scalar(scratch, "SELECT count(*) FROM schema_version")
            marker_count = _scalar(scratch, "SELECT count(*) FROM dv_sentinel.marker")
            _apply(scratch, _DDL_001)
            _apply(scratch, _DDL_002)
            sv_after = _scalar(scratch, "SELECT count(*) FROM schema_version")
            marker_after = _scalar(scratch, "SELECT count(*) FROM dv_sentinel.marker")
            assert sv_after == sv_count == 1, "re-applying 001 must not re-seed (idempotent)"
            assert marker_after == marker_count == 1, "re-applying 002 must preserve rows (idempotent)"
            print("PASS: 001/002 idempotency (re-apply: no error; schema_version=1 row, dv_sentinel.marker=1 row unchanged)")
        finally:
            scratch.close()  # release the scratch connection before dropping the database
    finally:
        admin.execute(f"DROP DATABASE IF EXISTS {_SCRATCH_DB}")  # scratch-only cleanup (autocommit)
        admin.close()


def test_provisioning_003_cluster_role(admin_dsn: str) -> None:
    """003 (sp2_provisioner) applied at CLUSTER scope; attributes + idempotent + non-vacuous. Roles are
    cluster-scoped, so this does not use the scratch database."""
    psycopg = _psycopg()

    _assert_blob(_DDL_003, _PROVISIONING_DDL_SHA_003)
    print(f"PASS: 003 blob pin (003={_PROVISIONING_DDL_SHA_003[:12]}…)")

    admin = psycopg.connect(admin_dsn)
    admin.autocommit = True
    try:
        admin.execute(f"DROP ROLE IF EXISTS {_PROV_ROLE}")  # start-of-run cleanup (idempotent precondition)

        # non-vacuity precondition: the role is ABSENT before apply
        role_present = _scalar(admin, "SELECT 1 FROM pg_roles WHERE rolname = %s", (_PROV_ROLE,))
        assert role_present is None, "sp2_provisioner must be ABSENT before apply"
        print("PASS: non-vacuity precondition (sp2_provisioner ABSENT before apply)")

        # apply 003 (DO-block CREATE ROLE … NOLOGIN + ALTER ROLE … CREATEDB + COMMENT)
        _apply(admin, _DDL_003)
        attrs = admin.execute(_LEAST_PRIV_QUERY, (_PROV_ROLE,)).fetchone()
        assert attrs is not None, "sp2_provisioner must exist after apply"
        _assert_least_privilege(attrs)  # AT-2: CREATEDB only; NO super/createrole/replication/bypassrls/login
        print("PASS: 003 apply (sp2_provisioner least-privilege: CREATEDB+NOLOGIN; no super/createrole/replication/bypassrls)")

        # idempotency — re-apply; the DO-block is IF-NOT-EXISTS-guarded, ALTER/COMMENT are no-ops
        _apply(admin, _DDL_003)
        attrs2 = admin.execute(_LEAST_PRIV_QUERY, (_PROV_ROLE,)).fetchone()
        _assert_least_privilege(attrs2)  # AT-2: least-privilege vector preserved across idempotent re-apply
        print("PASS: 003 idempotency (re-apply: no error; least-privilege vector unchanged)")
    finally:
        admin.execute(f"DROP ROLE IF EXISTS {_PROV_ROLE}")  # cluster-role cleanup
        admin.close()


if __name__ == "__main__":
    _pg.run([test_provisioning_001_002_tenant_db, test_provisioning_003_cluster_role])
