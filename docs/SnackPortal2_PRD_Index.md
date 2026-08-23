# SnackPortal2 — PRD Index (two-track numbering)

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
| B-7 | API Gateway | Backend Phase 7 / S5 PRD 16 | ⛔ **RETIRED as a build target** (D-46, 2026-08-21). Core *was* built under PRD 04 V2/V3 (`IMPLEMENTS_BEHAVIOR = True`) — the earlier "scaffold; V2 next" status was stale. **IC-010 is now `Superseded`**; the `api_gateway` package is category **D — old architecture, do not port**, untouched on disk pending Phase 1+. Superseded by **B-13**. |
| B-13 | **FastAPI BFF** — the single frontend-facing ingress | new (D-46 / IC-013) | ⬜ planned — Option A Phase 6. **Not a renamed Gateway:** enumerated operation surface, Pydantic models, no downstream body relay. |
| B-14 | **Access Control Service** | new (D-46 / IC-014) | ⬜ planned — Option A Phase 3. **The one genuinely greenfield service:** no permission engine exists in the current codebase. |
| B-15 | Contacts Service | new (Option A Phase 7) | ⬜ planned — **blocked on IC-015** (reserved, unauthored) |
| B-16 | Audit Service | new (Option A Phase 8) | ⬜ planned — durable sink for the ingress-edge audit classes; **blocked on migration M-1** |
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
- **Under B-7 (API Gateway — HISTORICAL):** PRD-P7-A1 (assessment), PRD 04 V1 (readiness review, READY_WITH_GUARDS), PRD 04 V2/V3 (implementation — **completed**), and the PRD 03 V4-R13→R18 governance arc. Retained for audit continuity; **B-7 is retired as a build target by D-46** and its successor is B-13 (FastAPI BFF).

> **D-46 note (2026-08-21).** Under the **Option A Clean FastAPI Rebuild**, the B- track's target is `Frontend → FastAPI BFF → FastAPI Services` with **zero API Gateway**. The existing B-1…B-7 work is a source of **requirements, validated behaviour, schemas and tests** — not architecture to preserve. **B-8 (AI Gateway & Model Router) is unaffected by the "zero Gateway" rule**: it is a *model-invocation* boundary (Canonical Overview Part 4B-C), unrelated to the superseded API Gateway — though it remains deferred and blocked on IC-006 being authored to Draft-complete.

---

*This index is a living reference. As PRDs are authored, add rows and update status. New product features get the next free P- number; new platform components get the next free B- number.*
