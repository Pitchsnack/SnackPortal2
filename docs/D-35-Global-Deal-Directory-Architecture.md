# D-35-R2 — Global Deal Directory Architecture

| | |
|---|---|
| **ADR ID** | D-35 (revision R2 — supersedes D-35-R1, delivered in the malformed file "D-35 creates Global Deals.md", and D-35; this is the clean authoritative re-issue) |
| **Status** | Approved for register entry per **PRD-D33-D36-P1-R1** (Phase 1, APPROVED FOR IMPLEMENTATION) |
| **Type** | Architecture Decision Record — governance correction only; no runtime behavior change |
| **Date** | 2026-06-12 |
| **Revision drivers** | PRD-D33-D37-R1 Independent Architecture Alignment Review finding **MAJ-1** (Publication Boundary Rule does not prohibit tenant attribution), plus minor findings (channel-scoped Future Publication Rule; undefined Discovery Metadata; contract-impact completeness; document integrity) |
| **Related ADRs** | D-33 (Workspace), D-34 (Audit — R2), D-36 (Ownership — R2), D-37 (Portals — pending); **extends D-31** (not reopened) |

---

## 1. Background

The Global Startup and Investor Directories are contracted (IC-001:48-49) **and implemented** (`control_plane/directory.py`, served by the control-plane read API). A Global **Deal** Directory was identified by PRD 1A-R2 (Question H) as uncontracted business vision. D-35 resolves that gap. The independent alignment review confirmed the decision but found the Publication Boundary Rule airtight in intent yet not in operative wording — the only constructible covert cross-tenant visibility channel was **tenant attribution** on directory records. This revision closes it.

## 2. Decision (unchanged from R1)

**O2 adopted:** the **Global Deal Directory** exists as a Control Database concept alongside the Startup and Investor directories, completing the Global Discovery Platform (matching the PRD 8A baseline: a Global Deal is a Control-managed opportunity). O1 (tenant-only deals) rejected — it contradicts the baseline vision (no curation, no discovery, no recommendation).

**Core principle:** `Global Deal ≠ Tenant Deal` — the existence of either never implies the other; after import they evolve independently.

## 3. Scope Boundaries (unchanged)

D-35 defines: the directory, deal discovery, deal recommendation (human/control workflows only), deal import, publication boundaries. D-35 does **not** define: cross-tenant sharing/visibility/deal mechanics (IC-007, deferred), AI deal behavior or AI recommendations (IC-006, deferred).

## 4. Publication Boundary Rule (hardened — MAJ-1 / Work Package B)

A Global Deal record MUST consist only of **approved global discovery metadata**: *Global Data, Reference Data, Discovery Data, Directory Data* — categories to be defined normatively in the IC-001 amendment (placeholder definitions: data originating in Control scope or public sources, identifying the opportunity and its non-sensitive discovery attributes).

A Global Deal record MUST NOT contain: tenant-owned deal data, tenant-confidential data, tenant pipeline data, tenant negotiation data, tenant commercial terms.

### Tenant Anonymity Rule (new — mandatory)

Global publication records MUST NOT contain:

- `tenant_id`
- `tenant_name`
- `tenant_code`
- `tenant_reference`
- `membership_reference`

— or any field that **references, names, or is attributable to any tenant or tenant activity** — unless explicitly governed by a future ADR. A "curated" or "market" opportunity must be publishable without revealing which tenant (if any) sourced, held, or pursued it.

*Scope note:* this rule governs **directory/publication records** (the tenant-facing, cross-tenant-readable surface). It does not apply to **audit records**, which are governance metadata carrying `tenant_ref` by design under the D-34-R2 §7 Global Audit Representation Rule (reference-only, access-controlled, never tenant-facing). The two record classes must never be conflated.

### Future Publication Rule (rephrased — any source, any mechanism)

Any operation that moves **tenant-resident information of any kind into any Global record, by any mechanism** (automated or manual, including re-keying by Control staff) — not merely "Tenant Deal → Global Deal" — MUST be explicit, consent-based, audited, and separately governed by a future ADR. **D-35 authorizes no tenant-to-global publication.**

## 5. Discovery, Recommendation, Import (unchanged from R1)

- **Discovery** (search/browse/review) creates no ownership, no import, no synchronization. Directory reads are authenticated, audited control-plane reads (D-31/IC-005), available to authorized principals from their own workspace context per role (D-33).
- **Recommendation:** human/control workflows only; no AI behavior authorized (IC-006-gated).
- **Import:** `Global Deal → Import → Tenant Deal Copy` under the unchanged Import-Copy model; Import ≠ Synchronization; tenants modify/advance/close/archive/reject their copies independently; the Global Deal remains unchanged. D-20 natural-key semantics for deals must be specified in the IC-003 amendment before implementation.

### Discovery Metadata (defined — independent-review minor)

"Discovery Metadata" owned by the Control DB (§6) is **deal-attributed and tenant-anonymous** (e.g., categorization, freshness, publication state). Any **tenant-attributed** action record (import initiation, directory views if ever recorded) is NOT discovery metadata and flows exclusively through D-34-R2 audit governance (reference-only, access-controlled, never tenant-facing).

## 6. Responsibilities (unchanged, with hardened terms)

**Control DB may own:** Global Deal Directory, Discovery Metadata (as defined in §5), Publication State, Operational Audit (per D-34-R2 taxonomy). **Control DB must not own:** tenant deal lineage, tenant deal ownership, tenant deal activity, tenant commercial terms. **Tenant DB owns:** tenant deals, activity, ownership, audit (tenant-resident classes per D-36-R2), lineage, commercial terms.

## 7. Consequences

Positive: completes the Global Discovery Platform; aligns with Import-Copy; preserves isolation; the Tenant Anonymity Rule closes the last constructible cross-tenant visibility path through the directory. Negative: publication/moderation workflows and the category definitions become required IC-001 amendment content.

## 8. Security Considerations

The directory carries **non-sensitive, tenant-anonymous discovery information only**; commercially sensitive terms remain tenant-resident. The directory must never become a cross-tenant data aggregation or visibility mechanism — now enforced by wording (Tenant Anonymity Rule), not only intent.

## 9. Frozen Invariant Impact

Global Record ≠ Tenant Record — **Strengthened**. Import ≠ Synchronization — **Strengthened**. Control DB ≠ Tenant DB — **Strengthened**. Authentication ≠ Routing — No impact. One Request → One Active Tenant → One Database — No impact.

## 10. Verification Criteria

V1 Global Deals can exist without Tenant Deals. V2 Tenant Deals can exist without Global Deals. V3 Import creates independent tenant copies. V4 No synchronization occurs after import. V5 The directory does not bypass tenant isolation. V6 No tenant-owned **or tenant-attributable** data resides in Global Deal records. **V7 No publication record reveals tenant identity** (AC-3/Work-Package-B criterion; testable as a residency-and-attribution audit over directory records).

## 11. Contract Impact

| Contract | Impact |
|---|---|
| **IC-001** | Amendment Required — add the Global Deal Directory at all five touchpoints (directory list, residency paragraph, scope, Control-DB section, decisions-applied); define the four discovery-metadata categories; carry the Tenant Anonymity Rule |
| **IC-003** | Amendment Required — extend the Global-record definition (Startup ∨ Investor ∨ **Deal** record) to make deal import contracted; specify D-20 natural-key semantics for deals |
| **D-31** | **Extended, not reopened** — the Deal Directory joins under identical absolute-residency terms (register annotation required) |
| IC-004 / D-30 | No change |
| IC-005 | No change — existing directory-access governance (authenticated, audited control-plane reads) applies to the new directory |
| IC-002 | No change |

## 12. Implementation Impact

None authorized. Future work: publication/moderation workflow, deal-import workflow, directory schema (D-12 discipline) — all gated on the IC-001/IC-003 amendments and governed by D-37 for any portal surface.
