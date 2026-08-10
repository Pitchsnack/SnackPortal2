"""Public-edge shapes stay REFERENCES ONLY — static/AST census (default suite; pure stdlib).

**Provenance.** The migrated successor of the references-only half of
`test_phase7_api_gateway.py`, which policed `api_gateway/models.py` (`RouteOutcome`,
`GatewayResponse`, `GatewayAuditEvent`) and `api_gateway/portal.py` (the IC-009-R1 DTOs). Those
modules were deleted with the Gateway; the *rule* they enforced — D-14 / IC-001 Global Audit
Representation Rule / IC-010 §G: no payload, credential, DSN, connection, database identity or
PII may ever appear in a shape that crosses a public boundary — is not the Gateway's rule and did
not go with it.

The census now covers the three shapes the Gateway-free MVP actually puts on or near the wire:

| Deleted shape | Successor censused here |
|---|---|
| `GatewayAuditEvent` (`api_gateway/models.py`) | `shared.public_edge.EdgeAuditEvent` |
| `RouteOutcome` / `GatewayResponse` | `shared.public_edge.TrustedPrincipal` + `PublicRequest` — the kernel's only per-request state |
| `api_gateway.portal` IC-009-R1 DTOs | `control_plane.portal` + `database_router.portal` (owner-resident) |

Deliberately NOT censused, because the shapes no longer exist anywhere: `DirectoryEntryDTO`,
`GlobalStartupSummaryDTO`, `GlobalInvestorSummaryDTO`, `ImportInitiationDTO`, `ImportResultDTO`.
Their routes are `REMOVE FROM MVP` / `DEFER` (no served Gateway route ever exposed `/directory`;
Import is outside the controlled local MVP journey). `test_the_removed_shapes_are_really_absent`
records that absence so "dropped on purpose" stays distinguishable from "lost in the deletion".

Every census returns the sentinel ``["<class> not found"]`` for an absent class, so an empty
match set can never read as a pass.

Standalone-runnable:  python tests/architecture/test_public_edge_references_only.py
"""

from __future__ import annotations

import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_KERNEL = _scan.BACKEND_ROOT / "shared" / "public_edge.py"
_CP_PORTAL = _scan.BACKEND_ROOT / "control_plane" / "portal.py"
_DBR_PORTAL = _scan.BACKEND_ROOT / "database_router" / "portal.py"

# The forbidden NAME set is global and is NEVER widened by any allow-set below. It is carried
# across verbatim from the Gateway-era census.
_FORBIDDEN_FIELD_NAMES = {
    "body",
    "payload",
    "data",
    "content",
    "dsn",
    "secret",
    "credential",
    "connection",
    "tenant_db",
    "route_ref",
}

# The audit event never may carry rows, the returned membership collection, or DB identity — a
# field that could smuggle any of them fails the build structurally. Additional to the global set.
_AUDIT_EVENT_FORBIDDEN_FIELD_NAMES = {"rows", "records", "memberships", "database", "db_name"}

# Scalars only. `EdgeAuditEvent` is the emitter-neutral successor of `GatewayAuditEvent` and its
# field set is the SAME eleven references (no class added, removed, renamed or re-homed).
_AUDIT_EVENT_ALLOWED_FIELD_TYPES = {"int", "str", "Optional"}
_AUDIT_EVENT_EXPECTED_FIELDS = {
    "action",
    "correlation_id",
    "outcome",
    "actor_ref",
    "tenant_ref",
    "carrier_ref",
    "audit_id",
    "subject_ref",
    "occurred_at",
    "event_version",
    "record_ref",  # D-42 CLM: the tenant-resident record reference (a reference only)
}

# The kernel's per-request state. `TrustedPrincipal` is the ONLY tenant authority in the system,
# so it must hold references and nothing else. `PublicRequest` is the kernel's view of the wire:
# `Sequence`/`Tuple` are admitted because the raw ASGI header pair-list is load-bearing (a
# mapping collapses duplicate headers and would make the straddle check unreachable).
_PRINCIPAL_ALLOWED_FIELD_TYPES = {"str", "Optional"}
_PRINCIPAL_EXPECTED_FIELDS = {"correlation_id", "principal_ref", "active_tenant_id", "role"}
_REQUEST_ALLOWED_FIELD_TYPES = {"str", "Optional", "Sequence", "Tuple"}
_REQUEST_EXPECTED_FIELDS = {"method", "path", "host", "headers", "authorization"}
# The kernel's request view must never GAIN one of these: they are the prohibited carriers, and
# not handing them over is what guarantees the kernel cannot read them.
_REQUEST_FORBIDDEN_FIELD_NAMES = {"body", "query", "query_string", "cookies", "form"}

# Owner-resident portal shapes: primitives + the one portal-local entry tuple.
_PORTAL_ALLOWED_FIELD_TYPES = {"int", "str", "bool", "Optional", "Tuple", "MembershipEntryDTO"}
_CP_PORTAL_SHAPES = ["MembershipEntryDTO", "WorkspaceMembershipDTO"]
_DBR_PORTAL_SHAPES = ["TenantStartupDetailDTO", "TenantStartupUpdateRequestDTO"]

# Shapes that existed only inside the deleted Gateway portal. Their routes are REMOVE/DEFER.
_REMOVED_SHAPES = (
    "DirectoryEntryDTO",
    "GlobalStartupSummaryDTO",
    "GlobalInvestorSummaryDTO",
    "ImportInitiationDTO",
    "ImportResultDTO",
    "GatewayResponse",
    "RouteOutcome",
    "GatewayAuditEvent",
)


def _find_classdef(source: str, name: str) -> "ast.ClassDef | None":
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _annotation_type_names(annotation: ast.expr) -> set:
    names: set = set()
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _references_only_violations(source: str, class_name: str, allowed_types: set) -> list:
    """Field-name + field-type violations for a references-only dataclass against the given TYPE
    allow-set (the forbidden NAME set is global and never widened). Returns the sentinel
    ``["<class> not found"]`` when the class is absent so an empty match set can NEVER read as a
    pass (the repo's 07E-1 census convention)."""
    node = _find_classdef(source, class_name)
    if node is None:
        return [f"{class_name} not found"]
    fields = [s for s in node.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)]
    if not fields:
        return [f"{class_name} declares no annotated fields"]
    violations: list = []
    for s in fields:
        fname = s.target.id  # type: ignore[union-attr]  # narrowed above
        if fname.lower() in _FORBIDDEN_FIELD_NAMES:
            violations.append(f"{class_name}.{fname}: forbidden field name")
        for tname in _annotation_type_names(s.annotation):
            if tname not in allowed_types:
                violations.append(f"{class_name}.{fname}: type '{tname}' outside references-only allow-set")
    return violations


def _field_names(source: str, class_name: str) -> set:
    node = _find_classdef(source, class_name)
    assert node is not None, f"{class_name} must be defined"
    return {s.target.id for s in node.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)}


# --- the audit event ---------------------------------------------------------------------------
def test_edge_audit_event_is_references_only_with_exact_field_set() -> None:
    source = _KERNEL.read_text(encoding="utf-8")
    violations = _references_only_violations(source, "EdgeAuditEvent", _AUDIT_EVENT_ALLOWED_FIELD_TYPES)
    assert violations == [], f"EdgeAuditEvent references-only violations: {violations}"
    names = _field_names(source, "EdgeAuditEvent")
    assert names == _AUDIT_EVENT_EXPECTED_FIELDS, sorted(names ^ _AUDIT_EVENT_EXPECTED_FIELDS)
    assert not (names & _AUDIT_EVENT_FORBIDDEN_FIELD_NAMES), sorted(names & _AUDIT_EVENT_FORBIDDEN_FIELD_NAMES)


# --- the kernel's per-request state --------------------------------------------------------------
def test_trusted_principal_is_references_only_with_exact_field_set() -> None:
    source = _KERNEL.read_text(encoding="utf-8")
    violations = _references_only_violations(source, "TrustedPrincipal", _PRINCIPAL_ALLOWED_FIELD_TYPES)
    assert violations == [], f"TrustedPrincipal references-only violations: {violations}"
    assert _field_names(source, "TrustedPrincipal") == _PRINCIPAL_EXPECTED_FIELDS, "the only tenant authority is an exact four-field shape"


def test_public_request_carries_no_prohibited_carrier_field() -> None:
    source = _KERNEL.read_text(encoding="utf-8")
    violations = _references_only_violations(source, "PublicRequest", _REQUEST_ALLOWED_FIELD_TYPES)
    assert violations == [], f"PublicRequest references-only violations: {violations}"
    names = _field_names(source, "PublicRequest")
    assert names == _REQUEST_EXPECTED_FIELDS, sorted(names ^ _REQUEST_EXPECTED_FIELDS)
    smuggled = names & _REQUEST_FORBIDDEN_FIELD_NAMES
    assert not smuggled, f"the kernel's request view must never gain a prohibited carrier field: {sorted(smuggled)}"


# --- the owner-resident portal DTOs ---------------------------------------------------------------
def test_owner_resident_portal_dtos_are_references_only() -> None:
    for path, shapes in ((_CP_PORTAL, _CP_PORTAL_SHAPES), (_DBR_PORTAL, _DBR_PORTAL_SHAPES)):
        source = path.read_text(encoding="utf-8")
        for cls in shapes:
            violations = _references_only_violations(source, cls, _PORTAL_ALLOWED_FIELD_TYPES)
            assert violations == [], f"{_scan.relposix(path)}::{cls} references-only violations: {violations}"


def test_the_removed_shapes_are_really_absent() -> None:
    """Recorded absence, so a dropped capability cannot be mistaken for an unguarded one."""
    sources = {p: p.read_text(encoding="utf-8") for p in (_KERNEL, _CP_PORTAL, _DBR_PORTAL)}
    for cls in _REMOVED_SHAPES:
        for path, source in sources.items():
            assert _find_classdef(source, cls) is None, (
                f"{cls} reappeared in {_scan.relposix(path)} — if a removed capability is being restored, it needs a census entry here"
            )


# --- non-vacuity companion --------------------------------------------------------------------
def test_references_only_census_flags_unsafe_shapes() -> None:
    # A forbidden field NAME (with a perfectly safe type) is flagged.
    named = "class EdgeAuditEvent:\n    action: str\n    payload: Optional[str]\n"
    v = _references_only_violations(named, "EdgeAuditEvent", _AUDIT_EVENT_ALLOWED_FIELD_TYPES)
    assert any("payload" in x for x in v), v
    # An unsafe TYPE is flagged even under a benign name.
    typed = "class EdgeAuditEvent:\n    action: str\n    rows: Tuple[str, ...]\n"
    v = _references_only_violations(typed, "EdgeAuditEvent", _AUDIT_EVENT_ALLOWED_FIELD_TYPES)
    assert any("Tuple" in x for x in v), v
    assert _field_names(typed, "EdgeAuditEvent") & _AUDIT_EVENT_FORBIDDEN_FIELD_NAMES == {"rows"}
    # A benign-typed but unexpected extra field still breaks the exact-set pin.
    extra = "class EdgeAuditEvent:\n    action: str\n    note: Optional[str]\n"
    assert _field_names(extra, "EdgeAuditEvent") != _AUDIT_EVENT_EXPECTED_FIELDS
    # A prohibited carrier planted on the kernel's request view is flagged BY NAME.
    carrier = "class PublicRequest:\n    method: str\n    query: Optional[str]\n"
    assert _field_names(carrier, "PublicRequest") & _REQUEST_FORBIDDEN_FIELD_NAMES == {"query"}
    # A raw-object (DB-row-like) field and a tenant_db field are flagged on a portal shape.
    bad_portal = "class MembershipEntryDTO:\n    memberships: object\n    tenant_db: str\n"
    portal_v = _references_only_violations(bad_portal, "MembershipEntryDTO", _PORTAL_ALLOWED_FIELD_TYPES)
    assert any("object" in x for x in portal_v), portal_v
    assert any("tenant_db" in x for x in portal_v), portal_v
    # Absent class -> sentinel (proves the census rejects an empty match set rather than passing).
    assert _references_only_violations("x = 1\n", "EdgeAuditEvent", _AUDIT_EVENT_ALLOWED_FIELD_TYPES) == ["EdgeAuditEvent not found"]
    # A class with no annotated fields is also a sentinel, not a pass.
    assert _references_only_violations("class EdgeAuditEvent:\n    pass\n", "EdgeAuditEvent", set()) == [
        "EdgeAuditEvent declares no annotated fields"
    ]


if __name__ == "__main__":
    _scan.run(
        [
            test_edge_audit_event_is_references_only_with_exact_field_set,
            test_trusted_principal_is_references_only_with_exact_field_set,
            test_public_request_carries_no_prohibited_carrier_field,
            test_owner_resident_portal_dtos_are_references_only,
            test_the_removed_shapes_are_really_absent,
            test_references_only_census_flags_unsafe_shapes,
        ]
    )
