"""IC-010 §V Response Composition amendment pin — PRD B5-BLK-6A (Dan-authorized, 2026-07-17).

Mechanically pins the contract-only B5-BLK-6A amendment so the distinction it draws cannot
drift or be silently weakened by a later slice:

    ARBITRARY DOWNSTREAM BODY PASS-THROUGH — FORBIDDEN      (retained in full)
    GATEWAY-COMPOSED, CONTRACT-APPROVED DTO RESPONSE — PERMITTED   (new, conditional)

The guard reads only markdown (`contracts/IC-010-API-Gateway-Contract.md` and
`docs/Architecture-Decision-Register.md`), imports no service package (lint-imports clean),
and pins **no line numbers**: every anchor is matched against markdown-normalized text taken
from a *structurally extracted* section (heading → next heading of the same level), so the
pins survive reflow, re-wrapping, and emphasis changes.

Non-vacuity is proven two ways, both in-memory (no file is ever mutated):
  * every required anchor has a planted-removal companion — deleting the anchor must make the
    detector report it missing;
  * six planted negative probes prove the forbidden-authorization detector rejects an
    amendment that authorizes pass-through, raw DB rows, secret-bearing DTOs, cross-tenant
    fan-out, a B5-BLK-6 closure claim, or a production-ready claim.

This guard closes no blocker. B5-BLK-6 remains OPEN; B5-BLK-5 remains OPEN; production
remains NOT READY / DO-NOT-ACTIVATE. Pure stdlib; standalone-runnable:
  python tests/architecture/test_ic010_response_composition_contract.py
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Callable, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

# --- Pin 1: the exact governing files (no line numbers, exact paths) ---------------------------
_CONTRACT = _scan.REPO_ROOT / "contracts" / "IC-010-API-Gateway-Contract.md"
_ADR = _scan.REPO_ROOT / "docs" / "Architecture-Decision-Register.md"

_V_HEADING = "## Response Composition Contract (§V"
_ADR_HEADING = "### B5-BLK-6A — IC-010 §V Response Composition Amendment"


def _read(path: pathlib.Path) -> str:
    assert path.is_file(), f"governing source missing: {path}"
    return path.read_text(encoding="utf-8")


def _norm(text: str) -> str:
    """Markdown-normalise: drop emphasis/backticks, lower-case, collapse whitespace."""
    return " ".join(text.lower().replace("*", "").replace("`", "").split())


def _section(md: str, heading_start: str, level: str) -> str:
    """Structural extraction: the heading line through to the next heading of the same level."""
    lines = md.split("\n")
    start = -1
    for i, line in enumerate(lines):
        if line.startswith(level) and line.startswith(heading_start):
            start = i
            break
    assert start >= 0, f"section heading not found: {heading_start!r}"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith(level):
            end = j
            break
    return "\n".join(lines[start:end])


def _v_section() -> str:
    return _section(_read(_CONTRACT), _V_HEADING, "## ")


def _adr_section() -> str:
    return _section(_read(_ADR), _ADR_HEADING, "### ")


def _missing(norm_text: str, anchors: Tuple[str, ...]) -> List[str]:
    """The detector: which required anchors are absent from the normalized section text."""
    return [a for a in anchors if a not in norm_text]


# --- Required anchors, grouped by the pin they serve -------------------------------------------
_A_EXISTENCE: Tuple[str, ...] = (
    "response composition contract (§v",
    "prd b5-blk-6a",
)
_A_PERMITTED_PHRASE: Tuple[str, ...] = (
    "gateway-composed, contract-approved dto response — permitted",
    "the gateway may compose and return a gateway-composed, contract-approved dto response, and only when all of the following hold",
)
_A_PASS_THROUGH_FORBIDDEN: Tuple[str, ...] = (
    "arbitrary downstream body pass-through — forbidden",
    "this prohibition is retained in full and is not weakened by §v.1",
    "relay an arbitrary backend body",
    "relay raw bytes, a byte stream, or an unapproved dictionary",
)
_A_ADOPTED_CONTRACT: Tuple[str, ...] = (
    "the dto must be defined by an adopted interface contract",
    "the gateway must not compose or return a dto that no adopted interface contract defines",
    "composition is gateway-owned and typed",
    "the gateway may consume typed results from injected ports as composition inputs",
)
_A_DETERMINISTIC: Tuple[str, ...] = (
    "serialization must be deterministic",
    "the same dto instance serializes to the same bytes",
)
_A_TRACEABILITY: Tuple[str, ...] = (
    "every composed response must carry contract and revision traceability",
    "the composing seam names the interface contract and the revision it serves",
    "ic-009-r1",
)
_A_DENIAL_PRESERVED: Tuple[str, ...] = (
    "denial and error semantics unchanged",
    "no new public_code is introduced by composition",
    "denial precedes data",
    "on any denial, the gateway returns the §l denial and no dto",
)
_A_NO_RAW_ROW: Tuple[str, ...] = ("expose a database row directly",)
_A_NO_SECRETS: Tuple[str, ...] = (
    "expose secrets, credentials, dsns, tokens, or authorization payloads",
    "expose raw exceptions, stack traces, sql, internal hostnames, or physical database identity",
)
_A_TENANT_ANONYMOUS: Tuple[str, ...] = (
    "expose tenant attribution in global-directory dtos",
    "directory dtos remain tenant-anonymous",
    "must expose only approved references",
)
_A_NO_AGGREGATION: Tuple[str, ...] = (
    "aggregate multiple tenant-database results",
    "no database is selected by the response composer",
    "one request → one approved operation → one database",
)
_A_ROUTEOUTCOME: Tuple[str, ...] = (
    "weaken routeoutcome into a business-payload carrier",
    "routeoutcome remains references-only and carries no business payload",
)
_A_IC009_OWNERSHIP: Tuple[str, ...] = (
    "ic-009-r1 owns the approved portal dto catalogue and portal visibility rules",
    "ic-010 §v owns the gateway's permission and mechanics for composing those dtos",
    "does not itself implement dtos, ports, handlers, transports, or serving edges",
)
_A_IC007_DEFERRAL: Tuple[str, ...] = (
    "ic-007 remains a deferral boundary only",
    "no positive cross-tenant capability, route, fan-out, workflow, or dto",
    "positive ic-007 design remains separately governed",
)
_A_NON_OVERCLAIM: Tuple[str, ...] = (
    "implement runtime response composition",
    "create a northbound http ingress",
    "connect lovable or authorize the lovable cutover",
    "provision infrastructure",
    "access production",
    "change any activation blocker",
    "or authorize activation",
)
_A_BLK6_OPEN: Tuple[str, ...] = ("b5-blk-6 remains open",)
_A_BLK5_OPEN: Tuple[str, ...] = ("b5-blk-5 remains open",)
_A_PRODUCTION: Tuple[str, ...] = ("production remains not ready / do-not-activate",)

_V_REQUIRED: Tuple[str, ...] = (
    _A_EXISTENCE
    + _A_PERMITTED_PHRASE
    + _A_PASS_THROUGH_FORBIDDEN
    + _A_ADOPTED_CONTRACT
    + _A_DETERMINISTIC
    + _A_TRACEABILITY
    + _A_DENIAL_PRESERVED
    + _A_NO_RAW_ROW
    + _A_NO_SECRETS
    + _A_TENANT_ANONYMOUS
    + _A_NO_AGGREGATION
    + _A_ROUTEOUTCOME
    + _A_IC009_OWNERSHIP
    + _A_IC007_DEFERRAL
    + _A_NON_OVERCLAIM
    + _A_BLK6_OPEN
    + _A_BLK5_OPEN
    + _A_PRODUCTION
)

# --- ADR anchors: the entry + the four locked scope decisions ----------------------------------
_ADR_SCOPE_DECISIONS: Tuple[str, ...] = (
    "ic-007 is deferral-bound only",
    "import initiation means accepted-initiation envelope only",
    "the global deal directory is excluded from this arc",
    "workspacemembershipdto.display_ref is a deterministic gateway-composed reference",
    "ref:tenant/<tenant_id>/display",
)
_ADR_REQUIRED: Tuple[str, ...] = _ADR_SCOPE_DECISIONS + (
    "b5-blk-6a — ic-010 §v response composition amendment",
    "arbitrary downstream body pass-through — forbidden (retained in full)",
    "gateway-composed, contract-approved dto response — permitted in principle",
    "runtime implementation remains pending b5-blk-6b",
    "proof and blocker closure remain pending b5-blk-6c — only b5-blk-6c may close b5-blk-6",
    "dan-authorized",
    "b5-blk-6 remains open",
    "b5-blk-5 remains open",
    "production remains not ready / do-not-activate",
)

# --- The forbidden-authorization detector (planted-probe target) -------------------------------
# Each pattern matches only an AFFIRMATIVE authorization. The live amendment states every one of
# these as a prohibition ("MUST NOT relay an arbitrary backend body", "close B5-BLK-6" inside a
# "does not:" list, "remains NOT READY"), so none of them may match the real text.
_FORBIDDEN_AUTHORIZATIONS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (
        "arbitrary pass-through authorization",
        re.compile(
            r"arbitrary downstream body pass-through — permitted"
            r"|may relay an arbitrary backend body"
            r"|arbitrary backend body is permitted"
        ),
    ),
    (
        "raw database-row authorization",
        re.compile(r"may expose a database row|may serialize a database row|database rows are permitted"),
    ),
    (
        "secret-bearing DTO authorization",
        re.compile(r"may expose secrets|may (return|carry) (secrets|credentials|dsns|tokens)|secrets are permitted in"),
    ),
    (
        "cross-tenant fan-out authorization",
        re.compile(
            r"may aggregate multiple tenant-database results"
            r"|cross-tenant fan-out is (permitted|authorized)"
            r"|may fan out across tenants"
        ),
    ),
    (
        "B5-BLK-6 closure claim",
        re.compile(r"b5-blk-6 is closed|closes b5-blk-6|b5-blk-6 — closed"),
    ),
    (
        "production-ready claim",
        re.compile(
            r"production is ready"
            r"|production remains ready"
            r"|production — ready"
            r"|ready to activate"
            r"|this amendment authorizes activation"
        ),
    ),
)


def _forbidden_hits(norm_text: str) -> List[str]:
    return [name for name, rx in _FORBIDDEN_AUTHORIZATIONS if rx.search(norm_text)]


# The six planted negative probes required by the B5-BLK-6A START-GATE §8.
_PROBES: Tuple[Tuple[str, str], ...] = (
    ("arbitrary pass-through authorization", "The gateway MAY relay an arbitrary backend body to the client."),
    ("raw database-row authorization", "The gateway MAY expose a database row directly in a composed response."),
    ("secret-bearing DTO authorization", "A composed DTO MAY carry secrets, credentials, DSNs, tokens as needed."),
    (
        "cross-tenant fan-out authorization",
        "The gateway MAY aggregate multiple tenant-database results; cross-tenant fan-out is permitted.",
    ),
    ("B5-BLK-6 closure claim", "This amendment closes B5-BLK-6."),
    ("production-ready claim", "Production is ready; this amendment authorizes activation."),
)


# --- Pin 1: locate the exact IC-010 file -------------------------------------------------------
def test_pin01_governing_files_located_exactly() -> None:
    assert _CONTRACT.is_file(), f"IC-010 must exist at exactly {_CONTRACT}"
    assert _ADR.is_file(), f"the decision register must exist at exactly {_ADR}"
    assert _CONTRACT.name == "IC-010-API-Gateway-Contract.md"
    head = _norm(_read(_CONTRACT)[:400])
    assert "ic-010 — api gateway contract" in head, "the located file must be IC-010 itself"


# --- Pin 2: §V exists (structurally, not by line number) ---------------------------------------
def test_pin02_section_v_exists() -> None:
    section = _v_section()
    assert section.startswith("## Response Composition Contract (§V"), section[:80]
    assert _missing(_norm(section), _A_EXISTENCE) == []
    body = section.split("\n", 1)[1]
    assert len(body.strip()) > 500, "§V must be a normative section, not a stub"


def test_pin02_section_v_letter_is_unclaimed_elsewhere() -> None:
    """§V must be the only section carrying the letter V (no collision with A-U/W/X)."""
    headings = [ln for ln in _read(_CONTRACT).split("\n") if ln.startswith("## ")]
    v_headings = [h for h in headings if "(§V" in h]
    assert len(v_headings) == 1, f"exactly one §V section expected, found {v_headings}"


# --- Pins 3-16: the normative content anchors --------------------------------------------------
def test_pin03_permitted_composed_response_phrase() -> None:
    assert _missing(_norm(_v_section()), _A_PERMITTED_PHRASE) == []


def test_pin04_arbitrary_pass_through_prohibition() -> None:
    assert _missing(_norm(_v_section()), _A_PASS_THROUGH_FORBIDDEN) == []


def test_pin05_adopted_contract_requirement() -> None:
    assert _missing(_norm(_v_section()), _A_ADOPTED_CONTRACT) == []


def test_pin06_deterministic_serialization() -> None:
    assert _missing(_norm(_v_section()), _A_DETERMINISTIC) == []


def test_pin07_contract_revision_traceability() -> None:
    assert _missing(_norm(_v_section()), _A_TRACEABILITY) == []


def test_pin08_denial_preservation() -> None:
    assert _missing(_norm(_v_section()), _A_DENIAL_PRESERVED) == []


def test_pin09_no_raw_database_row() -> None:
    assert _missing(_norm(_v_section()), _A_NO_RAW_ROW) == []


def test_pin10_no_secrets_dsns_tokens() -> None:
    assert _missing(_norm(_v_section()), _A_NO_SECRETS) == []


def test_pin11_no_tenant_attribution_in_directory_dtos() -> None:
    assert _missing(_norm(_v_section()), _A_TENANT_ANONYMOUS) == []


def test_pin12_no_multi_tenant_aggregation() -> None:
    assert _missing(_norm(_v_section()), _A_NO_AGGREGATION) == []


def test_pin13_routeoutcome_remains_references_only() -> None:
    assert _missing(_norm(_v_section()), _A_ROUTEOUTCOME) == []


def test_pin14_ic009_r1_owns_the_dto_catalogue() -> None:
    assert _missing(_norm(_v_section()), _A_IC009_OWNERSHIP) == []


def test_pin15_ic007_deferral_only() -> None:
    assert _missing(_norm(_v_section()), _A_IC007_DEFERRAL) == []


def test_pin16_non_overclaim_statements() -> None:
    assert _missing(_norm(_v_section()), _A_NON_OVERCLAIM) == []


# --- Pin 17: the ADR entry and all four scope decisions ----------------------------------------
def test_pin17_adr_entry_and_four_scope_decisions() -> None:
    adr = _norm(_adr_section())
    assert _missing(adr, _ADR_REQUIRED) == []
    for decision in _ADR_SCOPE_DECISIONS:
        assert decision in adr, f"the ADR entry must record the locked scope decision: {decision!r}"


def test_pin17_adr_edit_is_additive_only_for_dec11() -> None:
    """CLR-1: the ADR carries stale DEC-11 'pending' prose that this slice must NOT reconcile."""
    adr = _read(_ADR)
    stale = "the stale DEC-11 prose must remain byte-untouched (separately governed)"
    assert "ownership-audit extension pending — DEC-11" in adr, stale
    assert "IC-002 (ownership-audit extension — pending, DEC-11)" in adr, stale


# --- Pins 18-20: the state this amendment must NOT change --------------------------------------
def test_pin18_b5_blk6_remains_open() -> None:
    assert _missing(_norm(_v_section()), _A_BLK6_OPEN) == []
    assert _missing(_norm(_adr_section()), ("b5-blk-6 remains open",)) == []


def test_pin19_b5_blk5_remains_open() -> None:
    assert _missing(_norm(_v_section()), _A_BLK5_OPEN) == []
    assert _missing(_norm(_adr_section()), ("b5-blk-5 remains open",)) == []


def test_pin20_production_remains_not_ready() -> None:
    assert _missing(_norm(_v_section()), _A_PRODUCTION) == []
    assert _missing(_norm(_adr_section()), ("production remains not ready / do-not-activate",)) == []


# --- The two pre-existing pass-through notes must point to §V and keep their prohibition -------
def test_existing_notes_point_to_v_and_keep_their_prohibition() -> None:
    contract = _norm(_read(_CONTRACT))
    # historic prohibitions retained verbatim
    assert "full response-body pass-through is not approved" in contract, "the 07E-2-C prohibition must survive"
    assert "full response-body or business-payload pass-through remains not approved" in contract, "the D-15-T1a prohibition must survive"
    # both notes now name §V, and say so consistently
    assert contract.count("prd b5-blk-6a") >= 3, "§V plus both amended notes must cite PRD B5-BLK-6A"
    assert "the separate ic-010 amendment this note requires is now §v — response composition contract" in contract
    assert "the separate ic-010 normative amendment this capture requires is now §v — response composition contract" in contract
    assert "the two notes remain mutually consistent" in contract
    # the D-15-T1a wire contract is untouched by the amendment
    assert "the router still returns no body" in contract
    assert "dispatchdecision is still not serialized on the wire" in contract


# --- Non-vacuity: planted removal of every required anchor -------------------------------------
def test_nonvacuity_every_v_anchor_is_load_bearing() -> None:
    live = _norm(_v_section())
    assert _missing(live, _V_REQUIRED) == [], "control must be green before planting"
    for anchor in _V_REQUIRED:
        planted = live.replace(anchor, "")
        assert anchor in _missing(planted, _V_REQUIRED), f"detector did not fire when {anchor!r} was removed"
    assert _missing(_norm(_v_section()), _V_REQUIRED) == [], "control must remain green after planting (in-memory only)"


def test_nonvacuity_every_adr_anchor_is_load_bearing() -> None:
    live = _norm(_adr_section())
    assert _missing(live, _ADR_REQUIRED) == [], "control must be green before planting"
    for anchor in _ADR_REQUIRED:
        planted = live.replace(anchor, "")
        assert anchor in _missing(planted, _ADR_REQUIRED), f"detector did not fire when {anchor!r} was removed"


# --- The six planted negative probes ------------------------------------------------------------
def test_live_amendment_authorizes_nothing_forbidden() -> None:
    """Green control: the real §V + ADR entry trip none of the six forbidden-authorization detectors."""
    for name, text in (("§V", _v_section()), ("ADR entry", _adr_section())):
        hits = _forbidden_hits(_norm(text))
        assert hits == [], f"{name} must not authorize: {hits}"


def test_planted_probes_are_each_rejected() -> None:
    """Each of the six required probes must fail under the detector, by name."""
    base = _v_section()
    assert _forbidden_hits(_norm(base)) == [], "control must be green before planting"
    for expected, injected in _PROBES:
        planted = _norm(base + "\n" + injected)
        hits = _forbidden_hits(planted)
        assert expected in hits, f"probe not rejected: {expected!r} (injected {injected!r}; hits={hits})"
    assert _forbidden_hits(_norm(_v_section())) == [], "control must remain green after planting (in-memory only)"


def test_probe_set_covers_the_six_required_categories() -> None:
    assert len(_PROBES) == 6, "the START-GATE requires at least six planted negative probes"
    assert {name for name, _ in _PROBES} == {name for name, _ in _FORBIDDEN_AUTHORIZATIONS}, "every detector must carry a probe"


# ================================================================================================
# B5-BLK-6C-A — Audit Obligation Reconciliation (Dan-authorized Option A, 2026-07-17)
#
# Pins the four governed documents of the 6C-A amendment: IC-002, IC-005, IC-010, and the
# Architecture Decision Register. Option A: the MembershipsForPrincipal success audit is
# MANDATED (exactly one references-only `workspace_memberships_read` event per successful
# self-scoped enumeration, empty enumerations included; API Gateway emitter; Control-DB
# operational audit home; separate success-access subclass — the four denial/anomaly classes
# unchanged), and per-read Global Directory access audit is RESERVED. 6C-A adds no runtime
# implementation and closes no blocker; runtime binding follows in B5-BLK-6C-B.
# ================================================================================================
_IC002 = _scan.REPO_ROOT / "contracts" / "IC-002-Tenant-Startup-Contract.md"
_IC005 = _scan.REPO_ROOT / "contracts" / "IC-005-Authentication-Routing-Contract.md"

_ADR_6CA_HEADING = "### B5-BLK-6C-A — Audit Obligation Reconciliation"
_IC002_AUDIT_REQ_HEADING = "## Audit Requirements"
_IC002_AUDIT_EXT_HEADING = "## Audit-Section Extension"
_IC005_EMISSION_HEADING = "## Runtime Operational Audit Emission"
_J_HEADING = "## Audit Contract (§J"
_Q_HEADING = "## Endpoint Dispatch Taxonomy (§Q"
_R_HEADING = "## Internal-Surface Protection (§R"


def _nonempty_section(md: str, heading_start: str, level: str, min_body: int = 200) -> str:
    """Structural extraction that REFUSES an empty/stub section (a pair of empty sections must never match)."""
    section = _section(md, heading_start, level)
    body = section.split("\n", 1)[1] if "\n" in section else ""
    assert len(body.strip()) >= min_body, f"extracted section is empty or a stub: {heading_start!r}"
    return section


def _ic002_audit_requirements() -> str:
    return _nonempty_section(_read(_IC002), _IC002_AUDIT_REQ_HEADING, "## ")


def _ic002_audit_extension() -> str:
    return _nonempty_section(_read(_IC002), _IC002_AUDIT_EXT_HEADING, "## ")


def _ic005_emission() -> str:
    return _nonempty_section(_read(_IC005), _IC005_EMISSION_HEADING, "## ")


def _j_section() -> str:
    return _nonempty_section(_read(_CONTRACT), _J_HEADING, "## ")


def _q_section() -> str:
    return _nonempty_section(_read(_CONTRACT), _Q_HEADING, "## ")


def _r_section() -> str:
    return _nonempty_section(_read(_CONTRACT), _R_HEADING, "## ")


def _adr_6ca_section() -> str:
    return _nonempty_section(_read(_ADR), _ADR_6CA_HEADING, "### ")


# --- The canonical Option A anchors (normalized), shared verbatim across the three contracts ----
_6CA_MANDATE: Tuple[str, ...] = (
    "a successful self-scoped membershipsforprincipal enumeration must emit exactly one "
    'references-only operational audit event with action == "workspace_memberships_read"',
    "a successful empty enumeration is still a successful enumeration and must emit the event",
    "never zero events, never two, never one event per returned membership record, never one event per tenant",
    "the audit records the operation, not the number or contents of returned memberships",
)
_6CA_EMITTER: Tuple[str, ...] = (
    "the api gateway is the emitter",
    "sole emitter of this success event",
)
_6CA_HOME: Tuple[str, ...] = (
    "the event resides in control-db operational audit",
    "separate success-access subclass",
)
_6CA_SHAPE: Tuple[str, ...] = (
    "audit_id, action, actor_principal_ref, subject_principal_ref, correlation_id, occurred_at, outcome, event_version",
    'action == "workspace_memberships_read"',
    'outcome == "success"',
    "event_version == 1",
    "for the currently bound self-scoped operation, actor_principal_ref == subject_principal_ref",
)
_6CA_SEPARATION: Tuple[str, ...] = (
    "the four gateway-edge denial/anomaly classes remain exactly the historic four — "
    "routedenied, carriermismatch, carrieroncontrolanomaly, isolationanomaly — unchanged",
    "must not be relabelled or classified as a denial, anomaly, or routing event",
)
_6CA_ROWS_PROHIBITED: Tuple[str, ...] = (
    "the event must not contain the returned tenant-membership collection",
    "raw membership rows",
)
_6CA_NON_EMISSION: Tuple[str, ...] = ("does not emit this success event",)
_6CA_RUNTIME_PENDING: Tuple[str, ...] = (
    "b5-blk-6c-a authorizes and defines the later b5-blk-6c-b runtime implementation",
    "does not itself implement or prove runtime emission",
    "not yet emitted by the current runtime",
)
_6CA_CONTRACT_COMMON: Tuple[str, ...] = (
    _6CA_MANDATE + _6CA_EMITTER + _6CA_HOME + _6CA_SHAPE + _6CA_SEPARATION + _6CA_ROWS_PROHIBITED + _6CA_NON_EMISSION + _6CA_RUNTIME_PENDING
)

# The pre-6C-A IC-002:165 MUST, preserved verbatim, plus its new homing pointer.
_6CA_IC002_MUST: Tuple[str, ...] = (
    "membershipsforprincipal calls must be audited (actor, subject principal reference, timestamp, correlation id — references only)",
    "homed 2026-07-17 under b5-blk-6c-a",
)

# §Q must point at the mandated event; the CONTROL-on-behalf form stays unbound; taxonomy intact.
_6CA_Q: Tuple[str, ...] = (
    "must emit exactly one workspace_memberships_read success-access event (§j; b5-blk-6c-a), including a successful empty enumeration",
    "membership records only (tenant id, role, display ref), never tenant-db data",
    "is not runtime-bound by b5-blk-6b and is not implemented by b5-blk-6c-a",
    "dispatched to exactly one category",
    "one request → one category → one database",
)

# Option A directory-read reservation — required in IC-005 AND in IC-010 §R (the reconciliation).
_6CA_RESERVED: Tuple[str, ...] = (
    "per-read global directory access audit is reserved",
    "it is not required by b5-blk-6",
    "it is not emitted by the current runtime",
    "it may be elected only through a later governed contract decision",
    "startup directory read",
    "investor directory read",
    "reaches directory reads only",
    "does not shelter or reach membershipsforprincipal",
    "does not authorize or imply global deal directory support",
)
_6CA_R_RETAINED: Tuple[str, ...] = (
    "must add ic-005 authentication at the edge",
    "the internal read path is never offered raw to a client",
    "internal read apis must never be directly client-reachable",
)

# The historic §J four-event emit sentence, pinned in full — inserting a fifth event breaks it.
_J_HISTORIC_EMIT = (
    "the gateway emits these audit events where applicable: carriermismatch (403 carrier/claim mismatch), "
    "carrieroncontrolanomaly (recognized tenant carrier on a tenantless control token — mandatory per d-33-e1 item 1), "
    "routedenied (authorization/readiness denial at dispatch), and isolationanomaly "
    "(any detected attempt to cross the one-database boundary)"
)
# The IC-002 class-3 gateway-edge braced action set — exactly once, exactly four members.
_IC002_GATEWAY_EDGE_SET = "action ∈ {routedenied, carriermismatch, carrieroncontrolanomaly, isolationanomaly}"

_ADR_6CA_REQUIRED: Tuple[str, ...] = (
    "b5-blk-6c-a — audit obligation reconciliation (option a)",
    "dan selected option a",
    "decide b5-blk-6c-a option a",
    "the membershipsforprincipal success audit is mandated",
    "global directory per-read audit is reserved",
    "workspace_memberships_read is the action label",
    "the api gateway is the emitter",
    "control-db operational audit is the event home",
    "6c-b runtime work remains pending",
    "b5-blk-6c-a closes no blocker",
    "b5-blk-6c-a authorizes and defines the later b5-blk-6c-b runtime implementation",
    "does not itself implement or prove runtime emission",
    "§v response-composition rules unchanged",
    "b5-blk-6 remains open",
    "b5-blk-5 remains open",
    "eight of nine blockers remain open",
    "production remains not ready / do-not-activate",
)

# --- 6C-A forbidden-authorization detectors (each matches only an AFFIRMATIVE violation) --------
_FORBIDDEN_6CA: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (
        "memberships-audit reservation claim",
        re.compile(r"membershipsforprincipal (?:success )?audit (?:is|remains) ?reserved|reserves? the membershipsforprincipal audit"),
    ),
    (
        "memberships-audit weakening to may",
        re.compile(
            r"membershipsforprincipal (?:calls|enumerations?) may be audited"
            r"|memberships(?:forprincipal)? success audit is optional"
        ),
    ),
    (
        "raw membership-row authorization",
        re.compile(
            r"may (?:carry|contain|include) raw membership rows"
            r"|raw membership rows are permitted"
            r"|may contain the returned tenant-membership collection"
        ),
    ),
    (
        "per-membership fan-out emission",
        re.compile(
            r"one event per returned membership record (?:is|may be) emitted"
            r"|emits? one event per membership (?:row|record)"
            r"|one event per tenant (?:is|may be) emitted"
        ),
    ),
    (
        "per-read directory-audit mandate claim",
        re.compile(
            r"per-read (?:global )?directory (?:access )?audit is (?:mandated|mandatory|required)"
            r"|each directory read must emit"
            r"|directory reads? must (?:add|emit) a? ?(?:reference-only )?(?:per-read )?access audit"
        ),
    ),
    (
        "directory-audit already-implemented claim",
        re.compile(
            r"directory[- ]read (?:access )?audit is (?:already |currently )?(?:implemented|emitted)"
            r"|per-read (?:access )?audit is emitted by the current runtime"
        ),
    ),
    (
        "memberships-emission already-implemented claim",
        re.compile(
            r"workspace_memberships_read (?:event )?is (?:already |currently |now )?(?:implemented|emitted)"
            r"|the success event is already emitted"
            r"|memberships[^.;|]{0,50}runtime emission (?:is|has been) (?:implemented|landed|proven)"
        ),
    ),
)


def _forbidden_hits_6ca(norm_text: str) -> List[str]:
    hits = [name for name, rx in _FORBIDDEN_AUTHORIZATIONS if rx.search(norm_text)]
    hits += [name for name, rx in _FORBIDDEN_6CA if rx.search(norm_text)]
    return hits


_PROBES_6CA: Tuple[Tuple[str, str], ...] = (
    ("memberships-audit reservation claim", "The MembershipsForPrincipal audit is Reserved and no longer mandated."),
    ("memberships-audit weakening to may", "MembershipsForPrincipal calls MAY be audited at the gateway's discretion."),
    ("raw membership-row authorization", "The success event MAY contain the returned tenant-membership collection."),
    ("per-membership fan-out emission", "The gateway emits one event per membership record."),
    ("per-read directory-audit mandate claim", "Per-read Global Directory access audit is mandated for every read."),
    ("directory-audit already-implemented claim", "The directory-read access audit is already implemented at the edge."),
    ("memberships-emission already-implemented claim", "The workspace_memberships_read event is already emitted by the gateway."),
)

# Every 6C-A-governed section, by name, for the forbidden-authorization sweep.
_6CA_SECTIONS: Tuple[Tuple[str, Callable[[], str]], ...] = (
    ("IC-002 Audit Requirements", _ic002_audit_requirements),
    ("IC-002 Audit-Section Extension", _ic002_audit_extension),
    ("IC-005 Runtime Operational Audit Emission", _ic005_emission),
    ("IC-010 §J", _j_section),
    ("IC-010 §Q", _q_section),
    ("IC-010 §R", _r_section),
    ("IC-010 §V", _v_section),
    ("ADR B5-BLK-6C-A entry", _adr_6ca_section),
)


def test_6ca_governing_documents_present_and_sections_nonempty() -> None:
    """All four governed documents must open, and every selected section must be non-empty."""
    for path in (_CONTRACT, _ADR, _IC002, _IC005):
        assert path.is_file(), f"governed document missing: {path}"
    for name, section_fn in _6CA_SECTIONS:
        assert len(_norm(section_fn())) > 200, f"{name} must be non-empty"


def test_6ca_ic002_must_preserved_and_homed() -> None:
    assert _missing(_norm(_ic002_audit_requirements()), _6CA_IC002_MUST) == []


def test_6ca_mandate_emitter_home_shape_in_all_three_contracts() -> None:
    for name, section_fn in (
        ("IC-002 Audit-Section Extension", _ic002_audit_extension),
        ("IC-005 Runtime Operational Audit Emission", _ic005_emission),
        ("IC-010 §J", _j_section),
    ):
        missing = _missing(_norm(section_fn()), _6CA_CONTRACT_COMMON)
        assert missing == [], f"{name} is missing Option A anchors: {missing}"


def test_6ca_separation_from_the_historic_four_denial_anomaly_classes() -> None:
    assert _J_HISTORIC_EMIT in _norm(_j_section()), "the historic four-event §J emit sentence must survive verbatim"
    ic002 = _norm(_read(_IC002))
    assert ic002.count(_IC002_GATEWAY_EDGE_SET) == 1, "the IC-002 class-3 gateway-edge action set must stay exactly the frozen four"
    assert "workspace_memberships_read" not in _IC002_GATEWAY_EDGE_SET


def test_6ca_q_section_points_to_the_mandated_event() -> None:
    assert _missing(_norm(_q_section()), _6CA_Q) == []


def test_6ca_directory_read_audit_reserved_in_ic005_and_r() -> None:
    for name, section_fn in (("IC-005", _ic005_emission), ("IC-010 §R", _r_section)):
        missing = _missing(_norm(section_fn()), _6CA_RESERVED)
        assert missing == [], f"{name} is missing the Reserved directory-read anchors: {missing}"
    assert _missing(_norm(_r_section()), _6CA_R_RETAINED) == []


def test_6ca_adr_entry_records_option_a() -> None:
    assert _missing(_norm(_adr_6ca_section()), _ADR_6CA_REQUIRED) == []


def test_6ca_adr_record_begins_with_a_new_level_three_heading() -> None:
    """OBS-RDY-6C-3: the record must be a proper `### ` heading so the 6A extractor cannot swallow it."""
    lines = _read(_ADR).split("\n")
    heads = [ln for ln in lines if ln.startswith(_ADR_6CA_HEADING)]
    assert len(heads) == 1, f"exactly one `### B5-BLK-6C-A` heading line expected, found {len(heads)}"
    assert "audit obligation reconciliation (option a)" not in _norm(_adr_section()), (
        "the 6A ADR capture must terminate at the new `###` heading, not swallow the 6C-A record"
    )
    demoted = _read(_ADR).replace("\n" + _ADR_6CA_HEADING, "\n#" + _ADR_6CA_HEADING)
    assert not any(ln.startswith(_ADR_6CA_HEADING) for ln in demoted.split("\n")), (
        "the heading check must fail when the record is demoted to a #### sub-heading (in-memory only)"
    )


def test_6ca_nonvacuity_every_contract_anchor_is_load_bearing() -> None:
    for section_fn, anchors in (
        (_ic002_audit_requirements, _6CA_IC002_MUST),
        (_ic002_audit_extension, _6CA_CONTRACT_COMMON),
        (_ic005_emission, _6CA_CONTRACT_COMMON + _6CA_RESERVED),
        (_j_section, _6CA_CONTRACT_COMMON),
        (_q_section, _6CA_Q),
        (_r_section, _6CA_RESERVED + _6CA_R_RETAINED),
    ):
        live = _norm(section_fn())
        assert _missing(live, anchors) == [], "control must be green before planting"
        for anchor in anchors:
            planted = live.replace(anchor, "")
            assert anchor in _missing(planted, anchors), f"detector did not fire when {anchor!r} was removed"


def test_6ca_nonvacuity_every_adr_anchor_is_load_bearing() -> None:
    live = _norm(_adr_6ca_section())
    assert _missing(live, _ADR_6CA_REQUIRED) == [], "control must be green before planting"
    for anchor in _ADR_6CA_REQUIRED:
        planted = live.replace(anchor, "")
        assert anchor in _missing(planted, _ADR_6CA_REQUIRED), f"detector did not fire when {anchor!r} was removed"


def test_6ca_live_sections_authorize_nothing_forbidden() -> None:
    """Green control: no 6C-A-governed section trips any historic or new forbidden-authorization detector."""
    for name, section_fn in _6CA_SECTIONS:
        hits = _forbidden_hits_6ca(_norm(section_fn()))
        assert hits == [], f"{name} must not authorize: {hits}"


def test_6ca_planted_probes_are_each_rejected() -> None:
    base = _j_section()
    assert _forbidden_hits_6ca(_norm(base)) == [], "control must be green before planting"
    for expected, injected in _PROBES_6CA:
        planted = _norm(base + "\n" + injected)
        hits = _forbidden_hits_6ca(planted)
        assert expected in hits, f"probe not rejected: {expected!r} (injected {injected!r}; hits={hits})"
    assert _forbidden_hits_6ca(_norm(_j_section())) == [], "control must remain green after planting (in-memory only)"


def test_6ca_probe_set_covers_every_new_detector() -> None:
    assert len(_PROBES_6CA) == 7, "every 6C-A forbidden-authorization detector must carry a probe"
    assert {name for name, _ in _PROBES_6CA} == {name for name, _ in _FORBIDDEN_6CA}, "every detector must carry a probe"


def test_6ca_blockers_and_production_state_unchanged() -> None:
    adr = _norm(_adr_6ca_section())
    assert "b5-blk-6c-a closes no blocker" in adr
    assert "b5-blk-6 remains open" in adr
    assert "b5-blk-5 remains open" in adr
    assert "production remains not ready / do-not-activate" in adr
    for section_fn in (_ic002_audit_extension, _ic005_emission):
        norm = _norm(section_fn())
        assert "closes no blocker" in norm
        assert "b5-blk-6 remains open" in norm


if __name__ == "__main__":
    _scan.run(
        [
            test_pin01_governing_files_located_exactly,
            test_pin02_section_v_exists,
            test_pin02_section_v_letter_is_unclaimed_elsewhere,
            test_pin03_permitted_composed_response_phrase,
            test_pin04_arbitrary_pass_through_prohibition,
            test_pin05_adopted_contract_requirement,
            test_pin06_deterministic_serialization,
            test_pin07_contract_revision_traceability,
            test_pin08_denial_preservation,
            test_pin09_no_raw_database_row,
            test_pin10_no_secrets_dsns_tokens,
            test_pin11_no_tenant_attribution_in_directory_dtos,
            test_pin12_no_multi_tenant_aggregation,
            test_pin13_routeoutcome_remains_references_only,
            test_pin14_ic009_r1_owns_the_dto_catalogue,
            test_pin15_ic007_deferral_only,
            test_pin16_non_overclaim_statements,
            test_pin17_adr_entry_and_four_scope_decisions,
            test_pin17_adr_edit_is_additive_only_for_dec11,
            test_pin18_b5_blk6_remains_open,
            test_pin19_b5_blk5_remains_open,
            test_pin20_production_remains_not_ready,
            test_existing_notes_point_to_v_and_keep_their_prohibition,
            test_nonvacuity_every_v_anchor_is_load_bearing,
            test_nonvacuity_every_adr_anchor_is_load_bearing,
            test_live_amendment_authorizes_nothing_forbidden,
            test_planted_probes_are_each_rejected,
            test_probe_set_covers_the_six_required_categories,
            test_6ca_governing_documents_present_and_sections_nonempty,
            test_6ca_ic002_must_preserved_and_homed,
            test_6ca_mandate_emitter_home_shape_in_all_three_contracts,
            test_6ca_separation_from_the_historic_four_denial_anomaly_classes,
            test_6ca_q_section_points_to_the_mandated_event,
            test_6ca_directory_read_audit_reserved_in_ic005_and_r,
            test_6ca_adr_entry_records_option_a,
            test_6ca_adr_record_begins_with_a_new_level_three_heading,
            test_6ca_nonvacuity_every_contract_anchor_is_load_bearing,
            test_6ca_nonvacuity_every_adr_anchor_is_load_bearing,
            test_6ca_live_sections_authorize_nothing_forbidden,
            test_6ca_planted_probes_are_each_rejected,
            test_6ca_probe_set_covers_every_new_detector,
            test_6ca_blockers_and_production_state_unchanged,
        ]
    )
