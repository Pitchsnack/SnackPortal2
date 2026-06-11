# SnackPortal2 — Backend

**Build Phase 1 — Repository Setup (scaffolding only).** No business logic, no
contract behavior, no database access, no authentication, no routing.

This repository establishes the vendor-neutral structure, abstraction **ports**
(interfaces only), service **skeletons**, governance docs, and CI validation
rules that later build phases ride on. All work traces to the Final contracts
(IC-001…IC-005) and the Architecture Decision Register (D-01…D-32).

## Layout
| Path | Purpose |
|---|---|
| `shared/` | Vendor-neutral cross-cutting library — **dependency leaf** (pure stdlib). Ports + shapes only. |
| `api_gateway/` | Single request entry point (skeleton). |
| `auth_router/` | Authentication + tenant-context (skeleton; IC-005). |
| `database_router/` | Registry-authoritative routing (skeleton; IC-005/IC-002). |
| `control_plane/` | Control DB, registry, readiness, directories (skeleton; IC-001). |
| `import_service/` | Global→tenant import-copy (skeleton; IC-003). |
| `lineage_service/` | Tenant-resident provenance (skeleton; IC-004). |
| `tests/architecture/` | Architecture/governance validation (runnable via pytest or `python`). |

## Non-negotiable rules (enforced by CI)
- `shared` imports no service; no service imports another service.
- Vendor/cloud SDK imports are permitted **only** under `**/adapters/providers/**`.
- Database drivers are permitted **only** under `database_router/adapters/providers/**`.
- No secret values anywhere — references only (D-14).
- Lineage (IC-004) is separate from operational audit (IC-002/IC-003).

## Running the checks
From `backend/` (dev tools installed via `pip install .[dev]`):
```
ruff check . && ruff format --check .
mypy .
lint-imports
pytest tests/architecture
```
The architecture tests are pure-stdlib and also run standalone:
```
python tests/architecture/test_dependency_boundaries.py
python tests/architecture/test_vendor_and_db_containment.py
python tests/architecture/test_traceability.py
python tests/architecture/test_no_secret_literals.py
```

See `../docs/Coding-Standards.md` and `../docs/Phase-1-Governance-Standards.md`.
