"""Vendor-neutral env/file tenant-credential SecretStore provider (Build Phase 4).

Resolves a per-tenant database connection descriptor from infrastructure-owned
configuration (environment variable or file). Distinct from the Phase-2 trust-anchor
resolver: this provider is allow-listed to **tenant database** references only
(`tenant/...`) so neither resolver can read the other's secrets (least privilege /
blast-radius containment). No KMS/Vault/cloud SDK; pure stdlib, vendor-neutral, and
confined to the adapters/providers zone. Descriptors stay {store_ref, version}; the
value is returned in-memory only and never logged or persisted (D-14).

Pluggable: a Vault / cloud secret-manager provider may replace this behind the same
SecretStore port without touching business logic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from shared.secrets import SecretRef, SecretStore, SecretValue

TENANT_PREFIX = "tenant/"


class EnvTenantSecretStore(SecretStore):
    def __init__(self, secret_dir: Optional[str] = None) -> None:
        self._secret_dir = secret_dir or os.environ.get("SNACKPORTAL_TENANT_SECRET_DIR")

    @staticmethod
    def _env_key(store_ref: str, version: str) -> str:
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
