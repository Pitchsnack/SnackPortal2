# PRD 06 B-3A — Local Topology Proof Evidence Template (references-only)

A reusable, **references-only** evidence template for a controlled non-production B-3A local run. **All fields are
redacted of secrets.** Copy per run; fill the bracketed values; never enter a raw DSN, password, or credential.

> **Redaction rule (D-14; IC-001 Global Audit Representation Rule):** record database names, ports, and
> `system_identifier`s (non-secret); never record DSNs, passwords, tokens, or credentials.

---

## 1. Identity & scope

```
PRD / phase            : PRD 06 B-3A — Local Docker Multi-Database Test Environment (controlled non-production)
baseline commit        : [origin/main @ ...]
branch                 : [branch]
environment            : local (NEVER production)
Docker / Compose       : [Server Version] / [Compose version]
daemon status          : [running]
date (UTC)             : [YYYY-MM-DD]
```

## 2. Topology (non-secret)

```
service               container            database                         port (127.0.0.1)   system_identifier
control-postgres      sp2_b3a_control      snackportal2_control_local       5540               [sysid-1]
tenant-acme-postgres  sp2_b3a_tenant_acme  snackportal2_tenant_acme_local   5541               [sysid-2]
tenant-zeta-postgres  sp2_b3a_tenant_zeta  snackportal2_tenant_zeta_local   5542               [sysid-3]
tenant-nova-postgres  sp2_b3a_tenant_nova  snackportal2_tenant_nova_local   5543               [sysid-4]
distinct system_identifiers? : [YES — 4/4 distinct]    (FAIL if all four share one cluster identity)
distinct database names?     : [YES — 4/4 distinct]
distinct connection refs?    : [YES — 4/4 distinct]
```

## 3. Harness

```
test                  : backend/tests/control_plane/requires_pg/test_b3a_multi_database_topology.py
driver containment    : psycopg via importlib (no static import) — confirmed
default-suite impact  : none (requires_pg auto-excluded via addopts --ignore; default stays no-live-PostgreSQL)
result (B-3A env set) : [PASS — 4 distinct clusters; fail-closed verified]
```

## 4. Secret & state guards

```
password in committed files?  : NO (interpolated from untracked .env.local)
.env.local committed/staged?  : NO (gitignored)
raw DSNs / tokens committed?  : NO
Docker state / volumes / logs : NOT committed
gitleaks (local)              : [no leaks]
```

## 5. Teardown

```
containers removed   : [yes]
volumes removed      : [yes/retained — state which]
.env.local removed   : [yes]
SP2_B3A_* unset      : [yes]
working tree clean   : [yes — only owner-local untracked]
```

## 6. Gates

```
ruff / format        : [clean]
mypy                 : [0 issues / 212 files]   (one new test .py; mypy counts test files)
lint-imports         : [2 kept, 0 broken]
pytest architecture  : [120]                    (incl. test_vendor_and_db_containment)
pytest full (no PG)  : [363]
git diff --check     : [clean]
DDL applied?         : NO (governed infrastructure/db/** untouched; control ledger 30956ff1e8)
```

## 7. Outcome

```
invariants preserved : [Physical Multi-DB / Control-Plane D-15 lifecycle / Router-sole-selector / Gateway-ingress /
                        D-14 references / fail-closed / Docker-substrate-only / infra-independent — confirm each]
scope fence          : [changed paths ⊆ allowlist; infrastructure/iac/** + infrastructure/db/** + b3_* docs untouched]
risk                 : [LOW / MED / HIGH + rationale]
final verdict        : [READY FOR REVIEW | READY WITH OBSERVATIONS | NOT READY]
```
