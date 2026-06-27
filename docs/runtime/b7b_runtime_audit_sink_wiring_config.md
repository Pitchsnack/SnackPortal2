# B-7B — Configuration Surface (controlled non-production)

**PRD 06 B-7B.** Symbolic configuration only — **no secret values appear here or in the composition
root.** Default behavior is in-memory with no database I/O.

## Selector

| Env | Values | Default | Invalid |
|---|---|---|---|
| `SP2_CP_CONTROL_STORE` | `in_memory`, `postgres` | `in_memory` (unset/empty) | **raises** `ValueError` (fail closed) |

Selection is **startup-only** (no hot-swap). Trimmed + case-insensitive. The `postgres` value is
**implemented** here (non-production), unlike the `SP2_CP_PROVISIONING_ADAPTER` /
`SP2_CP_DISTINCTNESS_LEDGER` deferral-locks which still raise `NotImplementedError`.

## Secret reference (D-14)

| Env | Meaning | Default |
|---|---|---|
| `SP2_CP_CONTROL_STORE_DSN_REF` | the **`SecretRef.store_ref`** name of the control-store DSN (NOT a DSN) | `control/control-store-dsn` |

The composition root constructs `SecretRef(store_ref, version="1")` and resolves it through a
**dedicated** `EnvReferenceSecretStore` whose allow-list = `{trust-anchor ref} ∪ {control-store ref}`.
The default trust-anchor-only secret store used elsewhere (Bootstrap) is unchanged.

### How the descriptor is provided (infrastructure-owned)

`EnvReferenceSecretStore` resolves `SecretRef("control/control-store-dsn", "1")` from:

- environment variable **`SNACKPORTAL_SECRET_CONTROL_CONTROL_STORE_DSN_V1`** (derivation:
  `_env_key` upper-cases the ref, maps non-alphanumerics to `_`, suffix `_V<version>`), or
- a file `control/control-store-dsn@1` under `SNACKPORTAL_SECRET_DIR`.

The value is a standard PostgreSQL connection descriptor (URL or libpq keyword/value), resolved
**in-memory only** at first use and never retained on the adapter. **No DSN literal is held by the
composition root, and `SNACKPORTAL_TEST_DSN` is never reused as runtime config.**

## Portability

Standard PostgreSQL only (AWS RDS / Azure Database for PostgreSQL / Cloud SQL / self-hosted). No
provider-proprietary features. The DSN may pin a schema via libpq `options=-c search_path=...`; this
is infrastructure configuration, not application logic.

## Non-production posture

`postgres` mode is for **controlled non-production** wiring only. Production activation (production
descriptors, retention/redaction/hash policy approval, production sink readiness) is **out of scope**
and tracked in `..._blockers.md` (B5-BLK-4 remains OPEN).
