# SNACKPORTAL2-NEXT-PHASE

**Handover File C — the next authorized phase (as of `ab8a925`, 2026-06-12)**

## Next Authorized Phase: Contract Amendment Package

Execute the contract amendments that the Approved D-33..D-37 package requires. **The Physical Multi-Database MVP is mandatory** — no amendment may weaken physical isolation, and every change follows the frozen order **register entry → contract → code** (the register entries already exist; this phase is the *contract* step; code follows only under later execution PRDs).

**Authoritative specification:** *Contract Amendment Inventory R2* (`D:\Pitchsnack\PRD\2. Governance Chain Remediation\PRD-D33-D36-P1-R1 — Contract Amendment Inventory R2.md`). Consume the Inventory and the errata (D-33-E1/D-34-E1) — **not raw ADR bodies** (two retain pre-errata wording).

## Objectives (in order)

### Set A — IC-005 Amendment + IC-002 Amendment (D-33 set, per D-33-E1)
- IC-005: Workspace Terminology clause; **exact recognized carrier header enumeration**; tenantless-CONTROL carrier rule (ignored by routing, claim-only) with **mandatory anomaly-audit emission** (D-33-E1 Item 1); cookies/query-strings prohibited as carriers.
- IC-002: Tenant-Workspace alias (editorial); **MembershipsForPrincipal** operation added to the API Contract table (self-scoped-or-CONTROL, audited — D-33-E1 Item 2; implementation later, at gateway execution); **audit-section extension** (administrative/runtime/tenant-export-operation/ownership-audit classes under the Global Audit Representation Rule); Control-DB audit retention governance (shared with IC-001).
- Execution-PRD acceptance items to carry: anomaly-audit emission + the tenantless-CONTROL regression test.

### Set B — IC-001 Amendment + IC-003 Amendment (D-34/D-35 set)
- IC-001: Global Deal Directory at all five touchpoints; discovery-metadata category definitions + **Tenant Anonymity Rule** (with CI/unit enforcement at execution — `DirectoryRecord.attributes` is currently unconstrained); Publication + global-Export audit home **including directory-mutation audit (currently Not Implemented per D-34-E1)**; reference-only payload-minimization rule for every audit class; audit retention.
- IC-003: Global-record definition extension (∨ Deal); **user-controlled re-import** (Import New Copy / Replace Existing / Ignore) explicitly refining approved D-20, stated **platform-wide** (any initiator); future-merge constraints (discrete, user-initiated, lineage-appending, never automatic, never write-back); IC-004 "scheduled import" actor-example harmonization; D-20 deal natural-key semantics.

### IC-008 — Ownership Contract authoring (D-36)
Eligibility matrix over D-32 roles; initial-owner-on-import; transfer workflow per the Audit Residency Rule; `owner_agent_ref`/`owner_ai_agent_ref` record-shape amendments; the open decision: named global-record ownership **mandatory vs optional**; AI activation stays IC-006-gated.

## Success Criteria

1. Contract chain fully aligned with **D-33, D-34, D-35, D-36, D-37** (as errata-corrected): every register "amend/extend" obligation has landed as contract text; Inventory R2 items all checked off.
2. No frozen invariant weakened; each amendment's review confirms the five invariants and the **mandatory Physical Multi-Database MVP** explicitly.
3. D-20's register annotation matches the amended IC-003 (supersession completed, not just declared).
4. After Set A+B: IC-010 authoring is unblocked (its declared inputs exist).
5. Working tree stays docs/contracts-only; architecture tests stay 22/22.

## Parallel Track (no dependency)

**D-15 Provisioning Plan** — may start immediately. Must include the **physical-distinctness verification** (compare PostgreSQL system identifiers across tenants and vs the Control DB at VerifyTenant/ReassociateDatabase; audit collisions as IsolationAnomaly) so physical separation becomes platform-verified, not just process-guaranteed.

## Recommended ride-alongs (small, docs-only)

Front-door docs refresh (CLAUDE.md, Project-Overview.md, old handover §11–§19); commit the governance corpus (Inventory R2, verification reports, authorizing PRDs) into `docs/governance/`.
