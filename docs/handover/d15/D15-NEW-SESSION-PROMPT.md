# D15-NEW-SESSION-PROMPT

*Paste the following into a new Claude session working in `D:\Pitchsnack\SnackPortal2`.*

---

You are continuing SnackPortal2 Phase 3B after D15 architecture approval-readiness.

Read `docs/handover/d15/D15-HANDOVER-MASTER.md` first.

Current verified state:
- D15-ARCH-SPEC-01 is approval-ready.
- D15-ARCH-SPEC-01-R1 was executed.
- Output-D light re-review returned PASS.
- 0 Critical / 0 Major / 0 blockers.
- Physical Multi-Database MVP is mandatory.
- One Request → One Active Tenant → One Database is absolute.
- Tenant-vs-tenant distinctness is specified.
- Tenant-vs-Control-DB distinctness is specified.
- No implementation is authorized.

The D15 PRD chain + specification live out-of-repo under `D:\Pitchsnack\PRD\6.0 Provisioning Architecture Speciication\`. The repo backend is frozen; `api_gateway` is a scaffold; `frontend/` is empty by design.

Your first task is to create PRD-D15-IMPL-01, the Provisioning Architecture Implementation Authorization PRD (explicit and narrow — only the implementation work required to satisfy the approved D15 architecture; see `D15-NEXT-PHASE.md` for the required scope).

Do not write code.
Do not create databases.
Do not provision infrastructure.
Do not modify contracts.
Do not modify ADRs.
Do not implement API Gateway or Database Router.
Do not begin implementation until PRD-D15-IMPL-01 is independently reviewed and approved.
