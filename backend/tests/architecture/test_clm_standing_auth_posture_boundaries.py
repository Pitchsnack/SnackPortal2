"""Static guard for the AUTHFIX-B replacement standing authentication verification harness.

AUTHFIX-B requires the B5-4A standing auth fixture family to be superseded **by an accepted
replacement** — a new standing verification harness, not an annotation. This guard pins the
replacement's defining properties, because the ways it could quietly stop being a replacement are
specific and recognisable:

* **It must be read-only.** The predecessor's successor verifies a live standing database. A harness
  that can write is one membership INSERT away from manufacturing the state it claims to observe —
  and creating a membership row to make a journey pass is a Gate-B class-M6 mutation that destroys
  the evidence rather than producing it.
* **It must not pin a roster.** The predecessor pinned `b5_standing_alpha` / `b5_standing_beta` /
  `b5_standing_dormant` and a whole-table membership count of exactly three. The standing fixture was
  replaced; the pins survived; the harness went red and, being MANUAL_ONLY, nobody saw it. A
  replacement that re-pins a roster reproduces that failure with new names.
* **It must fail closed on an absent census.** If `control_tenants` / `control_memberships` are
  missing, every downstream check passes for the wrong reason.
* **It must skip explicitly.** A bare `return` on an unconfigured machine is recorded by pytest as a
  PASS — the vacuous green this whole exercise exists to eliminate.
* **It must state the supersession and its non-claims.** The evidence chain depends on nobody reading
  a coherence check as an authenticated-journey proof.
* **Every column it selects must exist in the governed Control DDL — in every ordinary spelling.**
  The harness selected `database_association_ref`, an application-record field that is not a column,
  and aborted every run with `undefined_column` unobserved (RB-2). The check parses the on-disk DDL
  for the valid column set and normalizes each select-list item — stripping `AS` and implicit
  aliases, and reducing `table.column` to its column component — so the same defect cannot re-enter
  through a spelling a bare-identifier scan discards.

Pure stdlib; runnable standalone:
    python tests/architecture/test_clm_standing_auth_posture_boundaries.py
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from typing import Dict, FrozenSet, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_REPLACEMENT = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "test_pg_clm_standing_auth_posture.py"
_PREDECESSOR = _scan.BACKEND_ROOT / "tests" / "control_plane" / "requires_pg" / "b5_standing_auth_fixture.py"
_PREDECESSOR_RUNBOOK = _scan.REPO_ROOT / "infrastructure" / "runbooks" / "b5_standing_auth_fixture.md"
_COMPLETENESS_GUARD = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_live_pg_workflow_runset_completeness.py"
_CONTROL_DDL_DIR = _scan.REPO_ROOT / "infrastructure" / "db" / "control"

# The roster the predecessor pinned. None of it may reappear as an assertion in the replacement.
_RETIRED_SUBJECT_STATE = ("b5_standing_alpha", "b5_standing_beta", "b5_standing_dormant", "b5_standing_member")

# Application-layer names that are NOT Control-DB columns. `database_association_ref` is the
# `TenantRecord` field (backend/control_plane/records.py:38) and the served routing-DTO key
# (control_plane/read_api.py:52) — a SecretRef the adapter SPLITS into the two governed columns
# `assoc_store_ref` / `assoc_version`. Selecting it from `control_tenants` aborts with
# `undefined_column` on the first row fetched, which is RB-2.
_NOT_A_COLUMN = ("database_association_ref",)

# `CREATE TABLE IF NOT EXISTS <name> ( ... \n);` — the closing paren anchored at line start so a
# nested `CHECK (...)` cannot terminate the body early.
_CREATE_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+(?P<table>\w+)\s*\((?P<body>.*?)^\);", re.DOTALL | re.MULTILINE)
_SELECT_FROM = re.compile(r"SELECT\s+(?P<columns>.+?)\s+FROM\s+(?P<table>[a-z_][a-z0-9_]*)", re.IGNORECASE | re.DOTALL)
# Table-constraint keywords that open a line inside a CREATE TABLE body but name no column.
_TABLE_CONSTRAINT_KEYWORDS = frozenset({"PRIMARY", "CONSTRAINT", "UNIQUE", "CHECK", "FOREIGN", "EXCLUDE", "LIKE"})

# A select-list item's ALIAS, explicit (`expr AS name`) or implicit (`expr name`). Stripped BEFORE
# the identifier test, because a bare-identifier-only extractor silently DISCARDS every aliased item
# — so `database_association_ref AS extra` was never checked against the schema at all, and the RB-2
# defect could be reintroduced verbatim in one of SQL's two ordinary spellings for the same thing.
_ALIASED = re.compile(r"^(?P<expression>.+?)\s+(?:AS\s+)?(?P<alias>[a-z_][a-z0-9_]*)$", re.IGNORECASE | re.DOTALL)
# An optionally table-qualified column reference. `control_tenants.database_association_ref` names
# the SAME column as the bare form; discarding it because of the dot is the other bypass.
_QUALIFIED = re.compile(r"^(?:(?P<qualifier>[a-z_][a-z0-9_]*)\.)?(?P<column>[a-z_][a-z0-9_]*)$", re.IGNORECASE)
# Leading select-list modifiers that are not part of the first item's expression.
_SELECT_MODIFIERS = ("DISTINCT ON", "DISTINCT", "ALL")


def _split_top_level(columns: str) -> List[str]:
    """Split a select list on its TOP-LEVEL commas only.

    `md5(a, b)` is one item, not two. A naive `.split(",")` turns the tail of a function call into a
    bare identifier that happens to look like a column name.
    """
    items: List[str] = []
    depth = 0
    current: List[str] = []
    for character in columns:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if character == "," and depth == 0:
            items.append("".join(current))
            current = []
            continue
        current.append(character)
    items.append("".join(current))
    return [item.strip() for item in items if item.strip()]


def _column_component(item: str) -> Optional[Tuple[Optional[str], str]]:
    """`(qualifier, column)` for a select-list item, or `None` when it names no single column.

    Aliases are stripped first, then the qualifier is separated from the column. An expression — a
    call, a cast, an operator, `*` — names no single column and is skipped rather than guessed at,
    exactly as before; what changed is that `x AS y` and `t.x` are now *normalized* instead of being
    discarded along with the expressions. Discarding them is what made the anti-recurrence guard
    porous: `database_association_ref AS extra` and `control_tenants.database_association_ref` are
    the same nonexistent column as the bare form, and each would abort a live run identically.
    """
    candidate = item.strip()
    for modifier in _SELECT_MODIFIERS:
        if candidate.upper().startswith(modifier + " "):
            candidate = candidate[len(modifier) :].strip()
            break
    for _ in range(2):  # `t.col AS name` needs one alias strip and one qualifier strip
        qualified = _QUALIFIED.fullmatch(candidate)
        if qualified is not None:
            return qualified.group("qualifier"), qualified.group("column")
        aliased = _ALIASED.fullmatch(candidate)
        if aliased is None:
            return None
        candidate = aliased.group("expression").strip()
    return None


def _text() -> str:
    return _REPLACEMENT.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_text(), filename=str(_REPLACEMENT))


def governed_control_columns() -> Dict[str, FrozenSet[str]]:
    """`{table: {column, ...}}` parsed from the governed on-disk Control DDL — the schema contract."""
    tables: Dict[str, FrozenSet[str]] = {}
    for path in sorted(_CONTROL_DDL_DIR.glob("*.sql")):
        for match in _CREATE_TABLE.finditer(path.read_text(encoding="utf-8")):
            columns = set()
            for raw in match.group("body").splitlines():
                line = raw.strip()
                if not line or line.startswith("--"):
                    continue
                token = line.split()[0].strip('",')
                if token.upper() in _TABLE_CONSTRAINT_KEYWORDS:
                    continue
                if re.fullmatch(r"[a-z_][a-z0-9_]*", token):
                    columns.add(token)
            tables[match.group("table")] = frozenset(columns)
    return tables


def selected_control_columns(source: str) -> List[Tuple[str, str]]:
    """Every `(table, column)` a SQL literal in `source` selects from a GOVERNED Control table.

    Column references only: an expression (`count(*)`, a cast, a function call) names no single
    column and is skipped rather than guessed at. `SELECT *` is likewise skipped — it selects
    whatever exists, so it cannot drift against the schema. Aliases are STRIPPED and qualifiers are
    NORMALIZED to the column they name, so all four ordinary spellings of one reference —
    `col`, `col AS x`, `col x`, `tbl.col` (and `tbl.col AS x`) — reach the same `(table, column)`
    pair and the same existence check.
    """
    governed = governed_control_columns()
    pairs: List[Tuple[str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        for match in _SELECT_FROM.finditer(node.value):
            table = match.group("table")
            if table not in governed:
                continue
            for item in _split_top_level(match.group("columns")):
                component = _column_component(item)
                if component is None:
                    continue
                qualifier, column = component
                # A qualifier naming a governed table attributes the column to THAT table; anything
                # else (a range alias) belongs to the table this SELECT reads.
                pairs.append(((qualifier if qualifier in governed else table), column))
    return pairs


def unknown_control_columns(source: str) -> List[Tuple[str, str]]:
    """The `(table, column)` pairs `source` selects that the governed Control DDL does NOT define.

    Fails closed: with the DDL unreadable `governed_control_columns()` is empty, no table is
    recognised, and the callers' non-vacuity assertions turn red rather than green.
    """
    governed = governed_control_columns()
    return [(table, column) for table, column in selected_control_columns(source) if column not in governed.get(table, frozenset())]


def test_replacement_exists_and_is_registered() -> None:
    assert _REPLACEMENT.is_file(), (
        "AUTHFIX-B requires supersession BY AN ACCEPTED REPLACEMENT — a new standing verification harness delivered "
        "under Gate A. An annotation-only disposition is a narrowing of that requirement, not a satisfaction of it."
    )
    guard = _COMPLETENESS_GUARD.read_text(encoding="utf-8")
    assert f"tests/control_plane/requires_pg/{_REPLACEMENT.name}" in guard, (
        "the replacement must carry a justified MANUAL_ONLY_EXCEPTIONS key in the same commit as the file"
    )


def test_replacement_is_strictly_read_only() -> None:
    text = _text()
    for write in ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE", "CREATE TABLE", "DROP ", "ALTER TABLE", "commit("):
        assert write not in text, f"the replacement must be strictly read-only (found {write!r})"
    assert "read_only = True" in text, "the verification connection must be set read-only"
    assert "class-M6" in text, (
        "the harness must state, in its own text, that creating a membership row to make a journey pass is a Gate-B "
        "M6 mutation that destroys the evidence — the single most tempting wrong move on this surface"
    )


def test_replacement_does_not_re_pin_a_roster() -> None:
    """The specific failure being replaced, asserted so it cannot be reintroduced under new names."""
    tree = _tree()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        source = ast.get_source_segment(_text(), node) or ""
        for retired in _RETIRED_SUBJECT_STATE:
            assert retired not in source, (
                f"the replacement asserts on the RETIRED subject state {retired!r}. That roster no longer exists — "
                "re-pinning it is how the predecessor died."
            )
        # A whole-table count equality is the other half of the predecessor's brittleness.
        assert "len(memberships) ==" not in source, (
            "the replacement must not pin the membership count. The predecessor pinned it at exactly three; the "
            "standing fixture changed; the harness went red and, being MANUAL_ONLY, nobody observed it."
        )
    assert "REPORTED, not pinned" in _text() or "REPORTS the roster" in _text() or "reported, never pinned" in _text().lower(), (
        "the harness must say which invariants it asserts and which state it merely reports"
    )


def test_replacement_fails_closed_on_a_vacuous_census() -> None:
    text = _text()
    assert "CSA-2" in text and "pass vacuously" in text, (
        "the harness must assert the authentication-bearing tables EXIST before checking anything about their "
        "contents — absent tables make every downstream check pass for the wrong reason"
    )
    assert "assert _table_exists(conn, table)" in text, "table presence must be asserted, not assumed"
    assert "assert tenants," in text, "an empty registry must fail, not pass silently"


def test_replacement_skips_explicitly_rather_than_returning() -> None:
    assert "unittest.SkipTest" in _text(), (
        "an unconfigured run must raise SkipTest. A bare `return` is recorded by pytest as a PASS — the vacuous "
        "green that let the predecessor's red go unobserved."
    )
    node = _skip_branch()
    bare_returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    assert not bare_returns, (
        "the verification entrypoint must contain no `return` statement: an early return on an unconfigured machine "
        "is exactly the vacuous PASS this replacement exists to stop reproducing"
    )
    raises = [n for n in ast.walk(node) if isinstance(n, ast.Raise)]
    assert raises, "the skip path must RAISE, not return"


def _skip_branch() -> ast.AST:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == "test_clm_standing_auth_posture":
            return node
    raise AssertionError("the replacement must expose test_clm_standing_auth_posture()")


def test_replacement_states_supersession_and_non_claims() -> None:
    text = _text()
    assert "SUPERSESSION" in text, "the harness must state that it supersedes the B5-4A fixture's subject-state census"
    assert "NO OVERCLAIM" in text, "the harness must state its non-claims"
    for non_claim in ("does NOT prove an authenticated journey", "does NOT prove the tenant data plane"):
        assert non_claim in text, f"the harness must disclaim: {non_claim}"


def test_predecessor_is_marked_superseded_and_left_intact() -> None:
    """Retirement-by-deletion was NOT chosen, and must not happen by accident."""
    assert _PREDECESSOR.is_file(), (
        "the predecessor must NOT be deleted. Its checks are still referenced by four default-suite guards and by "
        "the MANUAL_ONLY completeness invariants; deleting it turns those red."
    )
    text = _PREDECESSOR.read_text(encoding="utf-8")
    assert "SUPERSEDED" in text, "the predecessor must carry an explicit supersession marking"
    assert _REPLACEMENT.name in text, "the predecessor must name its replacement so a reader can follow the chain"
    # The supersession banner must not break the delegating surfaces' PASS-count arithmetic.
    banner_lines = [line for line in text.splitlines() if "SUPERSEDED" in line]
    for line in banner_lines:
        assert "PASS:" not in line, (
            "a supersession banner containing the substring 'PASS:' silently breaks the delegating operators' exact "
            "PASS-count arithmetic (they count occurrences)"
        )
    runbook = _PREDECESSOR_RUNBOOK.read_text(encoding="utf-8")
    assert "SUPERSEDED" in runbook, "the predecessor's runbook must carry the supersession notice too"
    for banned in ("B5-BLK-4 CLOSED", "MVP COMPLETE", "Smoke C passed", "Smoke C succeeded", "Smoke C has been executed"):
        assert banned not in runbook, f"the supersession notice must not introduce the banned claim {banned!r}"


def test_every_selected_column_exists_in_the_governed_control_ddl() -> None:
    """RB-2. The harness's SQL must agree with the on-disk schema contract, checked mechanically.

    The defect: the harness selected `database_association_ref` from `control_tenants`. That is the
    `TenantRecord` FIELD and the served routing-DTO KEY — a `SecretRef` the Control-Plane adapter
    splits into the two governed columns `assoc_store_ref` / `assoc_version`
    (`infrastructure/db/control/004_control_tenants.sql:38-39`). There is no such column, so the
    harness aborted with `undefined_column` on its very first census row — and because the family is
    MANUAL_ONLY, no automated gate ever observed the red.

    A prose review does not catch a one-identifier drift between two files that never import each
    other. Parsing both and comparing does, for EVERY column, not just the one that broke.
    """
    governed = governed_control_columns()
    assert "control_tenants" in governed and "control_memberships" in governed, (
        f"the governed Control DDL must be parseable for this check to mean anything; parsed tables: {sorted(governed)}"
    )
    pairs = selected_control_columns(_text())
    assert len(pairs) >= 6, (
        f"only {len(pairs)} governed column reference(s) were extracted from the harness. This check is vacuous if it "
        "sees nothing — the harness selects the tenant registry and the membership roster by name."
    )
    unknown = unknown_control_columns(_text())
    assert not unknown, "\n".join(
        f"the harness selects {column!r} from {table}, which the governed Control DDL does not define. "
        f"{table} carries: {sorted(governed[table])}. A name that exists in the application record is not a column."
        for table, column in unknown
    )
    for banned in _NOT_A_COLUMN:
        assert banned not in {column for _table, column in pairs}, (
            f"{banned!r} is an application-layer field name, not a Control-DB column. Selecting it is RB-2: the harness "
            "aborts with undefined_column on the first row and, being MANUAL_ONLY, does so unobserved."
        )
    # The two reference columns the CSA-4 assertion depends on must be the ones actually selected.
    selected_from_tenants = {column for table, column in pairs if table == "control_tenants"}
    assert {"assoc_store_ref", "assoc_version"} <= selected_from_tenants, (
        "CSA-4 verifies a SecretRef, and a SecretRef is BOTH halves: a store_ref with no version names nothing "
        f"resolvable. Selected from control_tenants: {sorted(selected_from_tenants)}"
    )


def test_the_schema_contract_guard_sees_every_ordinary_spelling_of_the_drift() -> None:
    """RB-2 anti-recurrence, hardened. The EXACT drift was refused; two ordinary variants were not.

    The predecessor of this check kept only select-list items matching `[a-z_][a-z0-9_]*` in full,
    so `database_association_ref AS extra` and `control_tenants.database_association_ref` were
    DISCARDED before the existence test ever ran. Both are the same nonexistent column, both abort a
    live run with `undefined_column` on the first census row, and both passed the guard.

    Every spelling is exercised against the real extractor here, so the mutation is proven caught in
    this file rather than only in a report.
    """
    governed = governed_control_columns()
    assert "database_association_ref" not in governed["control_tenants"], (
        "the parser must agree the drifted name is not a column, or every case below passes for the wrong reason"
    )
    base = "SELECT tenant_id, lifecycle_state, {} assoc_store_ref, assoc_version FROM control_tenants ORDER BY tenant_id"
    for label, spelling in (
        ("bare", "database_association_ref,"),
        ("explicitly aliased", "database_association_ref AS extra,"),
        ("implicitly aliased", "database_association_ref extra,"),
        ("table-qualified", "control_tenants.database_association_ref,"),
        ("qualified AND aliased", "control_tenants.database_association_ref AS extra,"),
        ("qualified by a range alias", "t.database_association_ref,"),
    ):
        source = f'X = "{base.format(spelling)}"\n'
        assert ("control_tenants", "database_association_ref") in selected_control_columns(source), (
            f"the {label} spelling was not extracted at all, so it was never checked against the schema. That is how "
            "the same defect re-enters through a form the guard cannot see."
        )
        assert unknown_control_columns(source), f"the {label} spelling must be reported as a column the governed DDL does not define"

    # And the forms that legitimately name no single column must still be skipped, not guessed at.
    for benign in (
        'X = "SELECT count(*) FROM control_audit"\n',
        'X = "SELECT count(*) AS total FROM control_audit"\n',
        'X = "SELECT * FROM control_audit"\n',
        'X = "SELECT system_identifier FROM pg_control_system()"\n',
    ):
        assert unknown_control_columns(benign) == [], f"an expression or ungoverned table must not be reported: {benign!r}"
    # A multi-argument call is ONE item: a naive comma split turns its tail into a bare identifier.
    assert unknown_control_columns('X = "SELECT md5(concat(tenant_id, lifecycle_state)) FROM control_tenants"\n') == [], (
        "a function call carrying commas must be split as one select-list item, not several"
    )
    # A GOVERNED column keeps passing in every one of the same spellings — the guard must not have
    # become a blanket refusal of aliases and qualifiers.
    for spelling in ("assoc_store_ref,", "assoc_store_ref AS ref,", "control_tenants.assoc_store_ref,", "t.assoc_store_ref AS ref,"):
        assert unknown_control_columns(f'X = "{base.format(spelling)}"\n') == [], f"a real column must still pass as {spelling!r}"


def test_guard_is_non_vacuous() -> None:
    assert _skip_branch() is not None
    assert len(_RETIRED_SUBJECT_STATE) == 4
    # The schema-contract check must be able to SEE the exact drift it exists to refuse, and must not
    # be fooled by the expression forms it deliberately skips.
    governed = governed_control_columns()
    assert "assoc_store_ref" in governed["control_tenants"] and "assoc_version" in governed["control_tenants"], (
        "the DDL parser must find the two governed reference columns, or the RB-2 check passes for the wrong reason"
    )
    assert "database_association_ref" not in governed["control_tenants"], "the parser must agree that the drifted name is not a column"
    drifted = selected_control_columns(
        'X = "SELECT tenant_id, lifecycle_state, database_association_ref FROM control_tenants ORDER BY tenant_id"\n'
    )
    assert ("control_tenants", "database_association_ref") in drifted, "the extractor must surface the pre-fix defect"
    assert selected_control_columns('X = "SELECT count(*) FROM control_audit"\n') == [], "expressions name no single column"
    assert selected_control_columns('X = "SELECT system_identifier FROM pg_control_system()"\n') == [], "ungoverned tables are skipped"
    # FAIL-CLOSED: with the governed DDL unreadable the parser must produce NOTHING, so the schema
    # contract check turns red on its own precondition instead of passing over an empty column set.
    global _CONTROL_DDL_DIR  # noqa: PLW0603 — restored in `finally`, and this file is single-threaded
    original_ddl_dir = _CONTROL_DDL_DIR
    try:
        _CONTROL_DDL_DIR = original_ddl_dir.with_name(original_ddl_dir.name + "__absent__")
        assert governed_control_columns() == {}, "an unreadable DDL directory must parse to nothing"
        assert selected_control_columns(_text()) == [], "with no schema contract, no pair may be claimed as checked"
        try:
            test_every_selected_column_exists_in_the_governed_control_ddl()
        except AssertionError:
            pass
        else:  # pragma: no cover — reached only if the guard stops failing closed
            raise AssertionError("the schema-contract check must FAIL when the governed Control DDL cannot be read")
    finally:
        _CONTROL_DDL_DIR = original_ddl_dir
    assert governed_control_columns(), "the DDL directory must be restored"
    probe = ast.parse("assert 'b5_standing_alpha' in x\n")
    found = [n for n in ast.walk(probe) if isinstance(n, ast.Assert)]
    assert found and "b5_standing_alpha" in (ast.get_source_segment("assert 'b5_standing_alpha' in x\n", found[0]) or ""), (
        "the retired-roster detector must be able to see a violation"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_replacement_exists_and_is_registered,
            test_replacement_is_strictly_read_only,
            test_replacement_does_not_re_pin_a_roster,
            test_replacement_fails_closed_on_a_vacuous_census,
            test_replacement_skips_explicitly_rather_than_returning,
            test_replacement_states_supersession_and_non_claims,
            test_predecessor_is_marked_superseded_and_left_intact,
            test_every_selected_column_exists_in_the_governed_control_ddl,
            test_the_schema_contract_guard_sees_every_ordinary_spelling_of_the_drift,
            test_guard_is_non_vacuous,
        ]
    )
