# NEW-SESSION-PROMPT

*Paste the following into a brand-new Claude session working in `D:\Pitchsnack\SnackPortal2`.*

---

You are continuing **SnackPortal2**, a contract-first multi-tenant investment-platform backend (FastAPI-free pure-Python core, PostgreSQL, React/Lovable frontend planned). **Read `docs/handover/HANDOVER-MASTER.md` first** — it links the full handover package (CURRENT-STATUS, COMPLETED-WORK, ARCHITECTURE-SUMMARY, DRIFT-ASSESSMENT, NEXT-PHASE, CONSTRAINTS). Treat that package as the orientation source of truth; `CLAUDE.md` and `docs/PROJECT-HANDOVER-MASTER.md §11–§19` are known-stale.

## Mandatory architecture (non-negotiable)

**The Physical Multi-Database MVP is mandatory:** one Control Database (control plane + Global Discovery Platform) plus one **physically separate PostgreSQL database per tenant**. One request → one active tenant → exactly one database. Never: a shared database, shared tenant tables, `tenant_id` row-filtering as isolation, workspace-as-routing-input, portal-side database access, Supabase business logic, or cross-tenant queries. Workspace = the UI representation of the signed JWT tenant claim. Ownership ≠ authorization/routing/residency (reference-only). Global Record ≠ Tenant Record (import = one-directional copy, never sync). Lineage is tenant-resident and append-only. Audit carries references only. Full list: `docs/handover/CONSTRAINTS.md`.

## Current state (verified — `main` @ `de3169a`, pushed to github.com/Pitchsnack/SnackPortal2)

- **Governance Complete.** D-33→D-37 Approved (errata D-33-E1/D-34-E1); the Contract Amendment Package (CAP-01A IC-005+IC-002, CAP-01B IC-001+IC-003, CAP-01C IC-008) executed and each R1-reviewed PASS; **PRD-CAP-01-V1** independently verified the whole package **PASS (99/100, MVP PASS, 0 Critical/0 Major)**; **IC-010 API Gateway Contract authored** (PRD-IC010-01-R1) with a §11 adversarial review **PASS** (all 14 invariant-disproof attempts failed).
- **Backend Build Phases 1–6 complete and verified** (166/166 stdlib tests; 22/22 architecture gates; live-PG lineage on PG 17.10). `api_gateway` is a deliberate scaffold (`IMPLEMENTS_BEHAVIOR=False`); `frontend/` is deliberately empty. Backend byte-identical since `0c2133a`.
- **Zero ungoverned architecture drift** (DRIFT-ASSESSMENT). The only known carry-forwards are documentation-level or tracked-execution items (stale front-door docs; the pending IC-005/IC-002 audit-section extension with no vehicle; register IC-010-Final refresh; tenant-DB distinctness check for D-15; mypy 45-error CI burn-down).

## Governance rules you must follow

1. **Register entry → contract → code**, always. Contracts precede code; no implementation without an explicitly authorizing execution PRD; review/verification PRDs are documentation-only; authorization does not carry between PRDs; no approved ADR may be silently replaced.
2. **Standing condition, absolute:** no client, frontend, or network exposure of any backend surface until the gateway is *built* (IC-010 contracts the edge; it is a scaffold today).
3. Do not modify frozen Build Phases 1–5 except via governance; keep architecture tests green (they are the executable architecture definition).
4. The governance corpus (PRDs, reviews, Inventory R2) lives under `D:\Pitchsnack\PRD\`.

## Next authorized phase

**PRD-AGW-01 — API Gateway Architecture (Phase 3A).** Then PRD-D15-01 Provisioning Architecture (3B, parallel-ready, must add tenant-DB physical-distinctness verification), IC-009 Portal Contracts (3C), Frontend Integration Governance (3D). **None is authorized yet.** See `docs/handover/NEXT-PHASE.md`.

## Environment

Windows 10; Python 3.12.10 64-bit on PATH (all dev deps installed); PostgreSQL 17.10 service running — disposable test DB `snackportal2_test`, DSN `postgresql://postgres:postgres@localhost:5432/snackportal2_test` for the standalone `requires_pg` harness; gitleaks via its winget package path; Docker unusable (virtualization disabled) — use native PostgreSQL. Tests: `python -m pytest tests/architecture -q` and per-file standalone runners from `backend/`. **Multi-agent workflows:** pin a plain model id (e.g. `opus`) — the `claude-fable-5[1m]` context-variant tag does not resolve on the subagent path.

## On startup, do exactly this — then stop:

1. Read all `docs/handover/` files.
2. Verify repository state: `git -C D:\Pitchsnack\SnackPortal2 status` (expect clean) and current commit `git rev-parse --short HEAD` (expect `de3169a` or later).
3. Verify branch is `main`.
4. Verify architecture tests: from `backend/`, `python -m pytest tests/architecture -q` (expect 22 passed).
5. Verify the contract inventory (`contracts/` — IC-001..IC-010) and the ADR inventory (`docs/Architecture-Decision-Register.md` — D-01..D-37).
6. **Do not execute anything. Await explicit authorization** for the next phase.
