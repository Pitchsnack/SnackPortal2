"""PRD 06 B-7C-1 — audit-before-state-change static (AST) ordering guard (architecture; no PostgreSQL).

Locks the B-7B/B7B-D5 fail-closed guarantee structurally: in every WIRED Control-Plane call site that
performs both a required audit write (``self._audit.record(...)``) and an irreversible state commit
(``self._store.put_tenant(...)``), the audit write MUST precede the commit — so a failed required durable
audit write rejects the transition with no committed partial state. This is enforced by source position
(formatting/comment-insensitive), not by a behavioral test, so a future refactor that reorders the pair at
ANY site (including ones without a dedicated failing-audit unit test, e.g. ``reassociate``) fails CI in the
default suite.

Scope = the wired call-site files ``registry.py`` and ``provisioning.py``. ``lifecycle.py``
(``TenantLifecycleService``) retains the pre-B-7B put-then-audit order and is intentionally NOT in the
``create_app()`` composition root; it is EXCLUDED from the ordering assertion and instead locked out of the
composition root below (so the exclusion stays justified). If it is ever wired, that future governed change
must reorder it and extend this guard.

Pure stdlib AST; imports no database driver; standalone-runnable:
  python tests/architecture/test_b7c1_audit_ordering_static.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_CP = _scan.BACKEND_ROOT / "control_plane"
_ORDERING_FILES = [_CP / "registry.py", _CP / "provisioning.py"]
_MAIN = _CP / "main.py"

_Pos = Tuple[int, int]  # (lineno, col_offset) — formatting-insensitive source order


def _calls(fn: ast.AST, value_attr: str, call_attr: str) -> List[_Pos]:
    """Positions of ``self.<value_attr>.<call_attr>(...)`` calls within a function body."""
    out: List[_Pos] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == call_attr
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == value_attr
        ):
            out.append((node.lineno, node.col_offset))
    return out


def _guarded_functions(path: pathlib.Path) -> Dict[str, Tuple[_Pos, _Pos]]:
    """name -> (first audit.record pos, first put_tenant pos) for functions containing BOTH."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: Dict[str, Tuple[_Pos, _Pos]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            audit = _calls(node, "_audit", "record")
            put = _calls(node, "_store", "put_tenant")
            if audit and put:
                out[node.name] = (min(audit), min(put))
    return out


def test_audit_record_precedes_put_tenant_in_wired_call_sites() -> None:
    names_by_file: Dict[str, set] = {}
    total = 0
    for path in _ORDERING_FILES:
        guarded = _guarded_functions(path)
        names_by_file[path.name] = set(guarded)
        for name, (audit_pos, put_pos) in guarded.items():
            assert audit_pos < put_pos, (
                f"{path.name}:{name} — required self._audit.record at {audit_pos} must PRECEDE "
                f"self._store.put_tenant at {put_pos} (B7B-D5 fail-closed ordering; no partial state)"
            )
            total += 1
    # Non-vacuity: the known wired ordering sites must be present, so a rename/removal fails loud
    # instead of the guard silently passing over zero sites.
    assert "register_tenant" in names_by_file["registry.py"], "registry.register_tenant ordering site missing"
    assert "_transition" in names_by_file["registry.py"], "registry._transition ordering site missing"
    assert "_transition" in names_by_file["provisioning.py"], "provisioning._transition ordering site missing"
    assert "reassociate" in names_by_file["provisioning.py"], "provisioning.reassociate ordering site missing"
    assert total >= 4, f"expected >= 4 guarded audit-before-put_tenant sites; found {total}"


def test_lifecycle_service_not_wired_into_composition_root() -> None:
    # lifecycle.py keeps the pre-B-7B put-then-audit order and is excluded from the ordering guard above
    # ONLY because it is not in the create_app() composition root. Lock that invariant.
    text = _MAIN.read_text(encoding="utf-8")
    assert "TenantLifecycleService" not in text, "main.py must not reference TenantLifecycleService (composition root)"
    tree = ast.parse(text, filename=str(_MAIN))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "lifecycle" not in (node.module or ""), f"main.py must not import lifecycle (got {node.module!r})"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "lifecycle" not in alias.name, f"main.py must not import lifecycle (got {alias.name!r})"


if __name__ == "__main__":
    _scan.run(
        [
            test_audit_record_precedes_put_tenant_in_wired_call_sites,
            test_lifecycle_service_not_wired_into_composition_root,
        ]
    )
