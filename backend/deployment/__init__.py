"""Deployment composition root — the ONE authorized CROSS-SERVICE composition root.

Governed by **D-44 — Deployment Cross-Service Composition Root (Edge 9 Import Edge)** and
**IC-012 — Service Composition & Deployment Root Contract** (IC-012-DRAFT-1).

Every service package (``auth_router``, ``database_router``, ``control_plane``,
``import_service``, ``lineage_service``) is mutually independent: no service may import another,
and ``shared`` is a dependency leaf that may import none of them. That DAG is enforced by the
import-linter contracts in ``pyproject.toml`` and by the AST guards under ``tests/architecture``.

Service-local composition is NOT centralized here (IC-012 §1). Every service keeps its own
``main``/composition seam and its own native ASGI factory, and continues to own the assembly of its
own objects. The rule is: service-local composition stays with each service; CROSS-service
composition happens only here.

Seven of the eight HTTP edges are composable entirely inside their owning service, so each exposes
its own native ASGI application factory in its own adapter module. The Import edge — D-44's
"Edge 9", a ratified decision identifier retained verbatim even though the edge count fell
when the API Gateway and its two internal transports were removed — is the one exception:
``ImportService`` requires a ``RoutedSessionProvider`` (implemented only by
``database_router``) and a ``LineageEmitPort`` (implemented only by ``lineage_service``). A routed
tenant session is a LIVE transactional database handle bound to exactly one physical tenant
database, so it cannot be obtained over a wire either — it must be constructed in-process. The
existing composition seams have always named the missing piece in prose ("a higher deployment root
that may import all three services injects them here"); this package IS that root.

Direction of the dependency is what keeps the DAG intact. The authorized import set is NARROW and
EXHAUSTIVE (IC-012 §3) — exactly what the proven Edge 9 composition requires, and no more:

* AUTHORIZED — this package may import ``import_service``, ``database_router``, ``lineage_service``
  and ``shared``; it sits ABOVE them;
* NOT AUTHORIZED — ``auth_router`` and ``control_plane`` MUST NOT be imported here, because Edge 9
  does not require them. That pair is the EXACT COMPLEMENT of the authorized set over the five
  surviving services, so the grant stayed narrow when the Gateway left the list. Widening the set
  needs an IC-012 §5.1 amendment, not a code edit: a second import-linter ``forbidden`` contract
  makes the narrow grant machine-enforced;
* NO service, and not ``shared``, may import this package — enforced by a dedicated import-linter
  contract, so the root can never become a back-channel between two services.

Scope discipline. This root composes and nothing else. It owns no business logic, no route, no
contract, no schema, no policy, and no persistence. It reuses each service's OWN published
composition seam (``database_router.main.build_router_from_env``,
``import_service.main.build_import_service_from_env``, ...) rather than re-deriving any wiring, so
there is exactly one source of truth for every dependency and no second composition architecture.

Import-time inertness: importing this package, or any module in it, performs no environment read,
no database connection, no socket bind, no DDL, no secret materialization, and starts nothing.
Composition happens only when a factory is called.

Governance: ratified architecture. D-44 (Approved 2026-08-03) authorizes THIS composition and no
other; IC-012 is its governing contract and grants no blanket cross-service composition authority.
A future cross-service module, or any widening of the authorized set above, is admitted only through
the IC-012 §5.1 governance gate. The module census is exhaustive (IC-012 §16): ``__init__.py`` and
``import_edge.py``.
"""

from __future__ import annotations

__all__: list[str] = []
