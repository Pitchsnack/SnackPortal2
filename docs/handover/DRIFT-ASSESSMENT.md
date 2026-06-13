# DRIFT-ASSESSMENT

**Authoritative drift record (PRD-HO-03). Source: PRD-SP2-SESSION-V2 (PASS WITH AMENDMENTS) — the adversarial refuter could not disprove zero-drift, MVP preservation, or chain consistency.**

## Verified Drift Status: **Zero Ungoverned Drift**

## Drift Matrix (all **Absent** — firsthand-verified against contract + code text, not merely inherited from prior reviews)

| Category | Result |
|---|---|
| Shared Database Drift | **Absent** |
| Shared Schema Drift | **Absent** |
| tenant_id Isolation Drift | **Absent** |
| Workspace Routing Drift | **Absent** |
| Portal Routing Drift | **Absent** |
| Authentication Drift | **Absent** |
| Ownership Drift | **Absent** |
| Import Drift | **Absent** |
| Gateway Drift | **Absent** |
| Multi-DB Drift | **Absent** |

## Approved Supersessions — **Supersession ≠ Drift**

Each is explicit, citation-chained, and registered — governed architectural evolution, **not** drift.

| Original Architecture | Replacement Architecture | Reason | Governing Source |
|---|---|---|---|
| Shared Database | **Physical Multi-Database MVP** | A shared store cannot give physical tenant isolation; physical separation is the security boundary | PRD 8A/8B Option B; D-30/D-31; IC-001 |
| `tenant_id` Isolation | **Physical Database Isolation** | `tenant_id` survives only as a governed non-isolation role (registry/claim/pool/audit key) — never a row-filter (audited: 318 occurrences, zero filtering) | PRD 8B; backend audit |
| Supabase-First / RLS-as-authorization | **Vendor-Neutral, Contract-First** | Cloud-portable standard PostgreSQL; no provider lock-in; CI ban-lists enforced | CLAUDE.md constraints; CAP package |
| Lovable-owned data layer | **Platform-owned schema; Lovable presentation-only** | No runtime/platform dependence in business logic | D-37 |
| D-20 re-import default (upsert) | **User-controlled re-import** (D-34 amends D-20 in part) | Prevent silent destruction of tenant edits | D-34-R2; IC-003; register annotation |

## Tracked Carry-Forwards (NOT drift)

| Item | Disposition |
|---|---|
| **D-15 tenant-DB physical-distinctness check** | The platform cannot yet detect two tenant references resolving to the same physical PostgreSQL database (the only runtime `IsolationAnomaly` is a *logical* tenant-binding check). **Phase-3B requirement** (IC-010 §P reserves the hook; AGW-ARCH-SPEC-R2 §22 reserves it to D-15). |
| IC-002 / IC-005 audit-section extension | Specified (runtime gateway audit classes + tenant-resident ownership-audit class), no named authoring vehicle yet. |
| IC-010 register refresh | Register closing note / D-37 traceability still describe landed CAP amendments / IC-008 / IC-010 as "pending"/"reserved." |
| Front-door documentation refresh | `CLAUDE.md` still says "planning phase, no code yet"; `docs/PROJECT-HANDOVER-MASTER.md §11–§19` stale — architecture-neutral. |
| Gateway corpus residency | The Phase-3A spec + verification corpus lives out-of-repo under `D:\Pitchsnack\PRD\5. API Gateway Architecture\` — commit it into the repo. |

**None of the above is drift or an MVP weakness.** They are documentation/execution-level carry-forwards, each governed and tracked.
