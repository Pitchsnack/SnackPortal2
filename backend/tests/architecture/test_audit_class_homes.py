"""Taxonomy-closure guard — PRD 05 (IC-002/IC-005 Audit-Section Extension, Inventory R2).

Locks the D-34-R2 §6 operational/administrative audit taxonomy after the PRD 05
amendment: every audit class has a *landed* contractual home (no class is "pending"),
the homing contracts are exactly the landed set {IC-001, IC-002, IC-003, IC-005},
and the two amended contracts carry their new section headers. Also locks OP-1:
IC-005 no longer carries the superseded "auth_router"-emits acceptance wording.

Pure stdlib; reads only contract markdown; imports no service package (lint-imports clean).
"""

from __future__ import annotations

import pathlib
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


def _read(contract_id: str) -> str:
    path = CONTRACTS / _CONTRACT_FILES[contract_id]
    assert path.exists(), f"missing contract file for {contract_id}: {path}"
    return path.read_text(encoding="utf-8")


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


if __name__ == "__main__":
    _scan.run(
        [
            test_no_audit_class_is_pending,
            test_homes_are_exactly_the_landed_set,
            test_amended_contracts_carry_new_sections,
            test_op1_supersession_landed,
        ]
    )
