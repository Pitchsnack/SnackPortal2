"""PRD 07D-2c (AT-PMV46-3) — deprovision sole-call-site + recovery-service construction pins.

Two static AST pins guarding the premises of the governed DROP DATABASE path landed in
PRD 07D-2b.2b, before further recovery work multiplies the entry points:

* **Sole call site.** ``ProvisioningOperator.deprovision`` — the first governed
  ``DROP DATABASE`` path — is CALLED in exactly ONE non-test production module:
  ``control_plane/recovery.py`` (``RecoveryCompensationService``, behind the full
  ownership-proof quintuple + §7.1 pre-DROP re-validation). A second production call site
  would bypass the proof gate entirely; the pin is non-vacuous (it must still SEE the
  sanctioned site, so a rename/relocation fails loud instead of passing over zero sites).
* **Construction root.** ``RecoveryCompensationService`` and ``OrphanScanService`` are
  constructed ONLY in the composition root ``control_plane/main.py`` (exactly once each) —
  a direct construction elsewhere would bypass the mixed-posture facade (the
  ``cp.recovery`` / ``cp.orphan_scan`` pre-effect denies).

MC-6 kill site: widening this allowlist (or adding a second production ``.deprovision(``
call) must fail here. Pure stdlib AST; imports no database driver; standalone-runnable:
  python tests/architecture/test_deprovision_call_site_pin.py
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_CP_MAIN = _scan.BACKEND_ROOT / "control_plane" / "main.py"
_RECOVERY = _scan.BACKEND_ROOT / "control_plane" / "recovery.py"
_TESTS_DIR = _scan.BACKEND_ROOT / "tests"

_SERVICE_NAMES = ("RecoveryCompensationService", "OrphanScanService")


def _call_count(path: pathlib.Path, name: str) -> int:
    """Number of ``name(...)`` / ``<expr>.name(...)`` call sites in a module (AST; comments
    and docstrings never count)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if (isinstance(fn, ast.Name) and fn.id == name) or (isinstance(fn, ast.Attribute) and fn.attr == name):
                count += 1
    return count


def _production_files() -> List[pathlib.Path]:
    return [p for p in _scan.py_files() if _TESTS_DIR not in p.parents]


def test_deprovision_called_in_exactly_one_production_module() -> None:
    # AT-PMV46-3 (sole call site; MC-6 kill site): `.deprovision(` in production code exactly
    # once, and only inside control_plane/recovery.py (the ownership-proof-gated compensation).
    offenders: Dict[str, int] = {}
    for path in _production_files():
        n = _call_count(path, "deprovision")
        if n:
            offenders[_scan.relposix(path)] = n
    assert offenders == {"control_plane/recovery.py": 1}, (
        f"ProvisioningOperator.deprovision must be CALLED exactly once in production, inside "
        f"control_plane/recovery.py (the proof-gated compensation service) — found: {offenders}"
    )
    # Non-vacuity: the scan must still see the sanctioned site itself.
    assert _call_count(_RECOVERY, "deprovision") == 1, "recovery.py must hold exactly one deprovision call site"


def test_recovery_services_constructed_only_in_composition_root() -> None:
    # AT-PMV46-3 (construction pin): both recovery services are constructed ONLY in the guarded
    # composition root (main.py), exactly once each — mirroring the OnboardingOrchestrator pin.
    for name in _SERVICE_NAMES:
        offenders: List[str] = []
        for path in _production_files():
            if path == _CP_MAIN:
                continue
            if _call_count(path, name):
                offenders.append(_scan.relposix(path))
        assert not offenders, (
            f"{name} must be constructed ONLY in control_plane/main.py (the guarded composition "
            f"root behind the mixed-posture facade) — found construction in: {offenders}"
        )
        # Non-vacuity: the sanctioned composition-root site must still be visible.
        assert _call_count(_CP_MAIN, name) == 1, f"main.py must hold exactly one {name} construction site"


if __name__ == "__main__":
    _scan.run(
        [
            test_deprovision_called_in_exactly_one_production_module,
            test_recovery_services_constructed_only_in_composition_root,
        ]
    )
