"""PRD 06 AT2-AR-1 — static least-privilege guard for sp2_provisioner (architecture; no PostgreSQL).

AT-2 (PRD 06) asserts ``sp2_provisioner``'s least-privilege attributes behaviorally, but only in the ADVISORY
live-PG harness. The required default suite catches *edits* to ``003_provisioning_role.sql`` via the AT-1
blob-drift guard, yet does not assert the *security intent* in required CI. This guard adds a required-suite
static early-warning: it parses ``003`` and fails if ``sp2_provisioner`` is granted a dangerous privilege.

CRITICAL PARSING TRAP. ``003_provisioning_role.sql`` contains the word "login credential" in a ``--`` header
comment AND in its ``COMMENT ON ROLE`` body — a naive whole-file ``LOGIN`` scan would false-positive. This
guard therefore extracts ONLY the ``CREATE ROLE sp2_provisioner`` and ``ALTER ROLE sp2_provisioner``
statements (the actual grants) and checks privilege tokens there. (``\bLOGIN\b`` also correctly does NOT match
inside ``NOLOGIN`` — no word boundary — so the required ``NOLOGIN`` and the forbidden ``LOGIN`` coexist
safely once comments are excluded.)

This is a required-CI early-warning complement; it does NOT replace the live-PG AT-2 behavioral check, and it
targets only ``003_provisioning_role.sql``. Pure stdlib; imports no database driver; standalone-runnable:

    python tests/architecture/test_provisioning_role_static_security.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_DDL_003 = _scan.REPO_ROOT / "infrastructure" / "db" / "provisioning" / "003_provisioning_role.sql"

# Capture ONLY the role-defining statements for sp2_provisioner (excludes `--` comments and COMMENT ON ROLE).
_ROLE_STMT = re.compile(r"(?is)(?:CREATE|ALTER)\s+ROLE\s+sp2_provisioner\b[^;]*;")

_REQUIRED = ("NOLOGIN", "CREATEDB")  # the intended positive envelope
_FORBIDDEN = ("SUPERUSER", "CREATEROLE", "REPLICATION", "BYPASSRLS", "LOGIN")  # must never be granted


# --- helpers (stdlib only; no DB) ----------------------------------------------------------------
def _role_statements(sql_text: str) -> list[str]:
    """The CREATE/ALTER ROLE sp2_provisioner statements only (NOT comments, NOT COMMENT ON ROLE)."""
    return _ROLE_STMT.findall(sql_text)


def _has_token(upper_text: str, token: str) -> bool:
    """Whole-word token presence (token is already uppercase). \\bLOGIN\\b does not match NOLOGIN."""
    return re.search(r"\b" + re.escape(token) + r"\b", upper_text) is not None


def _grant_text(sql_text: str) -> str:
    return " ".join(_role_statements(sql_text)).upper()


# --- the guard -----------------------------------------------------------------------------------
def test_at2ar1_positive_envelope_present() -> None:
    u = _grant_text(_DDL_003.read_text(encoding="utf-8"))
    for token in _REQUIRED:
        assert _has_token(u, token), f"003_provisioning_role.sql sp2_provisioner statements must keep {token}; got grant text: {u!r}"


def test_at2ar1_forbidden_privileges_absent() -> None:
    u = _grant_text(_DDL_003.read_text(encoding="utf-8"))
    granted = [t for t in _FORBIDDEN if _has_token(u, t)]
    assert not granted, (
        f"003_provisioning_role.sql grants forbidden privilege(s) to sp2_provisioner: {granted}. "
        f"Least-privilege violated — sp2_provisioner must be CREATEDB + NOLOGIN only."
    )


def test_at2ar1_parse_sanity() -> None:
    # Guard against a regex that silently matches nothing (which would make the checks vacuously pass).
    stmts = _role_statements(_DDL_003.read_text(encoding="utf-8"))
    assert len(stmts) >= 2, f"expected >=2 CREATE/ALTER ROLE sp2_provisioner statements; found {len(stmts)}: {stmts}"


# --- non-vacuity ---------------------------------------------------------------------------------
def test_nv_forbidden_detected_and_required_missing() -> None:
    bad = "ALTER ROLE sp2_provisioner SUPERUSER;"
    assert _has_token(_grant_text(bad), "SUPERUSER")  # a SUPERUSER grant WOULD trip the forbidden check
    no_nologin = "CREATE ROLE sp2_provisioner CREATEDB;"
    assert not _has_token(_grant_text(no_nologin), "NOLOGIN")  # dropping NOLOGIN WOULD trip the positive check


def test_nv_comment_login_not_flagged() -> None:
    # The COMMENT prose contains "login credential"; the extractor must NOT treat it as a grant.
    comment_only = (
        "-- the actual LOGIN credential is resolved from the D-14 secret store\n"
        "COMMENT ON ROLE sp2_provisioner IS 'NOLOGIN group role; login credential via D-14 secret store';\n"
    )
    assert _role_statements(comment_only) == []  # no CREATE/ALTER ROLE -> nothing extracted
    assert not _has_token(_grant_text(comment_only), "LOGIN")  # so the forbidden LOGIN is NOT falsely flagged


if __name__ == "__main__":
    _scan.run(
        [
            test_at2ar1_positive_envelope_present,
            test_at2ar1_forbidden_privileges_absent,
            test_at2ar1_parse_sanity,
            test_nv_forbidden_detected_and_required_missing,
            test_nv_comment_login_not_flagged,
        ]
    )
