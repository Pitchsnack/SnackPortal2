# D15-DRIFT-LOG

**All drift discovered during the D15 session. Every item is CLOSED.** Drift = a deviation from approved architecture that was detected and corrected. (Expected future work is recorded separately in `D15-EXPECTED-OUTSTANDING-WORK.md` and is **not** drift.)

| Drift | Artifact where it appeared | Description | Risk | Correction artifact | Status |
|---|---|---|---|---|---|
| **1** | PRD-D15-01 → R1 → R2 → R2-E1 | Earlier authoring-chain drift (see below) | Could have weakened lifecycle conformance + governing-source integrity | R2, R2-E1 | **CLOSED** |
| **2** | PRD-D15-SPEC-01 | Titled like a specification, but content was still an authoring PRD | Governance-chain confusion; risk of skipping the actual approved spec | PRD-D15-AUTH-01 + D15-ARCH-SPEC-01 | **CLOSED** |
| **3** | PRD-D15-SPEC-01 §2 | Governing-source citation regression | Reopened closed governance drift; pointed audit/provisioning at wrong decisions | PRD-D15-SPEC-01-R1 (verified by PRD-D15-AUTH-01) | **CLOSED** |
| **4** | PRD-D15-SPEC-01 / D15-ARCH-SPEC-01 | Audit authority routed to D-17 | Audit modeled under the wrong governance authority | PRD-D15-SPEC-01-R1 + D15-ARCH-SPEC-01-R1 | **CLOSED** |
| **5** | intermediate spec versions | Physical distinctness softened | Two tenant references could resolve to the same physical DB and still pass | PRD-D15-SPEC-01-R1 + R1-E1 + D15-ARCH-SPEC-01 | **CLOSED** |
| **6** | D15-ARCH-SPEC-01 §4 I6 | One-request rule softened by a future-contract carve-out | Pre-authorized a future single-request multi-tenant-DB path; weakened the MVP invariant | D15-ARCH-SPEC-01-R1 | **CLOSED** |
| **7** | D15-ARCH-SPEC-01 §9 | Missing tenant-vs-Control-DB distinctness | A tenant could be provisioned onto / routed to the Control DB undetected | D15-ARCH-SPEC-01-R1 | **CLOSED** |
| **8** | D15-ARCH-SPEC-01 §14.2 | Audit "non-sensitive metadata" too broad | Escape hatch for names/emails/PII/payloads/secrets | D15-ARCH-SPEC-01-R1 | **CLOSED** |

---

## Drift 1 — Earlier Authoring-Chain Drift  ·  `PRD-D15-01 → R1 → R2 → R2-E1`

- **R1 invented / introduced** an `Active` lifecycle state — not defined by IC-002 (whose lifecycle is `Registered/Provisioning/Verifying/Ready/Suspended/Failed/Decommissioned`; `Ready` is the serving state).
- **R1 dropped or corrupted** governing-source citations, including **D-15** and **IC-001** (and IC-003/IC-008), and mislabeled D-10/D-11/IC-002.
- **R2 corrected** the lifecycle and governing-source issues.
- **R2-E1 closed** the remaining **D-30 / D-31** title fixes and audit-vocabulary issues.
- **Final status: CLOSED** (chain converged; 0 Critical / 0 Major / 0 Minor).

## Drift 2 — SPEC-01 Was an Authoring PRD, Not the Actual Specification
- `PRD-D15-SPEC-01` **looked like a specification by title**; its content was still an **authoring PRD**.
- Corrected through **readiness verification (PRD-D15-AUTH-01)** and the later creation of the **actual architecture specification (D15-ARCH-SPEC-01)**.
- **Final status: CLOSED.**

## Drift 3 — Governing-Source Citation Regression
Wrong labels (in PRD-D15-SPEC-01 §2):
```text
D-10 mislabeled as Tenant Lifecycle        (correct: Global Ready vs Degraded)
D-11 mislabeled as Database Association     (correct: Registry Enumeration)
D-16 mislabeled as Failure Modes           (correct: Partial-Fleet Readiness)
D-17 mislabeled as Provisioning Audit       (correct: Schema Migration Coordination)
IC-001 mislabeled as Global Directory Contract  (correct: Global Startup Contract)
IC-002 mislabeled as Tenant Lifecycle Contract  (correct: Tenant Startup Contract)
IC-005 omitted
D-34 omitted
```
**Final status: CLOSED.**

## Drift 4 — Audit Authority Drift
- **Incorrect:** `Provisioning audit → D-17`
- **Correct:**
```text
Provisioning audit
→ IC-002 Audit Requirements
→ D-34 Operational Audit
→ IC-001 Reference-Only Representation
→ IC-010 §J
```
D-17 governs **Schema Migration Coordination only.** **Final status: CLOSED.**

## Drift 5 — Physical Distinctness Softening
Incomplete wording could have allowed **`system_identifier` alone** to be treated as sufficient. Correct mandatory verification:
```text
system_identifier
+
database-level identity
+
provisioning target validation
+
write-sentinel or equivalent
```
**Final status: CLOSED.**

## Drift 6 — I6 One-Request Rule Softening
The first D15 architecture specification introduced the carve-out:
```text
unless a future contract explicitly authorizes a platform-internal administrative process
```
This was **removed.** Correct rule:
```text
No request may read from or write to more than one tenant database.
No request may span tenant databases.
Cross-tenant operations are IC-007-deferred and not authorized by D15.
```
**Final status: CLOSED.**

## Drift 7 — Missing Tenant-vs-Control-DB Distinctness
Tenant-vs-tenant distinctness was present; **tenant-vs-Control-DB distinctness was initially missing.** Corrected by:
```text
DV-C7A Control DB Distinctness Verification
DV-AC16B
DV-AC16C
DV-AC16D
§25 C12–C14
IC-010 §P traceability
```
**Final status: CLOSED.**

## Drift 8 — Audit Metadata Escape Hatch
`non-sensitive metadata` was too broad. Corrected by binding the **IC-001 Global Audit Representation Rule** and prohibiting:
```text
names
emails
display names
PII
business payloads
copied tenant data
copied global data
raw secrets
credentials
database passwords
```
**Final status: CLOSED.**
