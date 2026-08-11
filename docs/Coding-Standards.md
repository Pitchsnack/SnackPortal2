# SnackPortal2 — Coding Standards

Binding engineering rules for the backend. Enforced by CI (`ruff`, `mypy`,
`import-linter`, architecture tests, `gitleaks`). See
`Phase-1-Governance-Standards.md` for the full normative standards.

## Dependency DAG (enforced)
1. `shared` is a leaf — imports no service package.
2. No service imports another service — inter-service comms is a **transport call**
   (network), never an **in-process import**.
3. An **approved public edge** performs no auth decision, no tenant routing, and no database selection — it delegates authentication to the Auth Router and database resolution to the Database Router (**D-45**; this rule formerly named the deleted `api_gateway` package, and is unweakened by the rename).
4. `auth_router` authentication is **DB-free** (D-01/D-05).
5. Database drivers only under `database_router/adapters/providers/**`.
6. Vendor/cloud SDKs only under `**/adapters/providers/**`.
7. `infrastructure/` is independent of `backend/`.
8. Secret values obtained only via `shared.secrets.SecretStore`.
9. Lineage (IC-004) ≠ operational audit (IC-002/IC-003) — separate modules.

## Secret hygiene (D-14, D-09)
- No secret value in code, templates, logs, DTOs, responses, audit, or lineage.
- References only: `{store_ref, version}`; env keys ending `_REF` = `ref:` or empty.
- `SecretValue.material` is `repr=False`; never log or serialize it.

## Adapters / vendor neutrality (governance A/B)
- Depend on **ports**, not providers. Concrete adapters live only in
  `**/adapters/providers/**`; selection is config-driven at the composition root.

## Naming (governance H)
- Use **Build Phase N** (construction) vs **Bootstrap Phase 0/1** (runtime). Never
  write unqualified "Phase 1". Use the canonical readiness / lifecycle / denial
  vocabularies.

## Readiness & disclosure (governance I)
- Liveness is static and non-disclosing; readiness is access-controlled and
  minimally disclosing; never leak tenant or database existence/topology.

## Python
- Target Python 3.8+. `from __future__ import annotations` in modules using
  annotations. Type hints required (`mypy --strict`). Line length 100.

## Running checks
```
# from backend/  (pip install .[dev])
ruff check . && ruff format --check .
mypy .
lint-imports
pytest tests/architecture
# standalone (no third-party tools):
python tests/architecture/test_dependency_boundaries.py
python tests/architecture/test_vendor_and_db_containment.py
python tests/architecture/test_traceability.py
python tests/architecture/test_no_secret_literals.py
```
