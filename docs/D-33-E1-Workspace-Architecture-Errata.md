# D-33-E1 — Workspace Architecture Errata

| | |
|---|---|
| **Errata for** | D-33 — Workspace Definition & Tenant Context Architecture (Approved 2026-06-12) |
| **Authorized by** | PRD-D33-D37-V2-R1 — Governance Chain Remediation, Work Package A (APPROVED FOR EXECUTION) |
| **Finding** | PRD-D33-D37-V2 Independent Architecture Compliance Verification, **MAJ-1**: ADR text ≠ register entry ≠ Contract Amendment Inventory on two items |
| **Date** | 2026-06-12 |
| **Nature** | Errata only — records the authoritative resolution of two documentation-chain inconsistencies. **No architecture decision changes; no behavior changes; the D-33 decision (Workspace = UI representation of a signed tenant context) is untouched.** |

---

## Item 1 — Carrier-on-CONTROL anomaly audit: OPTIONAL → MANDATORY (amendment content)

- **Original ADR position** (D-33 §4.5, §11): for a tenantless CONTROL context, a recognized carrier asserting a tenant is *ignored* by routing (ratifying implemented behavior); anomaly-audit or rejection hardening was listed as **optional Future Work**.
- **Revised authoritative position:** the routing behavior is unchanged (*ignored; claim-only*), but the **IC-005 Workspace Terminology amendment MUST mandate emission of an anomaly-audit event** whenever a recognized tenant carrier accompanies a tenantless CONTROL token. Implementation of the emission (a small additive `auth_router` change) and its regression test land with the IC-005-amendment execution PRD — never before the amendment (contracts precede code).
- **Reason:** the D-33 draft-closure review required the promotion; the register entry and Contract Amendment Inventory (IC-005 item 3) already record it as mandatory. The verification (MAJ-1) required one authoritative position; per PRD-D33-D37-V2-R1 WP-A's Required Decision, **Mandatory** is adopted.
- **Impact:** none at runtime today; one additive audit emission + test at amendment execution. No frozen invariant affected.
- **Traceability:** D-33 §4.5/§11 → D-33 closure review (2026-06-12) → register D-33 entry → Inventory IC-005 item 3 → PRD-D33-D37-V2 MAJ-1 → PRD-D33-D37-V2-R1 WP-A → this errata.

## Item 2 — MembershipsForPrincipal: contract owner = IC-002 amendment (timing unchanged)

- **Original ADR position** (D-33 §4.4, §7, §11): the workspace selector requires a small additive memberships-for-principal read endpoint; the IC-002 impact was classed *"Amend (editorial)"* and the endpoint was routed *"to be carried by the API Gateway / frontend-integration execution PRD."*
- **Revised authoritative position:** the operation's **contract owner is the IC-002 amendment** — a new `MembershipsForPrincipal` entry in IC-002's API Contract operation table (callable only for the authenticated principal's own subject, or by CONTROL; audited; returning membership records only — tenant id, role, display ref — never tenant-DB data). The IC-002 impact is reclassified from "editorial" to **"Amend (additive operation + alias)."** **Implementation timing is unchanged:** the endpoint is built by the API Gateway / frontend-integration execution PRD, after the amendment exists.
- **Reason:** a new control-plane API operation must have a contract owner before any implementation (contracts precede code; the ADR's own closure review and the register/Inventory already assigned IC-002). The verification (MAJ-1) required the chain to agree.
- **Impact:** none at runtime today; clarifies the amendment package only. No frozen invariant affected.
- **Traceability:** D-33 §4.4/§7/§11 → register D-33 entry → Inventory IC-002 item 2 → PRD-D33-D37-V2 MAJ-1 → PRD-D33-D37-V2-R1 WP-A → this errata.

## Item 3 — Header status correction

D-33's document header read *"Status: Proposed"* after approval and registration (verification Minor 1). Corrected to **Approved (2026-06-12, PRD-D33-D36-P1-R1)** in the source document, consistent with D-34/D-35/D-36/D-37.

---

*With this errata, ADR text, register entry, and Contract Amendment Inventory state one position. The register's D-33 entry carries an annotation referencing this errata.*
