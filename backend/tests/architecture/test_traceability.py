"""Every service package declares traceability metadata; not-yet-built services
implement no behavior. Updated for Build Phase 2 (control_plane is now built)."""
from __future__ import annotations

import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

# Services built so far (their __init__ declares IMPLEMENTS_BEHAVIOR = True).
# lineage_service is built as a Build Phase 5 write-path slice of Phase 6.
BUILT_SERVICES = {"control_plane", "auth_router", "database_router", "import_service", "lineage_service"}


def _module_assignments(path: pathlib.Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    out[tgt.id] = node.value
    return out


def test_every_service_has_traceability() -> None:
    for svc in _scan.SERVICE_PACKAGES:
        init = _scan.BACKEND_ROOT / svc / "__init__.py"
        assert init.exists(), f"missing {svc}/__init__.py"
        consts = _module_assignments(init)

        assert "GOVERNING_CONTRACTS" in consts, f"{svc}: GOVERNING_CONTRACTS missing"
        gc = consts["GOVERNING_CONTRACTS"]
        assert isinstance(gc, ast.List) and len(gc.elts) >= 1, f"{svc}: GOVERNING_CONTRACTS empty"

        assert "IMPLEMENTS_BEHAVIOR" in consts, f"{svc}: IMPLEMENTS_BEHAVIOR missing"
        val = consts["IMPLEMENTS_BEHAVIOR"]
        assert isinstance(val, ast.Constant) and isinstance(val.value, bool), (
            f"{svc}: IMPLEMENTS_BEHAVIOR must be a bool"
        )
        if svc not in BUILT_SERVICES:
            assert val.value is False, f"{svc}: not yet built — IMPLEMENTS_BEHAVIOR must be False"


if __name__ == "__main__":
    _scan.run([test_every_service_has_traceability])
