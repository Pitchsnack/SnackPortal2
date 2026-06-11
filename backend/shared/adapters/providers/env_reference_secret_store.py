"""Vendor-neutral env/file reference SecretStore provider (Build Phase 2).

Resolves a SecretRef from infrastructure-owned configuration (environment variable or
file). **Trust-anchor resolution only** (Bootstrap Phase 0). No KMS, no Vault, no cloud
SDK, no tenant-credential resolution, no secret persistence. Vendor-neutral (pure stdlib),
config-selectable, and confined to the adapters/providers zone (F-1). Descriptors stay
{store_ref, version}; the value is returned in-memory and never logged (D-14).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import FrozenSet, Optional

from shared.secrets import SecretRef, SecretStore, SecretValue

DEFAULT_ALLOWED: FrozenSet[str] = frozenset({"bootstrap/trust-anchor"})


class EnvReferenceSecretStore(SecretStore):
    def __init__(self, allowed: Optional[FrozenSet[str]] = None, secret_dir: Optional[str] = None) -> None:
        self._allowed = allowed if allowed is not None else DEFAULT_ALLOWED
        self._secret_dir = secret_dir or os.environ.get("SNACKPORTAL_SECRET_DIR")

    @staticmethod
    def _env_key(store_ref: str, version: str) -> str:
        base = "".join(c.upper() if c.isalnum() else "_" for c in store_ref)
        return f"SNACKPORTAL_SECRET_{base}_V{version}"

    def _guard(self, store_ref: str) -> None:
        if store_ref not in self._allowed:
            raise PermissionError("provider supports trust-anchor resolution only")

    def resolve(self, ref: SecretRef) -> SecretValue:
        self._guard(ref.store_ref)
        key = self._env_key(ref.store_ref, ref.version)
        if key in os.environ:
            return SecretValue(material=os.environ[key])
        if self._secret_dir:
            candidate = Path(self._secret_dir) / f"{ref.store_ref}@{ref.version}"
            if candidate.is_file():
                return SecretValue(material=candidate.read_text(encoding="utf-8").strip())
        raise LookupError(f"unresolved secret reference: {ref.store_ref}@{ref.version}")

    def current_version(self, store_ref: str) -> str:
        self._guard(store_ref)
        return os.environ.get(self._env_key(store_ref, "current"), "1")
