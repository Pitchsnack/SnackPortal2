# HANDOVER-MASTER

**SnackPortal2 — Physical Multi-Database MVP Governance Program · Cross-Session Handover**
Generated under **PRD-HO-03** · Repository: `main` @ `f06d8f5` (clean; backend frozen). **Supersedes the PRD-HO-02 package.**

> A brand-new Claude session bootstraps **entirely from this package** — start here, not from `CLAUDE.md` or `docs/PROJECT-HANDOVER-MASTER.md §11–§19` (both known-stale; tracked front-door-docs carry-forward).

## Headline state

| | |
|---|---|
| **Program status** | **Governance Complete + Phase 3A (API Gateway Architecture Specification) COMPLETE & VERIFIED.** |
| **Current commit / branch** | `main` @ `f06d8f5` (clean working tree; backend byte-identical since `0c2133a`; 22/22 architecture gates; 166/166 stdlib tests). |
| **Current phase** | Phase 3A closed; awaiting Phase 3B authorization. |
| **Next authorized phase** | **Phase 3B — PRD-D15-01 Provisioning Architecture** — **READY-WITH-CONDITIONS** (see [NEXT-PHASE](NEXT-PHASE.md)). |
| **Physical Multi-Database MVP** | **Mandatory · Active · Verified.** Zero ungoverned drift. |
| **Latest session verification** | **PRD-SP2-SESSION-V2 — PASS WITH AMENDMENTS** (tracked carry-forwards only; no drift). |

## Completed phases
- **Backend Build Phases 1–6** — complete, frozen, verified (live-PG on PG 17.10).
- **Governance** — D-33→D-37 approved; Contract Amendment Package CAP-01A/B/C executed + verified; IC-010 authored.
- **Phase 3A** — **AGW-ARCH-SPEC-R2** API Gateway Architecture Specification authored + **clean PASS**.

## Handover file index
- [CURRENT-STATUS](CURRENT-STATUS.md) · [COMPLETED-WORK](COMPLETED-WORK.md) · [ARCHITECTURE-SUMMARY](ARCHITECTURE-SUMMARY.md) · [DRIFT-ASSESSMENT](DRIFT-ASSESSMENT.md) · [NEXT-PHASE](NEXT-PHASE.md) · [CONSTRAINTS](CONSTRAINTS.md) · [NEW-SESSION-PROMPT](NEW-SESSION-PROMPT.md)

## Critical constraints
**Register → Contract → Specification → Code.** Contracts precede implementation. Authorization never carries between PRDs. **The Physical Multi-Database MVP cannot be weakened.** **No API Gateway implementation is authorized — `api_gateway` remains scaffold only (`IMPLEMENTS_BEHAVIOR=False`).**

## ⚠️ Corpus location note
The Phase-3A gateway **specification + verification corpus currently lives out-of-repo** under `D:\Pitchsnack\PRD\5. API Gateway Architecture\` (a tracked carry-forward: commit it into the repo). The repo at `f06d8f5` does **not** yet contain `AGW-ARCH-SPEC-R2` — only this refreshed `docs/handover/` package.

## Session summary
**PRD-SP2-SESSION-V2 = PASS WITH AMENDMENTS.** **Phase 3B Ready** — subject to the D-15 Tenant Physical Distinctness Verification requirement (see [NEXT-PHASE](NEXT-PHASE.md)).
