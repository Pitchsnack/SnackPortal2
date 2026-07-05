"""PRD 07D-2b.2b D-5 — PostgresProvisioningOperator `_SAFE_IDENTIFIER.fullmatch` pin (no I/O).

The identifier guard (`_guard`) is SHARED by provision() AND deprovision() — the CREATE and
the DROP path — so this single fix is defence in depth under the first governed DROP DATABASE
caller. With `.match` Python's `$` also matches before ONE trailing newline, so a
newline-tailed target slipped past the anchor into the quoted SQL. These pins prove:

* the newline-tailed / suffix-injected negative on BOTH operations (the MR-10 kill site —
  reverting `.fullmatch` to `.match` re-admits the trailing newline and fails these tests);
* no behavior broadening: every previously-valid plain identifier still passes, every
  previously-invalid shape still fails.

The guard raises BEFORE any connection attempt, so no live PostgreSQL is needed: the
operator is constructed lazily with a reference-only placeholder DSN that is never resolved.
Standalone-runnable: `python tests/control_plane/test_postgres_provisioning_operator.py`.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane.adapters.providers.postgres_provisioning_operator import PostgresProvisioningOperator  # noqa: E402
from control_plane.provisioning import ProvisioningError  # noqa: E402

# Lazy construction records the descriptor only (no connection, no resolution) — the guard
# rejects unsafe targets BEFORE _connect(), so this placeholder is never used.
_UNUSED_DSN = "postgresql://guard-pin-only-never-connected"

_BAD_TARGETS = (
    "sp2_tenant_t1\n",  # the D-5 hazard: trailing newline admitted by `.match` + `$`
    "sp2_tenant_t1\nx",
    'sp2_tenant_t1"; DROP DATABASE "sp2_control',  # quoted-identifier injection shape
    "sp2_tenant_t1;--",
    "sp2 tenant t1",
    "sp2_tenant_t1.evil",
    "sp2_tenant_t1-x",
    "",
    "\n",
)
_GOOD_TARGETS = ("sp2_tenant_t1", "sp2_tenant_acme", "SP2_TENANT_T1", "a", "A1_b2")


def test_guard_rejects_newline_and_injection_targets_on_both_operations() -> None:
    # MR-10 kill site: `.fullmatch` must reject every suffix-bearing shape on provision()
    # AND deprovision() — the guard fires before any connection is attempted.
    op = PostgresProvisioningOperator(admin_dsn=_UNUSED_DSN)
    for bad in _BAD_TARGETS:
        for operation in ("provision", "deprovision"):
            raised = False
            try:
                if operation == "provision":
                    op.provision("t1", target=bad)
                else:
                    op.deprovision(target=bad)
            except ProvisioningError:
                raised = True
            assert raised, f"{operation}() must reject unsafe target {bad!r} (fail closed, pre-connect)"


def test_guard_accepts_plain_identifiers_no_broadening() -> None:
    # No behavior broadening: the accepted alphabet stays exactly ^[A-Za-z0-9_]+$ (full-string).
    for good in _GOOD_TARGETS:
        PostgresProvisioningOperator._guard(good)  # must not raise


def test_guard_is_shared_by_provision_and_deprovision() -> None:
    # The D-5 premise: ONE guard protects BOTH the CREATE and the DROP path. A refactor that
    # gives deprovision() its own (weaker) validation must fail this source-level pin.
    providers_dir = pathlib.Path(__file__).resolve().parents[2] / "control_plane" / "adapters" / "providers"
    module_path = providers_dir / "postgres_provisioning_operator.py"
    source = module_path.read_text(encoding="utf-8")
    assert source.count("self._guard(target)") == 2, "provision() AND deprovision() must call the shared guard"
    assert "_SAFE_IDENTIFIER.fullmatch(" in source, "the guard must use fullmatch (D-5)"
    assert "_SAFE_IDENTIFIER.match(" not in source, "no `.match` call may remain (D-5)"


_TESTS = [
    test_guard_rejects_newline_and_injection_targets_on_both_operations,
    test_guard_accepts_plain_identifiers_no_broadening,
    test_guard_is_shared_by_provision_and_deprovision,
]

if __name__ == "__main__":
    for _t in _TESTS:
        _t()
        print("PASS:", _t.__name__)
    print("ALL PASSED")
