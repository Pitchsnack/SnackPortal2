# SnackPortal2 New Session Prompt

Use this prompt to start the next Claude session.

```text
Start SnackPortal2 backend governance session.

First verify live git. Do not rely on memory.

Read:

- docs/handover/HANDOVER-MASTER.md
- docs/handover/CURRENT-STATUS.md
- docs/handover/COMPLETED-WORK.md
- docs/handover/DRIFT-ASSESSMENT.md
- docs/handover/NEXT-PHASE.md
- docs/handover/ARCHITECTURE-SUMMARY.md
- docs/handover/CONSTRAINTS.md

Verify:

- current branch / HEAD
- origin/main
- clean tracked working tree
- IC-009 Final / IC-009-R1
- IC-009-ADOPT row and detail heading exactly once
- PR #11 merge state if V4-R17 has not yet run
- DEC-11 remains binding
- Physical Multi-Database MVP is mandatory

Do not start API Gateway implementation.

Do not modify repository files without an approved execution PRD.

Do not bind ownership-audit DTO residency until the IC-002 ownership-audit-section extension lands.

Gateway must not resolve databases directly.

Database Router remains the sole DB selector.

Next governed task:

If V4-R16 is merged, run V4-R17 post-merge verification.

If V4-R16 is not merged, review / merge V4-R16 first.

After V4-R17 passes, prepare API Gateway readiness PRD only. Do not jump directly to implementation.
```

## Non-negotiable constraints

Physical Multi-Database MVP is mandatory.

DEC-11 remains binding.

API Gateway implementation has not started unless a later verified PRD says otherwise.
