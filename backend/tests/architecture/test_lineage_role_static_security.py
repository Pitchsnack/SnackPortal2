"""PRD 06 PMA-AR-1 — static least-privilege guard for the lineage roles (architecture; no PostgreSQL).

``infrastructure/db/lineage/003_roles.sql`` defines two NOLOGIN group roles — ``lineage_writer`` and
``lineage_reader`` — with a deliberately **table-scoped** privilege model:

* the lineage **chain** tables (``lineage``, ``lineage_segment``) are **append-only**: the writer gets
  ``SELECT, INSERT`` only, plus an **explicit** ``REVOKE UPDATE, DELETE, TRUNCATE … FROM lineage_writer`` floor;
* the **import bookkeeping** tables (``import_job``, ``import_idempotency``, ``import_checkpoint``) are
  intentionally **not** append-only — the writer legitimately holds ``UPDATE``/``INSERT`` there (upserted by the
  import coordinator);
* ``DELETE``/``TRUNCATE`` are granted to **no** role on any table; ``lineage_reader`` is ``SELECT``-only.

The live-PG harness ``tests/lineage_service/requires_pg/test_pg_privilege.py`` checks this behaviorally, but only
in the ADVISORY live-PG workflow; the required default suite blob-pins ``003`` (ATR-1) but does not assert its
*security intent*. This guard adds a required-suite static early-warning — the lineage analogue of AT2-AR-1
(``test_provisioning_role_static_security.py``) for ``sp2_provisioner`` — whose idiom it reuses.

CRITICAL DESIGN PINS (see PRD 06 PMA-AR-1 V1 R1):

* **Table-scoped** GRANT/REVOKE parsing — a role-global "writer has no UPDATE" rule would FALSE-FAIL on the
  legitimate ``GRANT … UPDATE ON import_job … TO lineage_writer``. Append-only is asserted only on the chain tables.
* Roles are created inside a ``DO $$ … $$;`` block; the ``(?:CREATE|ALTER) ROLE <name> …;`` extractor still
  captures the inner statement (it ends at the first ``;``).
* Required attribute envelope is ``NOLOGIN`` **only** (no ``CREATEDB`` — unlike ``sp2_provisioner``).
* ``\bLOGIN\b`` does not match ``NOLOGIN`` (no word boundary); comments / ``COMMENT ON ROLE`` are stripped before
  GRANT/REVOKE parsing and excluded by the role-statement extractor — never a blanket whole-file grep.

Scope: required-CI static coverage for ``003_roles.sql`` role least-privilege ONLY. It does NOT prove live
PostgreSQL state, does NOT replace ``test_pg_privilege.py``, and does NOT assert the ``002`` append-only trigger
(separately blob-pinned by ATR-1). Pure stdlib; imports no database driver; standalone-runnable:

    python tests/architecture/test_lineage_role_static_security.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_DDL = _scan.REPO_ROOT / "infrastructure" / "db" / "lineage" / "003_roles.sql"

ROLES = ("lineage_writer", "lineage_reader")
_CHAIN_TABLES = ("lineage", "lineage_segment")  # append-only chain; cross-checked against the REVOKE-derived set
_REQUIRED_ATTR = ("NOLOGIN",)  # NOTE: no CREATEDB (lineage roles differ from sp2_provisioner)
_FORBIDDEN_ATTR = ("SUPERUSER", "CREATEROLE", "REPLICATION", "BYPASSRLS", "LOGIN")
_DESTRUCTIVE = {"UPDATE", "DELETE", "TRUNCATE"}  # never allowed on a chain table for the writer
_HARD_FORBIDDEN = {"DELETE", "TRUNCATE"}  # never granted to ANY lineage role, on ANY table
_ALL_PRIVS = {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}


# Role-defining statements only (works inside the DO $$ … $$; block — ends at the first ';').
def _role_stmts(sql: str, role: str) -> list[str]:
    return re.findall(r"(?is)(?:CREATE|ALTER)\s+ROLE\s+" + re.escape(role) + r"\b[^;]*;", sql)


def _has(upper_text: str, token: str) -> bool:
    """Whole-word token presence (token already uppercase). ``\\bLOGIN\\b`` does NOT match ``NOLOGIN``."""
    return re.search(r"\b" + re.escape(token) + r"\b", upper_text) is not None


def _strip_comments(sql: str) -> str:
    """Neutralize non-executable text so prose never reaches the role/grant parsers.

    Removes ``/* … */`` block comments and ``--`` line comments, and blanks single-quoted string literals
    (where ``COMMENT ON ROLE`` prose and any grant-like wording live — also avoiding embedded ``;`` and
    forbidden keywords inside literals being mis-parsed). Safe for ``003_roles.sql``: its only literals are
    ``'lineage_writer'``/``'lineage_reader'`` inside the ``IF EXISTS`` guard, which are not part of any
    ``CREATE ROLE`` / ``GRANT`` / ``REVOKE`` statement the extractors read.
    """
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"'[^']*'", "''", sql)
    return sql


def _parse_privs(privs: str) -> set[str]:
    """Comma-separated privilege keywords → uppercase token set; ``ALL [PRIVILEGES]`` widens to every privilege."""
    toks = {p.strip().upper() for p in privs.split(",") if p.strip()}
    if any(t.startswith("ALL") for t in toks):
        return set(_ALL_PRIVS)
    return toks


def _parse_tables(tables: str) -> set[str]:
    """Comma-separated table list → lowercase name set (schema-qualified names kept as written)."""
    return {t.strip().lower() for t in tables.split(",") if t.strip()}


_GRANT_RE = re.compile(r"(?is)\bGRANT\s+(?P<privs>.+?)\s+ON\s+(?P<tables>.+?)\s+TO\s+(?P<role>\w+)\s*;")
_REVOKE_RE = re.compile(r"(?is)\bREVOKE\s+(?P<privs>.+?)\s+ON\s+(?P<tables>.+?)\s+FROM\s+(?P<role>\w+)\s*;")


def _entries(sql: str, pattern: re.Pattern[str]) -> list[tuple[str, str, set[str]]]:
    """(role, table, privset) tuples — one per (statement × table) — for a GRANT or REVOKE pattern."""
    out: list[tuple[str, str, set[str]]] = []
    for m in pattern.finditer(sql):
        privs = _parse_privs(m.group("privs"))
        role = m.group("role").lower()
        for table in _parse_tables(m.group("tables")):
            out.append((role, table, privs))
    return out


def _grants(sql: str) -> list[tuple[str, str, set[str]]]:
    return _entries(sql, _GRANT_RE)


def _revokes(sql: str) -> list[tuple[str, str, set[str]]]:
    return _entries(sql, _REVOKE_RE)


def _privs_for(entries: list[tuple[str, str, set[str]]], role: str, table: str) -> set[str]:
    out: set[str] = set()
    for r, t, privs in entries:
        if r == role and t == table:
            out |= privs
    return out


def _append_only_tables(revokes: list[tuple[str, str, set[str]]]) -> set[str]:
    """Chain tables = those where lineage_writer has an explicit destructive REVOKE (DDL-derived, not hard-coded)."""
    return {t for (r, t, privs) in revokes if r == "lineage_writer" and _DESTRUCTIVE <= privs}


# --- T1: both roles NOLOGIN with no unsafe attributes --------------------------------------------
def test_t1_lineage_roles_nologin_no_unsafe_attrs() -> None:
    clean = _strip_comments(_DDL.read_text(encoding="utf-8"))
    for role in ROLES:
        stmts = _role_stmts(clean, role)
        assert stmts, f"no CREATE/ALTER ROLE statement found for {role} in 003_roles.sql"
        u = " ".join(stmts).upper()
        for attr in _REQUIRED_ATTR:
            assert _has(u, attr), f"{role} must be {attr}; got role statement(s): {u!r}"
        granted = [a for a in _FORBIDDEN_ATTR if _has(u, a)]
        assert not granted, f"{role} has forbidden attribute(s) {granted} — lineage roles must be NOLOGIN least-privilege"


# --- T2: append-only floor on the chain tables (GRANT-narrow + explicit REVOKE) ------------------
def test_t2_chain_tables_append_only_floor() -> None:
    clean = _strip_comments(_DDL.read_text(encoding="utf-8"))
    grants, revokes = _grants(clean), _revokes(clean)
    derived = _append_only_tables(revokes)
    assert derived == set(_CHAIN_TABLES), (
        f"REVOKE-derived append-only set {sorted(derived)} != expected chain tables {sorted(_CHAIN_TABLES)} — "
        f"the explicit append-only REVOKE floor for lineage_writer drifted."
    )
    for table in _CHAIN_TABLES:
        w_granted = _privs_for(grants, "lineage_writer", table)
        extra = w_granted - {"SELECT", "INSERT"}
        assert not extra, f"lineage_writer granted non-append-only privilege(s) {sorted(extra)} on chain table {table!r}"
        w_revoked = _privs_for(revokes, "lineage_writer", table)
        missing = _DESTRUCTIVE - w_revoked
        assert not missing, (
            f"chain table {table!r} is missing the explicit REVOKE {sorted(missing)} FROM lineage_writer (append-only floor)."
        )


# --- T3: reader is SELECT-only on every table ---------------------------------------------------
def test_t3_reader_select_only() -> None:
    clean = _strip_comments(_DDL.read_text(encoding="utf-8"))
    for role, table, privs in _grants(clean):
        if role == "lineage_reader":
            extra = privs - {"SELECT"}
            assert not extra, f"lineage_reader granted non-SELECT privilege(s) {sorted(extra)} on {table!r} — must be read-only"


# --- T4: DELETE/TRUNCATE granted to NO lineage role on ANY table ---------------------------------
def test_t4_no_destructive_grant_to_lineage_roles() -> None:
    clean = _strip_comments(_DDL.read_text(encoding="utf-8"))
    for role, table, privs in _grants(clean):
        if role in ROLES:
            bad = privs & _HARD_FORBIDDEN
            assert not bad, f"{role} granted forbidden destructive privilege(s) {sorted(bad)} on {table!r} (granted to NO role)"


# --- T5: parse sanity (non-vacuity) -------------------------------------------------------------
def test_t5_parse_sanity() -> None:
    clean = _strip_comments(_DDL.read_text(encoding="utf-8"))
    role_stmt_count = sum(len(_role_stmts(clean, r)) for r in ROLES)
    assert role_stmt_count >= 2, f"expected >=2 lineage role statements; found {role_stmt_count}"
    assert len(_revokes(clean)) >= 1, "expected >=1 REVOKE statement; the GRANT/REVOKE regex matched nothing"
    assert len(_grants(clean)) >= 1, "expected >=1 GRANT statement; the GRANT/REVOKE regex matched nothing"


# --- non-vacuity (synthetic strings ONLY; never mutate the tracked DDL) --------------------------
def test_nv_unsafe_attr_detected() -> None:  # RED-PMA-AR1-1
    u = " ".join(_role_stmts("CREATE ROLE lineage_writer NOLOGIN SUPERUSER;", "lineage_writer")).upper()
    assert _has(u, "SUPERUSER")  # an unsafe attribute WOULD trip T1's forbidden check
    for attr in ("CREATEROLE", "REPLICATION", "BYPASSRLS"):
        bad = " ".join(_role_stmts(f"ALTER ROLE lineage_reader {attr};", "lineage_reader")).upper()
        assert _has(bad, attr)


def test_nv_login_vs_nologin() -> None:  # RED-PMA-AR1-2
    login = " ".join(_role_stmts("CREATE ROLE lineage_writer LOGIN;", "lineage_writer")).upper()
    assert _has(login, "LOGIN")  # standalone LOGIN detected
    nologin = " ".join(_role_stmts("CREATE ROLE lineage_writer NOLOGIN;", "lineage_writer")).upper()
    assert not _has(nologin, "LOGIN")  # NOLOGIN does NOT false-fire \bLOGIN\b


def test_nv_missing_nologin_detected() -> None:  # RED-PMA-AR1-3
    u = " ".join(_role_stmts("CREATE ROLE lineage_writer;", "lineage_writer")).upper()
    assert not _has(u, "NOLOGIN")  # dropping NOLOGIN WOULD trip T1's required-attribute check


def test_nv_destructive_chain_grant_detected() -> None:  # RED-PMA-AR1-4
    update = _grants("GRANT UPDATE ON lineage TO lineage_writer;")
    assert _privs_for(update, "lineage_writer", "lineage") == {"UPDATE"}  # not subset of {SELECT,INSERT} -> T2 fails
    delete = _grants("GRANT DELETE ON lineage_segment TO lineage_writer;")
    assert _privs_for(delete, "lineage_writer", "lineage_segment") & _HARD_FORBIDDEN == {"DELETE"}  # -> T4 fails


def test_nv_missing_chain_revoke_detected() -> None:  # RED-PMA-AR1-5
    # Chain table granted append-only privs but WITHOUT the explicit REVOKE floor.
    only_grant = "GRANT SELECT, INSERT ON lineage TO lineage_writer;"
    revoked = _privs_for(_revokes(only_grant), "lineage_writer", "lineage")
    assert _DESTRUCTIVE - revoked == _DESTRUCTIVE  # nothing revoked -> T2 REVOKE-floor check fails
    assert _append_only_tables(_revokes(only_grant)) == set()  # and the table is not in the derived append-only set


def test_nv_reader_non_select_detected() -> None:  # RED-PMA-AR1-6
    for stmt in ("GRANT INSERT ON lineage TO lineage_reader;", "GRANT UPDATE ON import_job TO lineage_reader;"):
        privs = _privs_for(_grants(stmt), "lineage_reader", _parse_tables(stmt.split(" ON ")[1].split(" TO ")[0]).pop())
        assert privs - {"SELECT"}  # any non-SELECT grant to the reader WOULD trip T3


def test_nv_import_update_not_flagged() -> None:  # RED-PMA-AR1-7  (table-scoping proof)
    real = "GRANT SELECT, INSERT, UPDATE ON import_job, import_idempotency TO lineage_writer;"
    g = _grants(real)
    # writer DOES hold UPDATE on the import bookkeeping tables ...
    assert "UPDATE" in _privs_for(g, "lineage_writer", "import_job")
    assert "UPDATE" in _privs_for(g, "lineage_writer", "import_idempotency")
    # ... but those are NOT chain tables, so T2's append-only floor never inspects them ...
    assert "import_job" not in _CHAIN_TABLES and "import_idempotency" not in _CHAIN_TABLES
    # ... and they carry no DELETE/TRUNCATE, so T4 does not flag them either.
    for table in ("import_job", "import_idempotency"):
        assert not (_privs_for(g, "lineage_writer", table) & _HARD_FORBIDDEN)


def test_nv_comments_not_flagged() -> None:  # Trap 2 — prose/COMMENT must not affect the verdict
    commented = (
        "-- lineage_writer must never be SUPERUSER or get DELETE/TRUNCATE; the LOGIN credential is external\n"
        "COMMENT ON ROLE lineage_writer IS 'NOLOGIN group role; no DELETE/TRUNCATE; LOGIN via D-14 secret store';\n"
    )
    clean = _strip_comments(commented)
    assert _role_stmts(clean, "lineage_writer") == []  # COMMENT ON ROLE is not a role-defining statement
    assert _grants(clean) == [] and _revokes(clean) == []  # and no GRANT/REVOKE is parsed out of prose
    assert "SUPERUSER" not in clean.upper() and "DELETE" not in clean.upper()  # comment words were stripped


if __name__ == "__main__":
    _scan.run(
        [
            test_t1_lineage_roles_nologin_no_unsafe_attrs,
            test_t2_chain_tables_append_only_floor,
            test_t3_reader_select_only,
            test_t4_no_destructive_grant_to_lineage_roles,
            test_t5_parse_sanity,
            test_nv_unsafe_attr_detected,
            test_nv_login_vs_nologin,
            test_nv_missing_nologin_detected,
            test_nv_destructive_chain_grant_detected,
            test_nv_missing_chain_revoke_detected,
            test_nv_reader_non_select_detected,
            test_nv_import_update_not_flagged,
            test_nv_comments_not_flagged,
        ]
    )
