# D-34-E1 — Capability Inventory Errata

| | |
|---|---|
| **Errata for** | D-34 — Operational Audit Architecture & Re-Import Governance (Approved 2026-06-12), §2 Existing Audit Capability Inventory |
| **Authorized by** | PRD-D33-D37-V2-R1 — Governance Chain Remediation, Work Package B (APPROVED FOR EXECUTION) |
| **Finding** | PRD-D33-D37-V2 Independent Architecture Compliance Verification, Minor 3: the inventory's publication-audit row is disproven by code |
| **Date** | 2026-06-12 |
| **Nature** | Inventory-row correction only. **No architecture decisions change; no audit rules change.** The D-34 taxonomy, the O1 decision, the Global Audit Representation Rule, and all re-import governance are untouched. |

---

## Correction

**Original row (D-34 §2):**

> | Publication audit | **Partially implemented** | directory mutations audited (see `tests/control_plane/test_audit_directory.py`); no publication/approval/withdrawal workflow exists |

**Corrected row (verified against code at `dd5c132`):**

> | Publication audit | **Not implemented** | directory mutations are **unaudited**: `GlobalDirectory` (`control_plane/directory.py`) takes no audit dependency and `add()` only writes to the store; `audit.record(...)` is invoked solely from `control_plane/registry.py` and `control_plane/lifecycle.py`; the previously cited test (`tests/control_plane/test_audit_directory.py`) asserts lifecycle-event audit and directory **storage separation**, not directory-mutation audit. No publication/approval/withdrawal workflow exists. |

## Forward scope (carried into the amendment package — no rule change here)

Directory-mutation and publication audit become **explicit scope of the pending IC-001 amendment** and its execution PRD, including a test asserting that `GlobalDirectory` mutations emit reference-only audit events (per the D-34 §7 Global Audit Representation Rule). Recorded in Contract Amendment Inventory R2.

## Traceability

D-34 §2 (inventory) → PRD-D33-D37-V2 Section D/E Minor 3 (code-level disproof) → PRD-D33-D37-V2-R1 WP-B → this errata → Inventory R2 (IC-001 row).
