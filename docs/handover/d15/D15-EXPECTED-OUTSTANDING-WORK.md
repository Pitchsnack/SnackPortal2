# D15-EXPECTED-OUTSTANDING-WORK

**Expected outstanding work and pending artifacts — NOT drift.** These items reflect the project's **architecture-first posture**: no implementation has been authorized, so deployment, the implementation-authorization PRD, and frontend migration are **expected future work**, not deviations from the approved architecture. One boundary is a forward **watch item**.

---

## Expected Outstanding Work A — Physical Databases Not Yet Deployed

**Status:** `EXPECTED FUTURE WORK`

The architecture now specifies the Physical Multi-Database MVP, but actual Control DB and tenant DBs are **not yet provisioned**.

**Reason:** No implementation authorization PRD exists yet. The system is **architecture-ready, not physically implemented**.

---

## Expected Outstanding Work B — Frontend / Lovable Data Path Not Yet Proven Detached

**Status:** `EXPECTED FUTURE WORK`

The Lovable frontend data access must eventually be **verified to call the approved API Gateway** and **not rely directly on Supabase tables** for governed multi-database operations.

**Future required path:**
```text
Lovable UI
→ API Gateway
→ Database Router
→ Control DB / Tenant DBs
```
**Prohibited:** `Lovable UI → Supabase table direct multi-database business logic`.

---

## Pending Artifact C — Implementation Authorization PRD Not Yet Written

**Status:** `PENDING ARTIFACT`

The D15 architecture is approval-ready, but no implementation authorization PRD exists yet.

**Required next artifact:**
```text
PRD-D15-IMPL-01
Provisioning Architecture Implementation Authorization PRD
```
(See `D15-NEXT-PHASE.md`. Implementation may not begin until it is independently reviewed and approved.)

---

## Watch Item D — API Gateway / Database Router Boundary

**Status:** `WATCH`

The D15 specification assumes the API Gateway and Database Router boundaries from IC-010 and IC-005. Future implementation must continue to satisfy:
```text
Gateway ≠ Database Resolution
Database Router = sole database selector
```
