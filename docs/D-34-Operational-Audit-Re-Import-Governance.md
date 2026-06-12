# D-34-R2 — Operational Audit Architecture & Re-Import Governance

| | |
|---|---|
| **ADR ID** | D-34 (revision R2 — supersedes D-34-R1 and D-34) |
| **Status** | Approved for register entry per **PRD-D33-D36-P1-R1** (Governance Remediation Package — Phase 1, APPROVED FOR IMPLEMENTATION) |
| **Type** | Architecture Decision Record — governance correction only; no runtime behavior change |
| **Date** | 2026-06-12 |
| **Revision drivers** | PRD-D33-D37-R1 Independent Architecture Alignment Review findings **MAJ-4** (uncited D-20 amendment), **MAJ-3** (audit representation rule must be contract-normative — Work Package D), plus minor findings (audit-home split, future-merge constraints, export scope, document hygiene) |
| **Related ADRs** | D-33 (Workspace), D-35 (Deal Directory), D-36 (Ownership), D-37 (Portals — pending authoring); **amends D-20 in part** (see §4) |

---

## 1. Background

PRD 1A-R2 identified the governance gap between **operational audit** and **import lineage**. PRD 1A had incorrectly assumed the Control Database might store "Global Import Lineage"; review established this conflicts with IC-004 Invariant 1 (*"the Control DB MUST NOT hold tenant-data lineage"* — frozen). Re-import behavior was additionally under-governed. The independent alignment review (PRD-D33-D37-R1) subsequently found that the prior revision **silently amended an approved decision (D-20)** and that the platform's reference-only audit rule existed only as a code comment, not contract law. This revision corrects both.

## 2. Existing Audit Capability Inventory (required by PRD-WA-01-R1 A2)

Evidence base: `backend/shared/audit.py` and `backend/control_plane/audit.py` at commit `0c2133a` (the two files named by Amendment A2), plus the per-service audit sinks.

| Capability | Status | Evidence |
|---|---|---|
| Audit port + event DTO (reference-only) | **Implemented** | `shared/audit.py` — `OperationalAudit.initiate(OperationalAuditEvent)`; *"No payloads, secrets, or PII — references and non-sensitive fields only"* |
| Administrative audit (tenant lifecycle, association, provisioning) | **Implemented** | `control_plane/audit.py` — `ControlPlaneAudit.record(...)`, append-only via `ControlStore.append_audit`, control-plane scope only |
| Service-emitted runtime events (Route, RouteDenied, CarrierMismatch, IsolationAnomaly, ImportRequested/Completed/Failed) | **Implemented (emission); persistence incomplete** | per-service `in_memory_audit_sink` providers — no durable sink |
| Publication audit | **Partially implemented** | directory mutations audited (see `tests/control_plane/test_audit_directory.py`); no publication/approval/withdrawal workflow exists |
| Export audit | **Not implemented** | no export feature exists |
| Runtime governance / configuration audit | **Not implemented** | — |

## 3. Existing Contract Constraints (not reopened)

- **IC-004 Invariant 1** — import/transformation/tenant lineage is tenant-resident; the Control DB holds none of it. **Confirmed, not reopened.**
- **IC-003** — Import ≠ Synchronization.
- **D-30** — Cross-Tenant Isolation (defense-in-depth).
- **D-31** — Global Directory Residency (no tenant-owned data in the Control DB).

## 4. Relationship to D-20 (amendment statement — required by MAJ-4)

**This ADR amends D-20 in part.**

- **D-20 original position (Approved 2026-06-05, register):** *"default re-import = upsert by natural key (no-op when unchanged); re-import appends lineage recording the outcome; never mutates Global."* IC-003:56 contracts the same default. The current implementation (full-row natural-key upsert, `import_service/service.py`) is therefore **contract-conformant today** — the prior characterization of it as merely "under-specified" was wrong.
- **D-34 position (this decision):** re-import becomes **user-controlled** (§8, option R3); silent overwrite of tenant edits is rejected as the default; lineage and import history are preserved across every outcome.
- **Amendment statement:** *D-34 partially supersedes the D-20 re-import model.* D-20's idempotency-key and natural-key reconciliation mechanics, its lineage-append rule, and its never-mutate-Global rule remain in force; only the **default overwrite-on-re-import semantics** are superseded by R3. The register entry for D-20 carries an amendment annotation; the IC-003 change is accordingly classified **Amendment Required** (not "clarification" — see §13).
- **Code/contract sequencing:** until the IC-003 amendment lands, the as-built upsert behavior **remains contract-conformant and authorized**; no remediation of it may begin before the contract moves (contracts precede code). After the amendment, the as-built default becomes a tracked remediation item for a future execution PRD.

## 5. Decision — audit residency (unchanged from R1)

**O1 adopted:** Operational audit belongs to the **Control DB**; import lineage belongs to the **tenant DB**. (O2 — centralize everything — rejected: violates IC-004 Invariant 1. O3 — tenant-only audit — rejected: no governance visibility.)

## 6. Operational Audit Taxonomy (homes corrected per independent review)

| Class | Examples | Contractual home |
|---|---|---|
| **Administrative Audit** | tenant creation/suspension, database registration, provisioning actions, **ownership transfers of Control-domain (global) records** (per D-36-R2 §Audit Residency) | IC-002 audit section (existing scope + extension) |
| **Publication Audit** | directory publication, approval, withdrawal (Startup/Investor/Deal directories) | **IC-001 amendment** (global-directory scope) |
| **Export Audit — global-directory scope** | directory export, control-plane reporting export | **IC-001 amendment** |
| **Export Audit — tenant-scoped operations** | tenant-initiated CSV/bulk export *operational events* | **IC-002 audit extension** (tenant-scope operations; the audit record goes to control-plane scope per §7 rule 3 — exported *content* never appears in audit) |
| **Runtime Operational Audit** | RouteDenied, CarrierMismatch, IsolationAnomaly, ImportRequested/Completed/Failed | IC-002 audit extension (already contract-mandated for imports by IC-003:102) |

Ownership-transfer audit of **tenant-resident** records is **tenant-resident** and is *not* a Control-DB class — see D-36-R2 Audit Residency Rule (MAJ-2 correction lives there; this taxonomy defers to it).

## 7. Global Audit Representation Rule (package-wide — Work Package D, MAJ-3)

This rule is **normative for every audit class in this taxonomy and for all audit defined by D-33/D-35/D-36** (workspace, operational, ownership, publication, import, directory audit). It promotes the existing implementation rule (`shared/audit.py`) to contract law and must be carried verbatim into the IC-001 amendment and IC-002 audit extension:

1. **Audit records store references only:** `actor_ref`, `user_ref`, `tenant_ref`, `ownership_ref`, `record_ref` (and correlation/action/outcome/timestamp metadata).
2. **Audit records never store:** names, emails, display names, identity payloads, PII, authorization payloads, record payloads, secrets, or tenant business content.
3. Audit records of tenant-context operations are **governance metadata about actions**, not tenant data; they are access-controlled, reference-only, and explicitly distinct from "Tenant Deal Activity"/tenant business records (resolving the D-35 §13 tension in writing). Exported or published *content* never appears in any audit record.
4. Identity resolution happens at presentation time through the **D-03 identity model**; traceability: D-03 (identities), D-14 (secrets/reference discipline), D-34 (audit architecture), D-36 (ownership references).

## 8. Re-Import Governance (IC-003 amendment scope)

**R3 — User-Controlled Re-Import — adopted** (R1 automatic overwrite rejected: silent destruction of tenant edits; R2 automatic merge rejected: hidden synchronization). Options at re-import:

- **Import New Copy** — requires a distinct natural-key strategy (D-20 reconciliation interaction) to be defined by the execution PRD;
- **Replace Existing** — explicit, consent-based; never silent;
- **Ignore**;
- **Future Merge Workflow** — constrained now (independent-review guard): any future merge MUST be **discrete, explicitly user-initiated per event, lineage-appending (chained per IC-004/D-25), never scheduled/automatic/continuous, and never writing back to the Global record**. Anything else is R2 by the back door.

**Lineage preservation (mandatory):** every re-import outcome appends lineage; prior lineage and import history are never modified or deleted (IC-004 append-only is absolute); a Replace Existing event chains to the prior record's provenance.

## 9. Explicitly Excluded from the Control DB (unchanged)

Tenant import lineage, transformation lineage, import provenance, copy lineage — unless IC-004 is amended (no such amendment proposed).

## 10. Consequences

Positive: preserves IC-004/IC-003; strengthens audit separation; the representation rule becomes contract law platform-wide; no silent supersession of approved decisions. Negative: requires the IC-001/IC-002/IC-003 amendments; the as-built re-import default becomes a tracked post-amendment remediation item; Control-DB audit growth interacts with D-12 migration cadence (kept bounded by the reference-only rule).

## 11. Security Considerations

Audit must never become cross-tenant data replication or tenant-lineage aggregation; the Control DB remains governance scope only. The §7 rule bounds every audit record to references; audit reads are authenticated, role-appropriate, and disclosure-safe.

## 12. Frozen Invariant Impact

Global Record ≠ Tenant Record — **Preserved**. Import ≠ Synchronization — **Strengthened** (R3 + merge constraints). Control DB ≠ Tenant DB — **Strengthened** (taxonomy + residency-scoped audit). Authentication ≠ Routing — No impact. One Request → One Active Tenant → One Database — No impact.

## 13. Contract Impact

| Contract | Impact |
|---|---|
| IC-004 | **No change** (reaffirmed) |
| IC-003 | **Amendment Required** (reclassified from "clarification" per MAJ-4/AC-2): user-controlled re-import semantics explicitly refining the D-20 default; merge constraints; lineage-preservation rule |
| IC-001 | **Amendment Required**: contractual home for Publication Audit + global-directory Export Audit + the §7 representation rule |
| IC-002 | **Audit Section Extension Required**: administrative/runtime operational audit obligations, tenant-scoped export-operation audit, + the §7 representation rule |
| Register **D-20** | **Amended in part** by this ADR (annotation required at register entry) |

## 14. Verification Criteria

V1 Control DB contains no tenant lineage. V2 Tenant lineage remains tenant-resident. V3 Audit taxonomy classes are correctly classified and homed. V4 Re-import never silently overwrites tenant changes. V5 Re-import creates no hidden synchronization. V6 Lineage and import history survive every re-import outcome. V7 Every audit record satisfies the §7 representation rule (references only). **V8 No approved ADR is silently replaced — every supersession is explicit, cited, and registered (this criterion is itself a PRD-D33-D36-P1-R1 requirement).**

## 15. Implementation Impact

None authorized. Future work requires: IC-001/IC-002/IC-003 amendments first, then audit-persistence and re-import-workflow execution PRDs (which inherit §7/§8 as acceptance constraints).
