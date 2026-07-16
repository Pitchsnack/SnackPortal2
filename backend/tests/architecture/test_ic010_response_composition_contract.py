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
from typing import List, Tuple

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
        ]
    )
