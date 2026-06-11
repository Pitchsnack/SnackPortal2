"""Membership (1:N, roles stored not evaluated) + federation config (storage only)."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from control_plane.adapters.providers.in_memory_store import InMemoryControlStore  # noqa: E402
from control_plane.federation import FederationStore  # noqa: E402
from control_plane.membership import MembershipRegistry  # noqa: E402
from control_plane.records import FederationConfig, Role  # noqa: E402


def test_one_user_many_tenants_and_master_agent_multi_assignment() -> None:
    m = MembershipRegistry(InMemoryControlStore())
    m.add_membership(principal_ref="u1", tenant_id="t1", role=Role.TENANT_ADMIN)
    m.add_membership(principal_ref="u1", tenant_id="t2", role=Role.TENANT_AGENT)
    m.add_membership(principal_ref="ma", tenant_id="t1", role=Role.MASTER_AGENT)
    m.add_membership(principal_ref="ma", tenant_id="t2", role=Role.MASTER_AGENT)
    assert len(m.tenants_for("u1")) == 2
    assert len(m.tenants_for("ma")) == 2  # MASTER_AGENT may hold many tenant assignments


def test_membership_is_storage_only() -> None:
    m = MembershipRegistry(InMemoryControlStore())
    for evaluative in ("authorize", "check_permission", "evaluate", "validate_jwt"):
        assert not hasattr(m, evaluative)


def test_federation_storage_only() -> None:
    f = FederationStore(InMemoryControlStore())
    f.put(
        FederationConfig(
            tenant_id="t1", oidc_issuer="iss", oidc_audience="aud", jwks_ref="oidc/jwks@1", claim_to_tenant_rule="claim.tenant"
        )
    )
    cfg = f.get("t1")
    assert cfg is not None and cfg.oidc_issuer == "iss" and cfg.jwks_ref == "oidc/jwks@1"
    for evaluative in ("validate", "verify_jwt", "authenticate"):
        assert not hasattr(f, evaluative)


if __name__ == "__main__":
    _h.run(
        [
            test_one_user_many_tenants_and_master_agent_multi_assignment,
            test_membership_is_storage_only,
            test_federation_storage_only,
        ]
    )
