"""Stage 4D/4E — the tenant-resident domain services against real tenant databases.

Every service in this module runs as a real uvicorn process configured for PostgreSQL storage,
so the repository each one uses is the one its own ``_build_repository()`` selected from the
environment, holding a connection it opened under a real Database Router grant (D-48).

The isolation assertions are deliberately made **at the database**, not at the API. A service
answering "not found" for another tenant's record proves the service filtered; opening the
other tenant's database and finding nothing proves the row was never there. Only the second
is physical isolation, and the four Stage 4 databases are four separate clusters so the
difference is real.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import httpx
import pytest

from snackportal2.services.control_plane.models import SecretReference, TenantDescriptor
from snackportal2.services.control_plane.store import ENV_CONTROL_DSN, build_store
from snackportal2.services.database_router.resolver import EnvironmentTenantSecretStore
from snackportal2.shared.security import AuthContext, RequestContext
from snackportal2.shared.types import PlatformRole, TenantLifecycleState

from . import _stage4_pg as pg
from . import _stage4_servers as srv

pytestmark = pytest.mark.skipif(not pg.configured(), reason=pg.SKIP_REASON)

ROUTER_CREDENTIAL = "internal-router-credential"
DOMAIN_CREDENTIAL = "internal-domain-credential"
GRANT_CREDENTIALS = {
    "startups": "grant-startups",
    "investors": "grant-investors",
    "deals": "grant-deals",
    "lineage": "grant-lineage",
}


def _dsn_variable(store_ref: str) -> str:
    return EnvironmentTenantSecretStore.variable_name(store_ref, "1")


def _context(tenant_ref: Optional[str], principal: str = "p-agent") -> Dict[str, Any]:
    auth = AuthContext(
        correlation_id="c-stage4d",
        principal_ref=principal,
        role=PlatformRole.TENANT_AGENT,
        active_tenant_ref=tenant_ref,
    )
    return RequestContext.from_auth_context(auth).model_dump(mode="json")


@pytest.fixture(scope="module")
def fleet(tmp_path_factory: pytest.TempPathFactory) -> Iterator[srv.ServiceFleet]:
    pg.provision()

    store = build_store(env={ENV_CONTROL_DSN: pg.dsn("control")})
    for tenant in pg.TENANTS:
        store.put_tenant(
            TenantDescriptor(
                tenant_ref=tenant,
                organization_ref="org-" + tenant,
                lifecycle_state=TenantLifecycleState.ACTIVE,
                expected_schema_version="1",
                database_association_ref=SecretReference(store_ref="assoc/" + tenant, version="1"),
            )
        )
    pg.execute(
        pg.dsn("control"),
        "INSERT INTO control_directory (directory, record_id, display_name, attributes) "
        "VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (directory, record_id) DO NOTHING",
        ("GlobalStartupDirectory", "gs-1", "Alpha Corp", json.dumps({"industry": "robotics"})),
    )

    log_dir: Path = tmp_path_factory.mktemp("stage4d-logs")
    running = srv.ServiceFleet(log_dir)
    try:
        control = running.start("control_plane", {"SP2_CONTROL_PLANE_DSN": pg.dsn("control")})
        router = running.start(
            "database_router",
            {
                "SP2_DATABASE_ROUTER_CONTROL_PLANE_URL": control.base_url,
                "SP2_DATABASE_ROUTER_SERVICE_CREDENTIAL": ROUTER_CREDENTIAL,
                "SP2_DATABASE_ROUTER_GRANTEES": json.dumps(
                    {credential: service for service, credential in GRANT_CREDENTIALS.items()}
                ),
                **{_dsn_variable("assoc/" + tenant): pg.dsn(tenant) for tenant in pg.TENANTS},
            },
        )
        for service in ("startups", "investors", "deals", "lineage"):
            running.start(
                service,
                {
                    "SP2_" + service.upper() + "_STORAGE": "postgres",
                    "SP2_" + service.upper() + "_DATABASE_ROUTER_URL": router.base_url,
                    "SP2_" + service.upper() + "_SERVICE_CREDENTIAL": GRANT_CREDENTIALS[service],
                },
            )
        running.start(
            "import_service",
            {
                "SP2_IMPORT_SERVICE_CONTROL_PLANE_URL": control.base_url,
                "SP2_IMPORT_SERVICE_SERVICE_CREDENTIAL": ROUTER_CREDENTIAL,
            },
        )
        yield running
    finally:
        running.stop()


def _call(fleet: srv.ServiceFleet, service: str, path: str, payload: Dict[str, Any]) -> httpx.Response:
    return httpx.post(
        fleet.url(service) + path,
        headers={"Authorization": "Bearer " + DOMAIN_CREDENTIAL},
        json=payload,
        timeout=20.0,
    )


def _created(response: httpx.Response) -> Dict[str, Any]:
    assert response.status_code == 201, response.text
    return response.json()


# --- 6.1 Startup Service ------------------------------------------------------------------


def test_a_startup_created_through_the_service_is_physically_in_that_tenants_database(
    fleet: srv.ServiceFleet,
) -> None:
    record = _created(
        _call(
            fleet,
            "startups",
            "/internal/startups/create",
            {
                "context": _context("acme"),
                "company_name": "Acme Robotics",
                "company_url": "HTTPS://WWW.Acme-Robotics.example.COM/",
                "industry": "robotics",
                "investment_stage": "seed",
                "short_description": "Warehouse automation.",
                "headquarters_country": "NL",
            },
        )
    )
    assert record["record_ref"].startswith("ref:acme:startups:")

    stored = pg.rows(
        pg.dsn("acme"),
        "SELECT company_name, company_url, industry, investment_stage, short_description FROM startups "
        "WHERE company_name = %s",
        ("Acme Robotics",),
    )
    assert stored == [("Acme Robotics", "https://acme-robotics.example.com", "robotics", "seed", "Warehouse automation.")]


def test_website_normalization_happens_on_write_not_on_read(fleet: srv.ServiceFleet) -> None:
    """The normalized form is what the *database* holds, so a duplicate check can rely on it."""
    _created(
        _call(
            fleet,
            "startups",
            "/internal/startups/create",
            {"context": _context("acme"), "company_name": "Nordwind Labs", "company_url": "www.Nordwind.example.org/"},
        )
    )
    assert pg.scalar(
        pg.dsn("acme"), "SELECT company_url FROM startups WHERE company_name = 'Nordwind Labs'"
    ) == "https://nordwind.example.org"


def test_a_created_startup_reads_back_identically_through_postgresql(fleet: srv.ServiceFleet) -> None:
    """Create returns a composed record; read returns a row. They must agree.

    They are produced by different code paths — ``create`` composes from the submitted fields,
    ``read`` maps a ``SELECT`` — so a column the write silently dropped, or a type the driver
    coerced, shows up here and nowhere else.
    """
    created = _created(
        _call(
            fleet,
            "startups",
            "/internal/startups/create",
            {
                "context": _context("acme"),
                "company_name": "Roundtrip Ltd",
                "company_type": "private",
                "region": "EMEA",
                "year_founded": "2019",
                "industry": "logistics",
                "investment_stage": "series_a",
                "product_overview": "Freight scheduling.",
                "global_startup_id": "gs-roundtrip",
            },
        )
    )
    read = _call(
        fleet, "startups", "/internal/startups/read", {"context": _context("acme"), "record_ref": created["record_ref"]}
    )
    assert read.status_code == 200, read.text
    assert read.json() == created, "create and read disagree about the same record"


def test_a_non_numeric_year_founded_is_accepted_by_the_contract_and_rejected_by_the_column(
    fleet: srv.ServiceFleet,
) -> None:
    """**Stage 4 finding F-3, characterized rather than patched.**

    ``StartupCreateRequest.year_founded`` is ``Optional[str]`` bounded at eight characters;
    tenant DDL 003 types the column ``integer``. A non-numeric value therefore passes contract
    validation and fails at the driver, and the request answers **500 internal_error** — an
    undeclared outcome for what is really a rejected input.

    The root cause is the contract, not the adapter: the published schema accepts values the
    storage cannot represent. Narrowing it to digits changes the generated OpenAPI document,
    which §9 of the Stage 4 brief makes a STOP-and-report, not a change to be slipped in. So
    the behaviour is pinned here instead, and the conflict is reported: if this test starts
    failing, the contract moved and the report needs to move with it.

    A numeric string round-trips correctly, which is why nothing before Stage 4 caught this —
    the in-memory repository stores any string at all.
    """
    rejected = _call(
        fleet,
        "startups",
        "/internal/startups/create",
        {"context": _context("acme"), "company_name": "Ambiguous Year Ltd", "year_founded": "circa"},
    )
    assert rejected.status_code == 500, rejected.text
    assert rejected.json() == {"status": 500, "code": "internal_error"}
    assert "circa" not in rejected.text, "the failure echoed the submitted value back to the caller"
    assert pg.scalar(pg.dsn("acme"), "SELECT count(*) FROM startups WHERE company_name = 'Ambiguous Year Ltd'") == 0

    accepted = _created(
        _call(
            fleet,
            "startups",
            "/internal/startups/create",
            {"context": _context("acme"), "company_name": "Numeric Year Ltd", "year_founded": "1999"},
        )
    )
    assert accepted["year_founded"] == "1999"
    assert pg.scalar(pg.dsn("acme"), "SELECT year_founded FROM startups WHERE company_name = 'Numeric Year Ltd'") == 1999


def test_the_single_mutable_field_updates_in_the_database(fleet: srv.ServiceFleet) -> None:
    created = _created(
        _call(
            fleet,
            "startups",
            "/internal/startups/create",
            {"context": _context("acme"), "company_name": "Mutable Co", "short_description": "before"},
        )
    )
    updated = _call(
        fleet,
        "startups",
        "/internal/startups/update",
        {"context": _context("acme"), "record_ref": created["record_ref"], "short_description": "after"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["short_description"] == "after"
    assert pg.scalar(pg.dsn("acme"), "SELECT short_description FROM startups WHERE company_name = 'Mutable Co'") == "after"

    cleared = _call(
        fleet,
        "startups",
        "/internal/startups/update",
        {"context": _context("acme"), "record_ref": created["record_ref"], "short_description": None},
    )
    assert cleared.status_code == 200
    assert pg.scalar(pg.dsn("acme"), "SELECT short_description FROM startups WHERE company_name = 'Mutable Co'") is None


def test_updating_a_record_reference_from_another_tenant_is_not_found(fleet: srv.ServiceFleet) -> None:
    created = _created(
        _call(fleet, "startups", "/internal/startups/create", {"context": _context("zeta"), "company_name": "Zeta Only"})
    )
    response = _call(
        fleet,
        "startups",
        "/internal/startups/update",
        {"context": _context("acme"), "record_ref": created["record_ref"], "short_description": "hijack"},
    )
    assert response.status_code == 404
    assert pg.scalar(pg.dsn("zeta"), "SELECT short_description FROM startups WHERE company_name = 'Zeta Only'") is None


def test_the_list_operation_is_bounded_and_deterministic(fleet: srv.ServiceFleet) -> None:
    first = _call(fleet, "startups", "/internal/startups/list", {"context": _context("acme"), "limit": 3})
    second = _call(fleet, "startups", "/internal/startups/list", {"context": _context("acme"), "limit": 3})
    assert first.status_code == 200, first.text
    assert first.json() == second.json()
    assert len(first.json()["records"]) <= 3
    assert first.json()["tenant_ref"] == "acme"


def test_the_duplicate_check_matches_on_name_and_on_normalized_website(fleet: srv.ServiceFleet) -> None:
    by_name = _call(
        fleet,
        "startups",
        "/internal/startups/duplicate-check",
        {"context": _context("acme"), "company_name": "acme robotics"},
    )
    assert by_name.status_code == 200, by_name.text
    assert by_name.json()["blocking"] is True
    assert [c["reason"] for c in by_name.json()["candidates"]] == ["name"]

    by_site = _call(
        fleet,
        "startups",
        "/internal/startups/duplicate-check",
        {
            "context": _context("acme"),
            "company_name": "Totally Different",
            "company_url": "HTTPS://WWW.acme-robotics.example.com/",
        },
    )
    assert by_site.json()["blocking"] is True
    assert [c["reason"] for c in by_site.json()["candidates"]] == ["website"]

    clean = _call(
        fleet,
        "startups",
        "/internal/startups/duplicate-check",
        {"context": _context("acme"), "company_name": "Nothing Like This", "company_url": "https://nothing.example.net"},
    )
    assert clean.json() == {"candidates": [], "blocking": False}


def test_website_normalization_preserves_the_scheme_so_the_duplicate_check_is_scheme_sensitive(
    fleet: srv.ServiceFleet,
) -> None:
    """Documented behaviour, recorded here because it is easy to mistake for a bug.

    ``normalize_website`` supplies ``https://`` only when the input has no scheme; an explicit
    ``http://`` is preserved. So the same company entered once as ``http://x`` and once as
    ``https://x`` yields two records and no duplicate warning. That is what the operation's
    published description says it does, so Stage 4 records it rather than changing stored
    values to fit a different rule.
    """
    response = _call(
        fleet,
        "startups",
        "/internal/startups/duplicate-check",
        {"context": _context("acme"), "company_name": "Scheme Probe", "company_url": "http://acme-robotics.example.com"},
    )
    assert response.status_code == 200
    assert response.json() == {"candidates": [], "blocking": False}


def test_a_duplicate_check_never_sees_another_tenants_records(fleet: srv.ServiceFleet) -> None:
    response = _call(
        fleet,
        "startups",
        "/internal/startups/duplicate-check",
        {"context": _context("zeta"), "company_name": "Acme Robotics"},
    )
    assert response.json() == {"candidates": [], "blocking": False}


def test_no_startup_write_reaches_the_control_database(fleet: srv.ServiceFleet) -> None:
    control = pg.dsn("control")
    tables = pg.table_names(control)
    assert "startups" not in tables
    before = {table: pg.scalar(control, "SELECT count(*) FROM " + table) for table in tables}

    _created(
        _call(
            fleet,
            "startups",
            "/internal/startups/create",
            {"context": _context("acme"), "company_name": "Control Probe Ltd"},
        )
    )

    after = {table: pg.scalar(control, "SELECT count(*) FROM " + table) for table in tables}
    assert after == before, "a tenant write changed the Control database"


# --- 6.2 Investor Service -----------------------------------------------------------------


def test_investor_jsonb_focus_lists_round_trip_as_arrays(fleet: srv.ServiceFleet) -> None:
    """The jsonb columns are the reason this service has its own repository.

    psycopg 3 has no default dumper for ``list``/``dict``, so a raw bind raises before any SQL
    reaches PostgreSQL — the defect on record against the legacy adapter (MCC-AR-1). This is
    the first execution that could ever have caught a repeat of it.
    """
    created = _created(
        _call(
            fleet,
            "investors",
            "/internal/investors/create",
            {
                "context": _context("acme"),
                "investor_name": "Northwind Capital",
                "investor_type": "vc",
                "website_url": "WWW.Northwind.example.com/",
                "investment_stage_focus": ["seed", "series_a"],
                "industry_focus": ["robotics", "energy"],
                "short_description": "Early stage.",
            },
        )
    )
    assert created["investment_stage_focus"] == ["seed", "series_a"]
    assert created["industry_focus"] == ["robotics", "energy"]

    stored = pg.rows(
        pg.dsn("acme"),
        "SELECT investment_stage_focus, industry_focus, website_url, "
        "jsonb_typeof(investment_stage_focus), jsonb_typeof(industry_focus) "
        "FROM investors WHERE investor_name = %s",
        ("Northwind Capital",),
    )
    assert stored == [
        (["seed", "series_a"], ["robotics", "energy"], "https://northwind.example.com", "array", "array")
    ], "the focus lists did not reach PostgreSQL as jsonb arrays"

    read = _call(
        fleet, "investors", "/internal/investors/read", {"context": _context("acme"), "record_ref": created["record_ref"]}
    )
    assert read.status_code == 200
    assert read.json() == created


def test_an_investor_with_empty_focus_lists_stores_empty_arrays_not_null(fleet: srv.ServiceFleet) -> None:
    created = _created(
        _call(
            fleet,
            "investors",
            "/internal/investors/create",
            {"context": _context("acme"), "investor_name": "Sparse Partners"},
        )
    )
    assert created["investment_stage_focus"] == []
    assert pg.rows(
        pg.dsn("acme"),
        "SELECT investment_stage_focus, industry_focus FROM investors WHERE investor_name = 'Sparse Partners'",
    ) == [([], [])]


def test_the_investor_email_column_is_never_surfaced(fleet: srv.ServiceFleet) -> None:
    """DDL 004 has ``email``; IC-009 forbids it in the portal shape, so it is not read back."""
    pg.execute(
        pg.dsn("acme"),
        "INSERT INTO investors (investor_name, email) VALUES (%s, %s)",
        ("Emailed Ventures", "partner@example.com"),
    )
    listed = _call(fleet, "investors", "/internal/investors/list", {"context": _context("acme"), "limit": 500})
    assert listed.status_code == 200
    assert "partner@example.com" not in listed.text
    assert "email" not in listed.text


def test_an_investor_created_in_one_tenant_is_invisible_to_another(fleet: srv.ServiceFleet) -> None:
    created = _created(
        _call(
            fleet,
            "investors",
            "/internal/investors/create",
            {"context": _context("zeta"), "investor_name": "Zeta Ventures", "industry_focus": ["fintech"]},
        )
    )
    other = _call(
        fleet, "investors", "/internal/investors/read", {"context": _context("acme"), "record_ref": created["record_ref"]}
    )
    assert other.status_code == 404
    assert pg.scalar(pg.dsn("acme"), "SELECT count(*) FROM investors WHERE investor_name = 'Zeta Ventures'") == 0
    assert pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM investors WHERE investor_name = 'Zeta Ventures'") == 1


# --- 6.3 Deal Service ---------------------------------------------------------------------


def test_a_deal_binds_two_records_of_the_same_tenant(fleet: srv.ServiceFleet) -> None:
    startup = _created(
        _call(fleet, "startups", "/internal/startups/create", {"context": _context("nova"), "company_name": "Nova Startup"})
    )
    investor = _created(
        _call(fleet, "investors", "/internal/investors/create", {"context": _context("nova"), "investor_name": "Nova Fund"})
    )
    deal = _created(
        _call(
            fleet,
            "deals",
            "/internal/deals/create",
            {
                "context": _context("nova"),
                "deal_name": "Nova Seed",
                "startup_ref": startup["record_ref"],
                "investor_ref": investor["record_ref"],
                "stage": "term_sheet",
                "amount": "1500000.50",
                "currency": "EUR",
                "status": "open",
            },
        )
    )
    assert deal["startup_ref"] == startup["record_ref"]
    assert deal["investor_ref"] == investor["record_ref"]

    stored = pg.rows(
        pg.dsn("nova"),
        "SELECT deal_name, stage, amount, currency, status FROM deals WHERE deal_name = %s",
        ("Nova Seed",),
    )
    assert len(stored) == 1
    assert stored[0][0] == "Nova Seed"
    assert str(stored[0][2]) == "1500000.50", "the numeric amount lost precision"
    assert (stored[0][1], stored[0][3], stored[0][4]) == ("term_sheet", "EUR", "open")

    read = _call(fleet, "deals", "/internal/deals/read", {"context": _context("nova"), "record_ref": deal["record_ref"]})
    assert read.status_code == 200
    assert read.json() == deal


def test_the_intra_tenant_foreign_key_is_enforced_by_the_database(fleet: srv.ServiceFleet) -> None:
    """DDL 005's FK to ``startups`` is the last line of defence, and it is a real constraint."""
    with pytest.raises(pg.database_error()):
        pg.execute(
            pg.dsn("nova"),
            "INSERT INTO deals (startup_id, deal_name) VALUES (%s, %s)",
            (99999999, "Orphan Deal"),
        )


def test_a_deal_naming_another_tenants_party_is_rejected_outright(fleet: srv.ServiceFleet) -> None:
    """Not silently unmatched — rejected. A deal is the one record that names two others."""
    acme_startup = _created(
        _call(fleet, "startups", "/internal/startups/create", {"context": _context("acme"), "company_name": "Acme Party"})
    )
    response = _call(
        fleet,
        "deals",
        "/internal/deals/create",
        {"context": _context("zeta"), "deal_name": "Cross Tenant Deal", "startup_ref": acme_startup["record_ref"]},
    )
    assert response.status_code == 422, response.text
    assert response.json() == {"status": 422, "code": "invalid_request"}
    assert pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM deals WHERE deal_name = 'Cross Tenant Deal'") == 0
    assert pg.scalar(pg.dsn("acme"), "SELECT count(*) FROM deals WHERE deal_name = 'Cross Tenant Deal'") == 0


def test_a_deal_investor_from_another_tenant_is_rejected_rather_than_dropped(fleet: srv.ServiceFleet) -> None:
    zeta_startup = _created(
        _call(fleet, "startups", "/internal/startups/create", {"context": _context("zeta"), "company_name": "Zeta Party"})
    )
    acme_investor = _created(
        _call(fleet, "investors", "/internal/investors/create", {"context": _context("acme"), "investor_name": "Acme Fund"})
    )
    response = _call(
        fleet,
        "deals",
        "/internal/deals/create",
        {
            "context": _context("zeta"),
            "deal_name": "Half Crossed Deal",
            "startup_ref": zeta_startup["record_ref"],
            "investor_ref": acme_investor["record_ref"],
        },
    )
    assert response.status_code == 422
    assert pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM deals WHERE deal_name = 'Half Crossed Deal'") == 0


def test_a_deal_update_changes_stage_and_status_and_never_its_parties(fleet: srv.ServiceFleet) -> None:
    startup = _created(
        _call(fleet, "startups", "/internal/startups/create", {"context": _context("nova"), "company_name": "Update Target"})
    )
    deal = _created(
        _call(
            fleet,
            "deals",
            "/internal/deals/create",
            {"context": _context("nova"), "deal_name": "Updatable", "startup_ref": startup["record_ref"]},
        )
    )
    updated = _call(
        fleet,
        "deals",
        "/internal/deals/update",
        {"context": _context("nova"), "record_ref": deal["record_ref"], "stage": "diligence", "status": "in_diligence"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "in_diligence"
    assert updated.json()["startup_ref"] == deal["startup_ref"]
    assert pg.rows(pg.dsn("nova"), "SELECT stage, status FROM deals WHERE deal_name = 'Updatable'") == [
        ("diligence", "in_diligence")
    ]


def test_sharing_is_not_deal_duplication(fleet: srv.ServiceFleet) -> None:
    """No operation on this service produces a second record from an existing one.

    Asserted over the generated document rather than the source: the surface is the contract,
    and a copy operation would have to appear there.
    """
    document = httpx.get(fleet.url("deals") + "/openapi.json", timeout=10.0).json()
    operations = {
        operation["operationId"]
        for item in document["paths"].values()
        for method, operation in item.items()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert operations == {
        "getDealsHealth",
        "getDealsReadiness",
        "listTenantDeals",
        "readTenantDeal",
        "createTenantDeal",
        "updateTenantDeal",
    }
    for forbidden in ("copy", "duplicate", "clone", "share", "fork"):
        assert not [name for name in operations if forbidden in name.casefold()], forbidden


# --- 6.5 Lineage Service ------------------------------------------------------------------


def _seed_lineage(tenant: str, seq: int, target_ref: str, source_ref: str, operation: str) -> str:
    """Insert one lineage row by direct SQL, the way the accepted lineage write path would.

    The rebuild has no lineage *writer* (see the Stage 4 report's Import blocker), so the rows
    the Lineage Service reads are seeded here with every NOT NULL chain column the DDL
    requires. The marker value is a fixture value and is not, and does not claim to be, a
    D-23 chain marker.
    """
    lineage_id = "ln-" + tenant + "-" + str(seq)
    pg.execute(
        pg.dsn(tenant),
        "INSERT INTO lineage (seq, lineage_id, event_type, occurred_at, actor_ref, source_ref, target_ref, "
        "operation, schema_version, derivation_ref, integrity_marker) "
        "VALUES (%s, %s, 'import', %s, 'p-agent', %s, %s, %s, '1', %s, %s)",
        (
            seq,
            lineage_id,
            "2026-08-23T00:00:0" + str(seq % 10) + "+00:00",
            source_ref,
            target_ref,
            operation,
            "job-" + str(seq),
            "fixture-marker-" + str(seq),
        ),
    )
    return lineage_id


def test_lineage_reads_come_from_the_tenant_database_in_chain_order(fleet: srv.ServiceFleet) -> None:
    startup = _created(
        _call(fleet, "startups", "/internal/startups/create", {"context": _context("acme"), "company_name": "Lineage Subject"})
    )
    target = startup["record_ref"]
    _seed_lineage("acme", 2, target, "gs-1", "global_startup_import")
    _seed_lineage("acme", 1, target, "gs-0", "global_startup_import")

    listed = _call(fleet, "lineage", "/internal/lineage/list", {"context": _context("acme"), "limit": 100})
    assert listed.status_code == 200, listed.text
    entries = listed.json()["entries"]
    assert [entry["source_ref"] for entry in entries] == ["gs-0", "gs-1"], "rows were not ordered by the chain sequence"
    assert listed.json()["tenant_ref"] == "acme"
    assert all(entry["lineage_ref"].startswith("ref:acme:lineage:") for entry in entries)


def test_lineage_for_a_record_returns_only_that_records_provenance(fleet: srv.ServiceFleet) -> None:
    subject = _created(
        _call(fleet, "startups", "/internal/startups/create", {"context": _context("acme"), "company_name": "Other Subject"})
    )
    _seed_lineage("acme", 3, subject["record_ref"], "gs-9", "global_startup_import")

    response = _call(
        fleet, "lineage", "/internal/lineage/for-record", {"context": _context("acme"), "target_ref": subject["record_ref"]}
    )
    assert response.status_code == 200, response.text
    entries = response.json()["entries"]
    assert [entry["source_ref"] for entry in entries] == ["gs-9"]
    assert all(entry["target_ref"] == subject["record_ref"] for entry in entries)


def test_lineage_for_another_tenants_record_reference_is_refused(fleet: srv.ServiceFleet) -> None:
    response = _call(
        fleet,
        "lineage",
        "/internal/lineage/for-record",
        {"context": _context("zeta"), "target_ref": "ref:acme:startups:1"},
    )
    assert response.status_code == 404


def test_the_lineage_service_exposes_no_write_operation(fleet: srv.ServiceFleet) -> None:
    document = httpx.get(fleet.url("lineage") + "/openapi.json", timeout=10.0).json()
    operations = {
        operation["operationId"]
        for item in document["paths"].values()
        for method, operation in item.items()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert operations == {"getLineageHealth", "getLineageReadiness", "listTenantLineage", "readTenantRecordLineage"}


def test_the_lineage_table_rejects_mutation_in_the_database(fleet: srv.ServiceFleet) -> None:
    """Append-only is enforced by the tenant DDL, not only by the absence of an endpoint."""
    for statement in (
        "UPDATE lineage SET operation = 'tampered' WHERE seq = 1",
        "DELETE FROM lineage WHERE seq = 1",
        "TRUNCATE lineage",
    ):
        with pytest.raises(pg.database_error()):
            pg.execute(pg.dsn("acme"), statement)
    assert pg.scalar(pg.dsn("acme"), "SELECT count(*) FROM lineage WHERE seq = 1") == 1


def test_lineage_rows_never_cross_tenant_databases(fleet: srv.ServiceFleet) -> None:
    zeta_view = _call(fleet, "lineage", "/internal/lineage/list", {"context": _context("zeta"), "limit": 500})
    assert zeta_view.status_code == 200
    assert zeta_view.json()["entries"] == []
    assert pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM lineage") == 0


# --- 6.4 Import Service: the half that is live, and the half that is blocked ---------------


def test_the_import_source_is_read_from_the_real_control_database(fleet: srv.ServiceFleet) -> None:
    """The global read really does traverse Control PostgreSQL.

    A source reference absent from ``control_directory`` must be *not found*, and one present
    must import — which is only distinguishable if the read is genuinely hitting the database.
    """
    missing = _call(
        fleet, "import_service", "/internal/import/startup", {"context": _context("acme"), "source_ref": "gs-absent"}
    )
    assert missing.status_code == 404, missing.text

    created = _call(
        fleet, "import_service", "/internal/import/startup", {"context": _context("acme"), "source_ref": "gs-1"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["outcome"] == "created"
    assert created.json()["source_ref"] == "gs-1"
    assert created.json()["target_tenant_ref"] == "acme"


def test_import_is_idempotent_per_tenant_and_source(fleet: srv.ServiceFleet) -> None:
    first = _call(
        fleet, "import_service", "/internal/import/startup", {"context": _context("zeta"), "source_ref": "gs-1"}
    )
    assert first.status_code == 201, first.text
    assert first.json()["outcome"] == "created"

    replay = _call(
        fleet, "import_service", "/internal/import/startup", {"context": _context("zeta"), "source_ref": "gs-1"}
    )
    assert replay.status_code == 201
    assert replay.json()["outcome"] == "replayed"
    assert replay.json()["tenant_record_ref"] == first.json()["tenant_record_ref"]
    assert replay.json()["import_id"] == first.json()["import_id"]


def test_the_same_source_imported_into_two_tenants_produces_two_independent_copies(
    fleet: srv.ServiceFleet,
) -> None:
    acme = _call(fleet, "import_service", "/internal/import/startup", {"context": _context("acme"), "source_ref": "gs-1"})
    zeta = _call(fleet, "import_service", "/internal/import/startup", {"context": _context("zeta"), "source_ref": "gs-1"})
    assert acme.json()["import_id"] != zeta.json()["import_id"]
    assert acme.json()["tenant_record_ref"].startswith("ref:acme:")
    assert zeta.json()["tenant_record_ref"].startswith("ref:zeta:")


def test_the_import_service_exposes_exactly_one_operation_and_no_synchronization(
    fleet: srv.ServiceFleet,
) -> None:
    """Import != Synchronization, asserted against the published surface."""
    document = httpx.get(fleet.url("import_service") + "/openapi.json", timeout=10.0).json()
    operations = {
        operation["operationId"]
        for item in document["paths"].values()
        for method, operation in item.items()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert operations == {"getImportServiceHealth", "getImportServiceReadiness", "importGlobalStartup"}
    for forbidden in ("sync", "refresh", "poll", "schedule", "subscribe", "mirror"):
        assert not [name for name in operations if forbidden in name.casefold()], forbidden


def test_the_import_service_has_no_postgresql_store_and_writes_no_tenant_row(fleet: srv.ServiceFleet) -> None:
    """**Stage 4 blocker B-1, made machine-visible.**

    The Import Service composes ``InMemoryImportStore`` unconditionally — there is no storage
    selector, no grant provider and no PostgreSQL adapter — so an import that reports success
    leaves no row in the tenant database it names. This test asserts the *current* behaviour
    rather than the intended one, so that the gap fails loudly the day someone implements the
    adapter and forgets to update it.

    The blocker is not the adapter itself; it is that writing one entails writing an IC-004
    lineage row, and every lineage row needs the D-23 per-tenant HMAC chain key, for which the
    rebuild has no secret-resolution surface, no configuration and no contract. Inventing one
    is exactly what §0.5 forbids.
    """
    from snackportal2.services import import_service as import_package
    from snackportal2.services.import_service import main as import_main
    from snackportal2.services.import_service import service as import_service_module

    del import_package
    assert isinstance(import_main._store, import_service_module.InMemoryImportStore)
    assert not [name for name in dir(import_service_module) if name.startswith("Postgres")]

    before = pg.scalar(pg.dsn("nova"), "SELECT count(*) FROM startups")
    lineage_before = pg.scalar(pg.dsn("nova"), "SELECT count(*) FROM lineage")
    result = _call(
        fleet, "import_service", "/internal/import/startup", {"context": _context("nova"), "source_ref": "gs-1"}
    )
    assert result.status_code == 201, result.text
    assert pg.scalar(pg.dsn("nova"), "SELECT count(*) FROM startups") == before, (
        "the Import Service now writes to PostgreSQL — blocker B-1 is resolved and this test must be replaced"
    )
    assert pg.scalar(pg.dsn("nova"), "SELECT count(*) FROM lineage") == lineage_before


def test_a_tenantless_import_is_refused_before_anything_is_written(fleet: srv.ServiceFleet) -> None:
    response = _call(
        fleet, "import_service", "/internal/import/startup", {"context": _context(None), "source_ref": "gs-1"}
    )
    assert response.status_code == 404
    assert response.json() == {"status": 404, "code": "tenant_not_found"}


# --- credential hygiene across every domain service ---------------------------------------


def test_no_domain_service_response_or_log_discloses_a_connection_string(fleet: srv.ServiceFleet) -> None:
    fragments: List[str] = srv.dsn_secret_fragments()
    bodies = [
        _call(fleet, "startups", "/internal/startups/list", {"context": _context("acme"), "limit": 500}).text,
        _call(fleet, "investors", "/internal/investors/list", {"context": _context("acme"), "limit": 500}).text,
        _call(fleet, "deals", "/internal/deals/list", {"context": _context("nova"), "limit": 500}).text,
        _call(fleet, "lineage", "/internal/lineage/list", {"context": _context("acme"), "limit": 500}).text,
        _call(fleet, "startups", "/internal/startups/read", {"context": _context("acme"), "record_ref": "bogus"}).text,
    ]
    for service in ("startups", "investors", "deals", "lineage", "import_service"):
        bodies.append(httpx.get(fleet.url(service) + "/readiness", timeout=10.0).text)
        bodies.append(httpx.get(fleet.url(service) + "/openapi.json", timeout=10.0).text)

    for body in bodies:
        for fragment in fragments:
            assert fragment not in body, "a domain-service response disclosed a DSN fragment"

    for key, text in fleet.all_logs().items():
        for fragment in fragments:
            assert fragment not in text, key + " logged a DSN fragment"


def test_every_tenant_operation_requires_an_internal_credential(fleet: srv.ServiceFleet) -> None:
    for service, path in (
        ("startups", "/internal/startups/list"),
        ("investors", "/internal/investors/list"),
        ("deals", "/internal/deals/list"),
        ("lineage", "/internal/lineage/list"),
        ("import_service", "/internal/import/startup"),
    ):
        response = httpx.post(fleet.url(service) + path, json={"context": _context("acme")}, timeout=10.0)
        assert response.status_code == 401, service


def test_a_tenantless_context_reaches_no_tenant_database(fleet: srv.ServiceFleet) -> None:
    for service, path in (
        ("startups", "/internal/startups/list"),
        ("investors", "/internal/investors/list"),
        ("deals", "/internal/deals/list"),
        ("lineage", "/internal/lineage/list"),
    ):
        response = _call(fleet, service, path, {"context": _context(None), "limit": 10})
        assert response.status_code == 404, service
        assert response.json() == {"status": 404, "code": "tenant_not_found"}
