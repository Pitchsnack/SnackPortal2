"""SecretStore port (interface only) + reference/value shapes (D-14).

The SecretStore is the ONLY path to a secret value. Descriptors are references
({store_ref, version}); raw credentials never appear in DTOs, logs, responses, or
contracts. No resolution logic is implemented in Build Phase 1 — concrete
providers live only under `**/adapters/providers/**`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SecretRef:
    store_ref: str
    version: str


@dataclass(frozen=True)
class SecretValue:
    # Populated in-memory by an adapter at resolve() time only.
    # `repr=False` keeps the material out of logs/reprs (no leakage by construction).
    material: str = field(repr=False)


class SecretStore(ABC):
    @abstractmethod
    def resolve(self, ref: SecretRef) -> SecretValue: ...

    @abstractmethod
    def current_version(self, store_ref: str) -> str: ...
