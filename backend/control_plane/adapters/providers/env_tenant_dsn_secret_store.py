"""Control-plane-owned env/file tenant-DSN SecretStore provider (PRD 07D-1; D-14; D-A).

Resolves the CANONICAL tenant database secret reference minted by onboarding since 07D-1 —
``tenant/<tenant_id>/dsn`` (decision D-A) — to a tenant database connection descriptor from
infrastructure-owned configuration (environment variable or file). Needed because the Phase-2
trust-anchor resolver (``EnvReferenceSecretStore``) is EXACT-REF allow-listed and cannot resolve
unbounded dynamic tenant references (07D-1 exec-auth finding C-1).

REPLICATES (never imports) the database-router-side ``EnvTenantSecretStore`` convention
(``database_router/adapters/providers/env_tenant_secret_store.py``) so ONE materialized secret
serves BOTH sides — the control plane's applicator/probe/evidence path here, and the router's
serving path there — which is the direct cross-side alignment proof (D3). The services stay
mutually independent (import-linter: no cross-service import).

Shared convention (replicated verbatim from the router side):

* env form  — ``SNACKPORTAL_TENANT_SECRET_<REF_UPPER_NONALNUM_TO_UNDERSCORE>_V<version>``
* file form — ``$SNACKPORTAL_TENANT_SECRET_DIR/<store_ref>@<version>``

Least privilege / blast-radius containment: allow-listed by PREFIX to tenant database references
only (``tenant/...``) so this resolver can never read the trust-anchor or control-store secrets
(and vice versa). Pure stdlib; no database driver; no KMS/Vault/cloud SDK; confined to the
adapters/providers zone. Descriptors stay ``{store_ref, version}``; the value is returned
in-memory only (``SecretValue`` hides material from repr) and is never logged or persisted (D-14).
Fail-closed: a non-tenant reference raises ``PermissionError``; an unresolved reference raises
``LookupError``.

Pluggable: a Vault / cloud secret-manager provider may replace this behind the same SecretStore
port without touching business logic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from shared.secrets import SecretRef, SecretStore, SecretValue

TENANT_PREFIX = "tenant/"


class EnvTenantDsnSecretStore(SecretStore):
    def __init__(self, secret_dir: Optional[str] = None) -> None:
        self._secret_dir = secret_dir or os.environ.get("SNACKPORTAL_TENANT_SECRET_DIR")

    @staticmethod
    def _env_key(store_ref: str, version: str) -> str:
        # REPLICATES database_router/adapters/providers/env_tenant_secret_store.py:31-33 EXACTLY
        # (alphanumerics uppercased; every other character, incl. '/', -> '_'). Divergence here
        # would silently break the D3 cross-side alignment — one env var must serve both sides.
        base = "".join(c.upper() if c.isalnum() else "_" for c in store_ref)
        return f"SNACKPORTAL_TENANT_SECRET_{base}_V{version}"

    def _guard(self, store_ref: str) -> None:
        if not store_ref.startswith(TENANT_PREFIX):
            raise PermissionError("provider resolves tenant database references only")

    def resolve(self, ref: SecretRef) -> SecretValue:
        self._guard(ref.store_ref)
        key = self._env_key(ref.store_ref, ref.version)
        if key in os.environ:
            return SecretValue(material=os.environ[key])
        if self._secret_dir:
            candidate = Path(self._secret_dir) / f"{ref.store_ref}@{ref.version}"
            if candidate.is_file():
                return SecretValue(material=candidate.read_text(encoding="utf-8").strip())
        raise LookupError(f"unresolved tenant secret reference: {ref.store_ref}@{ref.version}")

    def current_version(self, store_ref: str) -> str:
        self._guard(store_ref)
        return os.environ.get(self._env_key(store_ref, "current"), "1")
