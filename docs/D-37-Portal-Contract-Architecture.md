# D-37-R3 — Portal Contract Architecture

| | |
|---|---|
| **ADR ID** | D-37 (revision R3 — supersedes R2 and R1) |
| **Status** | **✅ Approved** — user/PMO approval 2026-06-12, following mechanical closure check (per the D-37-R2 Closure & Alignment Review disposition) |
| **Classification** | Architecture Decision Record · Governance only · **Implementation prohibited** |
| **Priority** | Critical — final ADR of the D-33→D-37 governance package |
| **Date** | 2026-06-12 |
| **Revision drivers** | D-37-R2 Closure & Alignment Review: MAJ-A (restore Portal Import Rule), MAJ-B (remove authorization escape hatch; restore portal-wide cross-tenant criterion), MAJ-C (Decision Options + Frozen Invariant Impact), MIN-1..5 (gateway wording, provenance/anonymity precedence, audit list alignment, future-portal guard, Overview refinements) |
| **Depends on** | D-33 Workspace Definition & Tenant Context Architecture · D-34 Operational Audit & Re-Import Governance · D-35 Global Deal Directory Architecture · D-36 Ownership Architecture · D-31 Global Directory Residency (as extended by D-35) · D-32 Role Hierarchy & Operating Model — **all Approved in the register at `20368cf`** · IC-001 · IC-002 · IC-003 · IC-005 · Physical Multi-Database MVP architecture |

---

## 1. Executive Summary

D-37 defines the portal layer's contractual architecture — boundaries, responsibilities, data access, visibility, security, and integration rules — **before any portal implementation begins**, closing MAJ-5 of the independent architecture review. It authorizes no implementation; it authorizes the **IC-009 — Portal Contracts** reservation (§16).

## 2. Decision Options (required by package template)

| Option | Model | Assessment |
|---|---|---|
| O1 — Portals as full-stack applications | Each portal owns data access (its own DB connections / Supabase tables / RLS), as in the legacy Lovable prototype. | **Rejected.** Recreates the 5%-aligned prototype's coupling: vendor lock-in (Supabase RLS as authorization), client-side tenancy, unauditable data paths — drift classes D1/D2/D3 in one stroke. |
| O2 — Portals as presentation-layer contracts over the API Gateway (adopted) | Portals display, discover, and initiate; every data path goes through the gateway; all authority (auth, routing, residency, ownership) stays platform-side. | The only model compatible with IC-005, D-30/D-31, and the Physical Multi-Database MVP. Verified by two independent reviews (P1–P9 demonstrated preserved). |
| O3 — Portal-per-database | Portal boundaries align to database boundaries (a portal *is* a tenancy/routing boundary). | **Rejected.** Conflates presentation with residency; breaks the D-33 workspace model (multi-membership principals switch context within one shell) and invites portal-based routing (P6 violation). |

## 3. Core Decision (unchanged keystone)

Portals are **presentation-layer contracts**. Portals *display data, initiate requests, present workflows*. Portals do **not** determine: database, tenant, authentication, authorization, ownership, routing, or residency. Those responsibilities remain external to the portal layer.

## 4. Physical Multi-Database Preservation Rule

The approved request path is, per request: `Portal → API Gateway → Authentication Router → Database Router → exactly one database`. Portals shall never introduce: database selection, database connections, cross-database queries, tenant-based routing, portal-specific routing, or shared tenant tables.

## 5. Mandatory API Gateway Rule (hardened per MIN-1)

All portals access **all data exclusively** through the **API Gateway** (IC-005 token contexts). Portals shall never access databases directly — not the Control Database, not tenant databases, not the Database Router.

Portals shall never use **any portal-side Supabase data access of any kind** — Supabase RLS, Supabase table/PostgREST access, Supabase data SDKs — whether framed as business logic, display logic, or anything else; and shall never implement frontend database routing. (Vendor-neutral OIDC token issuance at the IdP is the only legitimate non-gateway traffic.)

The API Gateway is the sole portal-facing integration boundary.

## 6. Portal Model and the Channel Rule

Six portal classes: **Control Portal · Master Agent Portal · Tenant Portal · Startup Portal · Investor Portal · AI Portal (Reserved)**.

**Channel Rule (per PRD 8A §12):** the portal classes are **channel-agnostic presentation contracts**. Any client channel — web, future mobile app, future API-platform consumer — binds to the same IC-009 portal contracts and to §5 (gateway-only), §13 (residency), and §14 (caching) identically. No channel may bypass these rules.

**Future Portal Expansion (restored per MIN-4):** future portal classes (e.g. LP Portal, Advisor Portal, Partner Portal, Accelerator Portal) require new ADRs and IC-009 amendments; they must not be introduced under D-37.

## 7. Portal Classes

### 7.1 Control Portal
Purpose: platform governance, global discovery, global intelligence management, directory management, publication governance. Data scope: **Control Database only** (Global Startup/Investor/Deal Directories, publications, global audit) — accessed as authenticated, audited control-plane reads under **IC-005/D-31** via the gateway.

### 7.2 Master Agent Portal
Restricted to **per-tenant operations**: workspace switching (D-33 §4.3–4.4 token issuance — sequential, audited, one active tenant per request per D-32), directory discovery (IC-005/D-31 control-plane reads of tenant-anonymous global records), and tenant-specific review within the active tenant context.
**Reserved Pending IC-007 — no authority granted by D-37:** cross-tenant sharing, cross-tenant introductions, cross-tenant collaboration.

### 7.3 Tenant Portal
Purpose: tenant business operations. Data scope: **the active tenant's database only** (tenant startups, investors, deals, ownership, activity). **Discovery exception:** tenant users may use approved discovery capabilities (IC-005/D-31 directory reads per D-33; import per IC-003/D-35) through the gateway; this never alters residency or ownership.

### 7.4 Startup Portal
Purpose: startup self-service. Authorized visibility: assigned startup records, assigned deals, assigned activities; plus the **Global Startup Directory** for discovery (own-kind access, per the platform foundation), as an IC-005/D-31 authenticated, audited control-plane read, where authorized by D-33 and the IC-009 visibility matrix.
Prohibited: other startup records, other tenant records, administrative directories — **except via governed contracts; cross-tenant access remains IC-007-deferred, and D-37 defines no authorization mechanism** (MAJ-B fix). *Administrative directories* = Control-Portal-scoped management surfaces (directory administration, publication governance, registry views, audit reads).

### 7.5 Investor Portal
Purpose: investor self-service. Authorized visibility: assigned investor records, assigned deals, assigned introductions; plus the **Global Investor Directory** for discovery (own-kind access), same IC-005/D-31 basis and IC-009 gating as §7.4.
Prohibited: identical structure to §7.4 — other investor records, other tenant records, administrative directories — except via governed contracts; cross-tenant access remains IC-007-deferred; no authorization mechanism is defined here.

### 7.6 AI Portal (Reserved)
Reserved; governed by IC-006. No implementation, routing, or database authority. **AI presentation deferral (per MIN-5a):** all AI presentation within every portal — including the Overview's "Current AI Context" workspace-switcher element (PRD 1 §9) and the display of D-36 AI-owner references — is **deferred to IC-006**; this records the Overview requirement as deliberately deferred, not omitted.

## 8. Workspace Rule (shell-level, all portals — per MIN-5b)

Workspace switching per D-33 (§4.3–4.4: new scoped token, audited; selector fed by the membership read) is a **shell-level capability available in every portal class** to any multi-membership principal — the Master Agent Portal is merely its primary consumer (PRD 1 §9; PRD 1.1 §7). Portals never transmit workspace as a header, cookie, or query-string; the D-33 carrier rules (match-or-reject; strip-at-gateway) apply to all portal traffic.

## 9. Portal Import Rule (restored per MAJ-A)

Portals may initiate IC-003 imports **only as discrete, explicitly user-initiated operations within the active tenant context** (consistent with D-34's user-controlled re-import decision, R3). Result: an independent tenant copy with new tenant-side ownership (D-36), new activity, new audit history.

Portals shall **never** implement: synchronization, automatic or scheduled re-import, shared ownership, or cross-database updates. Timer-driven, background, or event-triggered re-import of Global records is prohibited regardless of how individually lawful each underlying call would be.

## 10. Portal Data Contract Rule (provenance, with anonymity precedence — MIN-2)

Portal DTOs must never merge global, tenant, ownership, or audit data without **explicit provenance**: contracts preserve `record_origin`, `record_residency`, `record_type`, and — **for tenant-resident records only** — `lineage_reference` (or equivalent contract-defined markers).

**Anonymity precedence:** directory/publication-record DTOs carry **no tenant-attributable provenance** of any kind; on any conflict between this section and D-35's Tenant Anonymity Rule, **the Tenant Anonymity Rule prevails**.

## 11. Authentication and Authorization Rules

Authentication remains governed by IC-005. Portals consume authenticated principals, JWT claims, and the active tenant context; portals do **not** manage sessions, session stores, or authentication state — the platform remains **stateless JWT** (D-05). Authorization remains separate from ownership, portal access, and workspace selection (D-36: Ownership ≠ Authorization).

## 12. Audit Rule (aligned per MIN-3)

Portal actions generate audit events per **D-34** and its **Global Audit Representation Rule**: records carry **references only** — `actor_ref`, `user_ref`, `tenant_ref`, `ownership_ref`, `record_ref` — never names, emails, display names, identity payloads, PII, or authorization payloads.

## 13. Portal Data Residency Rule

Portal-visible data follows **record residency**, not portal type: global records are retrieved from the Control Database; tenant records from the tenant database; **imported records from the tenant database** even when lineage references a Global record (point-in-time-copy model, IC-003).

## 14. Client Caching Rule

Portal implementations must not create cross-tenant client caches, cross-workspace cached datasets, or shared tenant data stores. A workspace change (new token) **invalidates the portal data context** before any subsequent retrieval.

## 15. Publication and Independence Rules

Portals comply with D-35 (Publication Boundary + Tenant Anonymity Rules); no portal may expose tenant attribution through publication records. The concepts *portal, workspace, database, ownership, authorization, authentication, residency* remain independent; no portal may redefine them.

## 16. Contract Impact

| Contract | Impact |
|---|---|
| IC-005 | No change (authentication/routing authority unchanged; directory access already governed) |
| IC-003 | No change (import authority unchanged; §9 restates, does not alter) |
| IC-001 / IC-002 | No change (residency and lifecycle untouched; cited as governing dependencies) |
| IC-007 | Remains deferred; no authority granted (cross-tenant capabilities reserved) |
| IC-008 | Ownership authority unchanged (reserved per D-36) |
| **IC-009 — Portal Contracts** | **Reserved — creation authorized by D-37.** Required content: portal DTOs (under §10); **the per-role × per-directory visibility matrix** (Global Startup/Investor/Deal Directories × CONTROL/MASTER_AGENT/TENANT_ADMIN/TENANT_AGENT/STARTUP_USER/INVESTOR_USER) — including the **deliberately deferred** decisions on Deal-Directory visibility for end-user roles and cross-kind discovery (anything introduction-shaped routes to IC-007); portal discovery rules; portal API contracts; portal access contracts; channel bindings (§6 Channel Rule). |

## 17. Consequences

Positive: portal boundaries explicit; the API Gateway becomes mandatory; Supabase coupling prevented by wording, not intent; the Physical Multi-Database MVP protected at the last unguarded layer; portal responsibilities contracted before any code exists. Trade-offs: an additional contract layer (IC-009); portal implementation deferred until IC-009, the API Gateway contract, and the amendment package exist.

## 18. Security Considerations

Portals never route databases, hold authentication state, store identity payloads, determine ownership, or bypass the API Gateway. Security authority remains in the Authentication Router, Database Router, and API Gateway. The §7.4/§7.5 prohibition structure contains no authorization escape hatch: cross-tenant access has **no defined mechanism** anywhere in this document.

## 19. Frozen Invariant Impact (required table)

| Invariant | Impact |
|---|---|
| Global Record ≠ Tenant Record | **Preserved — reinforced** (§10 provenance rule prevents blending; §13 residency retrieval) |
| Import ≠ Synchronization | **Preserved — reinforced** (§9 Portal Import Rule forbids portal-side synchronization in any form) |
| Control DB ≠ Tenant DB | **Preserved** (§4/§13; portals never select or connect to databases) |
| Authentication ≠ Routing | **Preserved** (§11; portals consume IC-005 outputs, never make either decision) |
| One Request → One Active Tenant → One Database | **Preserved** (§4 request path; §8 sequential workspace switching; §14 no cross-workspace state) |

## 20. Verification Criteria

V1 Portal never determines database routing. V2 Portal never determines tenant routing. V3 Portal accesses data only through the API Gateway — **verified by frontend-repository audit: no database client, no Supabase data SDK, no PostgREST usage** (MIN-1). V4 Master Agent Portal grants no IC-007 capability. V5 Global discovery remains consistent with D-33 and the IC-009 visibility matrix. V6 Portal DTOs preserve provenance, with directory DTOs tenant-anonymous (§10 precedence). V7 Portal data follows residency boundaries. V8 Portal caches never cross tenant or workspace boundaries. V9 **No portal introduces cross-tenant visibility outside approved contracts** (restored, portal-wide). V10 Imports initiated via portals are discrete and user-initiated; they create independent tenant records; no portal-driven synchronization exists. V11 Audit records comply with the D-34 representation rule (including `ownership_ref`). V12 The Physical Multi-Database MVP remains unchanged.

## 21. Decision

SnackPortal2 portals are presentation-layer contracts only. Portals **display, discover, initiate** — and never determine **database, routing, authentication, ownership, or residency**. All portal interactions occur through the API Gateway. This completes the D-33 → D-37 governance package while preserving the approved Physical Multi-Database MVP architecture: `Control DB + Tenant DBs + API Gateway + Database Router + One Request → One Database`.

## 22. Next governance sequence (upon approval)

1. Register entry **D-37** (completes the package) → 2. **IC-009** placeholder creation → 3. Contract Amendment Package (per the Phase-1 Inventory) → 4. API Gateway architecture (adopting D-33 criteria 4–6 and this ADR's V1–V3 as acceptance criteria) → 5. D-15 provisioning plan → 6. Frontend integration governance → 7. Portal implementation (blocked until IC-009 + gateway exist).
