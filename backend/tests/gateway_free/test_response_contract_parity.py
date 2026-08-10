"""Byte-for-byte parity between the FROZEN public response contract and what the owners compose.

The previous removal experiment's §8 finding was that the public response contract *changed
silently*: the eight-field ``TenantStartupDetailDTO`` collapsed to the five-field internal
envelope, losing ``record_origin`` / ``record_residency`` / ``record_type``. A client would have
seen a different shape with no error anywhere.

That regression is the reason the owning services COMPOSE their own DTO rather than relaying the
internal envelope, and this file is the check that keeps them honest.

**How the oracle changed when the Gateway was deleted.** This file used to import
``api_gateway.portal`` as the reference oracle. That module no longer exists, so the oracle is
now the contract ITSELF, transcribed here as frozen literals: the exact field names, ORDER and
defaults, the exact ``display_ref`` derivation, and the exact serialized bytes. The literals were
taken verbatim from ``api_gateway/portal.py`` at commit ``8719f4f3`` (the last commit before the
deletion) — recoverable with ``git show 8719f4f3:backend/api_gateway/portal.py`` — and the values
they pin were, at that commit, asserted equal to the owner-composed ones by the predecessor of
this file. A literal oracle is strictly stronger than the import was: an import tracks whatever
the Gateway's own DTO happened to say, whereas a literal cannot move without a reviewed edit to
this file.

If these ever diverge, the frontend cutover silently breaks; this test is what says so.
"""

from __future__ import annotations

import dataclasses
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

import control_plane.portal as cp_portal  # noqa: E402
import database_router.portal as dbr_portal  # noqa: E402
from control_plane.adapters.providers.control_membership_reader import ControlStoreMembershipReader  # noqa: E402
from control_plane.adapters.providers.control_store_factory import SharedControlStoreFactory  # noqa: E402
from control_plane.adapters.providers.http_public_workspace_edge import build_public_workspace_edge_server  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.membership import MembershipRegistry  # noqa: E402
from control_plane.records import Role  # noqa: E402
from database_router.adapters.providers.http_public_startup_edge import build_public_startup_edge_server  # noqa: E402
from database_router.tenant_startup_ops import TenantStartupOperations  # noqa: E402

_MISSING = dataclasses.MISSING

# --- the FROZEN contract oracle ------------------------------------------------------------
# Transcribed verbatim from api_gateway/portal.py at 8719f4f3 (the commit before the Gateway was
# deleted). `_MISSING` marks a field with no default — position in this list IS the field order,
# which IC-010 §V.1 makes part of the wire contract.
_CONTRACT_TENANT_STARTUP_FIELDS = [
    ("record_ref", _MISSING),
    ("display_name", _MISSING),
    ("short_description", _MISSING),
    ("investment_stage", _MISSING),
    ("record_origin", "tenant"),
    ("record_residency", "tenant"),
    ("record_type", "startup"),
    ("lineage_reference", None),
]
_CONTRACT_MEMBERSHIP_ENTRY_FIELDS = [("tenant_id", _MISSING), ("role", _MISSING), ("display_ref", _MISSING)]
_CONTRACT_WORKSPACE_FIELDS = [("memberships", _MISSING)]
_CONTRACT_DISPLAY_REF = "ref:tenant/" + ACME + "/display"
_CONTRACT_STARTUP_BYTES = (
    b'{"record_ref":"'
    + ACME_REF.encode()
    + b'","display_name":"ACME","short_description":"d","investment_stage":"seed",'
    + b'"record_origin":"tenant","record_residency":"tenant","record_type":"startup","lineage_reference":"lin-1"}'
)
_CONTRACT_MEMBERSHIP_BYTES = (
    b'{"memberships":[{"tenant_id":"'
    + ACME.encode()
    + b'","role":"TENANT_AGENT","display_ref":"'
    + _CONTRACT_DISPLAY_REF.encode()
    + b'"}]}'
)


def _fields(dto_cls):
    return [(f.name, f.default) for f in dto_cls.__dataclass_fields__.values()]


def test_the_tenant_startup_dto_is_field_identical_to_the_frozen_contract() -> None:
    owner_fields = _fields(dbr_portal.TenantStartupDetailDTO)
    assert owner_fields == _CONTRACT_TENANT_STARTUP_FIELDS, (
        f"field names, ORDER and defaults must match the frozen contract exactly\n"
        f"contract={_CONTRACT_TENANT_STARTUP_FIELDS}\nowner={owner_fields}"
    )


def test_the_tenant_startup_dto_serializes_to_the_frozen_contract_bytes() -> None:
    values = dict(record_ref=ACME_REF, display_name="ACME", short_description="d", investment_stage="seed", lineage_reference="lin-1")
    owner_bytes = dbr_portal.serialize_portal_dto(dbr_portal.TenantStartupDetailDTO(**values))
    assert owner_bytes == _CONTRACT_STARTUP_BYTES, (
        f"the wire must be byte-identical to the frozen contract\ncontract={_CONTRACT_STARTUP_BYTES!r}\nowner={owner_bytes!r}"
    )


def test_the_membership_dto_is_field_identical_and_serializes_identically() -> None:
    assert _fields(cp_portal.MembershipEntryDTO) == _CONTRACT_MEMBERSHIP_ENTRY_FIELDS, (
        "membership entry field names, order and defaults must match the frozen contract exactly"
    )
    assert _fields(cp_portal.WorkspaceMembershipDTO) == _CONTRACT_WORKSPACE_FIELDS, "the workspace envelope shape is one field"
    assert cp_portal.compose_display_ref(ACME) == _CONTRACT_DISPLAY_REF, "the derived display_ref must match the frozen derivation"

    owner_bytes = cp_portal.serialize_portal_dto(
        cp_portal.WorkspaceMembershipDTO(
            memberships=(
                cp_portal.MembershipEntryDTO(tenant_id=ACME, role="TENANT_AGENT", display_ref=cp_portal.compose_display_ref(ACME)),
            )
        )
    )
    assert owner_bytes == _CONTRACT_MEMBERSHIP_BYTES, "the membership wire must be byte-identical to the frozen contract"


def test_the_frozen_oracle_is_non_vacuous() -> None:
    """A literal oracle is only worth having if it would REJECT a drifted DTO.

    Three planted drifts, each a real regression shape: a dropped provenance field (the §8
    finding), a reordered field list (IC-010 §V.1 makes order contractual), and a changed
    default. Each must differ from the frozen list under the same comparison the live
    assertions use — and the two contracts must be distinguishable from one another.
    """
    dropped = [f for f in _CONTRACT_TENANT_STARTUP_FIELDS if f[0] != "record_origin"]
    reordered = [_CONTRACT_TENANT_STARTUP_FIELDS[1], _CONTRACT_TENANT_STARTUP_FIELDS[0], *_CONTRACT_TENANT_STARTUP_FIELDS[2:]]
    redefaulted = [(n, "global" if n == "record_residency" else d) for n, d in _CONTRACT_TENANT_STARTUP_FIELDS]
    for drifted in (dropped, reordered, redefaulted):
        assert drifted != _CONTRACT_TENANT_STARTUP_FIELDS, "the field comparison must reject a drifted shape"
    assert _CONTRACT_STARTUP_BYTES.replace(b'"record_type":"startup",', b"") != _CONTRACT_STARTUP_BYTES
    assert _fields(dbr_portal.TenantStartupDetailDTO) != _CONTRACT_MEMBERSHIP_ENTRY_FIELDS, "the two contracts are distinguishable"


def test_the_served_startup_response_is_the_eight_field_contract_not_the_internal_envelope() -> None:
    """The regression check with teeth: what the SERVED edge actually puts on the wire.

    The (now deleted) internal envelope's five keys were ``{record_ref, display_name,
    short_description, investment_stage, lineage_reference}``. The contract adds the three
    D-37 §10 provenance markers. A relay would produce the former; composition produces the
    latter.
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
    store = InMemoryControlStore()
    MembershipRegistry(store).add_membership(principal_ref=ACME_PRINCIPAL, tenant_id=ACME, role=Role.TENANT_AGENT)
    boundary, _auth, _audit = build_boundary()
    reader = ControlStoreMembershipReader(SharedControlStoreFactory(store))
    server, base_url = build_public_workspace_edge_server(reader, boundary, host="127.0.0.1", port=0)
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
