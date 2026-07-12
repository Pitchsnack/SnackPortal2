"""Taxonomy-closure + emitter-ownership guard — PRD 05 (Inventory R2) + DBR-AR-2A.

Locks the D-34-R2 §6 operational/administrative audit taxonomy after the PRD 05
amendment (every audit class has a *landed* contractual home; the homing contracts are
exactly {IC-001, IC-002, IC-003, IC-005}; the amended contracts carry their section
headers; OP-1 supersession holds) AND, since DBR-AR-2A, the two-subclass emitter
ownership of IC-002 class 3: the gateway-edge subclass remains gateway-owned, the
router-edge routing-decision subclass is Database-Router-owned with the exact frozen
four-action set, the Auth Router is never an emitter of record, no event has more than
one emitter, and IC-002/IC-005 agree. Every detector carries a planted non-vacuity
companion. Pure stdlib; reads only contract markdown; imports no service package
(lint-imports clean); standalone-runnable:
  python tests/architecture/test_audit_class_homes.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

CONTRACTS = _scan.REPO_ROOT / "contracts"

# D-34-R2 §6 operational/administrative audit taxonomy (IC-001:84-90) mapped to its
# landed homing contract, including the classes the PRD 05 IC-002/IC-005 Audit-Section
# Extension homes (Administrative, tenant-scope Export, Runtime Operational) and the
# tenant-resident ownership-audit class carried from IC-008/D-36.
AUDIT_CLASS_HOMES = {
    "Administrative Audit": "IC-002",
    "Directory Audit": "IC-001",
    "Publication Audit": "IC-001",
    "Export Audit (global scope)": "IC-001",
    "Export Audit (tenant scope)": "IC-002",
    "Import Audit": "IC-003",
    "Runtime Operational Audit": "IC-005",
    "Tenant-resident Ownership Audit": "IC-002",
}

LANDED_CONTRACTS = {"IC-001", "IC-002", "IC-003", "IC-005"}

_CONTRACT_FILES = {
    "IC-001": "IC-001-Global-Startup-Contract.md",
    "IC-002": "IC-002-Tenant-Startup-Contract.md",
    "IC-003": "IC-003-Import-Contract.md",
    "IC-005": "IC-005-Authentication-Routing-Contract.md",
}

# --- DBR-AR-2A two-subclass emitter ownership (exact normalized anchors) -------------
# The frozen router-edge action set, pinned as the exact braced enumeration so that a
# removed action OR an inserted fifth action breaks the pin (mutations 5-9).
_ROUTER_ACTION_SET = "action ∈ {route, routecontrol, routedenied, isolationanomaly}"
_ROUTER_EDGE_HOME = "runtime operational audit — database router edge"
_ROUTER_SOLE_EMITTER = "the database router is the sole emitter"
_GATEWAY_SOLE_EMITTER_IC005 = "the gateway is the sole emitter of these gateway-edge events"
_GATEWAY_EDGE_UNCHANGED_IC002 = "the gateway-edge event set in (3) above is unchanged and remains gateway-owned"
_NO_MULTI_EMITTER = "no event is emitted by more than one component"
_DIFFERENT_SUBCLASSES = "different subclasses with different sole emitters"
_EVENT_IDENTITY = "event identity is (edge/subclass, action)"
_AUTH_DETECT_ONLY = "detection and signalling only"
_AUTH_NOT_OF_RECORD = "not an emitter of record"
_EXACTLY_ONE = "exactly one event per completed or denied route() invocation"
_EARLY_DENIALS = "including the pre-target denials tenant_routing_unavailable and no_active_tenant"
_RECORDED_AT_STORE_SIDE = "recorded_at is store-assigned at persistence time (a future durable-store field, never router-minted)"
_NO_DURABLE_2A = "dbr-ar-2a adds no durable persistence"

# Anchors that must appear in BOTH IC-002 and IC-005 (the "contracts agree" proof).
_AGREEMENT_ANCHORS = (
    _ROUTER_SOLE_EMITTER,
    _NO_MULTI_EMITTER,
    _DIFFERENT_SUBCLASSES,
    _EVENT_IDENTITY,
    _EXACTLY_ONE,
    _EARLY_DENIALS,
)

# Reserved forward action names — must not be adopted anywhere in the two contracts.
_UNAPPROVED_ACTIONS_RE = re.compile(r"\b(?:dispatchcompleted|dispatchfailed|auditsinkfailed)\b")

# Auth Router granted emission of record (negations masked first).
_AUTH_EMIT_NEGATIONS = (
    re.compile(r"\bdoes\s+not\s+itself\s+emit\b"),
    re.compile(r"\bdoes\s+not\s+become\s+the\s+emitter\s+of\s+record\b"),
    re.compile(r"\bnot\s+an\s+emitter\s+of\s+record\b"),
    re.compile(r"\bnever\s+emits?\b"),
    re.compile(r"\bdoes\s+not\s+emit\b"),
)
_AUTH_EMITS_RE = re.compile(
    r"\b(?:auth[ _-]?router|authentication\s+router)\b[^.;|]{0,80}?"
    r"(?:\bemits\b|\bmay\s+emit\b|\bshall\s+emit\b|\bis\s+allowed\s+to\s+emit\b"
    r"|\b(?:is|becomes|acts\s+as|shall\s+be|may\s+be)\b[^.;|]{0,40}?\bemitter\b)"
)

# Gateway granted the router-edge subclass (ordering-sensitive forms).
_GATEWAY_ROUTER_EDGE_RE = re.compile(
    r"\bgateway\b[^.;|]{0,50}?\bsole\s+emitter\b[^.;|]{0,50}?\brouter-edge\b"
    r"|\bgateway\b[^.;|]{0,40}?\bemits\b[^.;|]{0,40}?\brouter-edge\b"
    r"|\brouter-edge\b[^.;|]{0,60}?\bsole\s+emitter\b[^.;|]{0,40}?\bgateway\b"
    r"|\brouter-edge\b[^.;|]{0,60}?\bemitted\s+by\b[^.;|]{0,40}?\bgateway\b"
)


def _read(contract_id: str) -> str:
    path = CONTRACTS / _CONTRACT_FILES[contract_id]
    assert path.exists(), f"missing contract file for {contract_id}: {path}"
    return path.read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("*", "").replace("`", "").split())


def _mask_auth_negations(norm_text: str) -> str:
    masked = norm_text
    for negation in _AUTH_EMIT_NEGATIONS:
        masked = negation.sub(" <auth-negated> ", masked)
    return masked


def _auth_router_granted_emission(norm_text: str) -> bool:
    return bool(_AUTH_EMITS_RE.search(_mask_auth_negations(norm_text)))


# ---------------------------------------------------------------------------
# PRD 05 taxonomy closure (carried, unchanged semantics)
# ---------------------------------------------------------------------------
def test_no_audit_class_is_pending() -> None:
    for cls, home in AUDIT_CLASS_HOMES.items():
        assert home and home.upper() != "PENDING", f"audit class still pending a home: {cls!r}"


def test_homes_are_exactly_the_landed_set() -> None:
    assert set(AUDIT_CLASS_HOMES.values()) == LANDED_CONTRACTS, (
        f"audit-class homes {sorted(set(AUDIT_CLASS_HOMES.values()))} != landed set {sorted(LANDED_CONTRACTS)}"
    )


def test_amended_contracts_carry_new_sections() -> None:
    ic002 = _read("IC-002")
    ic005 = _read("IC-005")
    assert "## Audit-Section Extension" in ic002, "IC-002 missing the Audit-Section Extension header"
    assert "## Runtime Operational Audit Emission" in ic005, "IC-005 missing the Runtime Operational Audit Emission header"


def test_op1_supersession_landed() -> None:
    # OP-1 lock: the pre-amendment "auth_router"-emits acceptance wording must be gone,
    # replaced by the gateway sole-emitter reconciliation.
    ic005 = _read("IC-005")
    assert "small additive `auth_router` change" not in ic005, (
        "IC-005:116 still carries the superseded 'auth_router'-emits wording (OP-1 not applied)"
    )
    assert "sole single-edge emitter" in ic005, "IC-005 missing the gateway sole-emitter reconciliation (OP-1)"


# ---------------------------------------------------------------------------
# DBR-AR-2A: router-edge subclass is Database-Router-owned (mutations 1, 5-9)
# ---------------------------------------------------------------------------
def test_router_edge_subclass_homed_and_router_owned() -> None:
    ic002 = _norm(_read("IC-002"))
    ic005 = _norm(_read("IC-005"))
    assert _ROUTER_EDGE_HOME in ic002, "IC-002 must home the Database Router edge subclass inside class 3"
    assert _ROUTER_SOLE_EMITTER in ic002, "IC-002 must name the Database Router as the sole router-edge emitter"
    assert _ROUTER_SOLE_EMITTER in ic005, "IC-005 must name the Database Router as the sole router-edge emitter"


def test_router_edge_subclass_nonvacuity() -> None:
    ic002 = _norm(_read("IC-002"))
    for anchor in (_ROUTER_EDGE_HOME, _ROUTER_SOLE_EMITTER):
        assert anchor not in ic002.replace(anchor, ""), anchor


def test_exact_router_action_set_pinned() -> None:
    ic002 = _norm(_read("IC-002"))
    assert _ROUTER_ACTION_SET in ic002, "IC-002 must pin the exact frozen four-action router-edge set"
    assert not _UNAPPROVED_ACTIONS_RE.search(ic002), "a reserved forward action name must not be adopted in IC-002"
    assert not _UNAPPROVED_ACTIONS_RE.search(_norm(_read("IC-005"))), "a reserved forward action name must not be adopted in IC-005"


def test_exact_router_action_set_nonvacuity() -> None:
    ic002 = _norm(_read("IC-002"))
    assert _ROUTER_ACTION_SET not in ic002.replace(_ROUTER_ACTION_SET, "")
    # A removed action breaks the pin...
    assert _ROUTER_ACTION_SET not in _norm("action ∈ {route, routecontrol, isolationanomaly}")
    # ...and so does an inserted fifth action.
    assert _ROUTER_ACTION_SET not in _norm("action ∈ {route, routecontrol, routedenied, dispatchcompleted, isolationanomaly}")
    assert _UNAPPROVED_ACTIONS_RE.search(_norm("the router also emits `DispatchCompleted`"))
    assert _UNAPPROVED_ACTIONS_RE.search(_norm("a future AuditSinkFailed action"))
    assert not _UNAPPROVED_ACTIONS_RE.search(_norm("dispatch completion is a reserved forward consideration"))


# ---------------------------------------------------------------------------
# DBR-AR-2A: gateway-edge subclass remains gateway-owned (mutations 2, 4)
# ---------------------------------------------------------------------------
def test_gateway_edge_remains_gateway_owned() -> None:
    ic002 = _norm(_read("IC-002"))
    ic005 = _norm(_read("IC-005"))
    assert _GATEWAY_EDGE_UNCHANGED_IC002 in ic002, "IC-002 must state the gateway-edge set is unchanged and gateway-owned"
    assert _GATEWAY_SOLE_EMITTER_IC005 in ic005, "IC-005 must keep the gateway as sole emitter of the gateway-edge events"
    assert not _GATEWAY_ROUTER_EDGE_RE.search(ic002), "IC-002 must not grant the gateway the router-edge subclass"
    assert not _GATEWAY_ROUTER_EDGE_RE.search(ic005), "IC-005 must not grant the gateway the router-edge subclass"


def test_gateway_edge_ownership_nonvacuity() -> None:
    ic005 = _norm(_read("IC-005"))
    assert _GATEWAY_SOLE_EMITTER_IC005 not in ic005.replace(_GATEWAY_SOLE_EMITTER_IC005, "")
    assert _GATEWAY_EDGE_UNCHANGED_IC002 not in _norm(_read("IC-002")).replace(_GATEWAY_EDGE_UNCHANGED_IC002, "")
    assert _GATEWAY_ROUTER_EDGE_RE.search("the gateway is the sole emitter of the router-edge subclass")
    assert _GATEWAY_ROUTER_EDGE_RE.search("the gateway emits the router-edge routing-decision events")
    assert _GATEWAY_ROUTER_EDGE_RE.search("router-edge events may also be emitted by the gateway")
    legit = "the gateway-edge and router-edge sets are different subclasses with different sole emitters"
    assert not _GATEWAY_ROUTER_EDGE_RE.search(_norm(legit))


# ---------------------------------------------------------------------------
# DBR-AR-2A: Auth Router is never an emitter of record (mutation 3)
# ---------------------------------------------------------------------------
def test_auth_router_not_an_emitter_of_record() -> None:
    ic002 = _norm(_read("IC-002"))
    ic005 = _norm(_read("IC-005"))
    assert _AUTH_DETECT_ONLY in ic005, "IC-005 must keep the Auth Router detection/signalling-only role"
    assert _AUTH_NOT_OF_RECORD in ic002, "IC-002 must state the Auth Router is not an emitter of record"
    assert not _auth_router_granted_emission(ic002), "IC-002 must not grant the Auth Router class-3 emission of record"
    assert not _auth_router_granted_emission(ic005), "IC-005 must not grant the Auth Router class-3 emission of record"


def test_auth_router_detector_nonvacuity() -> None:
    assert _auth_router_granted_emission(_norm("the auth_router emits class-3 events of record"))
    assert _auth_router_granted_emission(_norm("the authentication router may emit RouteDenied"))
    assert _auth_router_granted_emission(_norm("the auth router becomes the class-3 emitter"))
    assert _auth_router_granted_emission(_norm("the auth router is authorized as an emitter"))
    assert not _auth_router_granted_emission(_norm("the auth_router detects and surfaces the condition but does not itself emit"))
    assert not _auth_router_granted_emission(_norm("the authentication router remains detection and signalling only"))
    assert not _auth_router_granted_emission(_norm("the auth router does not become the emitter of record for any class-3 event"))
    ic005 = _norm(_read("IC-005"))
    assert _AUTH_DETECT_ONLY not in ic005.replace(_AUTH_DETECT_ONLY, "")


# ---------------------------------------------------------------------------
# DBR-AR-2A: no multi-emitter events; IC-002 and IC-005 agree (mutations 1-4, 26-27)
# ---------------------------------------------------------------------------
def test_no_event_has_multiple_emitters_and_contracts_agree() -> None:
    ic002 = _norm(_read("IC-002"))
    ic005 = _norm(_read("IC-005"))
    for anchor in _AGREEMENT_ANCHORS:
        assert anchor in ic002, f"IC-002 missing the agreed anchor: {anchor!r}"
        assert anchor in ic005, f"IC-005 missing the agreed anchor: {anchor!r}"


def test_agreement_anchors_nonvacuity() -> None:
    ic002 = _norm(_read("IC-002"))
    for anchor in _AGREEMENT_ANCHORS:
        assert anchor not in ic002.replace(anchor, ""), anchor
    assert _EXACTLY_ONE not in _norm("zero or more events per completed or denied route() invocation")
    assert _EARLY_DENIALS not in _norm("the pre-target denials are not audited")


# ---------------------------------------------------------------------------
# DBR-AR-2A: recorded_at separation + no durable-persistence claim (mutations 16, 19)
# ---------------------------------------------------------------------------
def test_recorded_at_stays_store_assigned_and_no_durable_claim() -> None:
    ic002 = _norm(_read("IC-002"))
    assert _RECORDED_AT_STORE_SIDE in ic002, "IC-002 must keep recorded_at store-assigned (never router-minted)"
    assert _NO_DURABLE_2A in ic002, "IC-002 must state that DBR-AR-2A adds no durable persistence"


def test_recorded_at_separation_nonvacuity() -> None:
    ic002 = _norm(_read("IC-002"))
    assert _RECORDED_AT_STORE_SIDE not in ic002.replace(_RECORDED_AT_STORE_SIDE, "")
    assert _NO_DURABLE_2A not in ic002.replace(_NO_DURABLE_2A, "")
    assert _RECORDED_AT_STORE_SIDE not in _norm("recorded_at is a router-minted durable timestamp")


if __name__ == "__main__":
    _scan.run(
        [
            test_no_audit_class_is_pending,
            test_homes_are_exactly_the_landed_set,
            test_amended_contracts_carry_new_sections,
            test_op1_supersession_landed,
            test_router_edge_subclass_homed_and_router_owned,
            test_router_edge_subclass_nonvacuity,
            test_exact_router_action_set_pinned,
            test_exact_router_action_set_nonvacuity,
            test_gateway_edge_remains_gateway_owned,
            test_gateway_edge_ownership_nonvacuity,
            test_auth_router_not_an_emitter_of_record,
            test_auth_router_detector_nonvacuity,
            test_no_event_has_multiple_emitters_and_contracts_agree,
            test_agreement_anchors_nonvacuity,
            test_recorded_at_stays_store_assigned_and_no_durable_claim,
            test_recorded_at_separation_nonvacuity,
        ]
    )
