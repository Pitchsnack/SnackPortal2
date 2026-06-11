# IC-007 — Deal Collaboration & Cross-Tenant Sharing Contract

**Status:** Deferred (future contract — not part of MVP) · **Phase:** Architecture Planning · **Type:** Placeholder (no design, no implementation)
**Origin:** Carved out by **D-32** (Role Hierarchy & Operating Model) and PRD 8C. Cross-tenant capabilities are explicitly excluded from the frozen MVP architecture.

> This is a **placeholder**. It reserves the contract and records its boundary. It does **not** design the contract, define its architecture, or authorize any implementation.

## Purpose
Reserve a future contract to govern **deal collaboration and cross-tenant sharing** — capabilities that deliberately fall outside the MVP because they cross the physical tenant-isolation boundary. The MVP architecture keeps every request bound to one tenant; any feature that spans tenants must be designed here, under its own decisions, before it may exist.

## Scope (future — illustrative, non-binding)
Subject to a future decision pack, IC-007 will govern:
- Cross-tenant **sharing** of records or artifacts.
- Cross-tenant **introductions** (e.g., startup ↔ investor across tenants).
- **Referral and collaboration workflows** between tenants and via MASTER_AGENT.
- **Deal collaboration and execution** that spans more than one tenant.

## Deferred Status
- **Deferred.** No part of IC-007 is in MVP scope.
- **No implementation** of cross-tenant sharing, introductions, referral workflows, or deal collaboration may proceed until IC-007 is designed and approved.
- The MVP invariants remain in force unless and until IC-007 explicitly defines a compliant, audited exception: **one request → one active tenant → one database**, **no cross-tenant joins**, **physical tenant isolation**, **Global Record ≠ Tenant Record**.

## Dependencies
- **IC-002** (Tenant Startup) — tenant identity, membership, registry.
- **IC-004** (Lineage) — provenance of any shared or derived records.
- **IC-005** (Authentication Routing) — identity, **D-04** one-active-tenant, **D-30** isolation; **D-32** role hierarchy (MASTER_AGENT coordination is single-tenant-per-request until IC-007).
- **D-30** Cross-Tenant Isolation Enforcement — any cross-tenant capability MUST state how it preserves isolation or defines a safe, audited, explicit relaxation.

## Future Decisions Placeholder
To be defined when IC-007 is opened (not yet decided; IDs assigned at authoring time):
- Cross-tenant **sharing model** (copy vs. reference vs. shared view) — must reconcile with *Global Record ≠ Tenant Record* and *no cross-tenant joins*.
- **Authorization model** for cross-tenant actions (who may share/introduce; consent/approval).
- **Isolation-preserving mechanism** for any cross-tenant data exposure, plus its audit and lineage.
- **MASTER_AGENT cross-tenant operating scope** beyond MVP single-tenant-per-request.
- **Data residency / compliance** (D-08) implications of cross-tenant flows.

---

> IC-007 must be designed and approved through the standard change-control process (decision register → contract) before any cross-tenant implementation. Until then, it remains **Deferred** and non-binding.
