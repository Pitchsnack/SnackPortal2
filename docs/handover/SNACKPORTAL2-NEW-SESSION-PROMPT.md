# SNACKPORTAL2-NEW-SESSION-PROMPT

*Paste the following into a brand-new Claude session working in `D:\Pitchsnack\SnackPortal2`.*

---

You are continuing **SnackPortal2**, a contract-first multi-tenant investment-platform backend (FastAPI-free pure-Python core, PostgreSQL, React/Lovable frontend planned). Read `docs/handover/SNACKPORTAL2-HANDOVER-MASTER.md` first — it links the full handover package (CURRENT-STATUS, NEXT-PHASE, CONSTRAINTS, ARCHITECTURE-SUMMARY, GOVERNANCE-SUMMARY). Treat that package as the orientation source of truth; `CLAUDE.md` and `docs/PROJECT-HANDOVER-MASTER.md` §11–§19 are known-stale.

## Mandatory architecture (non-negotiable)

**The Physical Multi-Database MVP is mandatory:** one Control Database (control plane + Global Discovery Platform) plus one **physically separate PostgreSQL database per tenant** (ACME DB, ZETA DB, NOVA DB, …). One request → one active tenant → exactly one database. Never: a shared database, shared tenant tables, tenant_id row-filtering as isolation, workspace-as-filter, portal-side database access, Supabase business logic, or cross-tenant queries. Workspace = the UI representation of the **signed JWT tenant claim** (switching = new scoped token, audited). Ownership ≠ authorization. Global Record ≠ Tenant Record (import = one-directional copy, never sync). Lineage is tenant-resident and append-only, absolutely. Audit records carry references only — never names/emails/PII/payloads. Full list: `docs/handover/SNACKPORTAL2-CONSTRAINTS.md`.

## Current state (verified, `main` @ `ab8a925`, pushed to github.com/Pitchsnack/SnackPortal2)

- **Backend Build Phases 1–6 complete and verified**: control_plane, auth_router, database_router, import_service, lineage_service all built and test-enforced (166/166 stdlib tests; 22/22 architecture gates; import-linter 2/2; live-PostgreSQL lineage evidence on PG 17.10). `api_gateway` is a deliberate scaffold (`IMPLEMENTS_BEHAVIOR=False`); `frontend/` is deliberately empty.
- **Governance package D-33..D-37 Approved and registered** (Workspace, Operational Audit & Re-Import, Global Deal Directory, Ownership, Portal Contracts), with errata D-33-E1/D-34-E1. D-34 amends D-20 in part; D-35 extends D-31. Placeholders reserved: **IC-008** (Ownership), **IC-009** (Portal Contracts), **IC-010** (API Gateway Contract — the gateway contract D-37 requires).
- **Independently verified twice post-approval**: 92/100 PASS, then **95/100 PASS — GO** (end-of-session): zero ungoverned architecture drift; implementation 7/7 aligned.
- **Pending**: the contract amendments the package requires are specified but NOT executed — **current contract text remains authoritative until they land**. The as-built re-import upsert stays conformant (D-20) until the IC-003 amendment. GitHub CI's validate job is red **by design** at the mypy step (deliberate 45-error inventory awaiting an authorized burn-down).

## Governance rules you must follow

1. **Register entry → contract → code**, always. Contracts precede code; no implementation without an explicitly authorizing execution PRD; review/verification PRDs are documentation-only; authorization does not carry between PRDs. No approved ADR may be silently replaced.
2. For the pending amendments, consume **Contract Amendment Inventory R2** (`D:\Pitchsnack\PRD\2. Governance Chain Remediation\`) and the errata — not raw ADR bodies (two retain pre-errata wording).
3. **Standing condition, absolute:** no client, frontend, or network exposure of any backend surface before the IC-005/IC-002 amendments and the IC-010 gateway exist (edge enforcement is library-internal today).
4. Do not modify frozen Build Phases 1–5 except via governance; keep architecture tests green (they are the executable architecture definition).

## Next authorized phase: Contract Amendment Package

Per `docs/handover/SNACKPORTAL2-NEXT-PHASE.md`, in order: **Set A — IC-005 + IC-002 amendments** (Workspace Terminology + exact carrier-header enumeration + mandatory tenantless-CONTROL anomaly-audit rule; Tenant-Workspace alias + MembershipsForPrincipal operation + audit-section extension); **Set B — IC-001 + IC-003 amendments** (Global Deal Directory + Tenant Anonymity Rule + audit homes; Global-record ∨ Deal + platform-wide user-controlled re-import refining D-20 + merge constraints); then **IC-008 authoring**. Success = the contract chain fully aligned with D-33..D-37 as errata-corrected, no invariant weakened, architecture tests still green. **Parallel track available any time: the D-15 Provisioning Plan** — it must add a physical-distinctness verification of tenant databases (PostgreSQL system-identifier comparison; IsolationAnomaly on collision).

## Environment

Windows 10; Python 3.12.10 64-bit on PATH (all dev deps installed); PostgreSQL 17.10 service running — disposable test DB `snackportal2_test`, DSN `postgresql://postgres:postgres@localhost:5432/snackportal2_test` for the standalone `requires_pg` harness (`python backend/tests/lineage_service/requires_pg/test_pg_*.py`); gitleaks via its winget package path; Docker unusable (virtualization disabled) — use native PostgreSQL. Tests: `python -m pytest tests/architecture -q` and per-file standalone runners from `backend/`.

Begin by reading the handover master, confirm the repo is at `ab8a925` and clean, then await (or execute, if already granted) authorization for the Contract Amendment Package.
