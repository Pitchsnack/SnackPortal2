# infrastructure/iac/environments — environment conventions (non-production examples)

Environment **conventions** for the cloud-portable substrate. **Scaffold only** (PRD 06 B-3): described as
README examples — **no `.template` files, no real values, no state files** committed this phase.

## Environments

```
local        disposable local PostgreSQL (e.g. PG 17.10); loopback only; Docker is NOT required
nonprod      disposable or explicitly test-safe non-production; the only target a future B-3 execution may touch
staging      planned; out of B-3 execution scope
production   planned; DEFERRED to B-5; a B-3 execution must NEVER target production
```

## Rules (every environment example must be safe)

- **References only (D-14):** environment configuration carries `secret_ref` references and aliases, never raw
  DSNs, passwords, connection strings, cloud account IDs, or credentials.
- **Environment-scoped references:** each environment resolves its own `secret_ref` set; references are
  environment-scoped so non-production can never resolve a production secret.
- **No real identifiers:** no real hostnames (loopback only), no real cloud account IDs, no real passwords/DSNs,
  no real tenant payload, no state file.
- **Visible environment identity:** the environment alias is visible (and redacted of secrets) in evidence
  reports so every action is attributable to a named, non-production target.
- **Database names make the environment unambiguous** (e.g. an explicit `nonprod` marker).

## Why README, not `.template`, in B-3

The architecture test suite (`backend/tests/architecture/test_no_secret_literals.py`) enforces that any
`infrastructure/**/*.template` file's `*_REF` keys are empty or `ref:`-prefixed. B-3 deliberately ships **no**
`.template` files (documentation only), so that rule is not engaged here. Actual `.template` files belong to the
later, separately-gated executable phase and **must** then satisfy that rule.

## Examples

- `local.example/` — disposable local PostgreSQL convention.
- `nonprod.example/` — disposable non-production convention.
