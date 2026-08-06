# DBR-AR-2D V3 — Standing-Witness Evidence Template (references only)

**Scope:** the evidence record for one Dan-authorized, exactly-once execution of the DBR-AR-2D V3
retained standing-topology witnesses (contract §16 proofs 1/2 standing halves, 4, 8, 12) by the
standing operator `backend/tests/control_plane/requires_pg/dbr_ar_2d_standing_witnesses.py`.

**Redaction rules (SMOKE-C-SPEC-01 §7; D-14; contract §9) — every field below is REFERENCES ONLY:**
no DSN, no password, no token-shaped string, no key material, no request/response body, no tenant
business data, and no connection-topology detail beyond the redacted scheme+host+port+database
identity. The backup archive itself is NEVER attached, committed, or quoted — only its checksum
and redacted location reference appear here.

---

## 1. Binding

| Field | Value |
|---|---|
| PRD | PRD DBR-AR-2D V3 (Dan START-GATE) |
| Tested commit (`git rev-parse HEAD`) | `<40-hex>` |
| Operator identity | `<operator name — references only>` |
| Date (UTC) | `<YYYY-MM-DD>` |
| B5-4 status | `6/6 PASS` (before AND after) |
| B5-4A status | `12/12 PASS` (before AND after) — **HISTORICAL / UNSATISFIABLE (AUTHFIX-B).** The b5_standing subject state was replaced around 2026-07-21; this row cannot be satisfied against the current standing environment and must not be filled in as though it could. Record the successor posture instead (`test_pg_clm_standing_auth_posture.py`). |
| Smoke C V2 prerequisites | `STATUS OK` (zero residue) |

## 2. Backup (before any DDL)

| Field | Value |
|---|---|
| Backup location (redacted reference) | `<outside-repository directory reference>/snackportal2_control_local.dbr_ar_2d_v3.pre_apply.dump` |
| Backup sha256 | `<64-hex>` |
| Readability witness | `pg_restore --list` exit 0 (no database touched) |

## 3. Blob verification and apply record

| Field | Value |
|---|---|
| `010_routing_audit.sql` LF blob | `0c5eeecd5e20ef9fe4f11293b6c6561ae7cc897e` (must equal the reviewed pin) |
| `011_routing_audit_append_only.sql` LF blob | `cea40fc62c063e9f711fdb7ac90b00a8859586d4` (must equal the reviewed pin) |
| Apply target | the retained local standing Control database ONLY (identity probed before DDL) |
| Apply order | 010 exactly once, then 011 exactly once (never a wildcard) |
| Automatic apply order | UNCHANGED — 001–009 (010/011 not enrolled) |

## 4. Schema census (post-apply, from the live catalogs)

Exact 20-column sequence in DDL order; identity PRIMARY KEY `id`; UNIQUE `event_id`;
`recorded_at` DB DEFAULT; the EXACT CHECK set (`control_routing_audit_action_check`,
`control_routing_audit_event_version_check`, `control_routing_audit_source_service_check`); the
EXACT trigger set (`control_routing_audit_no_mutation`, `control_routing_audit_no_truncate`);
the `control_routing_audit_append_only()` function.

## 5. Standing witness (run — exactly once)

| Scenario | Result | Durable rows |
|---|---|---|
| S1 alpha success (`dbr2dv3-s1-alpha`) | 200 ok; routed to the alpha database only; beta pool untouched | 1 × `Route` |
| S2 beta success (`dbr2dv3-s2-beta`) | 200 ok; routed to the beta database only; alpha pool untouched | 1 × `Route` |
| S3 dormant Auth-edge denial (`dbr2dv3-s3-dormant-auth`) | 403 forbidden; internal `tenant_not_ready`; zero dispatch | **0** |
| S4 dormant Router-edge denial (`dbr2dv3-s4-dormant-router`) | 503 `not_ready` over the real dispatch wire; zero dispatch | 1 × `RouteDenied` |
| S5 controlled isolation anomaly (`dbr2dv3-s5-anomaly`) | `routing_isolation_fault`; misbound connection discarded | 1 × `IsolationAnomaly` |

The final durable state carries **exactly four evidence rows** in identity order (no fifth V3 row);
the dormant tenant still has no secret, no database, and no schema; one request → one active
tenant → one physical database held with the durable sink composed.

## 6. Before/after allowed-delta proof (full snapshot families)

Families compared (full content, never bare counts): Control-DB tenant rows / memberships /
provisioning-audit rows / federation, routing-audit schema + rows, `pg_database` census, dormant
and disposable-proof-database absence, per-table tenant-DB content digests, secret-root inventory,
touched environment keys. Result: `before == after` outside exactly the four evidence rows.

## 7. Leakage proof

Every stored evidence cell scanned: no DSN, no password, no token-shaped value, no key material.
Every captured command output scanned: no resolved secret. All emitted identities redacted.

## 8. Locked state (unchanged by this record)

DBR-AR-2 — CLOSED (Dan-authorized governance decision, 2026-07-16); this closure closes zero B5 activation blockers, the blocker census remains nine with 8 of 9 OPEN, and production remains NOT READY / DO-NOT-ACTIVATE.
DBR-AR-2E — production-activation evidence consolidated (Outcome A — REMAIN NOT READY / DO-NOT-ACTIVATE).
Production activation remains
NOT READY / DO-NOT-ACTIVATE — 8 of 9 activation blockers remain OPEN. The hosted live-PG loop
remains exactly 14 harnesses; the standing harness is manual-only. ATR-2B-1 remains a separately
governed HTTP-hardening follow-up.
