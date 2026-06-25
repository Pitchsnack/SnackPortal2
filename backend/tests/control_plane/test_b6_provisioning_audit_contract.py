"""PRD 06 B-6 — Provisioning Audit Sink CONTRACT guard (control-plane).

Grounds B-6 on the EXISTING ControlPlaneAudit (append-only, references-only; IC-002/D-34, distinct from IC-004
lineage) and on the FROZEN events.py vocabulary. Behavioural (in-memory store; psycopg-free) + catalog mapping;
NO database-driver import. The EXPECTED_EVENT_ACTIONS set-equality guard lives in
tests/control_plane/test_onboarding_orchestration.py and is REFERENCED here, not duplicated. Standalone-runnable:
  python tests/control_plane/test_b6_provisioning_audit_contract.py
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys
from typing import List, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import events  # noqa: E402
from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.audit import ControlPlaneAudit  # noqa: E402
from control_plane.records import ControlAuditRecord  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_DOCS = _REPO_ROOT / "docs" / "runtime"
_SINK_DOC = _DOCS / "b6_provisioning_audit_sink.md"
_EVENTS_DOC = _DOCS / "b6_provisioning_audit_events.md"
_BLOCKERS_DOC = _DOCS / "b6_provisioning_audit_blockers.md"

_EXPECTED_RECORD_FIELDS = {"actor", "tenant_id", "action", "from_state", "to_state", "timestamp", "correlation_id"}


def _live_event_actions() -> Set[str]:
    # Same idiom as test_onboarding_orchestration.py: the frozen events.py action-name set.
    return {v for k, v in vars(events).items() if k.isupper() and isinstance(v, str)}


def _block(text: str, start: str, end: str) -> List[str]:
    out: List[str] = []
    collecting = False
    for line in text.splitlines():
        if start in line:
            collecting = True
            continue
        if end in line:
            break
        if collecting:
            out.append(line)
    return out


def _rhs_event_names(block_lines: List[str]) -> List[str]:
    return [line.split("->")[-1].strip() for line in block_lines if "->" in line]


# --- (a) behavioural: the EXISTING audit is append-only + references-only ---------------------------


def test_existing_audit_is_append_only() -> None:
    store = InMemoryControlStore()
    audit = ControlPlaneAudit(store)

    r1 = audit.record(
        actor="ops_ref",
        tenant_id="tenant_ref",
        action=events.DATABASE_PROVISION_REQUESTED,
        from_state=None,
        to_state="Provisioning",
        correlation_id="corr-1",
    )
    snap1 = audit.events()
    assert len(snap1) == 1 and snap1[0] == r1

    r2 = audit.record(
        actor="ops_ref",
        tenant_id="tenant_ref",
        action=events.DATABASE_PROVISION_SUCCEEDED,
        from_state="Provisioning",
        to_state="Verifying",
        correlation_id="corr-2",
    )
    snap2 = audit.events()
    # append order preserved; the first record is unchanged after the second append
    assert len(snap2) == 2
    assert snap2[0] == r1 and snap2[1] == r2
    # earlier snapshot is unaffected (append-only; no retroactive mutation)
    assert len(snap1) == 1
    # no update/delete surface (append-only at the API)
    assert not hasattr(store, "update_audit")
    assert not hasattr(store, "delete_audit")
    assert not hasattr(audit, "update")
    assert not hasattr(audit, "delete")


def test_audit_record_is_references_only_and_immutable() -> None:
    field_names = {f.name for f in dataclasses.fields(ControlAuditRecord)}
    # exactly the reference fields — no payload / secret / business-data field
    assert field_names == _EXPECTED_RECORD_FIELDS
    # frozen => append-only at the record level (no in-place mutation)
    params = getattr(ControlAuditRecord, "__dataclass_params__", None)
    assert params is not None and params.frozen is True


# --- (b) catalog reconciliation: map to events.py; rollback = forward proposal only -----------------


def test_event_catalog_maps_to_existing_vocabulary() -> None:
    assert _EVENTS_DOC.is_file(), "missing docs/runtime/b6_provisioning_audit_events.md"
    text = _EVENTS_DOC.read_text(encoding="utf-8")
    live = _live_event_actions()

    map_lines = _block(text, "B6-EVENT-MAP:START", "B6-EVENT-MAP:END")
    mapped = _rhs_event_names(map_lines)
    assert mapped, "B-6 event map block is empty"
    for name in mapped:
        assert name in live, f"mapped event {name!r} is not a member of the frozen events.py vocabulary"

    # secondary guard: the DEFINED catalog (map + forward blocks) must not use a parallel dotted
    # scheme. Scoped to the machine-readable blocks so prose that *names* the prohibition is exempt.
    catalog = "\n".join(map_lines + _block(text, "B6-EVENT-FORWARD:START", "B6-EVENT-FORWARD:END"))
    assert "tenant.provision." not in catalog, "B-6 catalog must not define a parallel tenant.provision.* scheme"
    assert "provisioning.rollback." not in catalog, "B-6 catalog must not define a parallel dotted rollback scheme"


def test_rollback_events_are_forward_proposal_only() -> None:
    text = _EVENTS_DOC.read_text(encoding="utf-8")
    live = _live_event_actions()
    forward = _rhs_event_names(_block(text, "B6-EVENT-FORWARD:START", "B6-EVENT-FORWARD:END"))
    assert forward, "B-6 forward-proposal block is empty"
    for name in forward:
        # genuinely new — NOT in events.py today (B-6 does not edit events.py)
        assert name not in live, f"forward-proposal event {name!r} unexpectedly already in events.py"
    # labelled a proposal, reconciled against EXPECTED_EVENT_ACTIONS (referenced, not duplicated)
    assert "additive-extension proposal" in text
    assert "EXPECTED_EVENT_ACTIONS" in text


# --- (c) the B-6 docs commit to the contract --------------------------------------------------------


def test_sink_doc_commits_to_contract() -> None:
    assert _SINK_DOC.is_file(), "missing docs/runtime/b6_provisioning_audit_sink.md"
    text = _SINK_DOC.read_text(encoding="utf-8")
    low = text.lower()
    assert "append-only" in low
    assert "references-only" in low or "references only" in low
    assert "fail-closed" in low or "fail closed" in low
    # provisioning audit (IC-002/D-34) distinct from lineage (IC-004/D-23)
    assert "IC-004" in text and "lineage" in low and "distinct" in low
    # the wired audit machinery is off-limits in B-6
    assert "audit.py" in text and ("off-limits" in low or "off limits" in low)


def test_blocker_doc_keeps_b5_blk_4_open() -> None:
    assert _BLOCKERS_DOC.is_file(), "missing docs/runtime/b6_provisioning_audit_blockers.md"
    text = _BLOCKERS_DOC.read_text(encoding="utf-8")
    assert "B5-BLK-4" in text
    assert "OPEN" in text
    assert "b5_activation_blockers.md" in text  # cross-reference, not edit
    assert "reduce" in text.lower()  # reduces but does not close


if __name__ == "__main__":
    _failed = 0
    for _t in [
        test_existing_audit_is_append_only,
        test_audit_record_is_references_only_and_immutable,
        test_event_catalog_maps_to_existing_vocabulary,
        test_rollback_events_are_forward_proposal_only,
        test_sink_doc_commits_to_contract,
        test_blocker_doc_keeps_b5_blk_4_open,
    ]:
        try:
            _t()
            print("PASS:", _t.__name__)
        except AssertionError as _exc:
            _failed += 1
            print("FAIL:", _t.__name__, "-", _exc)
    if _failed:
        sys.exit(1)
    print("ALL PASSED")
