# SnackPortal2 — PRD Index (two-track numbering)

> ## ✅ RATIFIED — D-45 retires B-7 (`experiment/complete-api-gateway-removal-mvp`)
>
> The prior DRIFT flag left the **B-7 API Gateway** row as-is because the index tracked `main`.
> **Dan has now decided (D-45, 2026-08-11): the API Gateway component is removed from the Controlled
> Local MVP architecture**, and the ratified boundary is the approved authenticated public edge owned
> by the service that owns the route. The B-7 row is therefore **retired and replaced by B-13**
> below — recorded, not deleted.
>
> See [D-45](D-45-Gateway-Free-Public-Edge-Architecture.md) and the
> [Architecture Decision Register](Architecture-Decision-Register.md).
> **D-45 is a Controlled Local MVP architecture decision, not a production approval**; no push, PR,
> merge, DDL, SecretRef, credential, Keycloak, or standing-runtime change is authorized by it, and
> **only Dan may explicitly authorize the specific future PR merge**. On `main` nothing here has moved.

> **Decision D5:** PRDs use two prefixed tracks so the old number clashes disappear.
> - **P- = Product PRDs** — user-facing features, built in Lovable.
> - **B- = Backend / Platform PRDs** — vendor-neutral infrastructure, external.
>
> Backend governance sub-PRDs (the review → execute → verify cycles) keep their existing IDs as **children** of their B- parent; they are not renumbered.

**Status key:** ✅ built/accepted · 🟡 partial / in progress · ⬜ planned · ⏸ deferred

---

## Product track (P-) — built in Lovable

| New ID | Title | Old ref | Status (per S6 Lovable report) |
|---|---|---|---|
| P-1 | Tenant Architecture | S5 PRD 1 | 🟡 multi-tenant exists (logical; physical pending) |
| P-2 | Authentication & RBAC | S5 PRD 2 | ✅ built |
| P-3 | Workspace Framework | S5 PRD 3 | ✅ built (workspace switching) |
| P-4 | Startup Ownership | S5 PRD 4 / S1 PRD 4 | ✅ built (dual Human+AI) |
| P-5 | Investor Ownership | S5 PRD 5 / S1 PRD 5 | ✅ built |
| P-6 | Deal Management | S5 PRD 6 / S1 PRD 6 | ✅ built |
| P-7 | Deal Sharing | S5 PRD 7 / S1 PRD 7 | ✅ built |
| P-8 | Communication & Messaging Hub | S5 PRD 8 | 🟡 notifications partial; messaging not built |
| P-9 | Startup Portal | S5 PRD 9 | ⬜ planned |
| P-10 | Investor Portal | S5 PRD 10 | ⬜ planned |
| P-11 | Document & Data Room Mgmt | S5 PRD 11 | 🟡 deal_documents partial |
| P-12 | Analytics & Reporting | S5 PRD 12 | 🟡 dashboard placeholder |
| P-13 | Integration Framework | S5 PRD 13 | ⬜ planned |
| P-14 | Billing & Subscription | S5 PRD 14 | 🟡 subscription table only |
| P-15 | Enterprise Compliance & Security | S5 PRD 15 | 🟡 audit built; security partial |
| P-16 | Collaboration Tools — email, chat/messaging, **calendar/appointment booking** | new (DoD) | ⬜ planned (MVP; AI plugs in later) |

## Backend / Platform track (B-) — external infrastructure

| New ID | Title | Old ref | Status |
|---|---|---|---|
| B-0 | **Physical Multi-Database Architecture (baseline)** | S4 PRD 8 | ✅ governing (~88% aligned) |
| B-1 | Repository & Foundation | Backend Phase 1 | ✅ accepted |
| B-2 | Control Plane | Backend Phase 2 | ✅ accepted |
| B-3 | Authentication Layer | Backend Phase 3 | ✅ accepted |
| B-4 | Database Router | Backend Phase 4 | ✅ accepted |
| B-5 | Import Service | Backend Phase 5 | ✅ accepted |
| B-6 | Lineage Service | Backend Phase 6 | ✅ accepted |
| ~~B-7~~ | ~~API Gateway~~ | Backend Phase 7 / S5 PRD 16 | **⊘ RETIRED by D-45 (2026-08-11)** — built, then removed from the MVP architecture; **PRD 04 V2 is not authored**. Replaced by **B-13**. |
| **B-13** | **Approved Authenticated Public Edges** (public Startup edge · public Workspace edge, behind the shared public-boundary security kernel) | new (D-45) | ✅ built on `experiment/complete-api-gateway-removal-mvp`; governed by **IC-010** (retargeted). Frontend cutover to the two origins ⬜ (IC-010 §Y); live proofs ⬜ (see Action Tracker #21–#23) |
| B-8 | AI Gateway & Model Router | S5 PRD 17 | ⏸ deferred (Intelligence) |
| B-9 | Agent Framework | S5 PRD 18 | ⏸ deferred |
| B-10 | Global Research & Discovery Engine | S5 PRD 19 | ⏸ deferred |
| B-11 | Cross-Tenant Learning Platform | S5 PRD 20 | ⏸ deferred |
| B-12 | Control AI Ecosystem | S1 PRD 1 (Control AI) | ⏸ deferred (D6) |

---

## How the old clashes resolve

- **"PRD 8" clash:** product → **P-8** (Communication Hub); architecture → **B-0** (Physical Multi-DB). They no longer share a number.
- **"PRD 1" clash:** product → **P-1** (Tenant Architecture); Control AI → **B-12** (deferred). No longer share a number.

## Backend governance sub-IDs (kept as-is, filed under their parent)

These keep their original names — just file them under the parent B- item:
- **Under B-6 (Lineage):** PRD-P6-R2, PRD-P6-E1, PRD-P6-V1.
- **Under ~~B-7~~ → B-13 (public edges):** PRD-P7-A1 (assessment), PRD 04 V1 (readiness review, READY_WITH_GUARDS) and the PRD 03 V4-R13→R18 governance arc are **historical records of the retired B-7**. **PRD 04 V2 is superseded by D-45 and is not authored.** B-13's governing contract is **IC-010** (retargeted to the *Public Edge Ingress Contract*); any **new** public edge requires an IC-010 §A.2 amendment plus a register entry before it may be served.

---

*This index is a living reference. As PRDs are authored, add rows and update status. New product features get the next free P- number; new platform components get the next free B- number. **A retired component keeps its number** (B-7) rather than having it reused — the row records what was retired and by which decision.*
