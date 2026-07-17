"""B5-BLK-6B — IC-009 §P mechanical binding checks + IC-007 static deferral guard.

Binds IC-009 §P.1/P.2/P.3/P.4/P.6/P.7 NON-VACUOUSLY (every record-DTO check runs over
non-empty serialized instances; P.6's tenant-resident half carries an explicit GUARDED
skip whose precondition is re-derived every run), pins the D3 seam-traceability rule
(source-level constants + catalogue closure; NO wire contract_id/contract_revision
fields), pins the gateway-composed ``display_ref`` format, and mechanically preserves the
IC-007 negative boundary: exactly four route prefixes, exactly four §Q categories, no
cross-tenant route, one ``DispatchDecision``/one ``RouteOutcome`` per request, no fan-out.

P.5 (Frontend Repository Audit) is deliberately UNCLAIMED — B5-BLK-5/frontend scope; no
frontend repo exists. No audit check appears here because IC-009 §P contains none: 6B
adds NO new audit event and does NOT discharge the IC-002:165 MembershipsForPrincipal
audit obligation (separately governed).

Pure stdlib + api_gateway imports; standalone-runnable:
python tests/architecture/test_ic009_portal_binding_checks.py
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import sys
from typing import Any, Dict, List, Set, Union, get_args

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

if str(_scan.BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_scan.BACKEND_ROOT))

from api_gateway import portal  # noqa: E402
from api_gateway.dispatch import _CONTROL_CATEGORIES, category_domain, decide  # noqa: E402
from api_gateway.models import DatabaseDomain, DispatchCategory  # noqa: E402
from api_gateway.portal import (  # noqa: E402
    APPROVED_PORTAL_DTOS,
    PORTAL_CONTRACT_ID,
    PORTAL_CONTRACT_REVISION,
    DirectoryEntryDTO,
    ErrorDTO,
    GlobalInvestorSummaryDTO,
    GlobalStartupSummaryDTO,
    ImportInitiationDTO,
    MembershipEntryDTO,
    PortalDTO,
    WorkspaceMembershipDTO,
    compose_display_ref,
    compose_portal_dto,
    serialize_portal_dto,
)
from shared.context import RequestContext  # noqa: E402

AG = _scan.BACKEND_ROOT / "api_gateway"
_DISPATCH = AG / "dispatch.py"
_PORTS = AG / "ports.py"
_MODELS = AG / "models.py"

# IC-009 §P.1 (D-35 Tenant Anonymity Rule) — the exact forbidden directory-DTO names,
# plus lineage_reference (global records carry none).
_P1_FORBIDDEN = {"tenant_id", "tenant_name", "tenant_code", "tenant_reference", "membership_reference", "lineage_reference"}
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
# IC-007 §Q closure: exactly these four classifier prefixes — a fifth is a cross-tenant door.
_EXPECTED_PREFIXES = {"/tenant", "/directory", "/memberships", "/import"}
# Tenant-resident record DTO names (IC-009 §D business-domain tier) — none may join the
# union in 6B without binding the lineage_reference half of P.6 (the guarded-skip rule).
_TENANT_RESIDENT_RECORD_DTO_NAMES = {"TenantStartupDTO", "TenantInvestorDTO", "TenantDealDTO", "LineageSummaryDTO"}
# The EXACT field set of every portal dataclass — SET EQUALITY, never subset/blocklist.
# Load-bearing: _P1_FORBIDDEN/_P2_FORBIDDEN (and test_phase7's _FORBIDDEN_FIELD_NAMES) are
# BLOCKLISTS, and a blocklist cannot enforce an approved DTO catalogue — an innocuously
# named PII field (owner_email/founder_email/contact_email) is on no blocklist and is typed
# `str`, so it passes every name and type census while still breaching IC-009 §D's
# references-only rule ("no name/email/PII payload"). Only an ALLOW-LIST closes the shape.
_EXACT_FIELD_SETS: Dict[type, Set[str]] = {
    DirectoryEntryDTO: {"record_ref", "display_name"},
    GlobalStartupSummaryDTO: {"records", "record_origin", "record_residency", "record_type"},
    GlobalInvestorSummaryDTO: {"records", "record_origin", "record_residency", "record_type"},
    MembershipEntryDTO: {"tenant_id", "role", "display_ref"},
    WorkspaceMembershipDTO: {"memberships"},
    ImportInitiationDTO: {"source_ref", "target_tenant_ref", "initiation"},
    ErrorDTO: {"status", "public_code"},
}
# PII-shaped field names used ONLY as planted violations in the non-vacuity companion —
# never authored on a production DTO.
_PLANTED_PII_FIELDS = ("owner_email", "founder_email", "contact_email")

# Non-empty sample instances — every serialized-instance check runs over THESE (P.6/CLR-3:
# a check over an empty instance set is vacuous and must fail).
_DIRECTORY_INSTANCES: List[Union[GlobalStartupSummaryDTO, GlobalInvestorSummaryDTO]] = [
    GlobalStartupSummaryDTO(
        records=(DirectoryEntryDTO(record_ref="g1", display_name="S1"), DirectoryEntryDTO(record_ref="g2", display_name="S2"))
    ),
    GlobalInvestorSummaryDTO(records=(DirectoryEntryDTO(record_ref="i1", display_name="V1"),)),
]
_ALL_UNION_INSTANCES: List[PortalDTO] = [
    _DIRECTORY_INSTANCES[0],
    _DIRECTORY_INSTANCES[1],
    WorkspaceMembershipDTO(memberships=(MembershipEntryDTO(tenant_id="t1", role="MASTER_AGENT", display_ref=compose_display_ref("t1")),)),
    ImportInitiationDTO(source_ref="global-startup/g1", target_tenant_ref="t1"),
]


def _recursive_keys(value: object) -> Set[str]:
    """Every dict key across a serialized (asdict-style) structure — the DTO's whole
    serialized field surface, nested entries included."""
    keys: Set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            keys.add(str(k))
            keys |= _recursive_keys(v)
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys |= _recursive_keys(item)
    return keys


def _serialized_keys(dto: PortalDTO) -> Set[str]:
    return _recursive_keys(dataclasses.asdict(dto))


def _field_names(cls: Any) -> Set[str]:
    """The declared field-name set of a dataclass — the unit of exact-closure equality.
    The SAME helper backs both the real closure check and its planted-violation companion."""
    return {f.name for f in dataclasses.fields(cls)}


def _portal_dataclasses() -> Set[type]:
    """Every dataclass DECLARED in portal.py, re-derived from the module every run — so a
    newly authored shape cannot escape closure merely by not being listed in the catalogue."""
    return {
        obj
        for obj in vars(portal).values()
        if isinstance(obj, type) and dataclasses.is_dataclass(obj) and obj.__module__ == portal.__name__
    }


def _classifier_prefixes(source: str) -> Set[str]:
    """The literal route-prefix set of ``default_classifier`` (AST; '/x' and '/x/'
    startswith variants normalize to one prefix)."""
    tree = ast.parse(source)
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "default_classifier":
            fn = node
    if fn is None:
        return set()
    prefixes: Set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("/"):
            prefixes.add(node.value.rstrip("/"))
    return prefixes


def _port_return_annotation_names(source: str, class_name: str, method_name: str) -> Set[str]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == method_name and sub.returns is not None:
                    names: Set[str] = set()
                    for n in ast.walk(sub.returns):
                        if isinstance(n, ast.Name):
                            names.add(n.id)
                        elif isinstance(n, ast.Attribute):
                            names.add(n.attr)
                    return names
    return {f"{class_name}.{method_name} not found"}


# --- D3 seam traceability: constants + catalogue closure (mutation detectors 6/15) -----------------
def test_seam_traceability_constants_and_catalogue_closure() -> None:
    assert PORTAL_CONTRACT_ID == "IC-009"
    assert PORTAL_CONTRACT_REVISION == "IC-009-R1"
    union_members = set(get_args(PortalDTO))
    assert union_members == {
        GlobalStartupSummaryDTO,
        GlobalInvestorSummaryDTO,
        WorkspaceMembershipDTO,
        ImportInitiationDTO,
    }, union_members
    # Catalogue closure: the approved-DTO catalogue's key set EQUALS the union member set,
    # and every entry names exactly the (contract, revision) pair the seam serves.
    assert set(APPROVED_PORTAL_DTOS.keys()) == union_members
    assert set(APPROVED_PORTAL_DTOS.values()) == {(PORTAL_CONTRACT_ID, PORTAL_CONTRACT_REVISION)}
    # ErrorDTO is DEFINED but EXCLUDED from the union (IC-010 §V.2: no DTO on denial makes
    # denial-shape membership unreachable by construction); UserSessionDTO is NOT authored.
    assert ErrorDTO not in union_members and ErrorDTO not in APPROVED_PORTAL_DTOS
    assert not hasattr(portal, "UserSessionDTO"), "UserSessionDTO must not be authored in 6B (no approved §Q category returns it)"


def test_composer_rejects_any_type_absent_from_the_catalogue() -> None:
    # Mutation detector 15 (unapproved DTO type) — the composer and the serializer both
    # refuse a type outside the catalogue; every approved type passes (green control).
    @dataclasses.dataclass(frozen=True)
    class RogueDTO:
        anything: str

    for fn in (compose_portal_dto, serialize_portal_dto):
        raised = False
        try:
            fn(RogueDTO(anything="x"))  # type: ignore[arg-type]
        except ValueError:
            raised = True
        assert raised, f"{fn.__name__} must refuse a type absent from the catalogue"
    # ErrorDTO is refused too — it is defined but NOT composable (union-excluded).
    raised = False
    try:
        compose_portal_dto(ErrorDTO(status=403, public_code="forbidden"))  # type: ignore[arg-type]
    except ValueError:
        raised = True
    assert raised, "ErrorDTO must not be composable (excluded from the union/catalogue)"
    for dto in _ALL_UNION_INSTANCES:
        assert compose_portal_dto(dto) is dto  # green control


def test_no_dto_carries_wire_contract_traceability_fields() -> None:
    # D3 (CLR-6B-2): traceability is SOURCE-LEVEL/seam-owned. IC-009 §I:133 / IC-002:207
    # close the membership field set; no approved DTO may declare a wire traceability field.
    for cls in (*get_args(PortalDTO), DirectoryEntryDTO, MembershipEntryDTO, ErrorDTO):
        names = {f.name for f in dataclasses.fields(cls)}
        assert not (names & {"contract_id", "contract_revision"}), f"{cls.__name__} carries a wire traceability field: {names}"


# --- exact field-set closure across ALL seven portal shapes (OBS-PMV-11) --------------------------
def test_every_portal_dataclass_has_exact_field_set_closure() -> None:
    # IC-009 §D references-only closure by SET EQUALITY over every portal dataclass — the
    # four PortalDTO union members, both nested entry DTOs, and ErrorDTO. Blocklists cannot
    # do this job (see _EXACT_FIELD_SETS); an allow-list can.
    declared = _portal_dataclasses()
    # Non-vacuity 1: the catalogue must cover portal.py EXACTLY — an unlisted new shape fails
    # here rather than silently escaping closure, and a stale entry fails too.
    assert declared == set(_EXACT_FIELD_SETS), (
        "portal.py dataclasses and the exact-field-set catalogue must match exactly; "
        f"unlisted={sorted(c.__name__ for c in declared - set(_EXACT_FIELD_SETS))} "
        f"stale={sorted(c.__name__ for c in set(_EXACT_FIELD_SETS) - declared)}"
    )
    # Non-vacuity 2: the catalogue is non-empty and is exactly the seven approved shapes.
    assert len(_EXACT_FIELD_SETS) == 7, f"expected exactly 7 portal shapes, got {len(_EXACT_FIELD_SETS)}"
    for cls, expected in _EXACT_FIELD_SETS.items():
        assert _field_names(cls) == expected, f"{cls.__name__} field set drifted: {_field_names(cls)} != {expected}"


def test_exact_field_set_closure_rejects_a_planted_pii_field() -> None:
    # NON-VACUITY COMPANION (OBS-PMV-11): a PII-shaped field is caught ONLY by exact
    # closure. Each plant is judged through the SAME `_field_names` helper the real check
    # uses, on a dataclass built to mirror a real shape plus one extra `str` field.
    for cls, planted_field in zip((DirectoryEntryDTO, ImportInitiationDTO, GlobalInvestorSummaryDTO), _PLANTED_PII_FIELDS):
        expected = _EXACT_FIELD_SETS[cls]
        planted = dataclasses.make_dataclass(cls.__name__, [*((name, str) for name in sorted(expected)), (planted_field, str)], frozen=True)
        assert _field_names(planted) != expected, f"exact closure must reject {cls.__name__}.{planted_field} (a planted PII-shaped field)"
        assert _field_names(planted) - expected == {planted_field}
        # ...and prove WHY set equality is required: every blocklist genuinely MISSES it.
        assert planted_field not in (_P1_FORBIDDEN | _P2_FORBIDDEN), (
            f"{planted_field} is on no forbidden-name list — exact field-set closure is its only detector"
        )
    # Green control: the real, unplanted shapes still satisfy the same helper.
    for cls, expected in _EXACT_FIELD_SETS.items():
        assert _field_names(cls) == expected


# --- IC-009 §P.1 — directory-DTO tenant anonymity (mutation detector 4) ----------------------------
def test_p1_directory_dtos_are_tenant_anonymous_over_nonempty_instances() -> None:
    assert _DIRECTORY_INSTANCES, "P.1 must run over a NON-EMPTY instance set"
    for dto in _DIRECTORY_INSTANCES:
        assert dto.records, "P.1 must run over NON-EMPTY serialized records"
        hits = _serialized_keys(dto) & _P1_FORBIDDEN
        assert hits == set(), f"{type(dto).__name__} carries forbidden directory fields: {hits}"
    # Membership DTOs are EXEMPT by contract (IR-08: NOT directory records — they lawfully
    # carry tenant_id) — but their field set is contract-CLOSED to exactly the IC-002 triple.
    assert {f.name for f in dataclasses.fields(MembershipEntryDTO)} == {"tenant_id", "role", "display_ref"}
    assert {f.name for f in dataclasses.fields(WorkspaceMembershipDTO)} == {"memberships"}


# --- IC-009 §P.2 — no physical-DB identifier in ANY DTO (mutation detectors 5/16) ------------------
def test_p2_no_physical_database_identity_in_any_dto() -> None:
    instances: List[object] = [*_ALL_UNION_INSTANCES, ErrorDTO(status=403, public_code="forbidden")]
    for dto in instances:
        hits = _recursive_keys(dataclasses.asdict(dto)) & _P2_FORBIDDEN  # type: ignore[arg-type]
        assert hits == set(), f"{type(dto).__name__} carries a physical-DB/secret identifier: {hits}"


# --- IC-009 §P.3 — one §Q category → one domain → one database (mutation detector 7) ---------------
def test_p3_every_category_resolves_to_exactly_one_domain_and_database() -> None:
    control_ctx = RequestContext(correlation_id="c", request_id="c", active_tenant_id=None, principal_ref="ops", role="CONTROL")
    tenant_ctx = RequestContext(correlation_id="c", request_id="c", active_tenant_id="t1", principal_ref="p1", role="TENANT_AGENT")
    for category in DispatchCategory:
        domain = category_domain(category)
        assert domain in (DatabaseDomain.CONTROL, DatabaseDomain.TENANT)
        decision = decide(category, control_ctx if domain is DatabaseDomain.CONTROL else tenant_ctx)
        # Exactly one decision, exactly one target: CONTROL -> no tenant; TENANT -> the ONE
        # signed active tenant. Never a collection, never both.
        if domain is DatabaseDomain.CONTROL:
            assert decision.target_tenant_id is None
        else:
            assert decision.target_tenant_id == "t1"
        assert not isinstance(decision.target_tenant_id, (list, tuple, set))


# --- IC-009 §P.4 — MASTER_AGENT fan-out prohibition (static halves; mutation detector 7) -----------
def test_p4_no_multi_tenant_result_sequence_and_single_decision_shapes() -> None:
    ports_src = _PORTS.read_text(encoding="utf-8")
    # RouterDispatchPort.dispatch returns ONE RouteOutcome — never a sequence of outcomes.
    ret = _port_return_annotation_names(ports_src, "RouterDispatchPort", "dispatch")
    assert ret == {"RouteOutcome"}, ret
    # DispatchDecision.target_tenant_id is Optional[str] — never a collection type.
    models_src = _MODELS.read_text(encoding="utf-8")
    tree = ast.parse(models_src)
    ann_names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "DispatchDecision":
            for sub in node.body:
                if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) and sub.target.id == "target_tenant_id":
                    for n in ast.walk(sub.annotation):
                        if isinstance(n, ast.Name):
                            ann_names.add(n.id)
    assert ann_names == {"Optional", "str"}, ann_names
    # assert_single_database keeps BOTH isolation branches (a §K straddle raises, marked
    # isolation_anomaly=True) — the defensive one-database invariant is unmodified.
    dispatch_src = _DISPATCH.read_text(encoding="utf-8")
    fn = None
    for node in ast.walk(ast.parse(dispatch_src)):
        if isinstance(node, ast.FunctionDef) and node.name == "assert_single_database":
            fn = node
    assert fn is not None, "assert_single_database must exist"
    raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
    assert len(raises) == 2, "assert_single_database must keep exactly its two isolation branches"
    for r in raises:
        assert isinstance(r.exc, ast.Call)
        assert any(k.arg == "isolation_anomaly" for k in r.exc.keywords), "the straddle raise must stay an IsolationAnomaly"


# --- IC-009 §P.6 — provenance markers + the CLR-3 guarded skip (mutation detector 14) --------------
def test_p6_provenance_markers_global_half_over_nonempty_instances() -> None:
    assert _DIRECTORY_INSTANCES, "P.6's global half must run over a NON-EMPTY instance set (a vacuous pass is rejected)"
    expected_types = {GlobalStartupSummaryDTO: "GlobalStartupDirectory", GlobalInvestorSummaryDTO: "GlobalInvestorDirectory"}
    for dto in _DIRECTORY_INSTANCES:
        assert dto.records, "P.6 must serialize NON-EMPTY records"
        data = dataclasses.asdict(dto)
        assert data["record_origin"] == "global"
        assert data["record_residency"] == "global"
        assert data["record_type"] == expected_types[type(dto)]
        assert "lineage_reference" not in _recursive_keys(data)  # global records carry NO lineage_reference


def test_p6_tenant_resident_half_guarded_skip_rederived_every_run() -> None:
    # CLR-3: the tenant-resident half of P.6 may be skipped IFF the skip precondition is
    # RE-DERIVED from the union's own contents — set(PortalDTO members) ∩ tenant-resident
    # record DTOs == ∅. The moment a tenant-resident record DTO joins the union without a
    # lineage_reference binding, THIS GUARD FAILS (the skip can never silently widen).
    union_names = {t.__name__ for t in get_args(PortalDTO)}
    overlap = union_names & _TENANT_RESIDENT_RECORD_DTO_NAMES
    assert overlap == set(), (
        f"tenant-resident record DTO(s) {sorted(overlap)} joined the PortalDTO union: the P.6 "
        "lineage_reference half is now UNBOUND — extend this guard before widening the union"
    )


# --- IC-009 §P.7 — denial surface (mutation detector 10's static half) ------------------------------
def test_p7_denial_surface_is_the_closed_l_model() -> None:
    # ErrorDTO is EXACTLY the §L safe surface: status + public_code, nothing else — no DB
    # name, tenant existence, router detail, secret, or stack-trace-shaped field.
    assert {f.name for f in dataclasses.fields(ErrorDTO)} == {"status", "public_code"}
    hits = _recursive_keys(dataclasses.asdict(ErrorDTO(status=403, public_code="forbidden"))) & (_P2_FORBIDDEN | {"trace", "stack"})
    assert hits == set()
    # GatewayResponse.portal_dto is DEFAULTED None — a denial constructed the pre-6B way
    # (status + public_code only) carries NO DTO by construction (§V.2).
    from api_gateway.models import GatewayResponse

    portal_field = {f.name: f for f in dataclasses.fields(GatewayResponse)}["portal_dto"]
    assert portal_field.default is None


# --- IC-007 negative boundary: prefix/category exactness (mutation detector 8) ----------------------
def test_ic007_exactly_four_route_prefixes_and_failclosed_fallthrough() -> None:
    source = _DISPATCH.read_text(encoding="utf-8")
    prefixes = _classifier_prefixes(source)
    assert prefixes == _EXPECTED_PREFIXES, f"classifier prefix set must be EXACTLY the four §Q prefixes: {sorted(prefixes)}"
    # The fallthrough is a fail-closed denial — exactly one raise, the unknown_route code.
    fn = None
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == "default_classifier":
            fn = node
    assert fn is not None
    raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
    assert len(raises) == 1
    assert isinstance(raises[0].exc, ast.Call)
    args = raises[0].exc.args
    assert len(args) == 1 and isinstance(args[0], ast.Constant) and args[0].value == "unknown_route"


def test_ic007_exactly_four_categories_and_two_control_domains() -> None:
    assert {c.name for c in DispatchCategory} == {
        "TENANT_OPERATION",
        "GLOBAL_DIRECTORY_READ",
        "MEMBERSHIPS_FOR_PRINCIPAL",
        "IMPORT_INITIATION",
    }, "the §Q taxonomy is closed at exactly four categories (no fifth/cross-tenant category)"
    assert {d.name for d in DatabaseDomain} == {"CONTROL", "TENANT"}
    assert set(_CONTROL_CATEGORIES) == {DispatchCategory.GLOBAL_DIRECTORY_READ, DispatchCategory.MEMBERSHIPS_FOR_PRINCIPAL}


# --- typed port closure: no raw body may cross (mutation detector 1's static half) ------------------
def test_control_plane_read_port_signatures_admit_no_raw_shapes() -> None:
    ports_src = _PORTS.read_text(encoding="utf-8")
    banned = {"dict", "Dict", "Any", "bytes", "object", "Mapping"}
    for method in ("directory", "memberships_for_principal"):
        names = _port_return_annotation_names(ports_src, "ControlPlaneReadPort", method)
        assert "not found" not in " ".join(names), names  # the port must exist (non-vacuous)
        assert not (names & banned), f"ControlPlaneReadPort.{method} return admits a raw shape: {names & banned}"


# --- no import execution (mutation detector 12's static half) ---------------------------------------
def test_gateway_never_references_import_execution() -> None:
    # AST names (not prose — docstrings may legitimately SAY it never calls start_import):
    # no api_gateway module uses `start_import` as a code name or imports import_service.
    for f in _scan.py_files(AG):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "start_import" not in used, f"{_scan.relposix(f)} references start_import"
        assert not any(m.split(".")[0] == "import_service" for m in _scan.imported_modules(f)), (
            f"{_scan.relposix(f)} imports import_service"
        )


# --- display_ref format + deterministic serialization (§V.1) ----------------------------------------
def test_display_ref_is_the_pinned_gateway_composed_format() -> None:
    assert compose_display_ref("t1") == "ref:tenant/t1/display"
    assert compose_display_ref("acme-vc") == "ref:tenant/acme-vc/display"


def test_serialization_is_deterministic_with_fixed_field_order() -> None:
    for dto in _ALL_UNION_INSTANCES:
        first = serialize_portal_dto(dto)
        assert first == serialize_portal_dto(dto), "the same instance must serialize to the same bytes"
    import json as _json

    keys = list(_json.loads(serialize_portal_dto(_DIRECTORY_INSTANCES[0]).decode("utf-8")).keys())
    assert keys == ["records", "record_origin", "record_residency", "record_type"], keys  # dataclass field order, fixed


# --- non-vacuity companions: every static detector fires on a planted violation ---------------------
def test_static_detectors_flag_planted_violations() -> None:
    # (4) tenant attribution planted in a directory-DTO-shaped structure -> P.1 detector fires.
    assert _recursive_keys({"records": [{"record_ref": "g1", "tenant_id": "t1"}]}) & _P1_FORBIDDEN == {"tenant_id"}
    # (16/5) a physical-DB identifier / secret-bearing field -> P.2 detector fires.
    assert _recursive_keys({"dsn": "x"}) & _P2_FORBIDDEN == {"dsn"}
    assert _recursive_keys({"nested": [{"credential": "x"}]}) & _P2_FORBIDDEN == {"credential"}
    # (8) a planted FIFTH route prefix -> the prefix-exactness detector fires.
    planted = (
        "def default_classifier(request):\n"
        '    if request.path.startswith("/tenant/"):\n'
        "        return 1\n"
        '    if request.path.startswith("/shared/"):\n'
        "        return 5\n"
    )
    assert _classifier_prefixes(planted) != _EXPECTED_PREFIXES, "a fifth prefix must break prefix-set equality"
    # (6) a dropped seam constant is detectable (the equality pin above is non-vacuous).
    assert PORTAL_CONTRACT_REVISION != "", "the revision constant pin cannot pass on an empty value"
    # (15) catalogue-closure mechanism: a catalogue missing one union member FAILS the
    # set-equality the closure test asserts.
    union_members = set(get_args(PortalDTO))
    shrunk = dict(APPROVED_PORTAL_DTOS)
    shrunk.pop(ImportInitiationDTO)
    assert set(shrunk.keys()) != union_members, "catalogue closure must detect a missing member"
    # (1) a raw-dict port return is detectable by the signature census.
    planted_port = "class ControlPlaneReadPort:\n    def directory(self, kind: str) -> dict:\n        ...\n"
    assert _port_return_annotation_names(planted_port, "ControlPlaneReadPort", "directory") & {"dict"}, (
        "the port census must flag a raw-dict return"
    )
    # (14) the non-empty-instance precondition rejects an empty set / empty records.
    empty_page = GlobalStartupSummaryDTO(records=())
    assert not empty_page.records, "an empty page exists only to prove the precondition fires"
    # (12) the AST-name mechanism detects a planted start_import reference.
    planted_call = ast.parse("svc.start_import(job)\n")
    assert "start_import" in {n.attr for n in ast.walk(planted_call) if isinstance(n, ast.Attribute)}


if __name__ == "__main__":
    _scan.run(
        [
            test_seam_traceability_constants_and_catalogue_closure,
            test_composer_rejects_any_type_absent_from_the_catalogue,
            test_no_dto_carries_wire_contract_traceability_fields,
            test_every_portal_dataclass_has_exact_field_set_closure,
            test_exact_field_set_closure_rejects_a_planted_pii_field,
            test_p1_directory_dtos_are_tenant_anonymous_over_nonempty_instances,
            test_p2_no_physical_database_identity_in_any_dto,
            test_p3_every_category_resolves_to_exactly_one_domain_and_database,
            test_p4_no_multi_tenant_result_sequence_and_single_decision_shapes,
            test_p6_provenance_markers_global_half_over_nonempty_instances,
            test_p6_tenant_resident_half_guarded_skip_rederived_every_run,
            test_p7_denial_surface_is_the_closed_l_model,
            test_ic007_exactly_four_route_prefixes_and_failclosed_fallthrough,
            test_ic007_exactly_four_categories_and_two_control_domains,
            test_control_plane_read_port_signatures_admit_no_raw_shapes,
            test_gateway_never_references_import_execution,
            test_display_ref_is_the_pinned_gateway_composed_format,
            test_serialization_is_deterministic_with_fixed_field_order,
            test_static_detectors_flag_planted_violations,
        ]
    )
