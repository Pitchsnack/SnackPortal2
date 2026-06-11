# SnackPortal2 — Project Overview

**Phase:** Architecture Planning · **Type:** Specifications & decisions only (no implementation code) · **Date:** 2026-06-05

This is the front door to SnackPortal2's architecture-planning artifacts. It summarizes **what has been created**: the interface contracts, the architecture decision record, and the decision packs that resolved each decision.

> **Status headline:** The **MVP architecture is frozen.** All five MVP contracts (IC-001–IC-005) are **Final**; IC-006 (AI Gateway) is intentionally deferred post-MVP. All MVP architecture decisions are resolved and recorded.

---

## What SnackPortal2 Is
A multi-tenant platform built on **physical multi-database isolation**: one **Control Database** for global/cross-tenant state and routing metadata, plus **one physically separate PostgreSQL database per tenant**. Core principles: cloud-portable PostgreSQL only, no vendor-specific business logic (no Supabase/Lovable lock-in), strict tenant isolation, and **contracts precede code**. See [../CLAUDE.md](../CLAUDE.md).

## Repository Map
| Path | Purpose | State |
|---|---|---|
| `contracts/` | Interface contracts IC-001…IC-006 — source of truth for system design | 5 Final, 1 Draft |
| `docs/` | Decision register, gap analysis, decision packs, this overview | Complete for MVP |
| `backend/` | FastAPI / Python backend | Empty (not yet implemented) |
| `frontend/` | React / TypeScript (Lovable) frontend | Empty (not yet implemented) |
| `infrastructure/` | IaC: Docker, Terraform, K8s, env templates | Empty (not yet implemented) |

---

## Interface Contracts (`contracts/`)
| ID | Title | Status | Purpose | Key decisions |
|---|---|---|---|---|
| **IC-001** | [Global Startup](../contracts/IC-001-Global-Startup-Contract.md) | 🔒 **Final** | Control-plane bring-up; two-phase bootstrap; global readiness | D-01, D-10, D-11, D-12 |
| **IC-002** | [Tenant Startup](../contracts/IC-002-Tenant-Startup-Contract.md) | 🔒 **Final** | Per-tenant registration, readiness, physical DB association | D-07, D-13–D-17 |
| **IC-003** | [Import](../contracts/IC-003-Import-Contract.md) | 🔒 **Final** | Global-to-tenant import-copy; tenant-owned copies | D-18–D-21, D-09 ingress |
| **IC-004** | [Lineage](../contracts/IC-004-Lineage-Contract.md) | 🔒 **Final** | Data provenance; append-only; AI-ready | D-08, D-22–D-25 |
| **IC-005** | [Authentication Routing](../contracts/IC-005-Authentication-Routing-Contract.md) | 🔒 **Final** | Auth, tenant context, routing; isolation enforcement | D-03–D-06, D-30, JWT |
| **IC-006** | [AI Gateway](../contracts/IC-006-AI-Gateway-Contract.md) | 📄 Draft (template) | Provider-agnostic AI boundary | post-MVP (D-02); D-26–D-29, D-09 egress |

## Architecture at a Glance
- **Bootstrap (D-01):** two-phase — Phase 0 control-plane uses a static-trust-anchor **system identity** (no DB lookup); Phase 1 runtime auth + tenant routing once the Control DB is online. Authentication is **separated from routing**.
- **Identity & auth (D-03/D-05/D-06):** hybrid identity (internal + OIDC-federated orgs); **OIDC stateless JWT**, no session store; the **signed tenant claim is authoritative** with carrier-match enforcement.
- **Tenancy (D-04/D-07):** 1:N membership, **exactly one active tenant per request → one database**, resolved registry-authoritatively.
- **Isolation (D-30):** defense-in-depth — authz + single-tenant routing + per-tenant credentials + audit; physical separation is the last line of defense; **no cross-tenant joins, ever**.
- **Tenant infra (D-13–D-17):** lazy bounded per-tenant pools; reference-based secret abstraction; IaC + control-plane provisioning; per-tenant readiness independence; expand/contract migrations.
- **Lineage (D-22–D-25):** minimal core + reference/code-only envelope; append-only + per-tenant hash-chaining; unified per-tenant provenance graph; AI-ready.
- **Import (D-18–D-21):** pluggable adapters (v1 Global + CSV/JSON); hybrid async/sync; idempotent re-import; batched/checkpointed; **import creates a tenant-owned copy, never synchronization**.

---

## Architecture Decision Record
The authoritative record is [Architecture-Decision-Register.md](Architecture-Decision-Register.md). The original analysis and reconciled statuses are in [Contract-Gap-Analysis.md](Contract-Gap-Analysis.md).

- **Resolved:** 25 numbered decisions (D-01–D-08, D-10–D-25, D-30) + **D-09 ingress** + the **JWT lifecycle**.
- **Open (all post-MVP, IC-006):** **D-26–D-29** + **D-09 egress**.
- **Standing business/legal action:** **D-08** — name the specific compliance floor regime and per-tenant values (the *mechanism* is fixed).

### Decision Packs (`docs/`)
| Pack | Resolved |
|---|---|
| [D-01-Bootstrap-Cycle-Resolution.md](D-01-Bootstrap-Cycle-Resolution.md) | D-01 (A+B: system identity + static trust anchor) |
| [D-02-to-D-05-Decision-Pack.md](D-02-to-D-05-Decision-Pack.md) | D-02 (defer AI), D-03 (hybrid identity), D-04 (1:N/one-active), D-05 (OIDC JWT) |
| [D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md](D-07-D13-D14-D15-D16-D17-Tenant-Infrastructure-Decision-Pack.md) | D-07, D-13, D-14, D-15, D-16, D-17 |
| [D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md](D-08-D22-D23-D24-D25-Lineage-Decision-Pack.md) | D-08, D-22, D-23, D-24, D-25 |
| [D-18-D19-D20-D21-D09-Import-Decision-Pack.md](D-18-D19-D20-D21-D09-Import-Decision-Pack.md) | D-18, D-19, D-20, D-21, D-09 ingress |
| [D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md](D-06-D10-D11-D12-D30-Finalization-Decision-Pack.md) | D-06, D-10, D-11, D-12, D-30, JWT lifecycle |

---

## MVP Architecture: Frozen
All MVP architecture decisions are resolved and incorporated; IC-001–IC-005 are **Final**.

**Change-control rule:** any change to frozen MVP behavior requires a **contract amendment first** — register entry → contract → code (per CLAUDE.md "contracts precede code").

## Remaining / Next Steps
- **IC-006 (AI Gateway)** — produce its decision pack (D-26–D-29 + D-09 egress) when AI is scheduled; expand template → spec.
- **D-08 named regime** — capture once business/legal decides (non-architecture).
- **Implementation** — when the build phase begins, backend/frontend/infrastructure trace back to these Final contracts.

## Document Index
- Contracts: `contracts/IC-001…IC-006`
- Decision record: [Architecture-Decision-Register.md](Architecture-Decision-Register.md) (authoritative) · [Contract-Gap-Analysis.md](Contract-Gap-Analysis.md)
- Decision packs: the six `D-…-Decision-Pack.md` / resolution files above
- Project guidance: [../CLAUDE.md](../CLAUDE.md)
