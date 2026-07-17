"""IC-009-R1 portal DTO catalogue + seam-owned contract traceability — B5-BLK-6B.

The gateway-composed, contract-approved DTO set the IC-010 §V Response Composition
Contract permits: every shape here is defined by the adopted IC-009 (revision IC-009-R1)
and composed by the gateway itself from typed port results — never relayed from a
downstream body (§V.2). References only (IC-010 §G): no name/email/PII payload, no
secret/credential/DSN/token, no physical-DB identifier, no router decision.

Traceability is SOURCE-LEVEL and SEAM-OWNED (IC-010 §V.1: "the composing seam names the
interface contract and the revision it serves"): the constants + catalogue below name
IC-009-R1 for every approved DTO type, and the composer refuses any type absent from the
catalogue. No DTO carries a ``contract_id``/``contract_revision`` wire field — the
membership field set is contract-closed to exactly the IC-002 triple (IC-002:207/:235;
IC-009 §I), and provenance markers are exactly the three D-37 §10 names (IC-009 §D).

``ErrorDTO`` is DEFINED here but EXCLUDED from the ``PortalDTO`` union: a composed
response exists only for an allowed, dispatched request — on any denial the gateway
returns the §L denial and NO DTO (IC-010 §V.2), so denial-shape union membership would be
unreachable by construction. ``UserSessionDTO`` is not authored: no approved §Q category
returns it, and serving it would require a fifth route (IC-007/IC-010 §Q closure).
"""

from __future__ import annotations

import dataclasses
import json
from typing import Mapping, Tuple, Type, Union

# IC-010 §V.1 contract-and-revision traceability — the seam names the contract it serves.
PORTAL_CONTRACT_ID = "IC-009"
PORTAL_CONTRACT_REVISION = "IC-009-R1"


@dataclasses.dataclass(frozen=True)
class DirectoryEntryDTO:
    """One tenant-anonymous discovery entry (IC-001 Directory Data; D-35 anonymity).

    ``record_ref`` is the stable global directory record id (the future IC-003 import
    ``source_ref``); ``display_name`` is the record's non-sensitive global reference
    display value, already served by the sanctioned control-plane read edge. Never a
    tenant attribution, lineage reference, or physical-DB identifier.
    """

    record_ref: str
    display_name: str


@dataclasses.dataclass(frozen=True)
class GlobalStartupSummaryDTO:
    """The Global Startup Directory read summary (IC-009 §D) — tenant-anonymous (D-35
    prevails). Carries the D-37 §10 provenance markers with their exact global values and
    NO ``lineage_reference`` (global records carry none); ``records`` preserves the
    Control-Plane read edge's deterministic order (the gateway never re-sorts, §B)."""

    records: Tuple[DirectoryEntryDTO, ...]
    record_origin: str = "global"
    record_residency: str = "global"
    record_type: str = "GlobalStartupDirectory"


@dataclasses.dataclass(frozen=True)
class GlobalInvestorSummaryDTO:
    """The Global Investor Directory read summary — same rules as the startup summary."""

    records: Tuple[DirectoryEntryDTO, ...]
    record_origin: str = "global"
    record_residency: str = "global"
    record_type: str = "GlobalInvestorDirectory"


@dataclasses.dataclass(frozen=True)
class MembershipEntryDTO:
    """Exactly the IC-002 Principal Membership Record triple (IC-002:235, D-33; IC-009
    §I: the switcher may receive ONLY these membership fields). ``display_ref`` is
    gateway-composed (``compose_display_ref``), never stored, never a name/PII."""

    tenant_id: str
    role: str
    display_ref: str


@dataclasses.dataclass(frozen=True)
class WorkspaceMembershipDTO:
    """The workspace-switcher feed (IC-009 §D: a list of ``{tenant_id, role, display_ref}``
    membership records — a membership DTO, NOT a directory record, so it lawfully carries
    ``tenant_id`` per IR-08). An empty ``memberships`` tuple is a lawful success — a
    principal with zero memberships is not an error."""

    memberships: Tuple[MembershipEntryDTO, ...]


@dataclasses.dataclass(frozen=True)
class ImportInitiationDTO:
    """The accepted-initiation envelope ONLY (IC-009 §D; V2 §3.2): a global source
    reference + the single active-tenant target, references only. States nothing beyond
    acceptance — never completion, never a job/lineage/idempotency identifier (no such
    thing was created; ``ImportService.start_import`` is never called)."""

    source_ref: str
    target_tenant_ref: str
    initiation: str = "accepted"


@dataclasses.dataclass(frozen=True)
class ErrorDTO:
    """The §L safe denial surface (IC-009 §D) — status + public code and NOTHING else: no
    DB name, tenant existence, router detail, secret, or stack trace. Deliberately
    EXCLUDED from ``PortalDTO``: on any denial the gateway returns the §L denial and no
    DTO (IC-010 §V.2), so this shape is never composed into a response."""

    status: int
    public_code: str


# The approved portal DTO union (IC-009-R1 foundation tier bound in B5-BLK-6B). Exactly
# these four members; ErrorDTO is excluded by construction (see its docstring).
PortalDTO = Union[
    GlobalStartupSummaryDTO,
    GlobalInvestorSummaryDTO,
    WorkspaceMembershipDTO,
    ImportInitiationDTO,
]

# The explicit approved-DTO catalogue (IC-010 §V.1 traceability): each composable type is
# mapped to the interface contract and revision the seam serves. The composer MUST refuse
# any type absent from this catalogue.
APPROVED_PORTAL_DTOS: Mapping[Type[object], Tuple[str, str]] = {
    GlobalStartupSummaryDTO: (PORTAL_CONTRACT_ID, PORTAL_CONTRACT_REVISION),
    GlobalInvestorSummaryDTO: (PORTAL_CONTRACT_ID, PORTAL_CONTRACT_REVISION),
    WorkspaceMembershipDTO: (PORTAL_CONTRACT_ID, PORTAL_CONTRACT_REVISION),
    ImportInitiationDTO: (PORTAL_CONTRACT_ID, PORTAL_CONTRACT_REVISION),
}


def compose_display_ref(tenant_id: str) -> str:
    """The gateway-composed, deterministic, references-only membership display reference
    (register-recorded derivation; IC-002 D-33: display naming resolved by reference).
    Derived, never stored — the control plane returns no display value (no DDL)."""
    return "ref:tenant/" + tenant_id + "/display"


def compose_portal_dto(dto: PortalDTO) -> PortalDTO:
    """The catalogue-closing composer: emits ONLY types the approved catalogue names
    (IC-010 §V.1 adopted-contract DTOs only). Any other type is refused — the gateway
    collapses the refusal fail-closed (§L; never a partial or unapproved response)."""
    if type(dto) not in APPROVED_PORTAL_DTOS:
        raise ValueError("unapproved portal DTO type: " + type(dto).__name__)
    return dto


def serialize_portal_dto(dto: PortalDTO) -> bytes:
    """Deterministic serialization (IC-010 §V.1): dataclass field order, compact
    separators — the same instance always serializes to the same bytes, with no
    environment-, clock-, or iteration-order-dependent variation."""
    if type(dto) not in APPROVED_PORTAL_DTOS:
        raise ValueError("unapproved portal DTO type: " + type(dto).__name__)
    return json.dumps(dataclasses.asdict(dto), separators=(",", ":")).encode("utf-8")
