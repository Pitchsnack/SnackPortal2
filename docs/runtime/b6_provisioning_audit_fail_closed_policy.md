# PRD 06 B-6 — Provisioning Audit Fail-Closed Policy (documented contract)

This is a **documented contract** that a **future, separately-gated** runtime wiring honors. **B-6 wires nothing.** The
existing distinctness fail-closed behavior is **unchanged**, and `backend/control_plane/provisioning.py` /
`backend/control_plane/main.py` remain **off-limits** in B-6.

---

## 1. Principle

When provisioning audit is **REQUIRED** (`PROVISIONING_AUDIT_REQUIRED=true`), provisioning must **fail closed** rather
than complete un-audited: any condition below blocks provisioning completion and surfaces the failure. Default is
conservative — missing/ambiguous evidence ⇒ fail closed.

## 2. Fail-closed conditions (per planning WP-B6-5)

| # | Condition | Result |
|---|-----------|--------|
| 1 | Required audit sink reference missing | fail closed |
| 2 | Required audit sink reference unresolved at connect time | fail closed |
| 3 | Missing correlation id | fail closed |
| 4 | Missing tenant identity (reference) | fail closed |
| 5 | Missing database-target reference | fail closed |
| 6 | Missing outcome | fail closed |
| 7 | Invalid / unmapped event type | fail closed |
| 8 | Raw secret detected in payload | fail closed (and reject) |
| 9 | Audit-write failure (sink rejects/errors) | fail closed |
| 10 | Append-only violation (update/delete attempted) | fail closed |
| 11 | Hash-chain mismatch — **only if** hash-chaining is enabled | fail closed |
| 12 | Sink unavailable at provisioning-completion | fail closed |

## 3. Forward additions (labelled — beyond the ratified WP-B6-5 set)

The following are **proposed forward** policy checks, **not** part of the ratified fail-closed contract; listed only so
a future wiring phase can consider them:

```
retention-policy reference missing when retention is required
redaction-policy reference missing when redaction is required
```

(Today, redaction failure is already covered by condition #8 "raw secret detected in payload".)

## 4. Out of scope for B-6

No runtime enforcement is added; no change to `provisioning.py` / `main.py`; no DDL; the optional hash policy is
**forward only** and is **not** IC-004/D-23 lineage.
