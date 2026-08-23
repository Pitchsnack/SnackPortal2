"""Stage 4A — migration verification against real PostgreSQL.

The gap Stage 4 exists to close is that migration M-1 was *authored* and never *applied*.
These tests apply the whole Control chain, M-1 included, to a disposable Control database and
the whole tenant chain independently to three disposable tenant databases, then assert the
properties the brief names: the schema arrives, M-1's table exists and behaves, no tenant
migration touches Control, no tenant migration reaches another tenant, and a database created
from zero reaches the same shape.

Nothing here mutates a historical migration. The chain is read from disk and applied as
authored; a failure would be reported, not patched away (§3.1).
"""

from __future__ import annotations

import pytest

from . import _stage4_pg as pg

pytestmark = pytest.mark.skipif(not pg.configured(), reason=pg.SKIP_REASON)


@pytest.fixture(scope="module", autouse=True)
def _provisioned() -> None:
    pg.provision()


# --- 3.1 inventory ----------------------------------------------------------------------


def test_the_authored_m1_migration_files_are_in_the_control_chain() -> None:
    names = [path.name for path in pg.control_chain()]
    for expected in pg.M1_FILES:
        assert expected in names, "M-1 file missing from the Control chain: " + expected
    # M-1 sorts last, so it is applied after every legacy migration rather than interleaved.
    assert names[-2:] == list(pg.M1_FILES), "M-1 must be the tail of the Control chain, got " + repr(names[-2:])


def test_no_migration_in_either_chain_requires_a_non_portable_extension() -> None:
    """Cloud-portable standard PostgreSQL only (CLAUDE.md constraint 1).

    ``dblink`` and ``postgres_fdw`` would additionally be a cross-database reach, which is
    what makes their absence a tenancy property and not merely a portability one.
    """
    forbidden = ("create extension", "dblink", "postgres_fdw")
    for path in list(pg.control_chain()) + list(pg.tenant_chain()):
        body = path.read_text(encoding="utf-8").casefold()
        for token in forbidden:
            assert token not in body, path.name + " uses " + token


# --- 3.2 Control chain, M-1 included ----------------------------------------------------


def test_the_control_chain_applies_and_creates_the_bff_ingress_audit_table() -> None:
    tables = pg.table_names(pg.dsn("control"))
    assert "control_ingress_audit" in tables, "M-1 did not create its table; found " + repr(tables)
    assert "control_tenants" in tables
    assert "control_memberships" in tables
    assert "control_directory" in tables


def test_the_m1_table_carries_every_column_the_audit_sink_writes() -> None:
    from snackportal2.services.audit.sink import AUDIT_TABLE

    assert AUDIT_TABLE == "control_ingress_audit"
    columns = set(pg.column_names(pg.dsn("control"), AUDIT_TABLE))
    written = {
        "event_id",
        "occurred_at",
        "source_service",
        "action",
        "outcome",
        "correlation_id",
        "actor_ref",
        "subject_ref",
        "tenant_ref",
        "record_ref",
        "carrier_ref",
    }
    assert written <= columns, "sink writes columns the table does not have: " + repr(sorted(written - columns))


def test_m1_and_ddl_012_are_disjoint_by_construction() -> None:
    """The two audit tables cannot both accept the same row (M-1 header, D-46 §7).

    DDL 012 pins ``source_service = 'api_gateway'``; M-1 pins ``source_service <>
    'api_gateway'``. Asserting both directions is the point: it proves the retired Gateway's
    historical audit cannot be polluted by new emission *and* that BFF emission is not
    blocked by 012's constraint, which is exactly why M-1 was authored.
    """
    control = pg.dsn("control")

    pg.execute(
        control,
        "INSERT INTO control_ingress_audit (event_id, occurred_at, source_service, action, outcome, "
        "correlation_id, actor_ref) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        ("m1-accepts-bff", "2026-08-23T00:00:00+00:00", "bff", "RouteDenied", "denied", "c-1", "p-1"),
    )
    assert pg.scalar(control, "SELECT count(*) FROM control_ingress_audit WHERE event_id = 'm1-accepts-bff'") == 1

    with pytest.raises(pg.database_error()):
        pg.execute(
            control,
            "INSERT INTO control_ingress_audit (event_id, occurred_at, source_service, action, outcome, "
            "correlation_id, actor_ref) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            ("m1-rejects-gateway", "2026-08-23T00:00:00+00:00", "api_gateway", "RouteDenied", "denied", "c-2", "p-2"),
        )

    gateway_columns = set(pg.column_names(control, "control_gateway_audit"))
    assert gateway_columns, "DDL 012 must remain applied as the historical record"
    with pytest.raises(pg.database_error()):
        pg.execute(
            control,
            "INSERT INTO control_gateway_audit (event_id, occurred_at, source_service, action, outcome, "
            "correlation_id, actor_ref) VALUES (%s, now(), %s, %s, %s, %s, %s)",
            ("012-rejects-bff", "bff", "RouteDenied", "denied", "c-3", "p-3"),
        )


def test_the_m1_table_is_append_only_in_the_database() -> None:
    """Migration 017's triggers hold against every writer, including this test."""
    control = pg.dsn("control")
    pg.execute(
        control,
        "INSERT INTO control_ingress_audit (event_id, occurred_at, source_service, action, outcome, "
        "correlation_id, actor_ref) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        ("m1-immutable", "2026-08-23T00:00:01+00:00", "bff", "RouteDenied", "denied", "c-4", "p-4"),
    )
    for statement in (
        "UPDATE control_ingress_audit SET outcome = 'allowed' WHERE event_id = 'm1-immutable'",
        "DELETE FROM control_ingress_audit WHERE event_id = 'm1-immutable'",
        "TRUNCATE control_ingress_audit",
    ):
        with pytest.raises(pg.database_error()):
            pg.execute(control, statement)
    assert pg.scalar(control, "SELECT count(*) FROM control_ingress_audit WHERE event_id = 'm1-immutable'") == 1


def test_no_control_migration_names_the_retired_gateway_runtime() -> None:
    """A migration may *record* the Gateway historically; none may *require* its runtime.

    The distinction is concrete: DDL 012/013 are retained because they hold the retired
    Gateway's audit rows, and M-1 must not reference them at all — if it did, applying the
    BFF's audit table would depend on the retired architecture's table still existing.
    """
    for name in pg.M1_FILES:
        body = (pg.REBUILD_MIGRATIONS / "control" / name).read_text(encoding="utf-8")
        statements = [line for line in body.splitlines() if not line.lstrip().startswith("--")]
        joined = "\n".join(statements).casefold()
        assert "control_gateway_audit" not in joined, name + " must not reference the retired Gateway's table in DDL"


# --- 3.3 tenant chains, applied independently -------------------------------------------


@pytest.mark.parametrize("tenant", list(pg.TENANTS))
def test_each_tenant_database_reaches_the_intended_schema(tenant: str) -> None:
    target = pg.dsn(tenant)
    tables = set(pg.table_names(target))
    required = {"startups", "investors", "deals", "lineage", "import_idempotency", "import_job", "schema_version"}
    assert required <= tables, tenant + " missing " + repr(sorted(required - tables))
    assert pg.scalar(target, "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1") == "1"


@pytest.mark.parametrize("tenant", list(pg.TENANTS))
def test_no_tenant_database_holds_a_control_table(tenant: str) -> None:
    """Physical separation, observed rather than assumed.

    A tenant database that carried ``control_tenants`` would mean the split was logical.
    """
    tables = pg.table_names(pg.dsn(tenant))
    assert not [name for name in tables if name.startswith("control_")], tenant + " holds Control tables: " + repr(tables)


@pytest.mark.parametrize("tenant", list(pg.TENANTS))
def test_no_tenant_business_table_carries_a_tenant_id_column(tenant: str) -> None:
    """Tenancy is physical. A ``tenant_id`` column in a business table would be the tell."""
    for table in ("startups", "investors", "deals"):
        columns = pg.column_names(pg.dsn(tenant), table)
        assert "tenant_id" not in columns, tenant + "." + table + " carries tenant_id: " + repr(columns)


def test_applying_the_tenant_chain_writes_nothing_to_the_control_database() -> None:
    """Observed, not inferred: the Control DB is unchanged across a full tenant application.

    A static scan for the string ``control_`` would pass on a file that reached Control by
    some other name. Counting every Control row before and after cannot.
    """
    control = pg.dsn("control")
    tables = pg.table_names(control)
    before = {table: pg.scalar(control, "SELECT count(*) FROM " + table) for table in tables}

    scratch = pg.dsn("nova")
    pg.reset_database(scratch)
    applied = pg.apply_chain(scratch, pg.tenant_chain())
    assert applied, "the tenant chain applied no files"

    after = {table: pg.scalar(control, "SELECT count(*) FROM " + table) for table in tables}
    assert after == before, "the tenant chain changed Control row counts: " + repr(
        {name: (before[name], after[name]) for name in before if before[name] != after[name]}
    )
    assert pg.table_names(control) == tables, "the tenant chain changed the Control table set"


def test_a_tenant_chain_application_leaves_the_other_tenants_untouched() -> None:
    """No tenant migration depends on, or reaches, another tenant database."""
    acme, zeta = pg.dsn("acme"), pg.dsn("zeta")
    acme_before = pg.table_names(acme)
    zeta_rows = pg.scalar(zeta, "SELECT count(*) FROM startups")

    pg.reset_database(pg.dsn("nova"))
    pg.apply_chain(pg.dsn("nova"), pg.tenant_chain())

    assert pg.table_names(acme) == acme_before
    assert pg.scalar(zeta, "SELECT count(*) FROM startups") == zeta_rows


# --- 3.4 fresh-database reproducibility --------------------------------------------------


@pytest.mark.skipif(
    not (pg.admin_dsn("control") and pg.admin_dsn("acme")),
    reason="fresh-database reproducibility needs " + pg.ENV_ADMIN_CONTROL + " and " + pg.ENV_ADMIN_ACME,
)
def test_a_database_created_from_zero_reaches_the_same_schema() -> None:
    """Clean database -> migrations -> the expected schema, for Control and for a tenant.

    ``CREATE DATABASE`` cannot run inside a transaction block, which is why it goes through
    the harness's autocommit helper rather than the ordinary one.
    """
    for admin, database, chain, reference in (
        (pg.admin_dsn("control"), "sp2_stage4_fresh_control", pg.control_chain(), pg.dsn("control")),
        (pg.admin_dsn("acme"), "sp2_stage4_fresh_tenant", pg.tenant_chain(), pg.dsn("acme")),
    ):
        pg.execute_outside_transaction(admin, "DROP DATABASE IF EXISTS " + database + " WITH (FORCE)")
        pg.execute_outside_transaction(admin, "CREATE DATABASE " + database)
        try:
            fresh = pg.swap_database(admin, database)
            applied = pg.apply_chain(fresh, chain)
            assert len(applied) == len(chain)
            assert pg.table_names(fresh) == pg.table_names(reference), (
                database + " schema differs from the provisioned reference"
            )
        finally:
            pg.execute_outside_transaction(admin, "DROP DATABASE IF EXISTS " + database + " WITH (FORCE)")


def test_the_control_chain_is_idempotent_on_reapplication() -> None:
    """Re-running the chain is a no-op, which is what makes a migration runner safe to retry."""
    control = pg.dsn("control")
    before = pg.table_names(control)
    counts = {table: pg.scalar(control, "SELECT count(*) FROM " + table) for table in before}
    pg.apply_chain(control, pg.control_chain())
    assert pg.table_names(control) == before
    assert {table: pg.scalar(control, "SELECT count(*) FROM " + table) for table in before} == counts
