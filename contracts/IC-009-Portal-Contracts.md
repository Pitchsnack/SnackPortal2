# IC-009 — Portal Contracts

**Status:** Reserved (future contract — creation authorized, not yet designed) · **Phase:** Architecture Governance · **Type:** Placeholder (no design, no implementation)
**Origin:** Reserved by **D-37** (Portal Contract Architecture, Approved 2026-06-12), the final decision of the D-33–D-37 governance package.

> This is a **placeholder**. It reserves the contract and records its boundary and required content. It does **not** design the contract or authorize any portal implementation.

## Purpose
Carry the concrete, per-portal data and visibility contracts for the six portal classes defined by D-37 (Control, Master Agent, Tenant, Startup, Investor, AI-Reserved), so that portal behavior is contracted before any frontend implementation exists.

## Required content (per D-37 §16 — binding on the future authoring)
- **Portal DTO contracts** under the D-37 §10 provenance rule (`record_origin`, `record_residency`, `record_type`; `lineage_reference` for tenant-resident records only; directory/publication DTOs tenant-anonymous — the D-35 Tenant Anonymity Rule prevails on any conflict).
- **The per-role × per-directory visibility matrix:** Global Startup / Investor / Deal Directories × CONTROL / MASTER_AGENT / TENANT_ADMIN / TENANT_AGENT / STARTUP_USER / INVESTOR_USER — including the decisions D-37 **deliberately deferred**: Deal-Directory visibility for end-user roles and any cross-kind discovery (anything introduction-shaped routes to IC-007).
- **Portal discovery rules** (IC-005/D-31 authenticated, audited control-plane reads; D-33 workspace context).
- **Portal API contracts** (gateway-facing; IC-005 token contexts; stateless).
- **Portal access contracts** (authorization separate from ownership per D-36).
- **Channel bindings** (D-37 §6 Channel Rule: web, mobile, API-platform consumers bind to identical contracts and to the gateway-only, residency, and caching rules).

## Boundary (in force now)
- **No portal implementation** (frontend or backend surface) may proceed until IC-009 is designed and approved and the API Gateway contract (**IC-010 — reserved 2026-06-12**) exists (D-37 §22 sequence; traceability per PRD-D33-D37-V2-R1 WP-D).
- All D-37 rules bind any future IC-009 design: gateway-only data access (no portal-side database or Supabase data access of any kind), record-residency retrieval, no cross-workspace client caching, the Portal Import Rule (discrete, user-initiated only), and the package-wide audit representation rule (D-34).
- Cross-tenant capabilities remain **IC-007-deferred**; AI presentation remains **IC-006-deferred**; ownership mechanics remain **IC-008-reserved**.

## Dependencies
- **D-37** (governing ADR) · **D-33** (workspace/tenant context) · **D-35** (directory + anonymity rules) · **D-36** (ownership references) · **D-34** (audit representation) · **IC-005** (authentication routing) · **D-31** (directory residency, as extended) · **D-32** (role hierarchy).

---

> IC-009 must be designed and approved through the standard change-control process (decision register → contract) before any portal contract takes effect. Until then it remains **Reserved** and non-binding, and portal implementation remains blocked.
