# D-36-R2 — Ownership Architecture

| | |
|---|---|
| **ADR ID** | D-36 (revision R2 — supersedes D-36-R1 and D-36) |
| **Status** | Approved for register entry per **PRD-D33-D36-P1-R1** (Phase 1, APPROVED FOR IMPLEMENTATION) |
| **Type** | Architecture Decision Record — governance correction only; no runtime behavior change |
| **Date** | 2026-06-12 |
| **Revision drivers** | PRD-D33-D37-R1 Independent Architecture Alignment Review finding **MAJ-2** (transfer-audit residency), plus minor findings (owner-domain rule for multi-membership principals; AI-reference resolution gap; contract-impact completeness; scope of the per-entity ownership mandate) |
| **Related ADRs** | D-33 (Workspace), D-34 (Audit — R2), D-35 (Deal Directory — R2), D-37 (Portals — pending); reserves **IC-008** |

---

## 1. Background

"Owning Agent" and "Owning AI Agent" pervade the SnackPortal2 business vision but were governed by no contract (PRD 1A-R2 Question I: not contracted, not implemented, not planned in any repo artifact). The contracts already contain the ownership *boundary*: IC-003 — *"The ownership boundary is enforced by physical database separation"* and *"ownership never transfers"* across import. D-36 formalizes the ownership *model* on top of that boundary. The independent alignment review confirmed the model (its D5 probe could not construct cross-tenant access, visibility, or control under any reading) and required one residency correction and several definitional closures, applied in this revision.

## 2. Decision (unchanged from R1)

**O3 adopted:** every governed entity has **exactly one human Owning Agent** (required) and **one reserved, nullable Owning AI Agent reference** (at most one when populated; unpopulated until IC-006). O1 (no ownership) rejected — no accountability. O2 (human-only, no reserved slot) rejected — the business vision makes AI agents first-class future owners; the data model names the concept now without requiring it (AI-***ready***, not AI-required).

**Ownership scope:** Startups, Investors, Deals — **tenant-resident records** (see §6 for global records).

## 3. Representation Rule (mandatory — unchanged from R1)

Ownership is stored as references only: `owner_agent_ref`, `owner_ai_agent_ref`. Never stored: agent name, agent email, AI name, display name, identity payload. Human references resolve at presentation time through the **D-03 identity model**.

**AI-slot gating (closed per independent review):** `owner_ai_agent_ref` MUST remain **NULL until IC-006 defines the AI-agent identity namespace and its resolution path** — D-03 defines only human identities (internal + OIDC-federated), so no valid AI reference target exists today. "Future assignment" is IC-006-gated, not presently permitted. Verification: the field is unpopulated platform-wide pre-IC-006 (V10).

## 4. Ownership Principles (unchanged)

1. Exactly one human owner per entity. 2. At most one AI owner reference per entity (reserved, nullable). 3. **Ownership ≠ Authorization** — ownership never grants permissions. 4. **Ownership ≠ Database Residency** — ownership never changes Control-DB/tenant-DB boundaries. 5. **Ownership ≠ Visibility** — visibility remains governed by permissions and contracts.

## 5. Ownership Domain Rule (replaces "Owner Tenant = Record Tenant" — independent-review correction)

The prior formulation was undefined for multi-membership principals (D-32 MASTER_AGENT) and for global records. Normative replacement:

> **The owning principal MUST hold membership in the record's residency domain, evaluated per record.** For a tenant-resident record: the owner is a principal with membership in that tenant (a MASTER_AGENT with membership in tenants A and B may own records in each — each ownership reference is evaluated against its own record's tenant). For a Control-DB-resident global record: the owner MUST be a **Control-domain (D-03 internal) principal** — this restriction is **normative now**, independent of the IC-008 eligibility matrix.

Cross-tenant ownership remains not authorized (a principal cannot own a record in a tenant where they hold no membership; no ownership construct spans tenants). Reserved for **IC-007 — Deal Collaboration & Cross-Tenant Sharing** (title per register/contract) — any future cross-tenant model must preserve V7.

## 6. Ownership by residency (unchanged, scoped)

- **Tenant DBs** carry ownership references for tenant Startups/Investors/Deals (the §2 per-entity mandate and V1–V3 apply to tenant records).
- **Control DB** may carry ownership references for Global Startups/Investors/Deals — global-record ownership is **optional** ("may") and Control-domain-only (§5); the per-entity mandate does not extend to global records unless IC-008 makes it so.

## 7. Ownership Transfer & Audit Residency Rule (MAJ-2 / Work Package C)

Transfers are explicit, authorized, audited.

> **Audit Residency Rule: ownership audit follows RECORD RESIDENCY, not ownership type.**
> - **Control-DB (global) record** transfer → audited in the **Control DB** (D-34-R2 Administrative Audit).
> - **Tenant-resident record** transfer → audited in the **tenant DB** (tenant-resident audit class per the IC-002 audit extension).
> - **Imported record** (tenant-resident by definition) → audited in the **tenant DB**.

Ownership audit never crosses residency boundaries (V9). All ownership audit records obey the **D-34-R2 §7 Global Audit Representation Rule** (references only — `ownership_ref`, `actor_ref`, etc.; no names/emails/PII/payloads).

## 8. Import Ownership Rule (unchanged from R1)

Import never transfers ownership (IC-003, existing law). The imported copy receives **new tenant-side ownership** within the importing tenant. Initial owner assignment after import is undefined and SHALL be defined by **IC-008**; V1's per-entity guarantee for imported records takes effect when IC-008 defines initial assignment.

## 9. Ownership Eligibility (unchanged)

Eligibility for human principals is defined within the D-32 role model; the eligibility matrix (which of CONTROL / MASTER_AGENT / TENANT_ADMIN / TENANT_AGENT / STARTUP_USER / INVESTOR_USER may own what) is decided by **IC-008**, not this ADR — except the §5 Control-domain restriction for global records, which is normative now.

## 10. Consequences

Positive: accountability with zero cross-tenant surface; reference-only by construction; AI-ready without AI dependency; audit residency now matches data residency (no tenant-activity chronicle in the Control DB). Negative: requires IC-008; requires the IC-002 audit extension to carry the tenant-resident ownership-audit class; transfer workflow is future work.

## 11. Security Considerations

Ownership records remain reference-only, minimal, non-authoritative; ownership must never become an authorization mechanism, identity store, or permission store; personal information resolves only through approved identity services (D-03). Ownership audit is bounded by D-34-R2 §7.

## 12. Frozen Invariant Impact

Global Record ≠ Tenant Record — **Preserved**. Import ≠ Synchronization — **Preserved** (import never moves ownership). Control DB ≠ Tenant DB — **Strengthened** (audit residency rule removes the last boundary-crossing default). Authentication ≠ Routing — No impact. One Request → One Active Tenant → One Database — No impact.

## 13. Verification Criteria

V1 Every tenant Startup has exactly one `owner_agent_ref` (effective for imported records per §8). V2 Every tenant Investor likewise. V3 Every tenant Deal likewise. V4 `owner_ai_agent_ref` is nullable. V5 Ownership transfers are audited. V6 Ownership grants no permissions. V7 Cross-tenant ownership is impossible. V8 Ownership records contain references only — no names, no emails, no identity payloads. **V9 Ownership audit never crosses residency boundaries** (AC-4/Work-Package-C criterion). **V10 `owner_ai_agent_ref` is unpopulated platform-wide pre-IC-006.**

## 14. Contract Impact

| Contract | Impact |
|---|---|
| **IC-008 — Ownership Contract** | **New contract — formally reserved.** Carries: eligibility matrix; initial-owner-on-import; transfer workflow; the record-shape amendments (ownership reference fields on tenant and global Startup/Investor/Deal record shapes — the IC-001/IC-002 DTO touches are routed through IC-008 to avoid smearing ownership across contracts) |
| **IC-002** | Audit Section Extension Required — tenant-resident ownership-audit class (per §7) |
| IC-003 | No change — ownership-boundary language already present; import-ownership rule conforms |
| IC-004 | No change |
| IC-006 | Future extension — AI-owner activation (identity namespace + resolution + population rules) |
| IC-007 | Future extension — any cross-tenant ownership model (must preserve V7) |
| IC-001 / IC-005 | No direct change — global-record ownership metadata and eligibility-role coupling are carried by IC-008 |

## 15. Implementation Impact

None authorized. Future work (IC-008-gated): ownership registry/fields (D-17 expand/contract migrations), assignment and transfer workflows, ownership audit persistence, UI.
