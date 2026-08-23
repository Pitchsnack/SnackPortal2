"""Stage 4B — the rebuilt Control Plane Service against the real Control database.

The service application is the real one (``snackportal2.services.control_plane.main.app``),
reached over ASGI, with its store replaced by the **real PostgreSQL adapter selected by the
real selector** — ``build_store`` reading a DSN out of a configuration mapping, exactly as it
would at boot. That distinction matters: a test that constructed ``PostgresControlStore``
directly would prove the adapter works while leaving open whether configuration ever selects
it.

The brief's controlling requirement is "no in-memory adapter is silently substituted"
(§4). Every test below asserts the store type as well as the response.
"""

from __future__ import annotations

import json
import socket
import time
from datetime import datetime, timedelta
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from snackportal2.services.control_plane import main as cp_main
from snackportal2.services.control_plane.models import DirectoryKind, SecretReference, TenantDescriptor
from snackportal2.services.control_plane.store import (
    ENV_CONTROL_DSN,
    InMemoryControlStore,
    PostgresControlStore,
    build_store,
    looks_like_a_connection_string,
)
from snackportal2.shared.types import PlatformRole, TenantLifecycleState

from . import _stage4_pg as pg

pytestmark = pytest.mark.skipif(not pg.configured(), reason=pg.SKIP_REASON)

SERVICE_HEADERS = {"Authorization": "Bearer internal-service-credential"}


def _live_store() -> PostgresControlStore:
    """The store the real selector produces from a configured DSN."""
    store = build_store(env={ENV_CONTROL_DSN: pg.dsn("control")})
    assert isinstance(store, PostgresControlStore), "a configured DSN must select the durable store, got " + type(store).__name__
    return store


def _closed_loopback_dsn() -> str:
    """A syntactically valid DSN pointing at a port nothing is listening on."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    return "postgresql://nobody:nothing@127.0.0.1:" + str(port) + "/absent"


def _seed_directory(directory: DirectoryKind, record_ref: str, display_name: str, attributes: dict) -> None:
    """Seed a global directory row by direct SQL.

    The rebuild's ``PostgresControlStore`` is deliberately read-only over ``control_directory``
    — it implements ``list_directory`` and ``get_directory_record`` and no writer — so the
    fixture writes the row the way operations would, and the service reads it back.
    """
    pg.execute(
        pg.dsn("control"),
        "INSERT INTO control_directory (directory, record_id, display_name, attributes) "
        "VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (directory, record_id) DO UPDATE "
        "SET display_name = EXCLUDED.display_name, attributes = EXCLUDED.attributes",
        (directory.value, record_ref, display_name, json.dumps(attributes)),
    )


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    pg.provision()
    store = _live_store()

    store.put_tenant(
        TenantDescriptor(
            tenant_ref="acme",
            organization_ref="org-acme",
            lifecycle_state=TenantLifecycleState.ACTIVE,
            expected_schema_version="1",
            database_association_ref=SecretReference(store_ref="assoc/acme", version="1"),
        )
    )
    store.put_tenant(
        TenantDescriptor(
            tenant_ref="zeta",
            organization_ref="org-zeta",
            lifecycle_state=TenantLifecycleState.ACTIVE,
            expected_schema_version="1",
            database_association_ref=SecretReference(store_ref="assoc/zeta", version="1"),
        )
    )
    store.put_tenant(
        TenantDescriptor(
            tenant_ref="nova",
            organization_ref="org-nova",
            lifecycle_state=TenantLifecycleState.ACTIVE,
            expected_schema_version="1",
            database_association_ref=SecretReference(store_ref="assoc/nova", version="1"),
        )
    )
    store.put_tenant(
        TenantDescriptor(
            tenant_ref="dormant",
            organization_ref="org-dormant",
            lifecycle_state=TenantLifecycleState.DISABLED,
            expected_schema_version="1",
            database_association_ref=SecretReference(store_ref="assoc/dormant", version="1"),
        )
    )
    store.put_membership("p-agent", "acme", PlatformRole.TENANT_AGENT)
    store.put_membership("p-zeta", "zeta", PlatformRole.TENANT_AGENT)
    store.put_membership("p-nova", "nova", PlatformRole.TENANT_AGENT)

    _seed_directory(DirectoryKind.GLOBAL_STARTUP, "gs-1", "Alpha Corp", {"industry": "robotics"})
    _seed_directory(DirectoryKind.GLOBAL_STARTUP, "gs-2", "Beta Systems", {"industry": "energy"})
    _seed_directory(DirectoryKind.GLOBAL_INVESTOR, "gi-1", "Northwind Capital", {"stage": "seed"})

    previous = cp_main._store
    cp_main._store = store
    try:
        yield TestClient(cp_main.app, raise_server_exceptions=False)
    finally:
        cp_main._store = previous


# --- the selector -----------------------------------------------------------------------


def test_an_unset_dsn_selects_the_in_memory_store_and_a_set_one_does_not() -> None:
    assert isinstance(build_store(env={}), InMemoryControlStore)
    assert isinstance(build_store(env={ENV_CONTROL_DSN: "   "}), InMemoryControlStore)
    assert isinstance(build_store(env={ENV_CONTROL_DSN: pg.dsn("control")}), PostgresControlStore)


def test_the_live_control_plane_is_not_serving_from_memory(client: TestClient) -> None:
    assert isinstance(cp_main._store, PostgresControlStore)
    assert not isinstance(cp_main._store, InMemoryControlStore)


# --- tenant registry read ---------------------------------------------------------------


def test_tenant_registry_read_round_trips_through_postgresql(client: TestClient) -> None:
    response = client.get("/internal/tenants/acme", headers=SERVICE_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "tenant_ref": "acme",
        "organization_ref": "org-acme",
        "lifecycle_state": "ACTIVE",
        "expected_schema_version": "1",
        "database_association_ref": {"store_ref": "assoc/acme", "version": "1"},
    }


def test_the_registry_row_is_physically_present_in_the_control_database(client: TestClient) -> None:
    stored = pg.rows(
        pg.dsn("control"),
        "SELECT organization_ref, lifecycle_state, expected_schema_version, assoc_store_ref, assoc_version "
        "FROM control_tenants WHERE tenant_id = %s",
        ("acme",),
    )
    assert stored == [("org-acme", "ACTIVE", "1", "assoc/acme", "1")]


def test_an_unknown_tenant_answers_with_the_consistent_denial(client: TestClient) -> None:
    response = client.get("/internal/tenants/no-such-tenant", headers=SERVICE_HEADERS)
    assert response.status_code == 404
    assert response.json() == {"status": 404, "code": "tenant_not_found"}


def test_tenant_status_read_reports_serviceability_from_the_stored_lifecycle(client: TestClient) -> None:
    active = client.get("/internal/tenants/acme/readiness", headers=SERVICE_HEADERS)
    assert active.status_code == 200
    assert active.json() == {"tenant_ref": "acme", "lifecycle_state": "ACTIVE", "serviceable": True}

    disabled = client.get("/internal/tenants/dormant/readiness", headers=SERVICE_HEADERS)
    assert disabled.status_code == 200
    assert disabled.json() == {"tenant_ref": "dormant", "lifecycle_state": "DISABLED", "serviceable": False}


def test_the_database_association_is_a_reference_and_never_a_connection_string(client: TestClient) -> None:
    """D-14, enforced at the write boundary and observable in the stored row."""
    body = client.get("/internal/tenants/acme", headers=SERVICE_HEADERS).json()
    association = body["database_association_ref"]
    assert not looks_like_a_connection_string(association["store_ref"])
    assert "://" not in json.dumps(body)
    assert "password" not in json.dumps(body).casefold()

    rejected = client.put(
        "/internal/tenants",
        headers=SERVICE_HEADERS,
        json={
            "tenant_ref": "smuggler",
            "organization_ref": "org-smuggler",
            "lifecycle_state": "ACTIVE",
            "expected_schema_version": "1",
            "database_association_ref": {"store_ref": "postgresql://user:pw@host/db", "version": "1"},
        },
    )
    assert rejected.status_code == 422
    assert pg.scalar(pg.dsn("control"), "SELECT count(*) FROM control_tenants WHERE tenant_id = 'smuggler'") == 0


# --- membership read --------------------------------------------------------------------


def test_the_registry_records_real_timestamps_and_preserves_the_creation_time(client: TestClient) -> None:
    """Stage 4 defect F-1: the columns were being written as empty strings.

    DDL 004 types ``created_at`` / ``updated_at`` as ``text`` so the value round-trips as a
    string. ``text NOT NULL`` accepts ``''``, so the empty write was schema-legal and could
    only ever be seen against a real database — the in-memory store has no such columns. A
    registry that records no creation time cannot be aged, ordered or reconciled, and rows the
    rebuild wrote would not resemble rows the accepted DDL's other writer produces.
    """
    store = _live_store()

    def stamps() -> tuple:
        return pg.rows(
            pg.dsn("control"), "SELECT created_at, updated_at FROM control_tenants WHERE tenant_id = %s", ("stamped",)
        )[0]

    descriptor = TenantDescriptor(
        tenant_ref="stamped",
        organization_ref="org-stamped",
        lifecycle_state=TenantLifecycleState.PROVISIONING,
        expected_schema_version="1",
        database_association_ref=SecretReference(store_ref="assoc/stamped", version="1"),
    )
    store.put_tenant(descriptor)
    created_at, updated_at = stamps()

    for value in (created_at, updated_at):
        assert value, "the registry wrote an empty timestamp"
        parsed = datetime.fromisoformat(value)
        assert parsed.tzinfo is not None, "the registry timestamp is not timezone-aware: " + repr(value)
        assert parsed.utcoffset() == timedelta(0), "the registry timestamp is not UTC: " + repr(value)

    store.put_tenant(descriptor.model_copy(update={"lifecycle_state": TenantLifecycleState.ACTIVE}))
    created_after, updated_after = stamps()
    assert created_after == created_at, "an update restamped the creation time"
    assert updated_after >= updated_at, "an update did not advance the update time"
    assert store.get_tenant("stamped").lifecycle_state is TenantLifecycleState.ACTIVE  # type: ignore[union-attr]


def test_the_control_store_bounds_how_long_it_will_wait_for_an_unreachable_database() -> None:
    """Stage 4 defect F-2, on the Control edge.

    Measured rather than asserted from source: an unbounded ``psycopg.connect`` takes about
    130 seconds to fail. A registry read that blocks for two minutes is not a fast failure,
    and every caller of this store is on a request path.
    """
    closed = _closed_loopback_dsn()
    store = PostgresControlStore(closed)
    started = time.monotonic()
    with pytest.raises(pg.database_error()):
        store.get_tenant("acme")
    elapsed = time.monotonic() - started
    assert elapsed < 30, "an unreachable Control database blocked for " + str(round(elapsed, 1)) + "s"


def test_membership_read_returns_the_rows_stored_in_postgresql(client: TestClient) -> None:
    response = client.get("/internal/memberships/p-agent", headers=SERVICE_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"principal_ref": "p-agent", "memberships": [{"tenant_ref": "acme", "role": "TENANT_AGENT"}]}


def test_a_principal_with_no_membership_is_a_lawful_empty_success(client: TestClient) -> None:
    response = client.get("/internal/memberships/p-stranger", headers=SERVICE_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"principal_ref": "p-stranger", "memberships": []}


def test_membership_write_is_an_upsert_not_a_duplicate(client: TestClient) -> None:
    store = _live_store()
    store.put_membership("p-upsert", "acme", PlatformRole.TENANT_AGENT)
    store.put_membership("p-upsert", "acme", PlatformRole.TENANT_ADMIN)
    assert pg.scalar(
        pg.dsn("control"), "SELECT count(*) FROM control_memberships WHERE principal_ref = 'p-upsert'"
    ) == 1
    assert store.list_memberships("p-upsert") == [
        type(store.list_memberships("p-upsert")[0])(tenant_ref="acme", role=PlatformRole.TENANT_ADMIN)
    ]


def test_membership_ordering_is_deterministic_across_two_reads(client: TestClient) -> None:
    store = _live_store()
    for tenant in ("zeta", "acme", "nova"):
        store.put_membership("p-many", tenant, PlatformRole.TENANT_AGENT)
    first = client.get("/internal/memberships/p-many", headers=SERVICE_HEADERS).json()["memberships"]
    second = client.get("/internal/memberships/p-many", headers=SERVICE_HEADERS).json()["memberships"]
    assert first == second
    assert [entry["tenant_ref"] for entry in first] == ["acme", "nova", "zeta"]


# --- global directory reads -------------------------------------------------------------


def test_global_directory_read_returns_jsonb_attributes_as_a_mapping(client: TestClient) -> None:
    response = client.get("/internal/directories/GlobalStartupDirectory/records", headers=SERVICE_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["directory"] == "GlobalStartupDirectory"
    assert [record["record_ref"] for record in body["records"]] == ["gs-1", "gs-2"]
    assert body["records"][0]["attributes"] == {"industry": "robotics"}


def test_the_two_global_directories_are_separate_reads(client: TestClient) -> None:
    startups = client.get("/internal/directories/GlobalStartupDirectory/records", headers=SERVICE_HEADERS).json()
    investors = client.get("/internal/directories/GlobalInvestorDirectory/records", headers=SERVICE_HEADERS).json()
    assert [r["record_ref"] for r in investors["records"]] == ["gi-1"]
    assert {r["record_ref"] for r in startups["records"]}.isdisjoint({r["record_ref"] for r in investors["records"]})


def test_one_global_directory_record_reads_back_by_reference(client: TestClient) -> None:
    response = client.get("/internal/directories/GlobalStartupDirectory/records/gs-2", headers=SERVICE_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"record_ref": "gs-2", "display_name": "Beta Systems", "attributes": {"industry": "energy"}}


def test_a_missing_directory_record_answers_with_the_consistent_denial(client: TestClient) -> None:
    response = client.get("/internal/directories/GlobalStartupDirectory/records/gs-absent", headers=SERVICE_HEADERS)
    assert response.status_code == 404
    assert response.json() == {"status": 404, "code": "tenant_not_found"}


def test_directory_records_are_tenant_anonymous_in_the_database(client: TestClient) -> None:
    """D-35: a global record has no tenant to disclose, and the column set proves it."""
    columns = pg.column_names(pg.dsn("control"), "control_directory")
    assert "tenant_id" not in columns and "tenant_ref" not in columns, repr(columns)


# --- no credential leakage --------------------------------------------------------------


def test_no_control_plane_response_discloses_a_connection_string(client: TestClient) -> None:
    paths = (
        "/internal/tenants/acme",
        "/internal/tenants/acme/readiness",
        "/internal/memberships/p-agent",
        "/internal/directories/GlobalStartupDirectory/records",
        "/internal/directories/GlobalStartupDirectory/records/gs-1",
        "/health",
        "/readiness",
    )
    for path in paths:
        text = client.get(path, headers=SERVICE_HEADERS).text.casefold()
        for marker in ("://", "password=", "dbname=", "host=", "5432"):
            assert marker not in text, path + " discloses " + marker


def test_every_internal_control_plane_surface_requires_a_credential(client: TestClient) -> None:
    for path in ("/internal/tenants/acme", "/internal/memberships/p-agent"):
        assert client.get(path).status_code == 401
