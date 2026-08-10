"""The tenant Startup public response contract (IC-009-R1 CLM section) — owner-resident.

Under the Gateway-free MVP the service that owns a route owns its public response shape.
The tenant Startup route family belongs to the Database Router, so its adopted IC-009-R1
DTO, its bounded request parser, and its deterministic serializer live here rather than in
a central composer.

**The wire is unchanged.** Field names, field order, defaults, and the compact
``json.dumps(..., separators=(",", ":"))`` serialization are byte-identical to the shape the
API Gateway composed, so a client cannot tell the two architectures apart from the response.
That is deliberate: the previous removal experiment found the public response contract
*silently diverged* (the eight-field DTO collapsed to the five-field internal envelope, losing
``record_origin`` / ``record_residency`` / ``record_type``). Keeping the composition — rather
than relaying the internal envelope — is what prevents that regression, and it is pinned by a
test.

Composition, not pass-through: the DTO is constructed here from values this service validated
and read, never relayed from another component's body. References only — no name, email, PII,
media field, URL, tenant display name, physical-database identifier, connection material, or
token may ever join this shape.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Mapping, Optional, Tuple, Type

# IC-009 §V.1 contract-and-revision traceability — the composing owner names what it serves.
PORTAL_CONTRACT_ID = "IC-009"
PORTAL_CONTRACT_REVISION = "IC-009-R1"

# The sole CLM-mutable field bound (IC-009/IC-010 CLM: at most 500 characters).
TENANT_STARTUP_SHORT_DESCRIPTION_MAX_CHARS = 500


@dataclasses.dataclass(frozen=True)
class TenantStartupDetailDTO:
    """The CLM tenant Startup read/update response — exactly the eight contract-pinned fields.

    ``record_ref`` is the tenant-resident Startup record reference the route addressed (the
    opaque ``<startup_ref>`` path suffix; never a raw row primary key, never a tenant or
    database selector). ``short_description`` is the sole CLM-mutable field (bounded free
    text, at most 500 characters, nullable); ``investment_stage`` is a bounded label
    (nullable). The provenance triple follows D-37 §10 with the tenant-resident values.
    ``lineage_reference`` is present ONLY when the record was imported (IC-004).
    """

    record_ref: str
    display_name: str
    short_description: Optional[str]
    investment_stage: Optional[str]
    record_origin: str = "tenant"
    record_residency: str = "tenant"
    record_type: str = "startup"
    lineage_reference: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class TenantStartupUpdateRequestDTO:
    """The bounded CLM update request — exactly one field.

    A REQUEST shape: it is parsed and validated, never composed or serialized as a response,
    so it is deliberately absent from the approved response catalogue below.
    """

    short_description: Optional[str]


# The approved response catalogue for this route family. The serializer refuses any type
# absent from it, so an internal envelope or a raw dictionary can never reach a client.
APPROVED_PORTAL_DTOS: Mapping[Type[object], Tuple[str, str]] = {
    TenantStartupDetailDTO: (PORTAL_CONTRACT_ID, PORTAL_CONTRACT_REVISION),
}


def parse_tenant_startup_update_request(raw: bytes) -> TenantStartupUpdateRequestDTO:
    """Strictly parse the bounded CLM update body — fail closed, before any write.

    Accepts EXACTLY one JSON object carrying EXACTLY the one allowlisted field
    ``short_description`` whose value is a string of at most 500 characters or null.
    Anything else — undecodable bytes, non-object JSON, an unknown or extra field, a missing
    field, a non-string non-null value, an over-bound value — raises ``ValueError``, and the
    caller rejects fail-closed with NO partial write. The 16384-byte transport bound is
    enforced by the edge's transport gate before this is reached.
    """
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        raise ValueError("malformed tenant startup update body") from None
    if not isinstance(body, dict) or set(body.keys()) != {"short_description"}:
        raise ValueError("tenant startup update must carry exactly the one allowlisted field")
    value = body["short_description"]
    if value is None:
        return TenantStartupUpdateRequestDTO(short_description=None)
    if not isinstance(value, str):
        raise ValueError("short_description must be a UTF-8 string or null")
    if len(value) > TENANT_STARTUP_SHORT_DESCRIPTION_MAX_CHARS:
        raise ValueError("short_description exceeds the 500-character bound")
    return TenantStartupUpdateRequestDTO(short_description=value)


def serialize_portal_dto(dto: TenantStartupDetailDTO) -> bytes:
    """Deterministic serialization: dataclass field order, compact separators.

    The same instance always serializes to the same bytes, with no environment-, clock-, or
    iteration-order-dependent variation. A type absent from the approved catalogue is refused.
    """
    if type(dto) not in APPROVED_PORTAL_DTOS:
        raise ValueError("unapproved portal DTO type: " + type(dto).__name__)
    return json.dumps(dataclasses.asdict(dto), separators=(",", ":")).encode("utf-8")
