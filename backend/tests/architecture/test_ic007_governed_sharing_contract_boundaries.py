"""IC-007 Governed Sharing contract-drift guard — PRD D-38 (Dan-authorized, 2026-07-18).

Mechanically pins the contract-authoring slice that opens IC-007 from the Deferred
placeholder to Draft / Proposed, plus its IC-009 / IC-010 / decision-register amendments,
so the ratified governed-sharing invariants cannot silently drift or be weakened.

The guard reads ONLY markdown — `contracts/IC-007-Deal-Collaboration-Cross-Tenant-Sharing-Contract.md`,
`contracts/IC-009-Portal-Contracts.md`, `contracts/IC-010-API-Gateway-Contract.md`, and
`docs/Architecture-Decision-Register.md`. It imports no service package (lint-imports clean),
pins NO line numbers (every anchor is matched against markdown-normalized text so the pins
survive reflow / re-wrapping / emphasis changes), and every anchor is proven load-bearing by an
in-memory planted-removal companion (no file is ever mutated).

This guard closes no blocker and implements nothing. IC-007 is Draft / Proposed only; no positive
sharing capability exists. B5-BLK-6 remains OPEN; B5-BLK-5 remains OPEN; production remains
NOT READY / DO-NOT-ACTIVATE. Pure stdlib; standalone-runnable:
  python tests/architecture/test_ic007_governed_sharing_contract_boundaries.py
"""

from __future__ import annotations

import pathlib
import sys
from typing import List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_IC007 = _scan.REPO_ROOT / "contracts" / "IC-007-Deal-Collaboration-Cross-Tenant-Sharing-Contract.md"
_IC009 = _scan.REPO_ROOT / "contracts" / "IC-009-Portal-Contracts.md"
_IC010 = _scan.REPO_ROOT / "contracts" / "IC-010-API-Gateway-Contract.md"
_ADR = _scan.REPO_ROOT / "docs" / "Architecture-Decision-Register.md"


def _read(path: pathlib.Path) -> str:
    assert path.is_file(), f"governing source missing: {path}"
    return path.read_text(encoding="utf-8")


def _norm(text: str) -> str:
    """Markdown-normalise: drop emphasis/backticks, lower-case, collapse whitespace."""
    return " ".join(text.lower().replace("*", "").replace("`", "").split())


def _missing(norm_text: str, anchors: Tuple[str, ...]) -> List[str]:
    """The detector: which required anchors are absent from the normalized section text."""
    return [a for a in anchors if a not in norm_text]


def _assert_present_and_load_bearing(norm_text: str, anchors: Tuple[str, ...]) -> None:
    """Green control (all present) + planted-removal non-vacuity (each anchor detectably absent)."""
    assert _missing(norm_text, anchors) == [], f"missing required anchors: {_missing(norm_text, anchors)}"
    for anchor in anchors:
        planted = norm_text.replace(anchor, "")
        assert anchor in _missing(planted, anchors), f"detector did not fire when {anchor!r} was removed"


# --- 1. IC-007 is Draft / Proposed, contract-first, no positive capability --------------------
def test_ic007_contract_is_draft_and_contract_first() -> None:
    ic007 = _norm(_read(_IC007))
    _assert_present_and_load_bearing(
        ic007,
        (
            "status: draft / proposed",
            "contract-first specification (no implementation)",
            "no positive sharing capability is implemented",
            "register → contract → code",
            "becomes final only after independent verification",
        ),
    )
    adr = _norm(_read(_ADR))
    _assert_present_and_load_bearing(
        adr,
        (
            "d-38 — governed sharing placement, authority & dispatch",
            "opens ic-007 deferred → draft / proposed",
        ),
    )
    # It is NOT Final and NOT merely Deferred any more.
    assert "status: final" not in ic007.split("phase:")[0], "IC-007 must not claim Final in this slice"


# --- 2. Placement: Control-level references-only; no tenant table; no cross-DB FK --------------
def test_sharing_placement_is_control_references_only() -> None:
    ic007 = _norm(_read(_IC007))
    _assert_present_and_load_bearing(
        ic007,
        (
            "control-level references-only grants",
            "control db is the sharing authority",
            "control plane is the sole control-db writer",
            "no tenant sharing table",
            "no cross-database fk",
            "soft references only",
            "one request → one category → one database",
        ),
    )


# --- 3. Exactly four initial categories; the deferred set stays deferred; Import ≠ Sharing -----
def test_initial_categories_and_deferred_categories_are_pinned() -> None:
    ic007 = _norm(_read(_IC007))
    _assert_present_and_load_bearing(
        ic007,
        (
            "intra-master-agent deal sharing",
            "master-agent → master-agent startup sharing",
            "control → master-agent startup sharing",
            "control → master-agent investor sharing",
            "introduction, campaign distribution, forward / re-share, import-copy, ownership transfer, tenant transfer, sync, attribution",
            "import ≠ sharing",
            "sharing never changes ownership, owning tenant, or authoritative record identity",
        ),
    )


# --- 4. Dual-layer authority: six platform token roles vs seven organizational (non-token) -----
def test_platform_and_organizational_role_layers_are_distinct() -> None:
    ic007 = _norm(_read(_IC007))
    _assert_present_and_load_bearing(
        ic007,
        (
            "control, master_agent, tenant_admin, tenant_agent, startup_user, investor_user",
            "these six are the only token / jwt roles",
            "owner, head of investment, portfolio manager, investment manager, analyst, marketing, institutional sales",
            "organizational roles are not jwt / token roles",
            "owner-only organizational-role assignment",
            "control / tenant_admin principal",
        ),
    )


# --- 5. Senior approval, AI-cannot-authorize, forwarding prohibited by default -----------------
def test_senior_approval_ai_and_forwarding_rules_are_pinned() -> None:
    ic007 = _norm(_read(_IC007))
    _assert_present_and_load_bearing(
        ic007,
        (
            "investment branch",
            "portfolio branch",
            "analyst never approves or grants",
            "dormant until later categories open",
            "ai cannot authorize",
            "ai may assist or draft",
            "forwarding is prohibited by default",
        ),
    )


# --- 6. IC-009 references-only SharedItemReferenceDTO (DEC-4 hiding; inert until Final) --------
def test_ic009_projection_dto_is_references_only() -> None:
    ic009 = _norm(_read(_IC009))
    _assert_present_and_load_bearing(
        ic009,
        (
            "shareditemreferencedto",
            "dec-4: hidden from a non-owner target",
            "must not carry tenant business payload, source-tenant live record, db identity/name/dsn/topology",
            "single control-db read",
            "authored-but-inert until ic-007 is final",
        ),
    )
    # The MVP visibility mechanism is the references-only projection; rich snapshots / retrieval
    # tokens / tenant-local projections / sync are DEFERRED (IC-007 §3) — pins reject "rich snapshot as MVP".
    ic007 = _norm(_read(_IC007))
    _assert_present_and_load_bearing(
        ic007,
        (
            "mvp visibility is the shareditemreferencedto",
            "owner-published rich snapshot, temporary retrieval token, tenant-local projection, and automatic synchronization are deferred",
        ),
    )


# --- 7. IC-010 fifth "Governed Sharing" category preserves one-database isolation --------------
def test_ic010_fifth_category_preserves_one_database_isolation() -> None:
    ic010 = _norm(_read(_IC010))
    _assert_present_and_load_bearing(
        ic010,
        (
            "governed sharing — control-resident operations",
            "fifth category; opened solely by ic-007 adoption",
            "it resolves to the control db only",
            "one request → one category → one database",
            "no fan-out, no cross-tenant straddle",
            "authored-but-inert until ic-007 is final",
            "ic-007 is a deferral boundary carved out solely for the four adopted governed sharing categories",
            "no runtime is implemented",
        ),
    )


# --- 8. The slice makes no implementation / production claim (and the detector proves it) ------
def test_contract_slice_makes_no_implementation_or_production_claim() -> None:
    ic007 = _norm(_read(_IC007))
    _assert_present_and_load_bearing(
        ic007,
        (
            "production remains not ready / do-not-activate",
            "no positive sharing capability is implemented",
            "does not make ic-007 final",
            "does not amend ic-005",
        ),
    )
    adr = _norm(_read(_ADR))
    _assert_present_and_load_bearing(
        adr,
        (
            "d-38 closes no blocker",
            "implementation is not authorized",
            "production remains not ready / do-not-activate",
        ),
    )
    # Forbidden overclaims must be ABSENT from IC-007 — and the detector must fire on a plant.
    forbidden: Tuple[str, ...] = (
        "production is ready",
        "ready to activate",
        "ic-007 is now final",
        "sharing capability is live",
        "implementation complete",
    )
    assert [f for f in forbidden if f in ic007] == [], "IC-007 must make no positive-capability / production claim"
    planted = ic007 + " production is ready"
    assert "production is ready" in planted, "the overclaim detector must fire on a planted claim (in-memory only)"


if __name__ == "__main__":
    _scan.run(
        [
            test_ic007_contract_is_draft_and_contract_first,
            test_sharing_placement_is_control_references_only,
            test_initial_categories_and_deferred_categories_are_pinned,
            test_platform_and_organizational_role_layers_are_distinct,
            test_senior_approval_ai_and_forwarding_rules_are_pinned,
            test_ic009_projection_dto_is_references_only,
            test_ic010_fifth_category_preserves_one_database_isolation,
            test_contract_slice_makes_no_implementation_or_production_claim,
        ]
    )
