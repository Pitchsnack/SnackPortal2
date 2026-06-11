"""Build Phase 2/4 guards: control_plane stays within IC-001/IC-002 control-plane scope.

Asserts control_plane imports no authentication/JWT/OIDC libraries (Phase 3) and no
other service package; that its audit module performs no lineage/hash-chaining; and
that database drivers (added in Build Phase 4 for the Control-DB persistence provider
and the tenant-DB verification probe) appear ONLY under
`control_plane/adapters/providers/**` — the domain stays persistence-agnostic
(Driver Containment Standard, PRD-P4-R2 C; E3/E4).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

CP = _scan.BACKEND_ROOT / "control_plane"

# Forbidden anywhere in control_plane: runtime auth/tokens (Phase 3) + vendor/cloud SDKs.
FORBIDDEN_IMPORT_PREFIXES = [
    "jwt",
    "jose",
    "authlib",
    "oauthlib",
    "oidc",
    "boto3",
    "botocore",
    "azure",
    "google.cloud",
    "supabase",
    "lovable",
]
# Permitted ONLY under control_plane/adapters/providers/** (Control-DB + verification probe).
DB_DRIVER_PREFIXES = ["psycopg2", "psycopg", "asyncpg", "sqlalchemy", "databases", "aiopg"]
CP_PROVIDER_ZONE = "control_plane/adapters/providers/"


def _matches(mod: str, prefixes: list) -> bool:
    return any(mod == p or mod.startswith(p + ".") for p in prefixes)


def test_control_plane_imports_are_in_scope() -> None:
    for f in _scan.py_files(CP):
        rp = _scan.relposix(f)
        for mod in _scan.imported_modules(f):
            top = mod.split(".")[0]
            assert top not in _scan.SERVICE_PACKAGES or top == "control_plane", f"{rp} imports another service '{mod}'"
            assert not _matches(mod, FORBIDDEN_IMPORT_PREFIXES), f"{rp} imports out-of-scope module '{mod}'"
            if _matches(mod, DB_DRIVER_PREFIXES):
                assert rp.startswith(CP_PROVIDER_ZONE), f"{rp} imports database driver '{mod}' outside {CP_PROVIDER_ZONE}"


def test_audit_has_no_lineage_or_hash_chaining() -> None:
    # Inspect code constructs (imports + identifiers), not docstrings: audit.py may
    # *document* that it is distinct from lineage; it must not *import or implement* it.
    import ast

    path = CP / "audit.py"
    tops = {m.split(".")[0] for m in _scan.imported_modules(path)}
    for banned in ("hashlib", "hmac", "lineage_service"):
        assert banned not in tops, f"control_plane/audit.py must not import '{banned}'"

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert "hash_chain" not in node.id.lower(), "no hash-chaining in audit"
        if isinstance(node, ast.Attribute):
            assert "hash_chain" not in node.attr.lower(), "no hash-chaining in audit"
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            low = node.name.lower()
            assert "hash_chain" not in low and "lineage" not in low, "no lineage/hash-chaining in audit"


if __name__ == "__main__":
    _scan.run([test_control_plane_imports_are_in_scope, test_audit_has_no_lineage_or_hash_chaining])
