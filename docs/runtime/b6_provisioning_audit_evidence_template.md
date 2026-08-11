# PRD 06 B-6 — Provisioning Audit Sink Evidence Template (references-only)

A reusable, **references-only** evidence record for any future provisioning-audit-sink readiness decision. **All fields
are redacted of secrets.** Copy per decision; fill the bracketed values; never enter a raw DSN, password, token, or
credential. Aligned to `docs/reports/ci-evidence/` and the B-5 evidence-template style.

> **Redaction rule (D-14; IC-001 Global Audit Representation Rule):** record references (`ref:…`), aliases, and
> non-secret identities; never DSNs, passwords, tokens, cloud credentials, or PII.

---

## 1. Identity & scope
```
PRD / phase            : PRD 06 B-6 — Provisioning Audit Sink
baseline commit        : [origin/main @ ...]
target environment     : [local | non-production]   (production prohibited in the B-6 era)
catalog version        : [b6_provisioning_audit_events.md vN]
operator / approver    : [name/role]    date (UTC) : [YYYY-MM-DD]
```

## 2. Sink configuration (references only)
```
PROVISIONING_AUDIT_REQUIRED        : [true]
PROVISIONING_AUDIT_SINK_REF        : ref:...        (key only — never a value)
retention / hash / redaction refs  : ref:...        (hash optional/forward; NOT lineage)
secret values stored?              : NO (references resolved at connect time; D-14)
```

## 3. Event sample (references only)
```
event id / type / version · timestamp · actor_ref · tenant_ref · db-target ref · phase · gate id ·
correlation id · outcome · error class (redacted) · evidence ref     [no raw secrets / payloads]
```

## 4. Contract proofs
```
append-only proof          : [records appended; no update/delete surface]
references-only proof       : [ControlAuditRecord fields = {actor,tenant_id,action,from_state,to_state,timestamp,correlation_id}]
redaction proof             : [no raw secret literals in any committed artifact (gitleaks)]
fail-closed proof           : [required-write failure blocks completion — per b6_provisioning_audit_fail_closed_policy.md]
sink-availability proof     : [sink reachable/available at provisioning-completion, or fail-closed exercised]
```

## 5. Boundaries (non-secret)
```
provisioning audit ≠ lineage : [IC-002/D-34 distinct from IC-004/D-23 — confirmed]
Database Router              : [sole DB selector — unchanged]
Approved public edges       : [the only served client ingress — D-45; unchanged by this slice]
audit.py / events.py / main.py : [unchanged — git scope fence]
```

## 6. Gates & CI
```
local : ruff/format | mypy | lint-imports | pytest architecture | pytest full | B-6 tests | gitleaks | git diff --check
CI    : validate (pytest tests/architecture) | secret-scan (gitleaks)
counts: [arch 124->124+n | full 370->370+n | mypy 0/214->0/214+m — additive, explained]
```

## 7. Outcome
```
invariants preserved   : [Physical Multi-DB / Control-Plane authority / Router-sole-selector / Gateway-ingress / D-14 /
                          fail-closed / provisioning-audit ≠ lineage — confirm each]
blocker standing        : [B5-BLK-4 remains OPEN — reduced, not closed]
human approval          : [recorded]
risk                    : [LOW / MED / HIGH + rationale]
final verdict           : [READY FOR REVIEW | NOT READY]
```
