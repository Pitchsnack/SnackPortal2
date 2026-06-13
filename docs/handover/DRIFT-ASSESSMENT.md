# DRIFT-ASSESSMENT

**Handover H5 — the most important file. Drift, supersession, alignment, reservation, prohibition, and the explicit Physical Multi-Database MVP verification. As of `de3169a` (2026-06-13).**

This assessment is independently grounded: it consolidates **PRD-D33-D37-V2 (92/100 PASS)**, **PRD-SP2-SESSION-R1 (95/100 PASS, zero ungoverned drift)**, and the whole-package **PRD-CAP-01-V1 (99/100 PASS — MVP PASS, 0 Critical/0 Major, every drift category ABSENT)** plus the IC-010 §11 review (14/14 invariant-disproof attempts failed).

## What drift occurred?

**None in architecture.** No approved decision was silently replaced; every supersession is explicit, cited, and registered (the no-silent-supersession rule, D-34 V8, held). The only ungoverned inconsistency anywhere in the corpus is **stale front-door documentation** (`CLAUDE.md` still says "planning phase, no code yet"; `docs/PROJECT-HANDOVER-MASTER.md §11–§19`; old `Project-Overview` text) — architecture-neutral, tracked as a docs-refresh item.

## Section A — Approved Supersessions (governed, citation-chained — NOT drift)

The original **PRD 1** product assumptions were **deliberately superseded by the baseline corpus's own later decision** (PRD 8A Option B → PRD 8B.0 "Physical Multi-Database from MVP"), and carried into IC-001..IC-005, D-30/D-31, and D-33..D-37:

| Superseded model | Superseded by | Why |
|---|---|---|
| **Shared database model** | PRD 8A/8B Option B — one Control DB + one physically separate DB per tenant | A shared store cannot give physical tenant isolation; physical separation is the security boundary (D-30) |
| **`tenant_id` isolation model** | Physical Multi-Database MVP | `tenant_id` survives only in governed non-isolation roles (registry key, claim identifier, pool key, audit reference) — never row-filtering over a shared store (audited: 318 occurrences, zero filtering) |
| **Supabase-first model** | OIDC + portable PostgreSQL; vendor SDKs ban-listed | No Supabase RLS-as-authorization, no Supabase data SDK/PostgREST; cloud-portable only (AWS RDS / Azure / Cloud SQL / self-hosted) |
| **Lovable-generated database model** | Lovable is presentation-only; schema is platform-owned | No Lovable runtime/platform dependence in business logic; the frontend is presentation, never a data path (D-37) |

The one ADR-level supersession — **D-34 amending D-20's re-import default** (upsert → user-controlled) — is explicitly annotated in the register and in IC-003.

## Section B — Alignment Verification

| Property | Result | Evidence |
|---|---|---|
| **Physical Multi-Database MVP** | **PASS** | one Control DB + per-tenant physical DBs; one request → one database; architecture gates 22/22 |
| Single Database | **NO** | no shared store introduced anywhere; every "shared" mention is a prohibition |
| Shared Schema | **NO** | no table/schema/store spans tenants (IC-002 Inv 4; IC-004 Inv 4) |
| `tenant_id` Isolation | **NO** | `tenant_id` only in governed non-isolation roles; never a row-filter |
| Workspace Routing | **NO** | workspace is UI-only; sole routing authority is the signed claim (IC-005); IC-010 §11 disproof failed |
| Portal Routing | **NO** | portals are presentation-only; gateway-only data access (D-37); IC-010 Portal Boundary |
| Supabase / vendor coupling | **NO** | no Supabase/Lovable logic; CI ban-lists enforced |

## Section C — Remaining Risks (tracked, none blocking)

| Risk | Status / mitigation |
|---|---|
| **Tenant-DB physical distinctness verification** | Governance-guaranteed but **not yet platform-verified** — two tenants' secret refs resolving to the same DSN would silently co-reside (pools key by tenant_id, never compare physical target). **D-15 execution PRD must add a distinctness check** (compare PostgreSQL system identifiers; `IsolationAnomaly` on collision). IC-010 §P reserves the contractual hook. |
| **D-15 provisioning dependency** | The first real Control DB + per-tenant provisioning is unbuilt; D-15 Provisioning Architecture is **Phase 3B**, parallel-ready. |
| **IC-009 (Portal Contracts) pending** | Reserved by D-37; authoring is **Phase 3C**. Portal implementation blocked until IC-009 + the (now-existing) gateway contract. |
| **IC-006 (AI) pending** | Draft, post-MVP (D-02). AI surfaces gated; `owner_ai_agent_ref` stays NULL until IC-006. |
| **IC-007 (cross-tenant) pending** | Deferred; cross-tenant prohibition in force; any future model must preserve D-36 V7. |
| **IC-005/IC-002 audit-section extension** | The runtime/operational audit classes (incl. the gateway's `RouteDenied`/`IsolationAnomaly`/`CarrierMismatch`/`CarrierOnControlAnomaly`) and the **tenant-resident ownership-audit class** are specified (Inventory R2) but **not executed and have no named authoring vehicle** — a governance carry-forward. |
| **Register hygiene** | Register could use an **IC-010 Final row / closing-note refresh** (a register edit, out of HO-02 scope). |
| **CI mypy** | 45-error inventory keeps CI `validate` red by design until an authorized burn-down. |

## §6 — Independent Drift Analysis (Overview / PRD 8A / PRD 8B / ADRs / Contracts / Repository)

| Classification | Items |
|---|---|
| **Aligned** | Backend (provably physically multi-DB, frozen); IC-001..IC-005/IC-008/IC-010 vs D-33..D-37; the Physical Multi-Database MVP across every layer; PRD 8A/8B Option B realized |
| **Superseded** | PRD 1's shared-DB / `tenant_id` / Supabase-first / Lovable-owns-schema (Section A); D-20 re-import default (by D-34) |
| **Reserved** | IC-009 (Portal Contracts); IC-006 (AI); IC-007 (cross-tenant); ownership *fields* (IC-008-authorized, execution-deferred); D-15 distinctness hook (IC-010 §P) |
| **Not Yet Implemented** | API Gateway behavior; IC-002/IC-005 audit-section extension; ownership fields/workflows/audit persistence; directory-mutation audit; anonymity CI guard; provisioning (D-15); frontend/portals |

## §7 — Physical Multi-Database MVP Verification (mandatory)

**Physical Multi-Database MVP remains mandatory.**

| Question | Answer |
|---|---|
| Has any ADR weakened it? | **NO** — D-33..D-37 each preserve or reinforce it (frozen-invariant tables) |
| Has any Contract weakened it? | **NO** — CAP-01-V1 verified all five amended contracts + IC-008 + IC-010 preserve it |
| Has any Verification weakened it? | **NO** — every review returned MVP PASS / no drift |
| Has any Implementation weakened it? | **NO** — backend byte-identical since `0c2133a`; architecture gates 22/22 |

**Expected result: NO / NO / NO / NO — confirmed.**
