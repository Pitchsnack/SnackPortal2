"""PRD 07C V5 — tenant business DDL schema/placement static guards (architecture; no PostgreSQL).

Default-suite static protection for the semantic rules of the tenant business schema family
(``infrastructure/db/tenant/``), per 07C V5 §13.B / exec-auth V2 §14.2. Companion to the blob-drift guard
(``test_tenant_ddl_blob_drift.py``, which pins bytes + order); THIS guard pins the schema-level invariants
on the comment-stripped SQL text so a governed revision cannot silently violate them:

* physical placement — tenant DDL creates no ``control_*`` / registry-authority / dedicated ``global_*``
  tables, and the Control DDL family creates no tenant operational tables;
* physical multi-DB — NO ``tenant_id`` column anywhere (tenancy is one-DB-per-tenant, never a column);
* IC-007 deferral — no ``deal_shares`` / ``deal_share_targets`` / ``deal_introductions`` / shared-deal
  inbox, and no queue-manager / reservation / claim-lock structures (claim = §6.4 first-writer-wins INSERT);
* hygiene — idempotent (``IF NOT EXISTS`` / ``CREATE OR REPLACE`` / ``DROP TRIGGER IF EXISTS``) and
  transaction-safe (no ``CREATE DATABASE`` / ``CREATE INDEX CONCURRENTLY`` / ``VACUUM``) for the atomic
  Step-2b apply; jsonb tag arrays (never ``text[]``); every intra-tenant FK is ``ON DELETE RESTRICT``;
* agents / System Primary (§9) — agent_kind / agent_status / nullable supervised_by_agent_id / IDENTITY id,
  the singleton partial unique index, the protective trigger, and NO human Agent required for readiness
  ('human' appears only as the agents.agent_kind default/vocabulary — nothing requires a human row);
* ownership cardinality (§11) — human ``{entity}_ownership`` PK on the entity id; AI ``{entity}_ai_ownership``
  composite PK ``({entity}_id, ai_agent_id)``;
* keep-now columns — ``control_user_id`` / ``global_startup_id`` / ``global_investor_id`` soft refs exist;
  ``startup_contacts`` / ``investor_contacts`` exist and ``startup_users`` / ``investor_users`` do NOT.

Scope: tenant DDL family semantics only. Does NOT prove live behavior (that is the 07C requires_pg harness)
and does NOT close B5-BLK-4. Pure stdlib; imports no database driver; standalone-runnable:
  python tests/architecture/test_tenant_ddl_schema_guards.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_TENANT_DIR = _scan.REPO_ROOT / "infrastructure" / "db" / "tenant"
_CONTROL_DIR = _scan.REPO_ROOT / "infrastructure" / "db" / "control"

_EXPECTED_TENANT_TABLES = {
    "agents",
    "ai_agents",
    "startups",
    "investors",
    "deals",
    "startup_ownership",
    "investor_ownership",
    "deal_ownership",
    "startup_ai_ownership",
    "investor_ai_ownership",
    "deal_ai_ownership",
    "startup_contacts",
    "investor_contacts",
    "startup_investors",
}

_FORBIDDEN_TABLE_NAMES = {
    "deal_shares",
    "deal_share_targets",
    "deal_introductions",  # IC-007 sharing (deferred)
    "startup_users",
    "investor_users",  # rejected naming (contacts, not users)
    "global_startups",
    "global_investors",
    "global_deals",
    "global_portfolios",  # Control-Registry PRD
    "portfolios",
    "agent_roles",
    "agent_role_assignments",
    "role_entity_permissions",  # 07C.2
    "ai_draft_proposals",
    "agent_actions",  # 07C.2
}
_FORBIDDEN_TOKENS = ["queue_manager", "queue-manager", "claim_lock", "reservation", "shared_deal", "inbox", "onward"]
_NON_TRANSACTIONAL = ["CREATE DATABASE", "CONCURRENTLY", "VACUUM"]

_CREATE_TABLE_OK = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)")
_CREATE_TABLE_ANY = re.compile(r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(\w+)")
_CREATE_INDEX_ANY = re.compile(r"CREATE (?:UNIQUE )?INDEX\s+(?:IF NOT EXISTS\s+)?(\w+)")
_REFERENCES_NO_RESTRICT = re.compile(r"REFERENCES\s+\w+\s*\([^)]*\)(?!\s+ON DELETE RESTRICT)")


def _stripped(path: pathlib.Path) -> str:
    """The SQL text with ``--`` line comments removed (guards target executable DDL, not prose)."""
    return re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))


def _tenant_sql() -> dict[str, str]:
    return {p.name: _stripped(p) for p in sorted(_TENANT_DIR.glob("*.sql"))}


def _all_tenant_text() -> str:
    return "\n".join(_tenant_sql().values())


# --- placement + census ---------------------------------------------------------------------------
def test_tenant_table_census_and_placement() -> None:
    created = set(_CREATE_TABLE_ANY.findall(_all_tenant_text()))
    assert created == _EXPECTED_TENANT_TABLES, (
        f"tenant DDL table census {sorted(created)} != expected {sorted(_EXPECTED_TENANT_TABLES)}; "
        f"adding/removing a tenant business table is a governed 07C change"
    )
    offenders = {t for t in created if t.startswith(("control_", "global_"))}
    assert not offenders, f"tenant DDL must not create Control/registry authority tables: {sorted(offenders)}"
    assert not (created & _FORBIDDEN_TABLE_NAMES), f"forbidden tables in tenant DDL: {sorted(created & _FORBIDDEN_TABLE_NAMES)}"


def test_control_ddl_creates_no_tenant_tables() -> None:
    control_created: set[str] = set()
    for p in _CONTROL_DIR.glob("*.sql"):
        control_created |= set(_CREATE_TABLE_ANY.findall(_stripped(p)))
    overlap = control_created & _EXPECTED_TENANT_TABLES
    assert not overlap, f"Control DDL must not create tenant operational tables: {sorted(overlap)}"
    assert all(t.startswith("control_") for t in control_created), (
        f"Control DDL family should create only control_* tables; found {sorted(control_created)}"
    )


# --- physical multi-DB + IC-007 deferral -----------------------------------------------------------
def test_no_tenant_id_column_anywhere() -> None:
    for name, text in _tenant_sql().items():
        assert not re.search(r"\btenant_id\b", text), (
            f"{name} contains a tenant_id token — tenancy is one physical DB per tenant, never a column "
            f"(single-shared-DB + tenant_id is NOT an MVP substitute)"
        )


def test_no_forbidden_tokens() -> None:
    text = _all_tenant_text().lower()
    for token in _FORBIDDEN_TOKENS:
        assert token not in text, f"forbidden token {token!r} in tenant DDL (IC-007 / §6.4 no-queue rules)"


# --- hygiene: idempotency + transaction-safety ------------------------------------------------------
def test_idempotent_creation_patterns() -> None:
    text = _all_tenant_text()
    all_tables = _CREATE_TABLE_ANY.findall(text)
    ok_tables = _CREATE_TABLE_OK.findall(text)
    assert sorted(all_tables) == sorted(ok_tables), "every CREATE TABLE must use IF NOT EXISTS"
    idx_all = _CREATE_INDEX_ANY.findall(text)
    idx_ok = re.findall(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+)", text)
    assert sorted(idx_all) == sorted(idx_ok), "every CREATE INDEX must use IF NOT EXISTS"
    n_triggers = len(re.findall(r"\bCREATE TRIGGER\b", text))
    n_drops = len(re.findall(r"\bDROP TRIGGER IF EXISTS\b", text))
    assert n_triggers == n_drops, "every CREATE TRIGGER must be preceded by DROP TRIGGER IF EXISTS (idempotent re-apply)"
    n_funcs = len(re.findall(r"\bCREATE OR REPLACE FUNCTION\b", text))
    n_funcs_any = len(re.findall(r"\bCREATE (?:OR REPLACE )?FUNCTION\b", text))
    assert n_funcs == n_funcs_any, "every function must use CREATE OR REPLACE (idempotent re-apply)"


def test_transaction_safe() -> None:
    text = _all_tenant_text().upper()
    for token in _NON_TRANSACTIONAL:
        assert token not in text, f"non-transactional statement {token!r} in tenant DDL (breaks atomic Step-2b apply)"


def test_all_fks_on_delete_restrict() -> None:
    for name, text in _tenant_sql().items():
        bad = _REFERENCES_NO_RESTRICT.findall(text)
        assert not bad, f"{name}: every intra-tenant FK must be ON DELETE RESTRICT; offending clauses: {bad}"


def test_jsonb_tags_not_text_arrays() -> None:
    text = _all_tenant_text()
    assert "text[]" not in text, "tag arrays must be jsonb, never text[]"
    for col in ("product_service_tags", "market_tags", "investment_stage_focus", "industry_focus"):
        assert re.search(col + r"\s+jsonb\s+NOT NULL DEFAULT '\[\]'::jsonb", text), f"{col} must be `jsonb NOT NULL DEFAULT '[]'::jsonb`"


# --- agents / System Primary (§9) -------------------------------------------------------------------
def test_agents_shape_statics() -> None:
    text = _tenant_sql()["001_agents.sql"]
    assert re.search(r"agent_kind\s+text\s+NOT NULL DEFAULT 'human'", text), "agents.agent_kind must exist, default 'human'"
    assert re.search(r"agent_status\s+text\s+NOT NULL DEFAULT 'active'", text), "agents.agent_status must exist, default 'active'"
    assert re.search(r"supervised_by_agent_id\s+bigint\s+REFERENCES agents\(id\)", text), "supervised_by_agent_id must exist"
    assert not re.search(r"supervised_by_agent_id\s+bigint\s+NOT NULL", text), "supervised_by_agent_id must be NULLABLE"
    assert re.search(r"id\s+bigint\s+GENERATED ALWAYS AS IDENTITY PRIMARY KEY", text), "agents.id must be IDENTITY"
    assert re.search(r"control_user_id\s+text", text), "agents.control_user_id text NULL must exist (soft Control ref)"
    assert "ux_agents_single_system_primary" in text and "WHERE agent_kind = 'system_primary'" in text, (
        "the System Primary singleton partial unique index must exist"
    )
    assert "agents_sp_unsupervised" in text and "agents_sp_active" in text, "System Primary safety CHECKs must exist"
    assert "trg_agents_protect_system_primary" in text and "BEFORE UPDATE OR DELETE ON agents" in text, (
        "the System Primary protective trigger (DELETE / kind-flip) must exist"
    )
    assert "INSERT INTO agents" not in _all_tenant_text(), "07C DDL must NOT seed System Primary (07B.1 owns the seed)"


def test_no_human_agent_required_for_readiness() -> None:
    # 'human' may appear ONLY as the agents.agent_kind default + CHECK vocabulary — nothing may REQUIRE a
    # human row for a fresh tenant (07C V5 §11.3: fresh bootstrap has zero human Agents).
    sql = _tenant_sql()
    occurrences = sql["001_agents.sql"].count("'human'")
    assert occurrences == 2, f"'human' must appear exactly twice in 001 (DEFAULT + CHECK vocab); found {occurrences}"
    for name, text in sql.items():
        if name != "001_agents.sql":
            assert "'human'" not in text, f"{name} must not reference 'human' (no human-required constraints)"


def test_ai_agents_tenant_local() -> None:
    text = _tenant_sql()["002_ai_agents.sql"]
    assert "CREATE TABLE IF NOT EXISTS ai_agents" in text, "ai_agents must be a tenant-DB table (002)"
    assert re.search(r"supervising_agent_id\s+bigint\s+NOT NULL REFERENCES agents\(id\) ON DELETE RESTRICT", text), (
        "ai_agents.supervising_agent_id must be a mandatory FK to agents(id) ON DELETE RESTRICT"
    )
    for p in _CONTROL_DIR.glob("*.sql"):
        assert "ai_agents" not in _stripped(p), f"ai_agents must not appear in Control DDL ({p.name})"


# --- ownership cardinality (§11) ---------------------------------------------------------------------
def test_ownership_pk_shapes() -> None:
    text = _tenant_sql()["006_ownership.sql"]
    for entity in ("startup", "investor", "deal"):
        assert re.search(rf"{entity}_ownership \(\s*{entity}_id\s+bigint\s+PRIMARY KEY", text), (
            f"{entity}_ownership must have PRIMARY KEY ({entity}_id) — at-most-one human owner"
        )
        assert re.search(rf"PRIMARY KEY \({entity}_id, ai_agent_id\)", text), (
            f"{entity}_ai_ownership must have composite PRIMARY KEY ({entity}_id, ai_agent_id)"
        )
        assert re.search(rf"{entity}_ai_ownership \(\s*{entity}_id\s+bigint\s+NOT NULL REFERENCES", text), (
            f"{entity}_ai_ownership.{entity}_id must be NOT NULL with an FK"
        )


# --- keep-now columns + contacts ---------------------------------------------------------------------
def test_keep_now_soft_reference_columns() -> None:
    sql = _tenant_sql()
    assert re.search(r"global_startup_id\s+text", sql["003_startups.sql"]), "startups.global_startup_id text NULL must exist"
    assert re.search(r"global_investor_id\s+text", sql["004_investors.sql"]), "investors.global_investor_id text NULL must exist"
    for name, col in (("003_startups.sql", "global_startup_id"), ("004_investors.sql", "global_investor_id")):
        assert not re.search(col + r"\s+text\s+NOT NULL", sql[name]), f"{col} must be NULLABLE (soft ref)"


def test_contacts_exist_users_absent() -> None:
    text = _tenant_sql()["007_links.sql"]
    for t in ("startup_contacts", "investor_contacts", "startup_investors"):
        assert f"CREATE TABLE IF NOT EXISTS {t}" in text, f"{t} must exist in 007_links.sql"
    everything = _all_tenant_text()
    assert "startup_users" not in everything and "investor_users" not in everything, (
        "startup_users / investor_users must NOT exist (contacts, not users — 07C V5 §12)"
    )


# --- non-vacuity (string fixtures only; never writes into governed dirs) ------------------------------
def test_nv_guards_detect_violations() -> None:
    assert _CREATE_TABLE_ANY.findall("CREATE TABLE bad (x int);") == ["bad"]  # non-idempotent WOULD be seen
    assert _CREATE_TABLE_OK.findall("CREATE TABLE bad (x int);") == []  # ...and WOULD fail the idempotency test
    assert _REFERENCES_NO_RESTRICT.search("startup_id bigint REFERENCES startups(id),")  # missing RESTRICT WOULD fail
    assert not _REFERENCES_NO_RESTRICT.search("startup_id bigint REFERENCES startups(id) ON DELETE RESTRICT,")
    assert re.search(r"\btenant_id\b", "tenant_id text NOT NULL")  # a tenant_id column WOULD be detected
    stripped = re.sub(r"--[^\n]*", "", "real sql -- tenant_id only in a comment\n")
    assert "tenant_id" not in stripped  # comments are excluded from token checks


if __name__ == "__main__":
    _scan.run(
        [
            test_tenant_table_census_and_placement,
            test_control_ddl_creates_no_tenant_tables,
            test_no_tenant_id_column_anywhere,
            test_no_forbidden_tokens,
            test_idempotent_creation_patterns,
            test_transaction_safe,
            test_all_fks_on_delete_restrict,
            test_jsonb_tags_not_text_arrays,
            test_agents_shape_statics,
            test_no_human_agent_required_for_readiness,
            test_ai_agents_tenant_local,
            test_ownership_pk_shapes,
            test_keep_now_soft_reference_columns,
            test_contacts_exist_users_absent,
            test_nv_guards_detect_violations,
        ]
    )
