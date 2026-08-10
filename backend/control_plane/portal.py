"""The workspace-membership public response contract (IC-009-R1 §I) — owner-resident.

Under the Gateway-free MVP the service that owns a route owns its public response shape. The
workspace-selector read is Control-DB data the Control Plane already holds, so its adopted
IC-009-R1 DTO, its derived display reference, and its deterministic serializer live here
rather than in a central composer.

**The wire is unchanged.** Field names, field order, the derived ``display_ref`` form, and the
compact ``json.dumps(..., separators=(",", ":"))`` serialization are byte-identical to the
shape the API Gateway composed, so a client cannot tell the two architectures apart.

The membership field set is contract-closed to exactly the IC-002 triple
(``tenant_id`` / ``role`` / ``display_ref``): the workspace switcher may receive only these.
No email, person name, tenant display name, physical-database identifier, connection material,
token, or tenant business content may ever join this shape. An EMPTY membership tuple is a
lawful success — a principal with zero memberships is not an error.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Mapping, Tuple, Type

# IC-009 §V.1 contract-and-revision traceability — the composing owner names what it serves.
PORTAL_CONTRACT_ID = "IC-009"
PORTAL_CONTRACT_REVISION = "IC-009-R1"


@dataclasses.dataclass(frozen=True)
class MembershipEntryDTO:
    """Exactly the IC-002 Principal Membership Record triple (IC-002:235, D-33).

    ``display_ref`` is composed here (``compose_display_ref``), never stored and never a
    name or any other PII.
    """

    tenant_id: str
    role: str
    display_ref: str


@dataclasses.dataclass(frozen=True)
class WorkspaceMembershipDTO:
    """The workspace-switcher feed: a list of ``{tenant_id, role, display_ref}`` records.

    A membership DTO, not a directory record, so it lawfully carries ``tenant_id`` (IR-08).
    """

    memberships: Tuple[MembershipEntryDTO, ...]


APPROVED_PORTAL_DTOS: Mapping[Type[object], Tuple[str, str]] = {
    WorkspaceMembershipDTO: (PORTAL_CONTRACT_ID, PORTAL_CONTRACT_REVISION),
}


def compose_display_ref(tenant_id: str) -> str:
    """The deterministic, references-only membership display reference (IC-002 D-33).

    Derived, never stored — the Control Plane holds no display value and no schema for one.
    """
    return "ref:tenant/" + tenant_id + "/display"


def serialize_portal_dto(dto: WorkspaceMembershipDTO) -> bytes:
    """Deterministic serialization: dataclass field order, compact separators.

    A type absent from the approved catalogue is refused, so a raw store row or an internal
    dictionary can never reach a client.
    """
    if type(dto) not in APPROVED_PORTAL_DTOS:
        raise ValueError("unapproved portal DTO type: " + type(dto).__name__)
    return json.dumps(dataclasses.asdict(dto), separators=(",", ":")).encode("utf-8")
