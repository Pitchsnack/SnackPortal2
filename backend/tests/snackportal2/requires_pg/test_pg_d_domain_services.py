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
from snackportal2.services.import_service.service import operation_key
from snackportal2.services.startups.models import YEAR_FOUNDED_MAX
from snackportal2.shared.lineage_chain import CURRENT_MARKER_VERSION, GENESIS_PREV_MARKER, marker_for
from snackportal2.shared.lineage_keys import EnvironmentLineageKeyResolver
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
    "import_service": "grant-import",
}

#: Per-tenant D-23 chain keys for the Import Service process.
#:
#: Test material, generated here and nowhere else — distinct per tenant, because a shared key
#: would make every tenant's chain verifiable with one secret and the per-tenant property would
#: be untested. Long enough to clear the resolver's configured floor.
LINEAGE_KEYS = {
    EnvironmentLineageKeyResolver.variable_name(tenant): "stage5-chain-key-" + tenant + "-" + ("0" * 20) for tenant in pg.TENANTS
}

#: The tenant whose chain the import section starts from genesis. Nothing seeds lineage here.
GENESIS_TENANT = "nova"

#: The prefix every derived import operation key carries. Seeded fixture lineage rows use
#: ``job-``, so the two sets never overlap.
IMPORT_KEY_PREFIX = "imp-%"

#: Fleet name of the second, deliberately key-less Import Service process.
KEYLESS_IMPORT = "import_service_without_keys"

#: The global record this module's own import assertions use.
#:
#: Dedicated rather than shared: ``gs-1`` is seeded by the Control Plane module too, with a
#: different attribute set, and ``ON CONFLICT DO NOTHING`` means whichever module runs first
#: wins. A test that asserts which columns an import maps must own the record it maps.
DOMAIN_SOURCE = "gs-domain-import"

#: Global directory records the rollback probes import. Seeded alongside the ordinary one.
ROLLBACK_LINEAGE_SOURCE = "gs-rollback-lineage"
ROLLBACK_STARTUP_SOURCE = "gs-rollback-startup"
ROLLBACK_STARTUP_NAME = "Rollback Probe Corp"


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
    for record_id, display_name, attributes in (
        ("gs-1", "Alpha Corp", {"industry": "robotics"}),
        (DOMAIN_SOURCE, "Domain Import Corp", {"industry": "robotics", "headquarters_country": "NL"}),
        (ROLLBACK_LINEAGE_SOURCE, "Lineage Rollback Corp", {}),
        (ROLLBACK_STARTUP_SOURCE, ROLLBACK_STARTUP_NAME, {}),
        ("gs-preexisting", "Preexisting Copy Corp", {}),
    ):
        pg.execute(
            pg.dsn("control"),
            "INSERT INTO control_directory (directory, record_id, display_name, attributes) "
            "VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (directory, record_id) DO NOTHING",
            ("GlobalStartupDirectory", record_id, display_name, json.dumps(attributes)),
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
                "SP2_DATABASE_ROUTER_GRANTEES": json.dumps({credential: service for service, credential in GRANT_CREDENTIALS.items()}),
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
                "SP2_IMPORT_SERVICE_SERVICE_CREDENTIAL": GRANT_CREDENTIALS["import_service"],
                "SP2_IMPORT_SERVICE_STORAGE": "postgres",
                "SP2_IMPORT_SERVICE_DATABASE_ROUTER_URL": router.base_url,
                **LINEAGE_KEYS,
            },
        )
        # A second Import Service, identical except that it holds no chain key for any tenant.
        # It exists to prove the fail-closed path end to end in a real process: the same code
        # that imports successfully next door must refuse here, and must refuse before it
        # writes anything.
        running.start(
            "import_service",
            {
                "SP2_IMPORT_SERVICE_CONTROL_PLANE_URL": control.base_url,
                "SP2_IMPORT_SERVICE_SERVICE_CREDENTIAL": GRANT_CREDENTIALS["import_service"],
                "SP2_IMPORT_SERVICE_STORAGE": "postgres",
                "SP2_IMPORT_SERVICE_DATABASE_ROUTER_URL": router.base_url,
            },
            alias=KEYLESS_IMPORT,
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
        "SELECT company_name, company_url, industry, investment_stage, short_description FROM startups WHERE company_name = %s",
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
    assert (
        pg.scalar(pg.dsn("acme"), "SELECT company_url FROM startups WHERE company_name = 'Nordwind Labs'") == "https://nordwind.example.org"
    )


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
                "year_founded": 2019,
                "industry": "logistics",
                "investment_stage": "series_a",
                "product_overview": "Freight scheduling.",
                "global_startup_id": "gs-roundtrip",
            },
        )
    )
    read = _call(fleet, "startups", "/internal/startups/read", {"context": _context("acme"), "record_ref": created["record_ref"]})
    assert read.status_code == 200, read.text
    assert read.json() == created, "create and read disagree about the same record"


def test_year_founded_reaches_postgresql_as_an_integer_and_reads_back_as_one(
    fleet: srv.ServiceFleet,
) -> None:
    """**Stage 4 finding F-3, closed and verified against the real column.**

    The contract published free text while tenant DDL 003 typed the column ``integer``, so a
    value like ``"circa"`` passed validation and failed at the driver — answering 500 for a
    rejected input. The contract is now an integer bounded at 1800 and the current year, and
    this checks both halves: the accepted value is an ``integer`` in PostgreSQL, and the
    rejected ones never get there.
    """
    accepted = _created(
        _call(
            fleet,
            "startups",
            "/internal/startups/create",
            {"context": _context("acme"), "company_name": "Numeric Year Ltd", "year_founded": 1999},
        )
    )
    assert accepted["year_founded"] == 1999
    assert isinstance(accepted["year_founded"], int)

    stored = pg.rows(
        pg.dsn("acme"),
        "SELECT year_founded, pg_typeof(year_founded)::text FROM startups WHERE company_name = %s",
        ("Numeric Year Ltd",),
    )
    assert stored == [(1999, "integer")], "the value did not reach PostgreSQL as an integer"

    read = _call(fleet, "startups", "/internal/startups/read", {"context": _context("acme"), "record_ref": accepted["record_ref"]})
    assert read.status_code == 200, read.text
    assert read.json()["year_founded"] == 1999


def test_a_year_the_column_cannot_hold_is_refused_before_the_driver_sees_it(
    fleet: srv.ServiceFleet,
) -> None:
    """422 rather than 500, and nothing written — for every shape of bad year.

    The distinction that matters is *where* the rejection happens. Previously the database
    refused the value and the service reported an internal error; now the contract refuses it,
    which is why the answer is the 422 the operation already declared.
    """
    for label, value in (
        ("non-numeric", "circa"),
        ("below the lower bound", 1700),
        ("in the future", YEAR_FOUNDED_MAX + 1),
        ("fractional", 2020.5),
    ):
        response = _call(
            fleet,
            "startups",
            "/internal/startups/create",
            {"context": _context("acme"), "company_name": "Ambiguous Year Ltd", "year_founded": value},
        )
        assert response.status_code == 422, label + " -> " + str(response.status_code) + " " + response.text
        assert response.json() == {"status": 422, "code": "invalid_request"}
        assert str(value) not in response.text, label + ": the failure echoed the submitted value back"

    assert pg.scalar(pg.dsn("acme"), "SELECT count(*) FROM startups WHERE company_name = 'Ambiguous Year Ltd'") == 0


def test_the_published_year_founded_contract_matches_the_column_type(fleet: srv.ServiceFleet) -> None:
    """The contract and the column, compared to each other rather than each to an expectation."""
    document = httpx.get(fleet.url("startups") + "/openapi.json", timeout=10.0).json()
    published = document["components"]["schemas"]["StartupCreateRequest"]["properties"]["year_founded"]
    variants = {option.get("type") for option in published["anyOf"]}
    assert variants == {"integer", "null"}, published
    assert published["description"].strip()

    column = pg.rows(
        pg.dsn("acme"),
        "SELECT data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'startups' AND column_name = 'year_founded'",
    )
    assert column == [("integer", "YES")], column


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
    created = _created(_call(fleet, "startups", "/internal/startups/create", {"context": _context("zeta"), "company_name": "Zeta Only"}))
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
    assert stored == [(["seed", "series_a"], ["robotics", "energy"], "https://northwind.example.com", "array", "array")], (
        "the focus lists did not reach PostgreSQL as jsonb arrays"
    )

    read = _call(fleet, "investors", "/internal/investors/read", {"context": _context("acme"), "record_ref": created["record_ref"]})
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
    other = _call(fleet, "investors", "/internal/investors/read", {"context": _context("acme"), "record_ref": created["record_ref"]})
    assert other.status_code == 404
    assert pg.scalar(pg.dsn("acme"), "SELECT count(*) FROM investors WHERE investor_name = 'Zeta Ventures'") == 0
    assert pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM investors WHERE investor_name = 'Zeta Ventures'") == 1


# --- 6.3 Deal Service ---------------------------------------------------------------------


def test_a_deal_binds_two_records_of_the_same_tenant(fleet: srv.ServiceFleet) -> None:
    startup = _created(_call(fleet, "startups", "/internal/startups/create", {"context": _context("nova"), "company_name": "Nova Startup"}))
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
    assert pg.rows(pg.dsn("nova"), "SELECT stage, status FROM deals WHERE deal_name = 'Updatable'") == [("diligence", "in_diligence")]


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

    response = _call(fleet, "lineage", "/internal/lineage/for-record", {"context": _context("acme"), "target_ref": subject["record_ref"]})
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


# --- 6.4 Import Service: the real PostgreSQL write path -------------------------------------
#
# Stage 4 recorded blocker B-1 here: the Import Service composed an in-memory store
# unconditionally, so an import that answered 201 left no row in the tenant database it named.
# Stage 5 closes it. These tests assert what is now written, that it is written atomically, and
# that it is written only into the one tenant the signed claim names.


def _import(fleet: srv.ServiceFleet, tenant: Optional[str], source_ref: str, service: str = "import_service") -> httpx.Response:
    return _call(fleet, service, "/internal/import/startup", {"context": _context(tenant), "source_ref": source_ref})


def _lineage_row(tenant: str, source_ref: str) -> Optional[tuple]:
    """The lineage row an import of ``source_ref`` produced in ``tenant``, with every chained
    column the marker is computed over."""
    found = pg.rows(
        pg.dsn(tenant),
        "SELECT lineage_id, seq, segment_id, event_type, occurred_at, actor_ref, source_ref, target_ref, "
        "operation, schema_version, derivation_ref, parent_lineage_ref, correlation_id, marker_version, "
        "prev_marker, integrity_marker FROM lineage WHERE source_ref = %s ORDER BY seq",
        (source_ref,),
    )
    return found[0] if found else None


_CHAINED = (
    "lineage_id",
    "seq",
    "segment_id",
    "event_type",
    "occurred_at",
    "actor_ref",
    "source_ref",
    "target_ref",
    "operation",
    "schema_version",
    "derivation_ref",
    "parent_lineage_ref",
    "correlation_id",
    "marker_version",
    "prev_marker",
    "integrity_marker",
)


def _as_record(row: tuple) -> Dict[str, Any]:
    return {name: row[index] for index, name in enumerate(_CHAINED)}


def test_the_import_source_is_read_from_the_real_control_database(fleet: srv.ServiceFleet) -> None:
    """The global read really does traverse Control PostgreSQL.

    A source reference absent from ``control_directory`` must be *not found*, and one present
    must import — which is only distinguishable if the read is genuinely hitting the database.
    """
    missing = _import(fleet, "acme", "gs-absent")
    assert missing.status_code == 404, missing.text

    created = _import(fleet, "acme", "gs-1")
    assert created.status_code == 201, created.text
    assert created.json()["outcome"] == "created"
    assert created.json()["source_ref"] == "gs-1"
    assert created.json()["target_tenant_ref"] == "acme"


def test_a_first_import_writes_the_copy_its_lineage_and_its_idempotency_row(fleet: srv.ServiceFleet) -> None:
    """**Stage 4 blocker B-1, now closed.** Three rows, in one tenant database.

    ``nova`` is used because nothing else in this module seeds its chain, so this is a genuine
    genesis append: sequence 1, with the empty predecessor marker the chain starts from.
    """
    tenant = GENESIS_TENANT
    assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM lineage") == 0, "the genesis tenant already had lineage"

    response = _import(fleet, tenant, DOMAIN_SOURCE)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["outcome"] == "created"

    # 1 — the independent tenant copy, carrying a soft reference to its global source.
    copy = pg.rows(
        pg.dsn(tenant),
        "SELECT id, global_startup_id, company_name, industry, headquarters_country FROM startups WHERE global_startup_id = %s",
        (DOMAIN_SOURCE,),
    )
    assert len(copy) == 1, "the import wrote no tenant startup row"
    assert copy[0][1:] == (DOMAIN_SOURCE, "Domain Import Corp", "robotics", "NL")
    assert body["tenant_record_ref"] == "ref:" + tenant + ":startups:" + str(copy[0][0])

    # 2 — its provenance, at the head of a chain that starts here.
    row = _lineage_row(tenant, DOMAIN_SOURCE)
    assert row is not None, "the import wrote no lineage row"
    record = _as_record(row)
    assert record["seq"] == 1
    assert record["prev_marker"] == GENESIS_PREV_MARKER
    assert record["event_type"] == "import"
    assert record["operation"] == "global_startup_import"
    assert record["actor_ref"] == "p-agent"
    assert record["target_ref"] == body["tenant_record_ref"]
    assert record["schema_version"] == "1"
    assert record["marker_version"] == CURRENT_MARKER_VERSION
    assert body["lineage_ref"] == "ref:" + tenant + ":lineage:" + str(record["lineage_id"])

    # 3 — the idempotency record and its job, keyed by the derived operation key.
    key = operation_key(tenant, DOMAIN_SOURCE)
    assert body["import_id"] == key
    assert record["derivation_ref"] == key
    assert pg.rows(pg.dsn(tenant), "SELECT job_id, status, applied FROM import_idempotency WHERE operation_key = %s", (key,)) == [
        (key, "completed", 1)
    ]
    assert pg.rows(pg.dsn(tenant), "SELECT operation_key, tenant_id, state FROM import_job WHERE job_id = %s", (key,)) == [
        (key, tenant, "completed")
    ]


def test_the_lineage_marker_is_a_real_d23_marker_and_not_a_placeholder(fleet: srv.ServiceFleet) -> None:
    """Recomputed from the stored row and this tenant's key — the only way to know it is real.

    A non-empty ``integrity_marker`` proves nothing on its own; Stage 4's own fixture rows
    carried the string ``fixture-marker-1``. This recomputes the keyed HMAC over the row's own
    canonical serialization and its recorded predecessor, and requires the stored value to
    match. It then shows that the *other* tenant's key does not verify it, which is what makes
    the chain per-tenant rather than merely tenant-resident.
    """
    del fleet  # the import happened in the previous test; this reads what it wrote
    tenant = GENESIS_TENANT
    row = _lineage_row(tenant, DOMAIN_SOURCE)
    assert row is not None
    record = _as_record(row)

    key = LINEAGE_KEYS[EnvironmentLineageKeyResolver.variable_name(tenant)].encode("utf-8")
    recomputed = marker_for(key, record, str(record["prev_marker"]), marker_version=int(record["marker_version"]))
    assert record["integrity_marker"] == recomputed, "the stored marker is not a D-23 marker over this row"
    assert len(str(record["integrity_marker"])) == 64

    other = LINEAGE_KEYS[EnvironmentLineageKeyResolver.variable_name("acme")].encode("utf-8")
    assert marker_for(other, record, str(record["prev_marker"])) != record["integrity_marker"]

    # And tampering with any chained field breaks it, which is the property the marker exists for.
    tampered = dict(record)
    tampered["target_ref"] = "ref:" + tenant + ":startups:999999"
    assert marker_for(key, tampered, str(record["prev_marker"])) != record["integrity_marker"]


def test_a_second_import_extends_the_chain_rather_than_starting_a_new_one(fleet: srv.ServiceFleet) -> None:
    tenant = GENESIS_TENANT
    first = _lineage_row(tenant, DOMAIN_SOURCE)
    assert first is not None
    first_record = _as_record(first)

    response = _import(fleet, tenant, "gs-preexisting")
    assert response.status_code == 201, response.text

    second = _lineage_row(tenant, "gs-preexisting")
    assert second is not None
    second_record = _as_record(second)

    assert second_record["seq"] == int(first_record["seq"]) + 1
    assert second_record["prev_marker"] == first_record["integrity_marker"], "the chain forked instead of extending"
    assert second_record["segment_id"] == first_record["segment_id"]

    key = LINEAGE_KEYS[EnvironmentLineageKeyResolver.variable_name(tenant)].encode("utf-8")
    assert second_record["integrity_marker"] == marker_for(key, second_record, str(second_record["prev_marker"]))


def test_import_is_idempotent_per_tenant_and_source(fleet: srv.ServiceFleet) -> None:
    """A retry must replay, and must add no second copy, lineage row, or idempotency record."""
    first = _import(fleet, "zeta", "gs-1")
    assert first.status_code == 201, first.text
    assert first.json()["outcome"] == "created"

    counts = (
        pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM startups WHERE global_startup_id = 'gs-1'"),
        pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM lineage"),
        pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM import_idempotency"),
    )
    assert counts == (1, 1, 1)

    replay = _import(fleet, "zeta", "gs-1")
    assert replay.status_code == 201
    assert replay.json()["outcome"] == "replayed"
    assert replay.json()["tenant_record_ref"] == first.json()["tenant_record_ref"]
    assert replay.json()["lineage_ref"] == first.json()["lineage_ref"]
    assert replay.json()["import_id"] == first.json()["import_id"]

    assert (
        pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM startups WHERE global_startup_id = 'gs-1'"),
        pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM lineage"),
        pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM import_idempotency"),
    ) == counts, "a replayed import wrote something"


def test_the_same_source_imported_into_two_tenants_produces_two_physically_separate_copies(
    fleet: srv.ServiceFleet,
) -> None:
    """Two independent copies in two separate clusters — asserted at the databases."""
    acme = _import(fleet, "acme", "gs-1")
    zeta = _import(fleet, "zeta", "gs-1")
    assert acme.json()["import_id"] != zeta.json()["import_id"]
    assert acme.json()["tenant_record_ref"].startswith("ref:acme:")
    assert zeta.json()["tenant_record_ref"].startswith("ref:zeta:")

    for tenant in ("acme", "zeta"):
        assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM startups WHERE global_startup_id = 'gs-1'") == 1
    assert pg.scalar(pg.dsn(GENESIS_TENANT), "SELECT count(*) FROM startups WHERE global_startup_id = 'gs-1'") == 0

    # The lineage rows are different rows, with different ids, in different databases.
    identities = {tenant: _as_record(_lineage_row(tenant, "gs-1"))["lineage_id"] for tenant in ("acme", "zeta")}
    assert identities["acme"] != identities["zeta"]
    assert pg.scalar(pg.dsn("zeta"), "SELECT count(*) FROM lineage WHERE lineage_id = %s", (identities["acme"],)) == 0


def test_an_import_opens_a_session_only_on_its_own_tenant_database(fleet: srv.ServiceFleet) -> None:
    """Physical isolation measured from inside each cluster, not inferred from the API."""
    with pg.SessionWatch(pg.TENANTS) as watch:
        baseline = watch.snapshot()
        response = _import(fleet, "acme", ROLLBACK_LINEAGE_SOURCE)
        assert response.status_code == 201, response.text
        delta = watch.delta_since(baseline)
    assert delta["acme"] > 0, "the import opened no session on its own tenant database"
    assert delta["zeta"] == 0 and delta[GENESIS_TENANT] == 0, delta


def test_an_import_writes_nothing_to_the_control_database(fleet: srv.ServiceFleet) -> None:
    """The global record is read, never written, and nothing falls back to the Control DB."""
    control = pg.dsn("control")
    tables = pg.table_names(control)
    before = {table: pg.scalar(control, "SELECT count(*) FROM " + table) for table in tables}

    response = _import(fleet, "zeta", "gs-preexisting")
    assert response.status_code == 201, response.text

    after = {table: pg.scalar(control, "SELECT count(*) FROM " + table) for table in tables}
    assert after == before, "an import changed the Control database"


def test_a_failed_lineage_write_rolls_back_the_startup_copy(fleet: srv.ServiceFleet) -> None:
    """Atomic provenance, proven by breaking the lineage write on purpose.

    A CHECK constraint scoped to one source reference makes exactly this import's lineage
    insert fail, and nothing else. If the three writes were not one transaction, the startup
    copy would survive without provenance — which IC-004 forbids outright.
    """
    tenant = "zeta"
    key = operation_key(tenant, ROLLBACK_LINEAGE_SOURCE)
    pg.execute(
        pg.dsn(tenant),
        "ALTER TABLE lineage ADD CONSTRAINT stage5_lineage_probe CHECK (source_ref <> %s)" % ("'" + ROLLBACK_LINEAGE_SOURCE + "'"),
    )
    try:
        response = _import(fleet, tenant, ROLLBACK_LINEAGE_SOURCE)
        assert response.status_code == 500, response.text
        assert response.json() == {"status": 500, "code": "internal_error"}
    finally:
        pg.execute(pg.dsn(tenant), "ALTER TABLE lineage DROP CONSTRAINT stage5_lineage_probe")

    assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM startups WHERE global_startup_id = %s", (ROLLBACK_LINEAGE_SOURCE,)) == 0, (
        "the tenant copy survived a failed lineage write"
    )
    assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM lineage WHERE source_ref = %s", (ROLLBACK_LINEAGE_SOURCE,)) == 0
    assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM import_idempotency WHERE operation_key = %s", (key,)) == 0
    assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM import_job WHERE job_id = %s", (key,)) == 0

    # And the same import succeeds once the injected fault is gone, so the rollback left the
    # tenant in a state a retry can still complete from.
    retried = _import(fleet, tenant, ROLLBACK_LINEAGE_SOURCE)
    assert retried.status_code == 201, retried.text
    assert retried.json()["outcome"] == "created"


def test_a_failed_startup_write_leaves_no_idempotency_or_lineage_row(fleet: srv.ServiceFleet) -> None:
    """The mirror case: the first write fails, so the other two must never happen."""
    tenant = "zeta"
    key = operation_key(tenant, ROLLBACK_STARTUP_SOURCE)
    pg.execute(
        pg.dsn(tenant),
        "ALTER TABLE startups ADD CONSTRAINT stage5_startup_probe CHECK (company_name <> %s)" % ("'" + ROLLBACK_STARTUP_NAME + "'"),
    )
    try:
        response = _import(fleet, tenant, ROLLBACK_STARTUP_SOURCE)
        assert response.status_code == 500, response.text
    finally:
        pg.execute(pg.dsn(tenant), "ALTER TABLE startups DROP CONSTRAINT stage5_startup_probe")

    assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM lineage WHERE source_ref = %s", (ROLLBACK_STARTUP_SOURCE,)) == 0
    assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM import_idempotency WHERE operation_key = %s", (key,)) == 0
    assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM import_job WHERE job_id = %s", (key,)) == 0


def test_a_tenant_that_already_holds_a_copy_of_the_source_is_refused_not_updated(
    fleet: srv.ServiceFleet,
) -> None:
    """An import produces a copy; it never mutates one. That is Import != Synchronization.

    The Startup Service can also create a record carrying a ``global_startup_id``. When one
    already exists, importing the same source cannot lawfully produce a second independent copy
    (the accepted DDL's per-tenant unique index forbids it) and must not quietly update the
    existing one. It is refused, with nothing written.
    """
    tenant = "acme"
    created = _created(
        _call(
            fleet,
            "startups",
            "/internal/startups/create",
            {"context": _context(tenant), "company_name": "Hand Made Copy", "global_startup_id": "gs-preexisting"},
        )
    )
    before = pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM lineage")

    response = _import(fleet, tenant, "gs-preexisting")
    assert response.status_code == 422, response.text
    assert response.json() == {"status": 422, "code": "invalid_request"}

    assert pg.rows(pg.dsn(tenant), "SELECT company_name FROM startups WHERE global_startup_id = 'gs-preexisting'") == [
        ("Hand Made Copy",)
    ], "the import updated an existing record instead of refusing"
    assert pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM lineage") == before
    del created


def test_an_import_service_without_a_chain_key_refuses_and_writes_nothing(fleet: srv.ServiceFleet) -> None:
    """The fail-closed path, in a real process, against the real databases.

    This is the same service module and the same PostgreSQL configuration as the working
    instance; the only difference is that no chain key is configured for any tenant. It must
    refuse rather than write a tenant record with an empty, absent, or default marker.
    """
    tenant = "acme"
    before = (
        pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM startups"),
        pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM lineage"),
        pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM import_idempotency"),
    )

    with pg.SessionWatch(pg.TENANTS) as watch:
        baseline = watch.snapshot()
        response = _import(fleet, tenant, ROLLBACK_STARTUP_SOURCE, service=KEYLESS_IMPORT)
        delta = watch.delta_since(baseline)

    assert response.status_code == 503, response.text
    assert response.json() == {"status": 503, "code": "tenant_unavailable"}
    assert delta[tenant] == 0, "the refused import still opened a tenant database connection"

    assert (
        pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM startups"),
        pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM lineage"),
        pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM import_idempotency"),
    ) == before


def test_no_lineage_row_written_by_an_import_carries_an_empty_marker(fleet: srv.ServiceFleet) -> None:
    """Across every tenant, every import-written row has a full-length keyed marker.

    Selected by ``derivation_ref``, not by ``event_type``: the Lineage Service section above
    seeds rows that deliberately carry ``event_type = 'import'`` and an avowedly fake marker,
    and a census that could not tell those apart from real ones would be measuring nothing. The
    derived operation key is prefixed ``imp-`` and the seeds use ``job-``, so the two sets are
    disjoint by construction.
    """
    del fleet
    written = 0
    for tenant in pg.TENANTS:
        written += int(pg.scalar(pg.dsn(tenant), "SELECT count(*) FROM lineage WHERE derivation_ref LIKE %s", (IMPORT_KEY_PREFIX,)) or 0)
        empty = pg.scalar(
            pg.dsn(tenant),
            "SELECT count(*) FROM lineage WHERE derivation_ref LIKE %s "
            "AND (integrity_marker IS NULL OR length(integrity_marker) <> 64 OR prev_marker IS NULL)",
            (IMPORT_KEY_PREFIX,),
        )
        assert empty == 0, tenant + " holds an import lineage row without a real marker"
    assert written >= 5, "the census matched too few rows to mean anything: " + str(written)


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


def test_configuring_postgresql_added_no_operation_and_no_secret_field(fleet: srv.ServiceFleet) -> None:
    """The write path is new; the published contract is not.

    Stage 5 gave the Import Service a database, a router grant and a secret resolver. None of
    those may appear on the wire — not as a route, not as a field, not as a schema.

    Checked over property *names* and over the real key values, not by grepping the whole
    document: the descriptions legitimately contain the words "dsn" and "credential" precisely
    because they promise the field carries neither, and a substring check would read those
    promises as violations.
    """
    document = httpx.get(fleet.url("import_service") + "/openapi.json", timeout=10.0).json()

    for name, definition in (document.get("components", {}).get("schemas", {}) or {}).items():
        for property_name in definition.get("properties") or {}:
            folded = property_name.casefold()
            for forbidden in ("key", "secret", "dsn", "password", "credential", "grant"):
                assert forbidden not in folded, "the import contract publishes " + name + "." + property_name

    rendered = json.dumps(document)
    for key_value in LINEAGE_KEYS.values():
        assert key_value not in rendered, "a chain key reached the published contract"
    for variable in LINEAGE_KEYS:
        assert variable not in rendered
    for fragment in srv.dsn_secret_fragments():
        assert fragment not in rendered


def test_a_tenantless_import_is_refused_before_anything_is_written(fleet: srv.ServiceFleet) -> None:
    response = _import(fleet, None, "gs-1")
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
