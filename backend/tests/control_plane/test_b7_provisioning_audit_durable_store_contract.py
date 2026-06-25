"""PRD 06 B-7 — Provisioning Audit Durable Store CONTRACT guard (control-plane).

Grounds B-7 on the EXISTING control_audit table that backend/control_plane/adapters/providers/postgres_store.py already
INSERTs into / SELECTs from. Verifies the created-not-applied DDL (002_provisioning_audit.sql) is ADAPTER-INSERT
COMPATIBLE (column set + nullability + DB-generated id + ts type — so a future apply never breaks append_audit()),
references-only, append-only by design, with NO SQL CHECK enum of the event vocabulary; and that the B-7 docs map to
events.py (positive membership), keep B5-BLK-4 OPEN, and reduce B6-BLK-2. Pure stdlib; text-inspection (the Python secret
scanners EXCLUDE .sql); NO database-driver import. Standalone-runnable:
  python tests/control_plane/test_b7_provisioning_audit_durable_store_contract.py
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Dict, List, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # backend on path

from control_plane import events  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_CONTROL = _REPO_ROOT / "infrastructure" / "db" / "control"
_DDL = _CONTROL / "002_provisioning_audit.sql"
_APPEND_ONLY = _CONTROL / "003_provisioning_audit_append_only.sql"
_DOCS = _REPO_ROOT / "docs" / "runtime"
_STORE_DOC = _DOCS / "b7_provisioning_audit_durable_store.md"
_SCHEMA_DOC = _DOCS / "b7_provisioning_audit_schema.md"
_BLOCKERS_DOC = _DOCS / "b7_provisioning_audit_blockers.md"
_ADAPTER = _REPO_ROOT / "backend" / "control_plane" / "adapters" / "providers" / "postgres_store.py"

# ControlAuditRecord (records.py): Optional fields must be NULLABLE; the rest NOT NULL.
_NULLABLE = {"tenant_id", "from_state", "to_state"}
_NOT_NULL = {"actor", "action", "ts", "correlation_id"}


def _live_event_actions() -> Set[str]:
    return {v for k, v in vars(events).items() if k.isupper() and isinstance(v, str)}


def _block(text: str, start: str, end: str) -> List[str]:
    out: List[str] = []
    collecting = False
    for line in text.splitlines():
        if start in line:
            collecting = True
            continue
        if end in line:
            break
        if collecting:
            out.append(line)
    return out


def _noncomment(sql: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def _adapter_insert_columns() -> List[str]:
    text = _ADAPTER.read_text(encoding="utf-8")
    m = re.search(r"INSERT\s+INTO\s+control_audit\s*\(([^)]*)\)", text, re.IGNORECASE)
    assert m, "could not find the control_audit INSERT column list in postgres_store.py"
    return [c.strip() for c in m.group(1).split(",") if c.strip()]


def _ddl_columns() -> Dict[str, str]:
    """column name -> its comment-stripped definition line, from CREATE TABLE control_audit (...)."""
    text = _DDL.read_text(encoding="utf-8")
    m = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+control_audit\s*\((.*?)\);",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    assert m, "002 must define CREATE TABLE IF NOT EXISTS control_audit (...)"
    cols: Dict[str, str] = {}
    for raw in m.group(1).splitlines():
        line = raw.split("--", 1)[0].strip().rstrip(",").strip()
        if not line:
            continue
        name = line.split()[0]
        if name.upper() in {"PRIMARY", "CONSTRAINT", "UNIQUE", "CHECK", "FOREIGN"}:
            continue
        cols[name] = line
    return cols


def test_ddl_exists_and_created_not_applied() -> None:
    assert _DDL.is_file(), "infrastructure/db/control/002_provisioning_audit.sql must exist"
    low = _DDL.read_text(encoding="utf-8").lower()
    assert "create table if not exists control_audit" in low, "must define the EXISTING control_audit table"
    assert "not applied" in low, "DDL must carry the 'Created, NOT applied' header"
    assert "references only" in low or "references-only" in low
    up = _noncomment(_DDL.read_text(encoding="utf-8")).upper()
    for forbidden in ("DROP TABLE", "DROP DATABASE", "DROP SCHEMA", "TRUNCATE"):
        assert forbidden not in up, f"002 must not contain {forbidden}"


def test_ddl_is_adapter_insert_compatible() -> None:
    cols = _ddl_columns()
    adapter_cols = _adapter_insert_columns()
    for c in adapter_cols:
        assert c in cols, f"DDL missing adapter-inserted column {c!r}"
    assert "id" in cols, "DDL must define the id primary key (adapter does ORDER BY id ASC)"
    assert "id" not in adapter_cols, "the adapter must not insert id (it is DB-generated)"
    idline = cols["id"].upper()
    assert ("IDENTITY" in idline) or ("SERIAL" in idline) or ("DEFAULT" in idline), (
        "id must be DB-generated (GENERATED ... AS IDENTITY / serial / DEFAULT)"
    )
    for c in _NULLABLE:
        assert "NOT NULL" not in cols[c].upper(), f"{c} must be NULLABLE (ControlAuditRecord.{c} is Optional)"
    for c in _NOT_NULL:
        assert "NOT NULL" in cols[c].upper(), f"{c} must be NOT NULL"
    allowed = set(adapter_cols) | {"id"}
    for name, line in cols.items():
        if name not in allowed:
            up = line.upper()
            assert ("NOT NULL" not in up) or ("DEFAULT" in up), (
                f"extra column {name!r} is NOT NULL without DEFAULT — a future apply would break append_audit()"
            )
    assert "timestamp" in cols["ts"].lower(), "ts must be a timestamp/timestamptz type"


def test_action_has_no_sql_check_enum() -> None:
    nc = _noncomment(_DDL.read_text(encoding="utf-8"))
    assert "CHECK" not in nc.upper(), "action must be a plain text column — no SQL CHECK (events.py is the source of truth)"
    # no event name hard-coded as a SQL literal (that would be a parallel vocabulary catalog)
    for name in _live_event_actions():
        assert f"'{name}'" not in nc, f"event name {name!r} must not be hard-coded in the DDL"


def test_ddl_no_secret_literals() -> None:
    # .sql is outside the Python secret scanners (SCAN_SUFFIXES); text-inspect here. gitleaks is the whole-tree backstop.
    # Scope to the NON-COMMENT DDL body — a comment that says "NO passwords" is documentation, not a secret literal.
    low = _noncomment(_DDL.read_text(encoding="utf-8")).lower()
    for pat in ("password", "postgres://", "postgresql://", "dsn=", "secret=", "-----begin", "akia"):
        assert pat not in low, f"DDL must not contain a secret-shaped literal: {pat!r}"


def test_append_only_enforcement() -> None:
    if _APPEND_ONLY.is_file():
        text = _APPEND_ONLY.read_text(encoding="utf-8")
        up = _noncomment(text).upper()
        assert "control_audit" in text
        assert "BEFORE UPDATE OR DELETE" in up, "append-only trigger must reject UPDATE/DELETE"
        assert "BEFORE TRUNCATE" in up, "append-only trigger must reject TRUNCATE"
        assert "not applied" in text.lower(), "003 must carry the 'Created, NOT applied' header"
        assert "DROP TABLE" not in up
    else:
        # folded inline into 002 — the store doc must still document append-only
        assert "append-only" in _STORE_DOC.read_text(encoding="utf-8").lower()


def test_event_map_members_of_events_py() -> None:
    assert _SCHEMA_DOC.is_file(), "missing docs/runtime/b7_provisioning_audit_schema.md"
    text = _SCHEMA_DOC.read_text(encoding="utf-8")
    live = _live_event_actions()
    map_lines = _block(text, "B7-EVENT-MAP:START", "B7-EVENT-MAP:END")
    mapped = [ln.split("->")[-1].strip() for ln in map_lines if "->" in ln]
    assert mapped, "schema doc must carry a non-empty B7-EVENT-MAP block"
    for name in mapped:
        assert name in live, f"mapped event {name!r} is not a member of the frozen events.py vocabulary"
    # Scoped to the machine-readable block (prose that names the prohibition is exempt).
    assert "tenant.provision." not in "\n".join(map_lines), "B7 catalog must not define a parallel tenant.provision.* scheme"


def test_schema_doc_has_live_and_forward_sections() -> None:
    text = _SCHEMA_DOC.read_text(encoding="utf-8")
    low = text.lower()
    assert "control_audit" in low
    assert "forward-contract" in low or "forward contract" in low, "schema doc must carry the forward-contract extension"
    assert "28-field" in low or "richer" in low


def test_store_doc_contract() -> None:
    assert _STORE_DOC.is_file(), "missing docs/runtime/b7_provisioning_audit_durable_store.md"
    text = _STORE_DOC.read_text(encoding="utf-8")
    low = text.lower()
    assert "not applied" in low
    assert "control_audit" in low
    assert "append-only" in low
    assert "IC-004" in text and "lineage" in low and "distinct" in low
    assert "28-field" in low  # explicitly rejects the parallel table


def test_blocker_doc_reduces_b6blk2_keeps_b5blk4_open() -> None:
    assert _BLOCKERS_DOC.is_file(), "missing docs/runtime/b7_provisioning_audit_blockers.md"
    text = _BLOCKERS_DOC.read_text(encoding="utf-8")
    assert "B5-BLK-4" in text and "OPEN" in text
    assert "B6-BLK-2" in text and "reduce" in text.lower()
    assert "b5_activation_blockers.md" in text
    assert "b6_provisioning_audit_blockers.md" in text


if __name__ == "__main__":
    _failed = 0
    for _t in [
        test_ddl_exists_and_created_not_applied,
        test_ddl_is_adapter_insert_compatible,
        test_action_has_no_sql_check_enum,
        test_ddl_no_secret_literals,
        test_append_only_enforcement,
        test_event_map_members_of_events_py,
        test_schema_doc_has_live_and_forward_sections,
        test_store_doc_contract,
        test_blocker_doc_reduces_b6blk2_keeps_b5blk4_open,
    ]:
        try:
            _t()
            print("PASS:", _t.__name__)
        except AssertionError as _exc:
            _failed += 1
            print("FAIL:", _t.__name__, "-", _exc)
    if _failed:
        sys.exit(1)
    print("ALL PASSED")
