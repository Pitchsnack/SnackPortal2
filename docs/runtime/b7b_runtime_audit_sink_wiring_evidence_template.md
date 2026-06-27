# B-7B — Evidence Template (controlled non-production)

**PRD 06 B-7B.** Record the runtime audit-sink wiring evidence below. No secret/DSN values; reference
`SNACKPORTAL_TEST_DSN` / secret env vars **by name only**.

## Environment

- Date / operator:
- Commit (branch tip):
- PostgreSQL version (`server_version_num`):
- `SNACKPORTAL_TEST_DSN` set (yes/no — value NOT recorded):

## Local gate battery (default suite — no live DB)

| Gate | Expected | Result |
|---|---|---|
| `ruff check` | clean | |
| `ruff format --check` | clean | |
| `mypy` | 0 errors / 219 source files (additive deltas allowed) | |
| `lint-imports` | 2 kept / 0 broken | |
| `pytest tests/architecture` | pass (≥ 136; additive) | |
| `pytest` (full) | pass (≥ 397; additive) | |
| `gitleaks detect` | no leaks | |
| `git diff --check` | clean | |

## Live PostgreSQL (standalone; `SNACKPORTAL_TEST_DSN` set)

`python backend/tests/control_plane/requires_pg/test_pg_control_store_runtime_wiring.py`

| Check | Description | Result |
|---|---|---|
| 1 | DDL blob pin + apply (002 → 003) in scratch schema | |
| 2 | durable selection + no-I/O construction (lazy-connect) | |
| 3 | durable audit write reaches `control_audit` via `create_app()` | |
| 4 | type-stable `str` timestamp, same instant (B7B-D7) | |
| 5 | reference-only stored row (no DSN/secret) | |
| 6 | cross-instance durability | |
| 7 | append-only rejection under durable wiring | |
| 8 | fail-closed unreachable DSN + no partial/orphan row | |
| 9 | fail-closed unresolved ref (`LookupError`) | |
| 10 | fail-closed non-allow-listed ref (`PermissionError`) | |
| 11 | fail-closed missing table (`list_audit` raises, not `[]`) | |

## Regression

- B-7A harness re-run (`test_pg_control_audit_ddl.py`): ALL 15 checks (lazy-connect compatible):

## Secret hygiene

- `grep -R "postgresql://" backend docs` / `postgres://` — only synthetic placeholders outside B-7B:
- `SNACKPORTAL_TEST_DSN` referenced by name only (no value committed/printed):
- `gitleaks detect` clean:

## Scope / off-limits confirmation

- Off-limits diff (DDL 001/002/003, lineage, b5/b6/b7/b7a docs, contracts/ADRs/.github/frontend,
  infra iac|docker|env|runtime) is **empty**:
- B5-BLK-4 remains **OPEN**; Physical Multi-Database MVP mandatory; no production activation; no
  runtime DDL; no frontend/Lovable change; Claude did not merge.
