"""Disclosure controls: no token/secret in context; 401 vs 403 semantics (IC-005 / L-3)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402
import doubles as D  # noqa: E402  (ensures path setup)

from auth_router.models import AuthContext, forbidden, not_ready, unauthenticated  # noqa: E402


def test_authcontext_has_no_token_or_secret_field() -> None:
    ctx = AuthContext(correlation_id="c", principal_ref="u", active_tenant_id="t", role="TENANT_ADMIN")
    for bad in ("token", "jwt", "secret", "credential", "password", "jwks", "material"):
        assert not hasattr(ctx, bad)


def test_status_code_semantics() -> None:
    assert unauthenticated().http_status == 401
    assert forbidden().http_status == 403
    # not-ready is a member-only signal (403 retry), distinct from the consistent 403 denial code
    assert not_ready().http_status == 403


if __name__ == "__main__":
    _h.run([test_authcontext_has_no_token_or_secret_field, test_status_code_semantics])
