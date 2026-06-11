"""lineage_service composition (Build Phase 6 — full Lineage Service).

Assembles the write path (`LineageEmit`) and the read/verify/graph/search/retention/
segmentation surfaces. The write path is injected a `RoutedTenantSession` by the caller
(import) and commits atomically with data (IC-004). The read surfaces are injected a
`LineageReadSessionProvider` (implemented by the Database Router) and open short-lived
tenant-bound read sessions on the INTERACTIVE lane. An `OperationalAudit` sink (shared port)
is injected for lineage operational events (≠ lineage; IC-002). No database access except
through the caller-provided / provider-issued routed sessions; no service imports (DAG).
"""
from __future__ import annotations

from typing import Dict, Optional

from shared.audit import OperationalAudit
from shared.secrets import SecretStore
from shared.session import LineageReadSessionProvider

from .emit import LineageEmit
from .graph import ProvenanceGraph
from .query import LineageQuery
from .retention import RetentionFramework
from .search import LineageSearch
from .segmentation import Segmentation
from .verification import LineageVerifier

SERVICE = "lineage_service"


def build_lineage_emit(*, secret_store: SecretStore,
                       audit: Optional[OperationalAudit] = None) -> LineageEmit:
    return LineageEmit(secret_store, audit=audit)


def build_lineage_query(*, read_provider: LineageReadSessionProvider) -> LineageQuery:
    return LineageQuery(read_provider)


def build_lineage_verifier(*, read_provider: LineageReadSessionProvider,
                           secret_store: SecretStore,
                           audit: Optional[OperationalAudit] = None) -> LineageVerifier:
    return LineageVerifier(read_provider, secret_store, audit=audit)


def build_provenance_graph(*, read_provider: LineageReadSessionProvider) -> ProvenanceGraph:
    return ProvenanceGraph(read_provider)


def build_lineage_search(*, read_provider: LineageReadSessionProvider) -> LineageSearch:
    return LineageSearch(read_provider)


def build_retention(*, audit: Optional[OperationalAudit] = None) -> RetentionFramework:
    return RetentionFramework(audit=audit)


def build_segmentation(*, read_provider: LineageReadSessionProvider,
                       audit: Optional[OperationalAudit] = None) -> Segmentation:
    return Segmentation(read_provider, audit=audit)


def liveness() -> Dict[str, str]:
    return {"service": SERVICE, "status": "alive", "build_phase": "6"}
