"""The ``WorkspaceMembershipReadPort`` adapter over the per-unit-of-work ControlStore factory.

This is the ONLY object the public workspace edge is handed on the data side. It converts the
one capability that edge legitimately needs — "given an authenticated principal reference,
enumerate that principal's tenant memberships" — into a single method, and holds nothing else
that a compromised public process could turn into a privileged action.

**What it deliberately does NOT hold.** Not a ``ControlPlane``: no provisioning operator, no
tenant-database create or drop, no schema applicator, no distinctness ledger, no
recovery/compensation service, no orphan scan, no onboarding orchestrator, no tenant registry,
no global directory, no federation store, no bootstrap controller, and no provisioning-admin
secret binding. Those objects are not hidden behind an unused attribute here — they are never
constructed on this path at all (see ``control_plane.main.build_workspace_membership_reader_from_env``).

**What it necessarily does hold.** A ``ControlStore`` factory, and therefore the Control-DB
credential *reference* the composition root already binds. That is irreducible: the route reads
Control-DB data, so something in the process must be able to reach the Control DB. What changed
is the SIZE of that authority — one enumeration instead of an administrative plane — and the
shape is deliberately credential-agnostic, so supplying a narrower, genuinely read-only
Control-DB role later is a configuration change, not a redesign.

**Per-request unit of work is preserved exactly.** Each call opens its own fresh unit of work
through the existing 07D-3b factory and releases it (rollback + close) on exit. No store is
cached, shared, or carried between calls, so the concurrency boundary the edge relied on when
it held a ``ControlPlane`` is unchanged — it simply moved behind the port.

The read itself is the EXISTING, unmodified ``ControlPlaneReadService.memberships_for_principal``
(its ordering and per-tenant de-duplication rules are what make the two store adapters agree),
so this adapter adds no read semantics of its own and cannot drift from the internal read edge.
"""

from __future__ import annotations

from typing import Any, ContextManager, Dict, Protocol

from control_plane.ports import ControlStore, WorkspaceMembershipReadPort
from control_plane.read_api import ControlPlaneReadService


class ControlStoreUnitOfWorkFactory(Protocol):
    """The 07D-3b per-unit-of-work acquisition surface, structurally.

    Structural rather than nominal so the reader binds to the CAPABILITY (acquire one store
    unit of work) instead of to either concrete factory class — which is what lets a test
    substitute a double, and what keeps this adapter from importing a driver-bound module.
    """

    def acquire(self) -> ContextManager[ControlStore]: ...


class ControlStoreMembershipReader(WorkspaceMembershipReadPort):
    """Serve the IC-002 membership enumeration from the Control DB, and nothing else."""

    def __init__(self, store_factory: ControlStoreUnitOfWorkFactory) -> None:
        self._store_factory = store_factory

    def memberships_for_principal(self, principal_ref: str) -> Dict[str, Any]:
        # One logical request == one fresh ControlStore unit of work, released (rollback +
        # close) before this returns. The store instance never escapes this block, so the
        # reader retains no reference to the full ControlStore surface between calls.
        with self._store_factory.acquire() as store:
            return ControlPlaneReadService(store).memberships_for_principal(principal_ref)


__all__ = ["ControlStoreMembershipReader", "ControlStoreUnitOfWorkFactory"]
