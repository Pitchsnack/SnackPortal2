# NEW-SESSION-PROMPT

*Paste the following into a brand-new Claude session working in `D:\Pitchsnack\SnackPortal2`.*

---

You are continuing **SnackPortal2**, a contract-first multi-tenant investment-platform backend (FastAPI-free pure-Python core, PostgreSQL, React/Lovable frontend planned). **Read `docs/handover/HANDOVER-MASTER.md` first** — it links the full handover package (CURRENT-STATUS, COMPLETED-WORK, ARCHITECTURE-SUMMARY, DRIFT-ASSESSMENT, NEXT-PHASE, CONSTRAINTS). Treat that package as the orientation source of truth; `CLAUDE.md` and `docs/PROJECT-HANDOVER-MASTER.md §11–§19` are known-stale (tracked front-door-docs carry-forward).

## Mandatory architecture (non-negotiable)

The **Physical Multi-Database MVP is mandatory**: one Control Database + one physically separate PostgreSQL database per tenant. One request → one active tenant → exactly one database. Never: a shared database, shared schema, `tenant_id` row-filtering as isolation, logical isolation, workspace/portal routing, gateway database-selection, Supabase/Lovable coupling, or cross-tenant queries.

## Current state (verified — `main` @ `f06d8f5`)

Governance Complete + **Phase 3A (`AGW-ARCH-SPEC-R2` API Gateway Architecture Specification) complete & verified PASS** (0 Critical / 0 unresolved Major, after the IC-010 §L remediation). **PRD-SP2-SESSION-V2 = PASS WITH AMENDMENTS**; zero ungoverned drift; MVP preserved. Backend frozen byte-identical since `0c2133a`; `api_gateway` is a scaffold (`IMPLEMENTS_BEHAVIOR=False`); `frontend/` empty by design. **Next authorized phase: Phase 3B — PRD-D15-01 Provisioning (READY-WITH-CONDITIONS: MUST add tenant-DB physical-distinctness verification).** The Phase-3A gateway spec + verification corpus lives out-of-repo under `D:\Pitchsnack\PRD\5. API Gateway Architecture\` (carry-forward: commit it into the repo).

## On startup, do exactly this — then stop:

1. Read all `docs/handover/` files.
2. Verify repository state: `git -C D:\Pitchsnack\SnackPortal2 status` (expect clean) and `git rev-parse --short HEAD` (expect `f06d8f5` or later); verify branch is `main`.
3. Verify the architecture gate: from `backend/`, `python -m pytest tests/architecture -q` (expect **22 passed**).
4. Verify the contract inventory (`contracts/` — IC-001..IC-010) and the ADR inventory (`docs/Architecture-Decision-Register.md` — D-01..D-37).
5. Confirm the **Physical Multi-Database MVP is still mandatory**.
6. Confirm **zero ungoverned drift**.
7. **Do not execute anything. Await explicit authorization** for the next phase.
