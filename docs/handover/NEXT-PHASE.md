# NEXT-PHASE

**The approved next sequence as of `f06d8f5` (2026-06-13, PRD-HO-03).** Nothing below is authorized to execute yet — each phase begins only under its own explicitly-authorizing execution PRD (register → contract → code).

## Next Authorized Phase: **Phase 3B — PRD-D15-01 Provisioning Architecture Specification**

**Readiness: READY-WITH-CONDITIONS** (PRD-SP2-SESSION-V2). Parallel-ready — no dependency on further gateway work.

### Mandatory Condition (from PRD-SP2-SESSION-V2)

**D-15 MUST implement Tenant Physical Distinctness Verification.**

> The platform currently cannot detect two tenant references resolving to the same physical PostgreSQL database.
>
> PRD-D15-01 MUST close this gap.

### Required Mechanism

```text
Compare PostgreSQL system identifiers (across tenant databases and vs the Control DB).

If two tenant references resolve to the same physical database:
    Emit IsolationAnomaly
    Fail verification
```

(IC-010 §P reserves the contractual hook; `AGW-ARCH-SPEC-R2 §22` reserves the check to D-15.)

## Parallel-Ready

- **Phase 3C — IC-009 Portal Contracts** — unblocked (IC-010 + the API Gateway Architecture Specification now exist). Per-role × per-directory visibility matrix; portal DTO/channel contracts.
- **Phase 3D — Frontend Integration Governance** — after IC-009 + the gateway.

## Standing Conditions (absolute)

1. **No client, frontend, or network exposure of any backend surface** until the gateway is *built* under a separate implementation-authorization PRD. The API Gateway Architecture Specification is architecture only.
2. Contracts precede implementation; authorization does not carry between PRDs.
3. No approved ADR or contract may be silently replaced.
4. **The Physical Multi-Database MVP is mandatory throughout — no phase may weaken it.**

## Useful ride-alongs (non-blocking)
Commit the gateway corpus into the repo; refresh the IC-010 register row + front-door docs; name a vehicle for the IC-002 audit extension.
