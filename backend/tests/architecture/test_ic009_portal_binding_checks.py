"""IC-009 §P mechanical binding checks — owner-resident portals (default suite; no DB, no network).

**Provenance.** The migrated successor of the B5-BLK-6B IC-009 §P binding guard, which bound the
API Gateway's single `api_gateway/portal.py`. That module was deleted with the Gateway; IC-009 was
not. Response composition moved to the services that own the records, so the same contract clauses
are now bound against **two** portals:

* `control_plane/portal.py`  — `MembershipEntryDTO`, `WorkspaceMembershipDTO`, `compose_display_ref`
* `database_router/portal.py` — `TenantStartupDetailDTO`, `TenantStartupUpdateRequestDTO`

**What is still bound** (every clause that has a runtime subject):

* §P.2 — no physical-database identifier, router decision, or secret in ANY DTO;
* §P.4 — no multi-tenant result sequence; one response shape per request;
* §P.6 — the tenant-resident provenance triple + `lineage_reference` on the CLM detail DTO;
* §P.7 — the denial surface is the closed §L model (no DTO on denial);
* D3 seam traceability — source-level `PORTAL_CONTRACT_ID` / `PORTAL_CONTRACT_REVISION` constants,
  catalogue closure, and NO wire `contract_id` / `contract_revision` field;
* exact field-set closure by SET EQUALITY over every portal dataclass (a blocklist cannot catch an
  innocuously named PII field such as `founder_email`; only an allow-list closes the shape);
* the pinned `display_ref` derivation and deterministic fixed-field-order serialization.

**What LOST its runtime subject, recorded here rather than dropped in silence**
(`test_the_withdrawn_ic009_surfaces_are_really_absent` asserts the absence):

| Clause | Subject | Why it is unbound |
|---|---|---|
| §P.1 directory-DTO tenant anonymity | the three directory/global-summary DTOs |
  `GET /directory/<kind>` is **REMOVE FROM MVP** — no served Gateway route ever exposed it |
| §P.3 one §Q category → one domain → one database | `DispatchCategory` / `decide` | there is no
  dispatcher; each edge serves one route family it owns, so the mapping is structural |
| IC-007 four route prefixes / four categories | the Gateway classifier | same — no classifier exists |
| the import DTOs (`ImportInitiationDTO`, `ImportResultDTO`) | the served `/import` route |
  Import is outside the controlled local MVP journey (IMPORT-A / D-3) |

Those four rows are an **IC-009 amendment requirement**, not a silent coverage loss: the clauses
still stand in the contract and simply have nothing to bind to until a successor route exists.

Pure stdlib + repository imports; standalone-runnable:
  python tests/architecture/test_ic009_portal_binding_checks.py
"""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import json
import pathlib
import sys
import tempfile
from typing import Dict, List, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

if str(_scan.BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_scan.BACKEND_ROOT))

import control_plane.portal as cp_portal  # noqa: E402
import database_router.portal as dbr_portal  # noqa: E402
from control_plane.portal import MembershipEntryDTO, WorkspaceMembershipDTO, compose_display_ref  # noqa: E402
from database_router.portal import TenantStartupDetailDTO, TenantStartupUpdateRequestDTO  # noqa: E402
from shared.public_edge import PublicBoundaryDenied, forbidden, unauthenticated  # noqa: E402

_CP_PORTAL_FILE = _scan.BACKEND_ROOT / "control_plane" / "portal.py"
_DBR_PORTAL_FILE = _scan.BACKEND_ROOT / "database_router" / "portal.py"
_CP_PORTS = _scan.BACKEND_ROOT / "control_plane" / "ports.py"

# IC-009 §P.2 — no physical-DB identifier / router decision / secret in ANY DTO.
_P2_FORBIDDEN = {
    "dsn",
    "database_url",
    "database_name",
    "db_name",
    "connection",
    "connection_string",
    "tenant_db",
    "secret",
    "credential",
    "password",
    "token",
    "router_decision",
    "route_ref",
}

# The EXACT field set of every portal dataclass — SET EQUALITY, never subset/blocklist.
# Load-bearing: _P2_FORBIDDEN is a BLOCKLIST, and a blocklist cannot enforce an approved DTO
# catalogue — an innocuously named PII field (owner_email / founder_email / contact_email) is on no
# blocklist and is typed `str`, so it passes every name and type census while still breaching
# IC-009 §D's references-only rule. Only an ALLOW-LIST closes the shape.
_EXACT_FIELD_SETS: Dict[type, Set[str]] = {
    MembershipEntryDTO: {"tenant_id", "role", "display_ref"},
    WorkspaceMembershipDTO: {"memberships"},
    TenantStartupDetailDTO: {
        "record_ref",
        "display_name",
        "short_description",
        "investment_stage",
        "record_origin",
        "record_residency",
        "record_type",
        "lineage_reference",
    },
    TenantStartupUpdateRequestDTO: {"short_description"},
}

# PII-shaped field names used ONLY as planted violations in the non-vacuity companion.
_PLANTED_PII_FIELDS = ("founder_email", "owner_email", "contact_email")

# Shapes that existed only inside the deleted Gateway portal.
_WITHDRAWN_SHAPES = (
    "DirectoryEntryDTO",
    "GlobalStartupSummaryDTO",
    "GlobalInvestorSummaryDTO",
    "ImportInitiationDTO",
    "ImportResultDTO",
    "ErrorDTO",
    "UserSessionDTO",
)
_WITHDRAWN_MODULES = ("api_gateway", "api_gateway.portal", "api_gateway.dispatch", "api_gateway.models")

_TENANT = "tenant-acme"


def _field_names(cls: type) -> Set[str]:
    return {f.name for f in dataclasses.fields(cls)}


def _membership_instance() -> WorkspaceMembershipDTO:
    return WorkspaceMembershipDTO(
        memberships=(MembershipEntryDTO(tenant_id=_TENANT, role="TENANT_AGENT", display_ref=compose_display_ref(_TENANT)),)
    )


def _detail_instance() -> TenantStartupDetailDTO:
    return TenantStartupDetailDTO(
        record_ref="clm-startup-1",
        display_name="ACME",
        short_description="bounded free text",
        investment_stage="seed",
        lineage_reference="lin-1",
    )


def _all_instances() -> List[object]:
    return [_membership_instance(), _detail_instance(), TenantStartupUpdateRequestDTO(short_description="x")]


def _recursive_keys(value: object) -> Set[str]:
    out: Set[str] = set()
    if isinstance(value, dict):
        for key, sub in value.items():
            out.add(str(key))
            out |= _recursive_keys(sub)
    elif isinstance(value, (list, tuple)):
        for sub in value:
            out |= _recursive_keys(sub)
    return out


def _portal_dataclasses(module_file: pathlib.Path, module: object) -> Set[type]:
    tree = ast.parse(module_file.read_text(encoding="utf-8"), filename=str(module_file))
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    return {getattr(module, name) for name in names if dataclasses.is_dataclass(getattr(module, name, None))}


# --- D3 seam traceability: constants + catalogue closure ------------------------------------------
def test_seam_traceability_constants_and_catalogue_closure() -> None:
    for module in (cp_portal, dbr_portal):
        assert module.PORTAL_CONTRACT_ID == "IC-009", f"{module.__name__} must name IC-009"
        assert module.PORTAL_CONTRACT_REVISION == "IC-009-R1", f"{module.__name__} must serve revision IC-009-R1"
    # Both owners serve the SAME contract revision: a split of the composition across two services
    # must not become a split of the CONTRACT.
    assert cp_portal.PORTAL_CONTRACT_REVISION == dbr_portal.PORTAL_CONTRACT_REVISION
    # Catalogue closure per owner: the approved catalogue names exactly the RESPONSE shapes that
    # owner composes, each against the (contract, revision) pair the seam serves.
    assert set(cp_portal.APPROVED_PORTAL_DTOS) == {WorkspaceMembershipDTO}, "the Control Plane composes one response shape"
    assert set(dbr_portal.APPROVED_PORTAL_DTOS) == {TenantStartupDetailDTO}, "the Database Router composes one response shape"
    for module in (cp_portal, dbr_portal):
        assert set(module.APPROVED_PORTAL_DTOS.values()) == {(module.PORTAL_CONTRACT_ID, module.PORTAL_CONTRACT_REVISION)}
    # The update REQUEST shape is DEFINED but EXCLUDED from the catalogue — a request DTO never
    # composes as a response (the IC-010 §V.2 idiom the deleted ErrorDTO exclusion also used).
    assert TenantStartupUpdateRequestDTO not in dbr_portal.APPROVED_PORTAL_DTOS
    # The two catalogues are DISJOINT: neither owner may compose the other's shape.
    assert not (set(cp_portal.APPROVED_PORTAL_DTOS) & set(dbr_portal.APPROVED_PORTAL_DTOS))


def test_serializers_reject_any_type_absent_from_the_catalogue() -> None:
    @dataclasses.dataclass(frozen=True)
    class RogueDTO:
        anything: str

    for module in (cp_portal, dbr_portal):
        raised = False
        try:
            module.serialize_portal_dto(RogueDTO(anything="x"))  # type: ignore[arg-type]
        except ValueError:
            raised = True
        assert raised, f"{module.__name__}.serialize_portal_dto must refuse a type absent from the catalogue"
    # Cross-owner refusal: each serializer refuses the OTHER owner's approved shape.
    for module, foreign in ((cp_portal, _detail_instance()), (dbr_portal, _membership_instance())):
        raised = False
        try:
            module.serialize_portal_dto(foreign)  # type: ignore[arg-type]
        except ValueError:
            raised = True
        assert raised, f"{module.__name__} must refuse the other owner's approved shape"
    # The update REQUEST shape is refused too.
    raised = False
    try:
        dbr_portal.serialize_portal_dto(TenantStartupUpdateRequestDTO(short_description="x"))  # type: ignore[arg-type]
    except ValueError:
        raised = True
    assert raised, "the update request shape must never serialize as a response"
    # Green controls.
    assert cp_portal.serialize_portal_dto(_membership_instance())
    assert dbr_portal.serialize_portal_dto(_detail_instance())


def test_no_dto_carries_wire_contract_traceability_fields() -> None:
    # D3 (CLR-6B-2): traceability is SOURCE-LEVEL / seam-owned. IC-009 §I:133 / IC-002:207 close the
    # membership field set; no approved DTO may declare a wire traceability field.
    for cls in _EXACT_FIELD_SETS:
        names = _field_names(cls)
        assert not (names & {"contract_id", "contract_revision"}), f"{cls.__name__} carries a wire traceability field: {names}"


# --- exact field-set closure across every owner-resident portal shape ------------------------------
def test_every_portal_dataclass_has_exact_field_set_closure() -> None:
    declared = _portal_dataclasses(_CP_PORTAL_FILE, cp_portal) | _portal_dataclasses(_DBR_PORTAL_FILE, dbr_portal)
    # Non-vacuity: the catalogue must cover BOTH portal modules EXACTLY — an unlisted new shape
    # fails here rather than silently escaping closure, and a stale entry fails too.
    assert declared == set(_EXACT_FIELD_SETS), (
        "the owner-resident portal dataclasses and the exact-field-set catalogue must match exactly; "
        f"unlisted={sorted(c.__name__ for c in declared - set(_EXACT_FIELD_SETS))} "
        f"stale={sorted(c.__name__ for c in set(_EXACT_FIELD_SETS) - declared)}"
    )
    assert len(_EXACT_FIELD_SETS) == 4, f"expected exactly 4 owner-resident portal shapes, got {len(_EXACT_FIELD_SETS)}"
    for cls, expected in _EXACT_FIELD_SETS.items():
        assert _field_names(cls) == expected, f"{cls.__name__} field set drifted: {_field_names(cls)} != {expected}"


def test_exact_field_set_closure_rejects_a_planted_pii_field() -> None:
    # NON-VACUITY COMPANION: a PII-shaped field is caught ONLY by exact closure. Each plant is
    # judged through the SAME `_field_names` helper the real check uses.
    planted_pairs = zip((MembershipEntryDTO, TenantStartupDetailDTO, TenantStartupUpdateRequestDTO), _PLANTED_PII_FIELDS, strict=True)
    for cls, planted_field in planted_pairs:
        expected = _EXACT_FIELD_SETS[cls]
        planted = dataclasses.make_dataclass(cls.__name__, [*((name, str) for name in sorted(expected)), (planted_field, str)], frozen=True)
        assert _field_names(planted) != expected, f"exact closure must reject {cls.__name__}.{planted_field}"
        assert _field_names(planted) - expected == {planted_field}
        # ...and prove WHY set equality is required: the blocklist genuinely MISSES it.
        assert planted_field not in _P2_FORBIDDEN, f"{planted_field} is on no forbidden-name list — exact closure is its only detector"
    for cls, expected in _EXACT_FIELD_SETS.items():
        assert _field_names(cls) == expected


# --- IC-009 §P.2 — no physical-database identity in ANY DTO ---------------------------------------
def test_p2_no_physical_database_identity_in_any_dto() -> None:
    instances = _all_instances()
    assert instances, "P.2 must run over a NON-EMPTY instance set"
    for dto in instances:
        hits = _recursive_keys(dataclasses.asdict(dto)) & _P2_FORBIDDEN  # type: ignore[arg-type]
        assert hits == set(), f"{type(dto).__name__} carries a physical-DB/secret identifier: {hits}"


# --- IC-009 §P.4 — one response shape per request, no multi-tenant sequence ------------------------
def test_p4_no_multi_tenant_result_sequence_and_one_response_shape() -> None:
    # The ONE sequence-valued field in the whole surface is `memberships`, and it is a membership
    # feed (IR-08), not a directory. Every other approved shape is scalar-only.
    for cls in _EXACT_FIELD_SETS:
        sequence_fields = {f.name for f in dataclasses.fields(cls) if "Tuple" in str(f.type) or "List" in str(f.type)}
        assert sequence_fields <= {"memberships"}, f"{cls.__name__} declares an unapproved sequence field: {sorted(sequence_fields)}"
    # A memberships feed may span tenants BY CONTRACT (it is the workspace switcher). No OTHER
    # shape may: the tenant detail response carries no tenant identifier at all.
    detail_keys = _recursive_keys(dataclasses.asdict(_detail_instance()))
    assert not (detail_keys & {"tenant_id", "tenant_ref", "target_tenant_ref"}), (
        "the tenant-resident detail response must carry no tenant selector — the tenant came from the signed claim"
    )


# --- IC-009 §P.6 — the tenant-resident provenance half --------------------------------------------
def test_p6_tenant_resident_provenance_triple_and_lineage_reference() -> None:
    detail = _detail_instance()
    assert (detail.record_origin, detail.record_residency, detail.record_type) == ("tenant", "tenant", "startup"), (
        "the D-37 §10 provenance triple must carry the tenant-resident values"
    )
    # lineage_reference is present ONLY when the record was imported; it is nullable and defaults
    # to None, so a never-imported record carries no lineage claim.
    never_imported = dataclasses.replace(detail, lineage_reference=None)
    assert never_imported.lineage_reference is None
    assert json.loads(dbr_portal.serialize_portal_dto(never_imported).decode("utf-8"))["lineage_reference"] is None
    # The provenance markers are DEFAULTS on the dataclass, not values a caller supplies per call.
    defaults = {f.name: f.default for f in dataclasses.fields(TenantStartupDetailDTO)}
    assert defaults["record_origin"] == "tenant" and defaults["record_residency"] == "tenant" and defaults["record_type"] == "startup"


# --- IC-009 §P.7 — the denial surface is the closed §L model ---------------------------------------
def test_p7_denial_surface_is_the_closed_l_model_with_no_dto() -> None:
    # No DTO is composable on denial: the denial type is an EXCEPTION carrying a status and a
    # bounded public code, and it is not a dataclass, so it can never enter a portal catalogue.
    denied = forbidden()
    assert isinstance(denied, PublicBoundaryDenied)
    assert not dataclasses.is_dataclass(type(denied)), "the denial shape must not be a composable DTO"
    assert (denied.http_status, denied.public_code) == (403, "forbidden")
    assert (unauthenticated().http_status, unauthenticated().public_code) == (401, "unauthenticated")
    for module in (cp_portal, dbr_portal):
        assert type(denied) not in module.APPROVED_PORTAL_DTOS, "a denial must never be composable"


# --- the pinned derivation + deterministic serialization -------------------------------------------
def test_display_ref_is_the_pinned_composed_format() -> None:
    assert compose_display_ref(_TENANT) == "ref:tenant/" + _TENANT + "/display"
    # Derived, never stored: the Control Plane returns no display value, so the derivation must be
    # a pure function of the tenant id alone.
    assert compose_display_ref("t2") != compose_display_ref("t3")


def test_serialization_is_deterministic_with_fixed_field_order() -> None:
    for module, dto in ((cp_portal, _membership_instance()), (dbr_portal, _detail_instance())):
        first = module.serialize_portal_dto(dto)
        assert first == module.serialize_portal_dto(dto), "the same instance must always serialize to the same bytes"
        decoded = json.loads(first.decode("utf-8"))
        assert list(decoded) == [f.name for f in dataclasses.fields(type(dto))], "field ORDER is part of the contract (IC-010 §V.1)"
        assert b", " not in first and b": " not in first, "compact separators only — deterministic serialization"


# --- the Control-Plane read port admits no raw shapes ----------------------------------------------
def test_the_public_edges_read_port_is_one_read_method_and_its_raw_shape_never_reaches_the_wire() -> None:
    """The successor of the Gateway-era "read ports admit no raw shape" check.

    That check bound ``api_gateway/ports.py``, whose ``ControlPlaneReadPort`` returned typed portal
    DTOs. It is gone. The public workspace edge instead holds ONE port,
    ``WorkspaceMembershipReadPort``, whose single method returns the transport-neutral enumeration
    ``Dict[str, Any]`` — the same shape the internal read edge has always produced.

    So the property is restated where it actually lives, and NOT weakened: the raw mapping is an
    internal shape that must never reach a client. Two halves, both asserted:

      (a) the port is exactly ONE read method, self-scoped by ``principal_ref``, declaring no
          write/provision/administer capability at all (narrow by TYPE — an edge holding only this
          port cannot express those operations);
      (b) the raw mapping is re-composed into the typed DTO before serialization, and the
          serializer refuses anything that is not the approved shape (proved by
          ``test_serializers_reject_any_type_absent_from_the_catalogue``), so no raw mapping can be
          put on the wire even if the port returned a wider one.
    """
    tree = ast.parse(_CP_PORTS.read_text(encoding="utf-8"), filename=str(_CP_PORTS))
    port = next(
        (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "WorkspaceMembershipReadPort"),
        None,
    )
    assert port is not None, "the public workspace edge's read port must exist — the census cannot be vacuous"
    methods = [node for node in port.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert [m.name for m in methods] == ["memberships_for_principal"], (
        f"the port must expose exactly ONE method; found {[m.name for m in methods]}"
    )
    only = methods[0]
    args = [a.arg for a in only.args.args if a.arg != "self"]
    assert args == ["principal_ref"], f"the one method must be self-scoped by principal_ref alone; found {args}"
    assert only.returns is not None, "the one method must declare a return annotation"
    # (a) no write/administer capability is EXPRESSIBLE through the port.
    for forbidden_shape in ("put_", "append_", "delete_", "drop_", "create_", "provision", "compare_and_swap", "apply_schema"):
        assert not any(forbidden_shape in m.name for m in methods), f"the public read port must declare no {forbidden_shape}* capability"
    # (b) the edge re-composes into the typed DTO; the raw mapping is never serialized.
    edge = (_scan.BACKEND_ROOT / "control_plane" / "adapters" / "providers" / "http_public_workspace_edge.py").read_text(encoding="utf-8")
    assert "WorkspaceMembershipDTO(" in edge, "the edge must compose the typed DTO from the raw enumeration"
    assert "serialize_portal_dto" in edge, "the edge must serialize through the catalogue-closing serializer"
    raised = False
    try:
        cp_portal.serialize_portal_dto({"memberships": [{"tenant_id": "t", "role": "TENANT_AGENT"}]})  # type: ignore[arg-type]
    except (ValueError, TypeError):
        raised = True
    assert raised, "the raw port mapping must be UNSERIALIZABLE — it can never reach a client as-is"


# --- withdrawn surfaces: recorded absence ----------------------------------------------------------
def test_the_withdrawn_ic009_surfaces_are_really_absent() -> None:
    """So a dropped capability cannot be mistaken for an unguarded one."""
    for module_name in _WITHDRAWN_MODULES:
        try:
            found = importlib.util.find_spec(module_name)
        except ModuleNotFoundError:
            found = None
        assert found is None, f"{module_name} must not be importable — the API Gateway was deleted"
    for shape in _WITHDRAWN_SHAPES:
        for module in (cp_portal, dbr_portal):
            assert not hasattr(module, shape), (
                f"{shape} reappeared in {module.__name__} — restoring a withdrawn capability needs a catalogue entry above"
            )


def test_static_detectors_flag_planted_violations() -> None:
    # The recursive key walk sees nested keys (a smuggled DSN inside a nested record is caught).
    assert _recursive_keys({"memberships": [{"tenant_id": "t", "dsn": "x"}]}) & _P2_FORBIDDEN == {"dsn"}
    # The dataclass census reads the module's own AST, so an added shape is visible.
    # A TEMPORARY directory, never the tracked tree: a guard that writes into tests/architecture/
    # dirties the working tree during a normal `pytest` run and strands a file if the process dies.
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir) / "_nv_probe_portal.py"
        tmp.write_text("import dataclasses\n\n\n@dataclasses.dataclass(frozen=True)\nclass PlantedDTO:\n    x: str\n", encoding="utf-8")
        spec = importlib.util.spec_from_file_location("_nv_probe_portal", tmp)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        found = _portal_dataclasses(tmp, module)
    assert {c.__name__ for c in found} == {"PlantedDTO"}, "the dataclass census must see a planted shape"
    assert found != set(_EXACT_FIELD_SETS), "an unlisted shape must break catalogue closure"


if __name__ == "__main__":
    _scan.run(
        [
            test_seam_traceability_constants_and_catalogue_closure,
            test_serializers_reject_any_type_absent_from_the_catalogue,
            test_no_dto_carries_wire_contract_traceability_fields,
            test_every_portal_dataclass_has_exact_field_set_closure,
            test_exact_field_set_closure_rejects_a_planted_pii_field,
            test_p2_no_physical_database_identity_in_any_dto,
            test_p4_no_multi_tenant_result_sequence_and_one_response_shape,
            test_p6_tenant_resident_provenance_triple_and_lineage_reference,
            test_p7_denial_surface_is_the_closed_l_model_with_no_dto,
            test_display_ref_is_the_pinned_composed_format,
            test_serialization_is_deterministic_with_fixed_field_order,
            test_the_public_edges_read_port_is_one_read_method_and_its_raw_shape_never_reaches_the_wire,
            test_the_withdrawn_ic009_surfaces_are_really_absent,
            test_static_detectors_flag_planted_violations,
        ]
    )
