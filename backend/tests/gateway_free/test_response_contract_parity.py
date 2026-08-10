"""Byte-for-byte parity between the Gateway-composed and owner-composed public responses.

The previous removal experiment's §8 finding was that the public response contract *changed
silently*: the Gateway's eight-field ``TenantStartupDetailDTO`` collapsed to the five-field
internal envelope, losing ``record_origin`` / ``record_residency`` / ``record_type``. A client
would have seen a different shape with no error anywhere.

That regression is the reason the owning services COMPOSE their own DTO rather than relaying
the internal envelope, and this file is the check that keeps them honest. It imports the
Gateway's own DTO definitions purely as the reference oracle — a test-only import, which is
exactly why GF-1 proves the *composition* loads no ``api_gateway`` module independently.

If these ever diverge, the frontend cutover silently breaks; this test is what says so.
"""

from __future__ import annotations

import pathlib
import sys

# APPEND, never insert(0): backend/tests contains packages named after the services
# (tests/database_router/, tests/control_plane/, tests/shared/). Putting it first makes those
# EMPTY stubs win over the production packages, which silently blinds any sys.modules census.
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from gateway_free._fakes import (  # noqa: E402
    ACME,
    ACME_BEARER,
    ACME_PRINCIPAL,
    ACME_REF,
    HostedEdge,
    TwoTenantProvider,
    bearer,
    build_boundary,
)

import api_gateway.portal as gateway_portal  # noqa: E402  (test-only reference oracle)
import control_plane.portal as cp_portal  # noqa: E402
import database_router.portal as dbr_portal  # noqa: E402
from control_plane.adapters.providers.http_public_workspace_edge import build_public_workspace_edge_server  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.main import ControlPlane  # noqa: E402
from control_plane.records import Role  # noqa: E402
from database_router.adapters.providers.http_public_startup_edge import build_public_startup_edge_server  # noqa: E402
from database_router.tenant_startup_ops import TenantStartupOperations  # noqa: E402


def test_the_tenant_startup_dto_is_field_identical_to_the_gateway_composed_one() -> None:
    gateway_fields = [(f.name, f.default) for f in gateway_portal.TenantStartupDetailDTO.__dataclass_fields__.values()]
    owner_fields = [(f.name, f.default) for f in dbr_portal.TenantStartupDetailDTO.__dataclass_fields__.values()]
    assert owner_fields == gateway_fields, (
        f"field names, ORDER and defaults must match exactly\ngateway={gateway_fields}\nowner={owner_fields}"
    )


def test_the_tenant_startup_dto_serializes_to_identical_bytes() -> None:
    values = dict(record_ref=ACME_REF, display_name="ACME", short_description="d", investment_stage="seed", lineage_reference="lin-1")
    gateway_bytes = gateway_portal.serialize_portal_dto(gateway_portal.TenantStartupDetailDTO(**values))
    owner_bytes = dbr_portal.serialize_portal_dto(dbr_portal.TenantStartupDetailDTO(**values))
    assert owner_bytes == gateway_bytes, f"the wire must be byte-identical\ngateway={gateway_bytes!r}\nowner={owner_bytes!r}"


def test_the_membership_dto_is_field_identical_and_serializes_identically() -> None:
    gateway_entry = [(f.name, f.default) for f in gateway_portal.MembershipEntryDTO.__dataclass_fields__.values()]
    owner_entry = [(f.name, f.default) for f in cp_portal.MembershipEntryDTO.__dataclass_fields__.values()]
    assert owner_entry == gateway_entry, "membership entry field names, order and defaults must match exactly"
    assert cp_portal.compose_display_ref(ACME) == gateway_portal.compose_display_ref(ACME), "the derived display_ref must match"

    entries = ((ACME, "TENANT_AGENT"),)
    gateway_bytes = gateway_portal.serialize_portal_dto(
        gateway_portal.WorkspaceMembershipDTO(
            memberships=tuple(
                gateway_portal.MembershipEntryDTO(tenant_id=t, role=r, display_ref=gateway_portal.compose_display_ref(t))
                for t, r in entries
            )
        )
    )
    owner_bytes = cp_portal.serialize_portal_dto(
        cp_portal.WorkspaceMembershipDTO(
            memberships=tuple(
                cp_portal.MembershipEntryDTO(tenant_id=t, role=r, display_ref=cp_portal.compose_display_ref(t)) for t, r in entries
            )
        )
    )
    assert owner_bytes == gateway_bytes, "the membership wire must be byte-identical"


def test_the_served_startup_response_is_the_eight_field_contract_not_the_internal_envelope() -> None:
    """The regression check with teeth: what the SERVED edge actually puts on the wire.

    The internal envelope's five keys are ``{record_ref, display_name, short_description,
    investment_stage, lineage_reference}``. The contract adds the three D-37 §10 provenance
    markers. A relay would produce the former; composition produces the latter.
    """
    provider = TwoTenantProvider()
    boundary, _auth, _audit = build_boundary()
    server, base_url = build_public_startup_edge_server(TenantStartupOperations(provider), boundary, host="127.0.0.1", port=0)
    with HostedEdge(server, base_url) as edge:
        status, body, headers = edge.request("GET", "/tenant/startups/" + ACME_REF, headers=bearer(ACME_BEARER))
    assert status == 200
    assert headers["content-type"].startswith("application/json")
    import json

    served = json.loads(body.decode("utf-8"))
    assert set(served) == {f.name for f in dbr_portal.TenantStartupDetailDTO.__dataclass_fields__.values()}
    assert {"record_origin", "record_residency", "record_type"} <= set(served), (
        "the provenance triple must survive — losing it is exactly the silent divergence the previous experiment found"
    )
    assert (served["record_origin"], served["record_residency"], served["record_type"]) == ("tenant", "tenant", "startup")
    assert list(served) == [f.name for f in dbr_portal.TenantStartupDetailDTO.__dataclass_fields__.values()], (
        "field ORDER is part of the contract"
    )


def test_the_served_membership_response_matches_the_contract_shape() -> None:
    control_plane = ControlPlane(store=InMemoryControlStore())
    control_plane.membership.add_membership(principal_ref=ACME_PRINCIPAL, tenant_id=ACME, role=Role.TENANT_AGENT)
    boundary, _auth, _audit = build_boundary()
    server, base_url = build_public_workspace_edge_server(control_plane, boundary, host="127.0.0.1", port=0)
    with HostedEdge(server, base_url) as edge:
        status, body, _headers = edge.request("GET", "/memberships", headers=bearer(ACME_BEARER))
    assert status == 200
    expected = cp_portal.serialize_portal_dto(
        cp_portal.WorkspaceMembershipDTO(
            memberships=(
                cp_portal.MembershipEntryDTO(tenant_id=ACME, role="TENANT_AGENT", display_ref=cp_portal.compose_display_ref(ACME)),
            )
        )
    )
    assert body == expected, "the served membership bytes must equal the contract composition exactly"
