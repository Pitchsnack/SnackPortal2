"""PRD 06 B-7C-1 + PRD 07D-2e — audit/state-write ordering + CAS-routing static (AST) guards.

Locks the B-7B/B7B-D5 fail-closed guarantee structurally, in its PRD 07D-2e form:

* **Create path (positional, unchanged).** ``registry.register_tenant`` — the ONLY production
  ``put_tenant`` caller — writes the required audit record BEFORE the irreversible
  ``put_tenant`` commit, so a failed required durable audit write rejects the registration
  with no committed partial state.
* **Lifecycle transitions (transactional since 07D-2e).** Every real lifecycle mutation routes
  through ``compare_and_swap_tenant`` (version-predicated CAS; D-2e-2), and the CAS write
  PRECEDES the required ``self._audit.record`` — because in the durable store the CAS executes
  uncommitted and the audit append COMMITS BOTH in one Control-DB transaction (D-2e-4): a lost
  race raises with no orphan audit, and a failed audit write rolls the state change back. The
  B7B-D5 property is therefore enforced by the store transaction (fake-connection unit tests in
  ``test_lifecycle_cas_2e.py`` + the live-PG proof), and the positional rule for these sites is
  CAS-before-audit — the source order that makes the transaction shape possible.
* **No blind tenant write.** Outside ``register_tenant`` (create/seed), NO production
  control-plane module calls ``put_tenant`` — a blind last-writer-wins overwrite of a lifecycle
  record (R-2c-LWW) cannot silently reappear (MC-2e regression probe).

``lifecycle.py`` (``TenantLifecycleService``) is CAS-routed like the wired services since
07D-2e but remains intentionally NOT in the ``create_app()`` composition root; that exclusion
is still locked below.

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
# Files holding audited state-write call sites (lifecycle.py joined in 07D-2e: CAS-routed).
_ORDERING_FILES = [_CP / "registry.py", _CP / "provisioning.py", _CP / "lifecycle.py"]
# Production control-plane service modules swept by the no-blind-write census (the adapter
# providers IMPLEMENT the port methods and are excluded; tests are excluded).
_CENSUS_FILES = [
    _CP / "registry.py",
    _CP / "provisioning.py",
    _CP / "lifecycle.py",
    _CP / "onboarding.py",
    _CP / "recovery.py",
    _CP / "main.py",
]
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


def _functions(path: pathlib.Path) -> List[ast.AST]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def test_audit_record_precedes_put_tenant_in_create_sites() -> None:
    # The surviving positional rule: every function that both audits and put_tenant-commits
    # (the create/seed path) writes the audit FIRST (B7B-D5). Since 07D-2e the ONLY such
    # production site is registry.register_tenant — asserted exactly, so a lifecycle path
    # quietly reverting from CAS to put_tenant surfaces here as an unexpected site.
    sites_by_file: Dict[str, List[str]] = {}
    for path in _ORDERING_FILES:
        names: List[str] = []
        for fn in _functions(path):
            audit = _calls(fn, "_audit", "record")
            put = _calls(fn, "_store", "put_tenant")
            if put:
                assert audit, f"{path.name}:{fn.name} — a put_tenant site must carry a required audit write"  # type: ignore[attr-defined]
                assert min(audit) < min(put), (
                    f"{path.name}:{fn.name} — required self._audit.record at {min(audit)} must PRECEDE "  # type: ignore[attr-defined]
                    f"self._store.put_tenant at {min(put)} (B7B-D5 fail-closed ordering on the create path)"
                )
                names.append(fn.name)  # type: ignore[attr-defined]
        sites_by_file[path.name] = names
    assert sites_by_file["registry.py"] == ["register_tenant"], (
        f"registry.py put_tenant sites must be exactly [register_tenant]; got {sites_by_file['registry.py']}"
    )
    assert sites_by_file["provisioning.py"] == [], "provisioning.py must hold NO put_tenant site (CAS-routed since 07D-2e)"
    assert sites_by_file["lifecycle.py"] == [], "lifecycle.py must hold NO put_tenant site (CAS-routed since 07D-2e)"


def test_cas_precedes_its_committing_audit_in_transition_sites() -> None:
    # PRD 07D-2e (D-2e-4): in every function that both CASes and audits, the CAS write comes
    # FIRST — the durable store leaves it uncommitted and the required audit append commits
    # both in one transaction (conflict -> no orphan audit; audit failure -> state rolled
    # back). An inverted pair would commit the audit in its own transaction and reopen the
    # orphan-audit window on conflict.
    names_by_file: Dict[str, set] = {}
    total = 0
    for path in _ORDERING_FILES:
        names = set()
        for fn in _functions(path):
            cas = _calls(fn, "_store", "compare_and_swap_tenant")
            audit = _calls(fn, "_audit", "record")
            if cas:
                assert audit, f"{path.name}:{fn.name} — a CAS lifecycle write must carry a required audit append"  # type: ignore[attr-defined]
                assert min(cas) < min(audit), (
                    f"{path.name}:{fn.name} — self._store.compare_and_swap_tenant at {min(cas)} must PRECEDE "  # type: ignore[attr-defined]
                    f"self._audit.record at {min(audit)} (D-2e-4: the audit append commits the CAS transaction)"
                )
                names.add(fn.name)  # type: ignore[attr-defined]
                total += 1
        names_by_file[path.name] = names
    # Non-vacuity: the known CAS transition sites must be present, so a rename/reversion fails
    # loud instead of the guard silently passing over zero sites.
    assert "_transition" in names_by_file["registry.py"], "registry._transition CAS site missing"
    assert "_transition" in names_by_file["provisioning.py"], "provisioning._transition CAS site missing"
    assert "reassociate" in names_by_file["provisioning.py"], "provisioning.reassociate CAS site missing"
    assert "_set" in names_by_file["lifecycle.py"], "lifecycle._set CAS site missing"
    assert "reassociate_database" in names_by_file["lifecycle.py"], "lifecycle.reassociate_database CAS site missing"
    assert total >= 5, f"expected >= 5 guarded CAS-before-audit sites; found {total}"


def test_no_blind_tenant_write_in_lifecycle_mutation_paths() -> None:
    # PRD 07D-2e (§8.1 census; MC-2e probe): across the production control-plane service
    # modules, the ONLY put_tenant call site is registry.register_tenant (create). Everything
    # else must route through compare_and_swap_tenant — a blind overwrite is the R-2c-LWW
    # defect this slice closes and may not silently reappear.
    offenders: List[str] = []
    for path in _CENSUS_FILES:
        for fn in _functions(path):
            for pos in _calls(fn, "_store", "put_tenant"):
                site = f"{path.name}:{fn.name}"  # type: ignore[attr-defined]
                if site != "registry.py:register_tenant":
                    offenders.append(f"{site}@{pos}")
    assert not offenders, f"blind self._store.put_tenant call(s) outside the create path: {offenders}"


def test_quarantine_tenant_routes_through_guarded_transition() -> None:
    # PRD 07D-2b.2a: the registry QuarantineTenant operation keeps the audited, guarded write
    # path by performing its state write ONLY through the `_transition` site asserted above —
    # never a direct put_tenant or a direct CAS of its own.
    tree = ast.parse((_CP / "registry.py").read_text(encoding="utf-8"), filename=str(_CP / "registry.py"))
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "quarantine_tenant":
            fn = node
    assert fn is not None, "registry.quarantine_tenant missing (PRD 07D-2b.2a ordering site)"
    delegates = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_transition"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        for node in ast.walk(fn)
    )
    assert delegates, "quarantine_tenant must delegate its state write to the guarded self._transition"
    assert not _calls(fn, "_store", "put_tenant"), "quarantine_tenant must not put_tenant directly"
    assert not _calls(fn, "_store", "compare_and_swap_tenant"), "quarantine_tenant must not CAS directly"


def test_lifecycle_service_not_wired_into_composition_root() -> None:
    # lifecycle.py is CAS-routed like the wired services since 07D-2e, but it remains
    # intentionally OUTSIDE the create_app() composition root. Lock that invariant.
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
            test_audit_record_precedes_put_tenant_in_create_sites,
            test_cas_precedes_its_committing_audit_in_transition_sites,
            test_no_blind_tenant_write_in_lifecycle_mutation_paths,
            test_quarantine_tenant_routes_through_guarded_transition,
            test_lifecycle_service_not_wired_into_composition_root,
        ]
    )
