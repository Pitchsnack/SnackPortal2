# D15-NEXT-PHASE

## Next phase

```text
PRD-D15-IMPL-01
Provisioning Architecture Implementation Authorization PRD
```

This is the **first artifact that may authorize implementation** — but **only after its own independent review and approval.** Until then, no code, database, infrastructure, or deployment work is permitted.

`PRD-D15-IMPL-01` must be **explicit and narrow**: it must not authorize broad backend implementation, only the implementation work required to satisfy the approved `D15-ARCH-SPEC-01`.

## Required scope for PRD-D15-IMPL-01

1. Control DB provisioning model.
2. Tenant DB provisioning model.
3. Registry association implementation.
4. Secret reference implementation.
5. Physical Distinctness Verifier implementation.
6. Tenant-vs-tenant distinctness checks.
7. Tenant-vs-Control-DB distinctness checks.
8. Write-sentinel or equivalent verification.
9. IsolationAnomaly event handling.
10. Fail-closed routing behavior.
11. Router cache invalidation after association changes.
12. Reference-only operational audit events.
13. No cross-tenant request fan-out.
14. No frontend database routing.
15. No workspace database routing.
16. No portal database routing.
17. No implementation outside D15 scope.

## Governance sequence (where we are)

```text
Register
→ Contract
→ Authoring PRD
→ Readiness Verification
→ Architecture Specification          ← D15-ARCH-SPEC-01 (approval-ready) ✅
→ Independent Specification Review     ← done (§27 + R1 + light re-review PASS) ✅
→ Implementation Authorization PRD     ← PRD-D15-IMPL-01  (NEXT — not yet written)
→ Code                                 ← blocked until the above is approved
```
