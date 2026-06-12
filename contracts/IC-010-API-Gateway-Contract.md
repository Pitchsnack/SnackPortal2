# IC-010 — API Gateway Contract

**Status:** Reserved (future contract — not yet authored) · **Phase:** Architecture Governance · **Type:** Placeholder (no design, no implementation)
**Authority source:** Reserved under **PRD-D33-D37-V2-R1** Work Package D, remediating **PRD-D33-D37-V2 finding MAJ-2** (the "API Gateway contract" was a mandatory dependency with no contractual vehicle).

> This is a **placeholder**. It reserves the contract number and records its future scope. It contains no gateway architecture, behavior, or implementation authority.

## Identification (traceability — resolves MAJ-2)
**IC-010 *is* the "API Gateway contract"** referenced as a hard prerequisite for portal implementation by: D-37 §17 and §22 ("until IC-009, the API Gateway contract, and the amendment package exist"), the IC-009 placeholder's Boundary ("until IC-009 is designed and approved and the API Gateway contract exists"), and the Architecture Decision Register's D-37 entry and closing note. All such references resolve here.

## Purpose
Contract the API Gateway — the sole portal-facing integration boundary (D-37 §5) and the component that wires edge enforcement of the tenant-context guarantees that are currently library-internal (the PRD 1A-R2 Critical-risk item).

## Future scope (to be designed at authoring time, not decided here)
- **Edge wiring per D-33 §4.6:** construct the Database Router's `RequestContext` exclusively from the Authenticator's `AuthContext`; pass recognized carriers into the IC-005 carrier-match check; strip inbound workspace cookies/query-strings; never read any workspace value as a tenant selector.
- **Consumption of the amended IC-005:** the enumerated recognized carrier header name(s); the mandatory carrier-on-CONTROL anomaly audit (per D-33-E1 Item 1).
- **Request path and prohibitions per D-37 §4/§5:** Portal → Gateway → Authentication Router → Database Router → exactly one database; no portal-side data paths.
- **Endpoint dispatch taxonomy:** tenant-context operations; control-plane reads (directory discovery for tenant-claimed principals per D-31/D-33; `MembershipsForPrincipal` per the IC-002 amendment); import initiation per IC-003 and the D-37 §9 Portal Import Rule.
- **Protection of internal surfaces (PRD-D33-D37-V2 Minor 6):** the internal control-plane read API must never be network-reachable from portal/client zones; gateway-fronted directory reads add IC-005 authentication plus reference-only access audit.
- **Readiness disclosure** per IC-001/D-10 (degraded is observability-only; non-disclosing liveness).
- **Acceptance criteria (already adopted):** D-33 §10 criteria 4–6 and D-37 §20 V1–V3 (including the frontend-repository audit: no database client, no Supabase data SDK, no PostgREST).

## Not yet authored · Implementation prohibited
No gateway behavior may be implemented until IC-010 is designed and approved through the standard change-control process (register entry → contract → code), sequenced after the Contract Amendment Package (the IC-005/IC-002 amendments are IC-010's inputs). The `api_gateway` package remains a scaffold (`IMPLEMENTS_BEHAVIOR = False`), enforced by the architecture test suite.

## Dependencies
**D-37** (portal rules) · **D-33** (workspace/carrier wiring, as corrected by D-33-E1) · **IC-005** (authentication routing; pending Workspace Terminology amendment) · **IC-002** (pending MembershipsForPrincipal amendment) · **IC-001/D-10** (readiness) · **IC-009** (portal contracts, reserved) · **D-30** (isolation defense-in-depth).
