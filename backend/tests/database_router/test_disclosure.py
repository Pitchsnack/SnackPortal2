"""Database Routing Disclosure Standard (PRD-P4-R2 M; Governance §I): non-leaking denials."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from database_router.disclosure import denial_for_state  # noqa: E402
from database_router.models import (  # noqa: E402
    administratively_disabled,
    forbidden,
    not_found,
    not_ready,
    unavailable,
)
from shared.errors import DenialReason  # noqa: E402


def test_http_status_mapping() -> None:
    assert not_found().http_status == 404
    assert forbidden().http_status == 403
    assert administratively_disabled().http_status == 403
    assert not_ready().http_status == 503
    assert unavailable().http_status == 503


def test_denial_reason_codes() -> None:
    assert not_found().reason is DenialReason.NOT_FOUND
    assert forbidden().reason is DenialReason.FORBIDDEN
    assert administratively_disabled().reason is DenialReason.ADMINISTRATIVELY_DISABLED
    assert not_ready().reason is DenialReason.NOT_READY
    assert unavailable().reason is DenialReason.UNAVAILABLE


def test_denial_for_state_mapping() -> None:
    assert denial_for_state("Ready", True) is None
    assert denial_for_state("Suspended", False).http_status == 403
    assert denial_for_state("Failed", False).http_status == 503
    assert denial_for_state("Provisioning", False).http_status == 503
    assert denial_for_state("Verifying", False).http_status == 503
    assert denial_for_state("Registered", False).http_status == 503
    assert denial_for_state("Decommissioned", False).reason is DenialReason.NOT_FOUND
    assert denial_for_state("Ready", False).reason is DenialReason.NOT_READY  # flag false
    assert denial_for_state("Anything-Unknown", True).reason is DenialReason.NOT_FOUND


def test_quarantined_interim_denial_is_fail_closed() -> None:
    # PRD 07D-2b.2a (AT-2B2A-6; test-only — router source unchanged): the interim behavior for
    # the new IC-002 `Quarantined` state is the fail-closed not_ready catch-all (ready=False),
    # exactly as IC-002's non-normative router note documents. Tightening Quarantined to the
    # *unavailable* denial class is a DEFERRED router-side slice; this pin proves the interim
    # is deny-by-default (never routable, never a leak) until that slice lands.
    denial = denial_for_state("Quarantined", False)
    assert denial is not None, "a Quarantined tenant must never route"
    assert denial.reason is DenialReason.NOT_READY  # interim fail-closed catch-all (documented)
    assert denial.http_status == 503
    # defence-in-depth: even a (contract-impossible) ready=True flag must not route Quarantined
    assert denial_for_state("Quarantined", True) is not None


def test_denial_carries_no_sensitive_detail() -> None:
    # Public code is a canonical, non-sensitive token — never a tenant id / dsn / host.
    for d in (not_found(), forbidden(), not_ready(), unavailable(), administratively_disabled()):
        s = str(d)
        for needle in ("tenant/", "dsn", "host=", "descriptor", "password"):
            assert needle not in s


if __name__ == "__main__":
    _h.run(
        [
            test_http_status_mapping,
            test_denial_reason_codes,
            test_denial_for_state_mapping,
            test_quarantined_interim_denial_is_fail_closed,
            test_denial_carries_no_sensitive_detail,
        ]
    )
