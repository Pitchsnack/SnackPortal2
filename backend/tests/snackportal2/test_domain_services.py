"""Day 2 — the seven domain services.

Each service is exercised for the behaviour its contract actually names, and for the isolation
property that matters most in its own shape: for Startups and Investors that a record reference
does not travel between tenants, for Deals that a party reference cannot, for Import that a
retry does not duplicate, and for Contacts and Sharing that the absence of a contract produces a
refusal rather than an improvisation.
"""

from __future__ import annotations

import ast
import pathlib

from fastapi.testclient import TestClient

from snackportal2.services.ai_agents import main as ai_main
from snackportal2.services.contacts import main as contacts_main
from snackportal2.services.deals import main as deals_main
from snackportal2.services.deals.repository import InMemoryDealRepository
from snackportal2.services.import_service import main as import_main
from snackportal2.services.import_service import service as import_service
from snackportal2.services.import_service import store as import_store
from snackportal2.services.investors import main as investors_main
from snackportal2.services.investors.repository import InMemoryInvestorRepository
from snackportal2.services.lineage import main as lineage_main
from snackportal2.services.sharing import main as sharing_main
from snackportal2.services.startups import main as startups_main
from snackportal2.services.startups.repository import InMemoryStartupRepository, find_duplicates
from snackportal2.shared.errors import AppError
from snackportal2.shared.security import AuthContext, RequestContext
from snackportal2.shared.types import PlatformRole
from snackportal2.shared.urls import normalize_website

from ._openapi_rules import assert_document

_CREDENTIAL = {"Authorization": "Bearer internal-service-credential"}


def _context(tenant: str | None = "acme") -> dict[str, object]:
    return RequestContext.from_auth_context(
        AuthContext(correlation_id="c-1", principal_ref="p-agent", role=PlatformRole.TENANT_AGENT, active_tenant_ref=tenant)
    ).model_dump(mode="json")


# --- Website normalization (shared, used by Startups and Investors) --------------------------

def test_website_normalization_makes_equal_things_compare_equal() -> None:
    """Two records differing only by scheme, case, 'www.' or a trailing slash are one company."""
    canonical = "https://acme.example"
    for variant in ("acme.example", "HTTPS://ACME.EXAMPLE", "https://www.acme.example", "https://acme.example/"):
        assert normalize_website(variant) == canonical, variant


def test_a_malformed_website_is_rejected_not_stored_raw() -> None:
    for hostile in ("ftp://acme.example", "https://", "not a url at all", "javascript:alert(1)"):
        try:
            normalize_website(hostile)
        except AppError as error:
            assert error.status == 422
        else:
            raise AssertionError("a malformed website was accepted: " + hostile)


def test_an_absent_website_stays_absent() -> None:
    assert normalize_website(None) is None
    assert normalize_website("   ") is None


# --- Startup Service -------------------------------------------------------------------------

def _startups_client() -> TestClient:
    startups_main._repository = InMemoryStartupRepository()  # type: ignore[attr-defined]
    return TestClient(startups_main.app, raise_server_exceptions=False)


def test_startup_create_read_update_round_trip() -> None:
    client = _startups_client()
    created = client.post(
        "/internal/startups/create",
        headers=_CREDENTIAL,
        json={"context": _context(), "company_name": "Acme Robotics", "company_url": "www.acme.example/"},
    )
    assert created.status_code == 201
    record_ref = created.json()["record_ref"]
    assert created.json()["company_url"] == "https://acme.example"

    read = client.post("/internal/startups/read", headers=_CREDENTIAL, json={"context": _context(), "record_ref": record_ref})
    assert read.status_code == 200
    assert read.json()["company_name"] == "Acme Robotics"

    updated = client.post(
        "/internal/startups/update",
        headers=_CREDENTIAL,
        json={"context": _context(), "record_ref": record_ref, "short_description": "Industrial robotics."},
    )
    assert updated.status_code == 200
    assert updated.json()["short_description"] == "Industrial robotics."


def test_a_startup_reference_does_not_travel_between_tenants() -> None:
    client = _startups_client()
    created = client.post(
        "/internal/startups/create", headers=_CREDENTIAL, json={"context": _context("acme"), "company_name": "Acme"}
    )
    record_ref = created.json()["record_ref"]

    elsewhere = client.post(
        "/internal/startups/read", headers=_CREDENTIAL, json={"context": _context("zeta"), "record_ref": record_ref}
    )
    assert elsewhere.status_code == 404


def test_the_bounded_update_accepts_exactly_one_field() -> None:
    """IC-009 CLM: short_description is the sole mutable field, bounded at 500 characters."""
    client = _startups_client()
    created = client.post(
        "/internal/startups/create", headers=_CREDENTIAL, json={"context": _context(), "company_name": "Acme"}
    )
    record_ref = created.json()["record_ref"]

    over_bound = client.post(
        "/internal/startups/update",
        headers=_CREDENTIAL,
        json={"context": _context(), "record_ref": record_ref, "short_description": "x" * 501},
    )
    assert over_bound.status_code == 422

    other_field = client.post(
        "/internal/startups/update",
        headers=_CREDENTIAL,
        json={"context": _context(), "record_ref": record_ref, "company_name": "Renamed"},
    )
    # The extra field is not a mutable one; the update carries only short_description, so the
    # name is unchanged rather than quietly rewritten.
    assert other_field.status_code == 200
    read = client.post("/internal/startups/read", headers=_CREDENTIAL, json={"context": _context(), "record_ref": record_ref})
    assert read.json()["company_name"] == "Acme"


def test_the_duplicate_check_returns_candidates_not_decisions() -> None:
    repository = InMemoryStartupRepository()
    repository.create("acme", {"company_name": "Acme Robotics", "company_url": "https://acme.example"})

    by_name = find_duplicates(repository, "acme", "acme robotics", None)
    assert [reason for _record, reason in by_name] == ["name"]

    by_site = find_duplicates(repository, "acme", "Totally Different Ltd", "www.acme.example/")
    assert [reason for _record, reason in by_site] == ["website"]

    assert find_duplicates(repository, "acme", "Unrelated Ltd", "https://unrelated.example") == []
    # And nothing was merged, deleted, or altered by asking.
    assert len(repository.list("acme", 100)) == 1


def test_a_tenantless_context_cannot_reach_a_tenant_record() -> None:
    client = _startups_client()
    response = client.post("/internal/startups/list", headers=_CREDENTIAL, json={"context": _context(None), "limit": 10})
    assert response.status_code == 404
    assert response.json() == {"status": 404, "code": "tenant_not_found"}


# --- Investor Service --------------------------------------------------------------------------

def _investors_client() -> TestClient:
    investors_main._repository = InMemoryInvestorRepository()  # type: ignore[attr-defined]
    return TestClient(investors_main.app, raise_server_exceptions=False)


def test_investor_create_preserves_focus_lists_as_lists() -> None:
    """The DDL stores these as jsonb arrays; flattening them to strings would corrupt the shape."""
    client = _investors_client()
    created = client.post(
        "/internal/investors/create",
        headers=_CREDENTIAL,
        json={
            "context": _context(),
            "investor_name": "Northwind Capital",
            "website_url": "WWW.Northwind.example/",
            "investment_stage_focus": ["seed", "series_a"],
            "industry_focus": ["robotics"],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["investment_stage_focus"] == ["seed", "series_a"]
    assert body["industry_focus"] == ["robotics"]
    assert body["website_url"] == "https://northwind.example"


def test_investor_records_do_not_travel_between_tenants() -> None:
    client = _investors_client()
    created = client.post(
        "/internal/investors/create", headers=_CREDENTIAL, json={"context": _context("acme"), "investor_name": "Northwind"}
    )
    record_ref = created.json()["record_ref"]
    elsewhere = client.post(
        "/internal/investors/read", headers=_CREDENTIAL, json={"context": _context("zeta"), "record_ref": record_ref}
    )
    assert elsewhere.status_code == 404


# --- Deal Service --------------------------------------------------------------------------------

def _deals_client() -> TestClient:
    deals_main._repository = InMemoryDealRepository()  # type: ignore[attr-defined]
    return TestClient(deals_main.app, raise_server_exceptions=False)


def test_a_deal_cannot_be_created_from_another_tenants_party_reference() -> None:
    """The one record type naming two others is the one place a second tenant could sneak in."""
    client = _deals_client()
    response = client.post(
        "/internal/deals/create",
        headers=_CREDENTIAL,
        json={
            "context": _context("acme"),
            "deal_name": "Series A",
            "startup_ref": "ref:zeta:startups:1",
        },
    )
    assert response.status_code == 422
    assert response.json() == {"status": 422, "code": "invalid_request"}


def test_a_foreign_investor_reference_is_refused_not_silently_dropped() -> None:
    """Ignoring it would quietly produce an unmatched deal instead of failing the request."""
    client = _deals_client()
    response = client.post(
        "/internal/deals/create",
        headers=_CREDENTIAL,
        json={
            "context": _context("acme"),
            "deal_name": "Series A",
            "startup_ref": "ref:acme:startups:1",
            "investor_ref": "ref:zeta:investors:1",
        },
    )
    assert response.status_code == 422


def test_deal_parties_are_immutable_through_update() -> None:
    client = _deals_client()
    created = client.post(
        "/internal/deals/create",
        headers=_CREDENTIAL,
        json={"context": _context(), "deal_name": "Series A", "startup_ref": "ref:acme:startups:1"},
    )
    record_ref = created.json()["record_ref"]

    from snackportal2.services.deals.models import DealUpdateRequest

    assert set(DealUpdateRequest.model_fields) == {"context", "record_ref", "stage", "status"}

    updated = client.post(
        "/internal/deals/update",
        headers=_CREDENTIAL,
        json={"context": _context(), "record_ref": record_ref, "stage": "diligence", "status": "in_diligence"},
    )
    assert updated.status_code == 200
    assert updated.json()["startup_ref"] == "ref:acme:startups:1"


def test_the_deal_service_exposes_no_operation_that_copies_a_deal() -> None:
    """Sharing ≠ Deal Duplication, checked against the route table rather than by inspection."""
    paths = deals_main.app.openapi()["paths"]
    for path, item in paths.items():
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            identifier = str(operation.get("operationId", "")).casefold()
            for forbidden in ("copy", "duplicate", "clone", "fork", "share"):
                assert forbidden not in identifier, path + " exposes " + identifier


# --- Contacts Service (blocked on IC-015) ---------------------------------------------------------

def test_contacts_exposes_no_business_operation_and_names_its_blockers() -> None:
    client = TestClient(contacts_main.app, raise_server_exceptions=False)
    response = client.get("/internal/contacts/capabilities", headers=_CREDENTIAL)
    assert response.status_code == 200
    body = response.json()
    assert body["implemented"] is False
    assert any("IC-015" in blocker for blocker in body["blocked_on"])
    assert any("DDL" in blocker for blocker in body["blocked_on"])

    # No route invents a contact shape.
    paths = set(contacts_main.app.openapi()["paths"])
    assert paths == {"/health", "/readiness", "/internal/contacts/capabilities"}


def test_no_contacts_table_exists_in_the_accepted_ddl() -> None:
    """The finding this service is built around, verified against the repository rather than asserted."""
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    tenant_ddl = sorted((repo_root / "infrastructure" / "db" / "tenant").glob("*.sql"))
    assert tenant_ddl, "tenant DDL directory not found; the check would pass vacuously"
    for path in tenant_ddl:
        sql = path.read_text(encoding="utf-8").casefold()
        assert "create table if not exists contacts" not in sql, path.name + " defines a contacts table after all"


# --- Sharing Service (inert until IC-007 is Final) -------------------------------------------------

def test_sharing_refuses_every_proposal_and_says_why() -> None:
    client = TestClient(sharing_main.app, raise_server_exceptions=False)
    capabilities = client.get("/internal/sharing/capabilities", headers=_CREDENTIAL).json()
    assert capabilities["implemented"] is False
    assert any("IC-007" in blocker for blocker in capabilities["blocked_on"])
    assert len(capabilities["invariants"]) == 3

    refused = client.post(
        "/internal/sharing/proposals",
        headers=_CREDENTIAL,
        json={"context": _context(), "source_record_ref": "ref:acme:deals:1", "target_ref": "zeta"},
    )
    assert refused.status_code == 403
    assert refused.json() == {"status": 403, "code": "access_denied"}


# --- Import Service (IC-003) --------------------------------------------------------------------------

def _import_client() -> TestClient:
    store = import_service.InMemoryImportStore()
    directory = import_service.StaticGlobalDirectory(
        {
            "gs-1": import_service.GlobalSourceRecord(
                record_ref="gs-1", display_name="Alpha Corp", attributes={"industry": "robotics"}
            )
        }
    )
    import_main._store = store  # type: ignore[attr-defined]
    import_main._service = import_service.ImportService(directory, store)  # type: ignore[attr-defined]
    return TestClient(import_main.app, raise_server_exceptions=False)


def test_an_import_creates_an_independent_tenant_copy_with_a_soft_source_reference() -> None:
    client = _import_client()
    response = client.post("/internal/import/startup", headers=_CREDENTIAL, json={"context": _context(), "source_ref": "gs-1"})
    assert response.status_code == 201
    body = response.json()
    assert body["outcome"] == "created"
    assert body["source_ref"] == "gs-1"
    assert body["tenant_record_ref"].startswith("ref:acme:startups:")
    assert body["lineage_ref"].startswith("ref:acme:lineage:")


def test_a_repeated_import_replays_rather_than_duplicating() -> None:
    """A retried request — a client timeout, a proxy retry — must not produce a second copy."""
    client = _import_client()
    first = client.post("/internal/import/startup", headers=_CREDENTIAL, json={"context": _context(), "source_ref": "gs-1"}).json()
    second = client.post("/internal/import/startup", headers=_CREDENTIAL, json={"context": _context(), "source_ref": "gs-1"}).json()

    assert first["outcome"] == "created"
    assert second["outcome"] == "replayed"
    assert second["tenant_record_ref"] == first["tenant_record_ref"]
    assert second["import_id"] == first["import_id"]
    assert len(import_main._store.startups.list("acme", 100)) == 1  # type: ignore[attr-defined]


def test_the_same_source_imported_into_two_tenants_produces_two_independent_copies() -> None:
    client = _import_client()
    acme = client.post("/internal/import/startup", headers=_CREDENTIAL, json={"context": _context("acme"), "source_ref": "gs-1"}).json()
    zeta = client.post("/internal/import/startup", headers=_CREDENTIAL, json={"context": _context("zeta"), "source_ref": "gs-1"}).json()
    assert acme["outcome"] == "created" and zeta["outcome"] == "created"
    assert acme["tenant_record_ref"] != zeta["tenant_record_ref"]


def test_an_unknown_source_is_not_found() -> None:
    client = _import_client()
    response = client.post("/internal/import/startup", headers=_CREDENTIAL, json={"context": _context(), "source_ref": "gs-999"})
    assert response.status_code == 404


def test_the_import_service_contains_no_re_import_mechanism() -> None:
    """Import ≠ Synchronization, proven structurally rather than by absence of a test.

    A behavioural test cannot show that nothing schedules a re-import; it can only show that
    nothing did during the test. This shows the module has no scheduler, timer, background task,
    event subscription, or refresh entry point to schedule one with.
    """
    package = pathlib.Path(import_main.__file__).parent
    forbidden_calls = ("create_task", "call_later", "Timer", "Thread", "sleep", "schedule", "cron", "poll")
    forbidden_imports = ("asyncio", "threading", "sched", "apscheduler", "celery")
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_imports, path.name + " imports " + alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_imports, path.name + " imports " + node.module
            elif isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_calls, path.name + " references " + node.attr
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                folded = node.name.casefold()
                for forbidden in ("resync", "refresh", "reimport", "synchronize"):
                    assert forbidden not in folded, path.name + " defines " + node.name


def test_the_idempotency_key_is_derived_never_supplied() -> None:
    """A caller that could choose its key could choose an unused one and duplicate a record."""
    from snackportal2.services.import_service.models import ImportInitiationRequest

    assert set(ImportInitiationRequest.model_fields) == {"context", "source_ref"}
    first = import_service.operation_key("acme", "gs-1")
    assert first == import_service.operation_key("acme", "gs-1")
    assert first != import_service.operation_key("zeta", "gs-1")
    assert first != import_service.operation_key("acme", "gs-2")


# --- Import Service storage composition (Stage 5) ----------------------------------------------------

def test_the_import_store_is_in_memory_by_omission_and_postgresql_only_when_asked() -> None:
    """A silent fallback would turn a database outage into an import that writes nothing."""
    from snackportal2.services.import_service.store import PostgresImportStore

    assert isinstance(import_main._build_store({}), import_service.InMemoryImportStore)
    assert isinstance(import_main._build_store({import_main.ENV_STORAGE: "not-postgres"}), import_service.InMemoryImportStore)
    assert isinstance(import_main._build_store({import_main.ENV_STORAGE: "PostgreS"}), PostgresImportStore)


class _RecordingGrants:
    """A grant provider that records whether it was asked, and never issues anything."""

    def __init__(self) -> None:
        self.requests = 0

    def grant_for(self, tenant_ref: str | None) -> object:
        self.requests += 1
        raise AssertionError("a grant was requested")


def test_a_missing_chain_key_refuses_the_import_before_any_grant_is_requested() -> None:
    """Fail-closed ordering, asserted rather than assumed.

    A tenant with no provenance key cannot lawfully be written to. Resolving the key first
    means such a tenant never causes a router call and never causes a tenant database
    connection — the import is refused before it can touch anything at all.
    """
    from snackportal2.services.import_service.store import PostgresImportStore
    from snackportal2.shared.lineage_keys import build_lineage_key_resolver

    grants = _RecordingGrants()
    store = PostgresImportStore(grants, build_lineage_key_resolver({}))
    source = import_service.GlobalSourceRecord(record_ref="gs-1", display_name="Alpha Corp", attributes={})

    try:
        store.write_import("acme", "imp-key", source, import_service.ImportAttribution(actor_ref="p-agent"))
    except AppError as denial:
        assert denial.status == 503
    else:
        raise AssertionError("a missing chain key did not refuse the import")

    assert grants.requests == 0, "the router was asked for a grant before the chain key resolved"


def test_the_in_memory_lineage_row_carries_the_same_core_the_durable_one_writes() -> None:
    """The two stores must agree on field names, or a hermetic test predicts nothing."""
    from snackportal2.services.import_service.store import PostgresImportStore

    client = _import_client()
    client.post("/internal/import/startup", headers=_CREDENTIAL, json={"context": _context(), "source_ref": "gs-1"})
    rows = import_main._store.lineage.list("acme", 10)  # type: ignore[attr-defined]
    assert len(rows) == 1
    fields = rows[0][1]
    assert fields["event_type"] == import_service.EVENT_TYPE_IMPORT
    assert fields["operation"] == import_service.OPERATION_IMPORT
    assert fields["actor_ref"] == "p-agent"
    assert fields["correlation_id"] == "c-1"
    assert fields["derivation_ref"] == import_service.operation_key("acme", "gs-1")
    assert fields["source_ref"] == "gs-1"

    # Read from the durable store's own insert list, so renaming a column there fails here
    # rather than quietly leaving this test asserting names nothing writes any more.
    durable_columns = set(import_store._LINEAGE_COLUMNS)
    assert set(fields) - {"occurred_at"} <= durable_columns
    for name in ("event_type", "operation", "actor_ref", "correlation_id", "derivation_ref", "source_ref", "target_ref"):
        assert name in durable_columns, name
    assert PostgresImportStore is not None


def test_the_actor_and_correlation_cannot_be_chosen_by_the_caller() -> None:
    """IC-004 requires an actor reference; IC-013 §7 requires it to come from the signed context."""
    from snackportal2.services.import_service.models import ImportInitiationRequest

    assert set(ImportInitiationRequest.model_fields) == {"context", "source_ref"}
    client = _import_client()
    response = client.post(
        "/internal/import/startup",
        headers=_CREDENTIAL,
        json={"context": _context(), "source_ref": "gs-1", "actor_ref": "someone-else", "correlation_id": "forged"},
    )
    assert response.status_code == 201
    fields = import_main._store.lineage.list("acme", 10)[0][1]  # type: ignore[attr-defined]
    assert fields["actor_ref"] == "p-agent"
    assert fields["correlation_id"] == "c-1"


# --- Lineage Service (IC-004) ------------------------------------------------------------------------

def test_lineage_exposes_no_update_or_delete() -> None:
    """Append-only. An audit-adjacent record that can be rewritten is not provenance."""
    for path, item in lineage_main.app.openapi()["paths"].items():
        for method, operation in item.items():
            if not isinstance(operation, dict):
                continue
            assert method not in ("put", "delete", "patch"), path + " exposes " + method.upper()
            identifier = str(operation.get("operationId", "")).casefold()
            for forbidden in ("update", "delete", "amend", "rewrite"):
                assert forbidden not in identifier, path + " exposes " + identifier


def test_a_lineage_target_from_another_tenant_is_not_found() -> None:
    client = TestClient(lineage_main.app, raise_server_exceptions=False)
    response = client.post(
        "/internal/lineage/for-record",
        headers=_CREDENTIAL,
        json={"context": _context("acme"), "target_ref": "ref:zeta:startups:1"},
    )
    assert response.status_code == 404


# --- AI Agent Service (inert under IC-006) --------------------------------------------------------------

def test_the_ai_service_is_inert_and_records_the_approved_lifecycle() -> None:
    client = TestClient(ai_main.app, raise_server_exceptions=False)
    governance = client.get("/internal/ai/governance", headers=_CREDENTIAL).json()
    assert governance["implemented"] is False
    assert any("IC-006" in blocker for blocker in governance["blocked_on"])
    assert any("Part 4B" in blocker for blocker in governance["blocked_on"])

    # The lifecycle has no path from research straight to an approved Global record.
    lifecycle = governance["draft_lifecycle"]
    assert lifecycle.index("under_human_review") < lifecycle.index("approved")
    assert any("duplicate check is rerun" in precondition for precondition in governance["approval_preconditions"])
    assert any("AI Draft only" in precondition for precondition in governance["approval_preconditions"])

    refused = client.post(
        "/internal/ai/tasks",
        headers=_CREDENTIAL,
        json={"context": _context(), "skill_ref": "research", "subject_ref": "gs-1"},
    )
    assert refused.status_code == 403


# --- OpenAPI gate for every Day 2 and Day 3 service -------------------------------------------------------

def test_domain_service_openapi_documents_meet_the_standing_rules() -> None:
    for service, module, paths in (
        ("startups", startups_main, ["/internal/startups/list", "/internal/startups/duplicate-check"]),
        ("investors", investors_main, ["/internal/investors/list", "/internal/investors/create"]),
        ("deals", deals_main, ["/internal/deals/list", "/internal/deals/create"]),
        ("contacts", contacts_main, ["/internal/contacts/capabilities"]),
        ("sharing", sharing_main, ["/internal/sharing/proposals"]),
        ("import_service", import_main, ["/internal/import/startup"]),
        ("lineage", lineage_main, ["/internal/lineage/for-record"]),
        ("ai_agents", ai_main, ["/internal/ai/governance"]),
    ):
        assert_document(
            module.app.openapi(),
            service=service,
            expected_paths=["/health", "/readiness"] + paths,
            required_security_schemes=["InternalServiceBearer"],
        )
