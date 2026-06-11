"""Generic adapter & provider-registry contracts (interface only).

A Port is a vendor-neutral interface (e.g. SecretStore, Queue, OperationalAudit).
A concrete Adapter implements a port for one backend and lives ONLY under
`**/adapters/providers/**`. A ProviderRegistry binds a config-selected provider to
a port at the composition root. No implementations exist in Build Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class ProviderAdapter(ABC):
    @abstractmethod
    def provider_id(self) -> str: ...


class ProviderRegistry(ABC):
    @abstractmethod
    def register(self, port: str, provider_id: str, factory: Callable[..., ProviderAdapter]) -> None: ...

    @abstractmethod
    def resolve(self, port: str) -> ProviderAdapter: ...
