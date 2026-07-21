"""SP2-NEXT-A-PORTABILITY — portability architecture guards (O-7, §8.5, §9).

Path-bounded, pure-stdlib, default suite (no DB, no Docker, no network, no runtime).
Scope: the RUNTIME packages (shared + the six services). Tests, runbooks, and docs
are out of scope by design — the master plan (§25) explicitly allows runbook
examples, test fixtures, and profile/operator configuration values.

Sanctioned loopback zones (must NOT be falsely rejected, §8.5): the vendor
containment zone ``**/adapters/providers/**`` (internal transport adapters are
REQUIRED to default-bind 127.0.0.1 by the existing transport guards) and the
``<package>/main.py`` composition roots (env-overridable loopback defaults).
Docstrings are prose, not configuration, and are ignored by the loopback guard.

Complements — does not duplicate — ``test_vendor_and_db_containment.py``: that
guard confines cloud/DB/JWT SDK imports; this one adds the portability-specific
provider families (secrets/orchestration/monitoring vendors) and the physical-
identity guards (Windows paths, fleet handles, ports, DSN shapes, profiles).
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
from typing import Iterator, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

if str(_scan.BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_scan.BACKEND_ROOT))

RUNTIME_PACKAGES: Tuple[str, ...] = ("shared",) + tuple(_scan.SERVICE_PACKAGES)
PROFILES_DIR = _scan.REPO_ROOT / "infrastructure" / "env" / "profiles"
ENV_DIR = _scan.REPO_ROOT / "infrastructure" / "env"

# --- Detectors -----------------------------------------------------------------

# Drive letter + \ (single or source-doubled) or a single / — URI '://' schemes never match.
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:(?:\\{1,2}[A-Za-z0-9_.]|/(?!/)[A-Za-z0-9_.])")
_FLEET_PORT_RE = re.compile(r"\b554[0-3]\b")
_DSN_RE = re.compile(r"postgres(ql)?://", re.IGNORECASE)
_URL_CREDENTIALS_RE = re.compile(r"://[^/@\s\"']+:[^/@\s\"']+@")
_LOOPBACK_MARKERS: Tuple[str, ...] = ("localhost", "127.0.0.1", "::1")
# Operational handles of the current fixture must never enter runtime code as identities.
_FLEET_HANDLE_MARKERS: Tuple[str, ...] = (
    "sp2_b3a_",
    "snackportal2-b3a",
    "snackportal2_control_local",
    "snackportal2_tenant_",
)
# Portability-specific provider SDK families (secrets / orchestration / monitoring
# vendors), additive to the VENDOR_PREFIXES of test_vendor_and_db_containment.py.
PORTABILITY_VENDOR_PREFIXES: Tuple[str, ...] = (
    "hvac",
    "kubernetes",
    "docker",
    "datadog",
    "ddtrace",
    "newrelic",
    "sentry_sdk",
    "prometheus_client",
    "elastic_apm",
    "splunklib",
)


# These two modules DEFINE the prohibition vocabulary (denylist marker constants and
# detector regex sources), so their own text necessarily contains the forbidden strings.
# Exact-file allowance for the loopback/fleet-handle literal sweeps ONLY (never for the
# import censuses); anti-widening is enforced by test_vocabulary_allowance_is_exact.
_VOCABULARY_DEFINITION_ALLOW: Tuple[str, ...] = (
    "shared/portability/identity.py",
    "shared/portability/profile.py",
)


def _runtime_py_files() -> Iterator[pathlib.Path]:
    for package in RUNTIME_PACKAGES:
        yield from _scan.py_files(_scan.BACKEND_ROOT / package)


def _is_sanctioned_loopback_zone(relposix: str) -> bool:
    return "/adapters/providers/" in ("/" + relposix) or relposix.endswith("/main.py")


def _non_docstring_string_constants(source: str) -> List[str]:
    tree = ast.parse(source)
    docstring_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                docstring_ids.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstring_ids
    ]


def _loopback_literals(source: str) -> List[str]:
    return [s for s in _non_docstring_string_constants(source) if any(marker in s for marker in _LOOPBACK_MARKERS)]


def _matches_prefix(module: str, prefixes: Tuple[str, ...]) -> bool:
    return any(module == p or module.startswith(p + ".") for p in prefixes)


# ---------------------------------------------------------------------------
# 1. Hard-coded Windows paths in business code (O-7 / §9)
# ---------------------------------------------------------------------------


def test_no_windows_paths_in_runtime_packages() -> None:
    for f in _runtime_py_files():
        text = f.read_text(encoding="utf-8")
        assert not _WINDOWS_PATH_RE.search(text), (
            f"{_scan.relposix(f)}: hard-coded Windows/drive path in business code — paths are operator configuration, never architecture"
        )


def test_windows_path_detector_nonvacuity() -> None:
    assert _WINDOWS_PATH_RE.search('ROOT = "D:\\\\SP2-Local-Concept\\\\artifacts"')
    assert _WINDOWS_PATH_RE.search('root = "C:/Users/example/data"')
    assert not _WINDOWS_PATH_RE.search('url = "https://example.internal/path"')


# ---------------------------------------------------------------------------
# 2. Hard-coded loopback endpoints outside sanctioned zones (O-7 / §9)
# ---------------------------------------------------------------------------


def test_no_loopback_literals_outside_sanctioned_zones() -> None:
    for f in _runtime_py_files():
        rp = _scan.relposix(f)
        if _is_sanctioned_loopback_zone(rp) or rp in _VOCABULARY_DEFINITION_ALLOW:
            continue
        found = _loopback_literals(f.read_text(encoding="utf-8"))
        assert not found, f"{rp}: loopback endpoint literal in business code outside adapters/providers or a composition root: {found}"


def test_loopback_detector_nonvacuity_and_docstring_exemption() -> None:
    flagged = _loopback_literals('HOST = "127.0.0.1"\n')
    assert flagged == ["127.0.0.1"], "a planted loopback literal must be detected"
    assert _loopback_literals('"""hosts like localhost are documented here"""\nX = 1\n') == [], "docstrings are prose, not configuration"
    assert _loopback_literals('def f() -> None:\n    """binds 127.0.0.1 by default"""\n') == [], "function docstrings are exempt"


def test_sanctioned_zone_predicate_is_exact() -> None:
    assert _is_sanctioned_loopback_zone("api_gateway/adapters/providers/http_gateway_edge.py")
    assert _is_sanctioned_loopback_zone("api_gateway/main.py")
    assert not _is_sanctioned_loopback_zone("api_gateway/carrier.py")
    assert not _is_sanctioned_loopback_zone("shared/portability/profile.py")
    assert not _is_sanctioned_loopback_zone("api_gateway/main_helpers.py")


def test_vocabulary_allowance_is_exact() -> None:
    # Anti-widening: the literal-sweep allowance is exactly the two vocabulary-defining
    # modules, both must exist, and both must actually define the vocabulary they are
    # excused for (no free rides, no wildcards, no directories).
    assert _VOCABULARY_DEFINITION_ALLOW == ("shared/portability/identity.py", "shared/portability/profile.py")
    for rp in _VOCABULARY_DEFINITION_ALLOW:
        assert "*" not in rp and not rp.endswith("/"), "allowance entries must be exact files"
        assert (_scan.BACKEND_ROOT / rp).is_file(), f"allowance names a missing file: {rp}"
    assert "PHYSICAL_HANDLE_MARKERS" in (_scan.BACKEND_ROOT / "shared/portability/identity.py").read_text(encoding="utf-8")
    assert "_PHYSICAL_ENDPOINT_PATTERNS" in (_scan.BACKEND_ROOT / "shared/portability/profile.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 3. Container names / fleet ports as domain identities (O-7 / §9)
# ---------------------------------------------------------------------------


def test_no_fleet_handles_or_ports_in_runtime_packages() -> None:
    for f in _runtime_py_files():
        rp = _scan.relposix(f)
        if rp in _VOCABULARY_DEFINITION_ALLOW:
            continue
        text = f.read_text(encoding="utf-8")
        for marker in _FLEET_HANDLE_MARKERS:
            assert marker not in text, (
                f"{rp}: operational fleet handle {marker!r} in business code — container/database names are never identities"
            )
        assert not _FLEET_PORT_RE.search(text), f"{rp}: fleet port literal (5540–5543) in business code — ports are operator configuration"


def test_fleet_handle_detector_nonvacuity() -> None:
    planted = 'TENANT_DB = "sp2_b3a_tenant_acme"  # port 5541'
    assert any(marker in planted for marker in _FLEET_HANDLE_MARKERS)
    assert _FLEET_PORT_RE.search(planted)
    assert not _FLEET_PORT_RE.search("offset = 15540  # not a fleet port")


# ---------------------------------------------------------------------------
# 4. Raw DSN / credential shapes (O-7 / §9; AC-6)
# ---------------------------------------------------------------------------


def test_no_dsn_or_credential_literals_in_runtime_packages() -> None:
    for f in _runtime_py_files():
        rp = _scan.relposix(f)
        text = f.read_text(encoding="utf-8")
        assert not _DSN_RE.search(text), f"{rp}: DSN-shaped literal in business code — DSNs resolve via the SecretStore port (D-14)"
        assert not _URL_CREDENTIALS_RE.search(text), f"{rp}: URL with embedded credentials in business code"


def test_no_dsn_or_credential_shapes_in_env_templates_and_profiles() -> None:
    scanned = 0
    for pattern in ("*.template", "profiles/*.json"):
        for f in ENV_DIR.glob(pattern):
            scanned += 1
            text = f.read_text(encoding="utf-8")
            assert not _DSN_RE.search(text), f"{f.name}: DSN-shaped value — env artifacts are references-only (D-14)"
            assert not _URL_CREDENTIALS_RE.search(text), f"{f.name}: URL with embedded credentials"
            for marker in _LOOPBACK_MARKERS + _FLEET_HANDLE_MARKERS:
                assert marker not in text, f"{f.name}: physical handle {marker!r} — profiles/templates carry logical references only"
            assert not _FLEET_PORT_RE.search(text), f"{f.name}: fleet port literal — ports live in untracked operator configuration"
    assert scanned >= 4, "expected the env templates and both committed profiles to be scanned"


def test_dsn_detector_nonvacuity() -> None:
    assert _DSN_RE.search('DSN = "postgresql://sp2:pw@host:5432/db"')
    assert _URL_CREDENTIALS_RE.search('URL = "https://user:token@example.internal/hook"')
    assert not _DSN_RE.search('ref = "ref:db/control/endpoint@1"')


# ---------------------------------------------------------------------------
# 5. Provider SDK imports outside adapters/providers (O-7 / §9; AC-7)
# ---------------------------------------------------------------------------


def test_portability_vendor_imports_only_in_providers() -> None:
    for f in _scan.py_files():
        rp = _scan.relposix(f)
        for mod in _scan.imported_modules(f):
            if _matches_prefix(mod, PORTABILITY_VENDOR_PREFIXES):
                assert "/adapters/providers/" in ("/" + rp), f"portability provider SDK import '{mod}' outside adapters/providers: {rp}"


def test_portability_vendor_detector_nonvacuity() -> None:
    tree = ast.parse("import hvac\nfrom kubernetes import client\nimport docker.errors\n")
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    flagged = [m for m in mods if _matches_prefix(m, PORTABILITY_VENDOR_PREFIXES)]
    assert flagged == ["hvac", "kubernetes", "docker.errors"], "planted provider SDK imports must be detected"
    assert not _matches_prefix("dockerfile_parse", PORTABILITY_VENDOR_PREFIXES), "prefix matching must be dotted-boundary exact"


def test_existing_vendor_containment_not_weakened() -> None:
    # Anti-regression pin: the pre-existing cloud-SDK containment guard must keep
    # covering the cloud families; this file only ADDS prefixes (no duplication, no drift).
    text = (pathlib.Path(__file__).resolve().parent / "test_vendor_and_db_containment.py").read_text(encoding="utf-8")
    for prefix in ("supabase", "boto3", "botocore", "azure", "google.cloud"):
        assert f'"{prefix}"' in text, f"existing vendor containment no longer lists {prefix!r} — portability coverage regressed"
    overlap = set(PORTABILITY_VENDOR_PREFIXES) & {"supabase", "lovable", "boto3", "botocore", "azure", "google.cloud", "google.auth"}
    assert not overlap, f"portability prefixes must not duplicate the existing vendor guard: {sorted(overlap)}"


# ---------------------------------------------------------------------------
# 6. Committed profiles validate; logical identity stays physically independent
# ---------------------------------------------------------------------------


def test_committed_profiles_validate_via_shared_portability() -> None:
    from shared.portability import identity, profile

    local = profile.load_profile(PROFILES_DIR / "sp2-local-mvp.profile.json")
    cloud = profile.load_profile(PROFILES_DIR / "sp2-cloud-template.profile.json")
    assert local.environment_id == identity.OFFICIAL_LOCAL_ENVIRONMENT_ID
    assert sorted(local.logical_database_ids()) == sorted(identity.REQUIRED_LOGICAL_DATABASE_IDS)
    assert local.logical_database_ids() == cloud.logical_database_ids()
    assert local.is_runtime_capable and not cloud.is_runtime_capable
    try:
        cloud.assert_runtime_capable()
    except profile.ProfileNotRuntimeCapableError:
        return
    assert False, "cloud template accepted as runtime-capable"


def test_profile_validation_nonvacuity() -> None:
    from shared.portability import profile

    document = json.loads((PROFILES_DIR / "sp2-local-mvp.profile.json").read_text(encoding="utf-8"))
    document["logical_databases"][0]["endpoint_ref"] = "postgresql://sp2:pw@db.internal:5432/control"
    try:
        profile.parse_profile(document)
    except profile.ProfileValidationError:
        return
    assert False, "a planted raw-DSN endpoint must be rejected by profile validation"


def test_shared_portability_stays_stdlib_and_leaf() -> None:
    portability_dir = _scan.BACKEND_ROOT / "shared" / "portability"
    allowed_tops = {"__future__", "dataclasses", "enum", "hashlib", "json", "pathlib", "re", "shared", "typing"}
    for f in _scan.py_files(portability_dir):
        for mod in _scan.imported_modules(f):
            top = mod.split(".")[0]
            assert top in allowed_tops, f"{_scan.relposix(f)}: import '{mod}' — shared.portability must stay a pure-stdlib leaf"
            assert top not in _scan.SERVICE_PACKAGES, f"{_scan.relposix(f)}: shared.portability must not import a service"


if __name__ == "__main__":
    _scan.run(
        [
            test_no_windows_paths_in_runtime_packages,
            test_windows_path_detector_nonvacuity,
            test_no_loopback_literals_outside_sanctioned_zones,
            test_loopback_detector_nonvacuity_and_docstring_exemption,
            test_sanctioned_zone_predicate_is_exact,
            test_vocabulary_allowance_is_exact,
            test_no_fleet_handles_or_ports_in_runtime_packages,
            test_fleet_handle_detector_nonvacuity,
            test_no_dsn_or_credential_literals_in_runtime_packages,
            test_no_dsn_or_credential_shapes_in_env_templates_and_profiles,
            test_dsn_detector_nonvacuity,
            test_portability_vendor_imports_only_in_providers,
            test_portability_vendor_detector_nonvacuity,
            test_existing_vendor_containment_not_weakened,
            test_committed_profiles_validate_via_shared_portability,
            test_profile_validation_nonvacuity,
            test_shared_portability_stays_stdlib_and_leaf,
        ]
    )
