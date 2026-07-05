"""PRD 07D-2b.2a — orchestrator-construction + composition-root signature pins (architecture; no PostgreSQL).

Two static pins guarding the premises of the PRD 07D-2b.1 symmetric effective-posture onboard-time
guard (main.py `_guarded_onboarding`), landed here BEFORE the recovery entry points multiply:

* AT-07D2B1-2 — `OnboardingOrchestrator(` is constructed in NO non-test production module other
  than the composition root `control_plane/main.py`. A direct construction elsewhere would bypass
  the mixed-posture facade (its onboard/reassociate/recover denies) entirely.
* AT-07D2B1-3 — the `ControlPlane.__init__` signature stays exactly
  ``(self, store: ControlStore | None = None)``. The guard's documented premise is that ``store=``
  is the SOLE explicit constructor parameter (so the live side is always env-composed and the
  operator can stand for the whole live trio); recovery composition must remain INTERNAL-only —
  a new constructor parameter invalidates the premise and must fail this tripwire.

Pure stdlib AST; imports no database driver; standalone-runnable:
  python tests/architecture/test_orchestrator_construction_pin.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_CP_MAIN = _scan.BACKEND_ROOT / "control_plane" / "main.py"
_TESTS_DIR = _scan.BACKEND_ROOT / "tests"


def _construction_count(path: pathlib.Path) -> int:
    """Number of `OnboardingOrchestrator(...)` call sites in a module (Name or Attribute form)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if (isinstance(fn, ast.Name) and fn.id == "OnboardingOrchestrator") or (
                isinstance(fn, ast.Attribute) and fn.attr == "OnboardingOrchestrator"
            ):
                count += 1
    return count


def test_no_non_test_orchestrator_construction_outside_main() -> None:
    # AT-07D2B1-2: the composition root is the ONLY production construction site.
    offenders: List[str] = []
    for path in _scan.py_files():
        if _TESTS_DIR in path.parents or path == _CP_MAIN:
            continue
        if _construction_count(path):
            offenders.append(_scan.relposix(path))
    assert not offenders, (
        f"OnboardingOrchestrator must be constructed ONLY in control_plane/main.py "
        f"(the guarded composition root) — found construction in: {offenders}"
    )
    # Non-vacuity: the scan must still see the sanctioned composition-root site, so a rename or
    # relocation fails loud instead of this pin silently passing over zero sites.
    assert _construction_count(_CP_MAIN) == 1, "main.py must hold exactly one construction site"


def test_control_plane_ctor_signature_tripwire() -> None:
    # AT-07D2B1-3: `(self, store: ControlStore | None = None)` — no new public ctor param.
    tree = ast.parse(_CP_MAIN.read_text(encoding="utf-8"), filename=str(_CP_MAIN))
    init = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ControlPlane":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    init = item
    assert init is not None, "ControlPlane.__init__ not found in control_plane/main.py"
    args = init.args
    assert [a.arg for a in args.args] == ["self", "store"], (
        f"ControlPlane.__init__ positional args must be exactly (self, store) — got "
        f"{[a.arg for a in args.args]}; recovery/2b.2 composition must be INTERNAL-only "
        f"(no new constructor parameter — the 07D-2b.1 guard premise)"
    )
    assert not args.kwonlyargs and args.vararg is None and args.kwarg is None, (
        "ControlPlane.__init__ must take no *args/**kwargs/keyword-only parameters"
    )
    store_arg = args.args[1]
    assert store_arg.annotation is not None and ast.unparse(store_arg.annotation) == "ControlStore | None", (
        f"store annotation must stay `ControlStore | None` — got {ast.unparse(store_arg.annotation) if store_arg.annotation else None!r}"
    )
    assert len(args.defaults) == 1 and isinstance(args.defaults[0], ast.Constant) and args.defaults[0].value is None, (
        "store must default to None (the env-composed default path)"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_no_non_test_orchestrator_construction_outside_main,
            test_control_plane_ctor_signature_tripwire,
        ]
    )
