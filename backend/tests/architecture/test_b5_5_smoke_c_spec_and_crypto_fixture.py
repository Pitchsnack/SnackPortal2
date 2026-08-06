"""PRD B5-5 — SMOKE-C-SPEC-01 + runtime RS256 fixture boundary pins (default suite; no DB, no network).

Non-vacuously pins the B5-5 surface without generating a key or touching anything live:

* the spec (``docs/acceptance/SMOKE-C-SPEC-01.md``) carries EVERY authority / topology / happy-path /
  failure-mode / audit-disclosure / evidence-format / no-overclaim obligation (exact-needle census with
  planted-mutant companions), states that it does not execute Smoke C, and can never claim B5-BLK-4
  closure (the required standing-status block is pinned; the closure phrase is forbidden);
* the fixture (``tests/api_gateway/crypto_fixture.py``) is import-inert (top level = docstring /
  imports / call-free constants / defs only — a module-level key generation cannot pass), carries
  EXACTLY the required import surface (stdlib + ``jwt`` + ``jwt.algorithms`` + the ``cryptography``
  RSA module — one vendor package more is a containment breach), calls no file-write / print / exec
  API, never touches ``private_bytes``/serialization, and mints RS256 ONLY (every ``jwt.encode`` call
  pins ``algorithm="RS256"`` and a ``kid`` header; other JWS alg literals are banned);
* the fixture TEST module imports no JWT/crypto vendor itself (the allowance stays one module);
* the containment guard's allowance constants are pinned by AST (exact list + exact single-file
  string — widening to a tuple, prefix, directory, or wildcard fails here even if the census still
  passes);
* no production module imports the fixture; no default-suite module newly invokes the B5-4
  standing-topology harness; the new modules introduce NO new environment variable name;
* no changed-surface file carries a token-shaped literal or PEM header (needles built dynamically so
  this guard never self-matches); ``backend/pyproject.toml`` dependencies stay EXACTLY the three
  declared entries (a new dependency fails here).

Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_5_smoke_c_spec_and_crypto_fixture.py

B5-BLK-4 remains OPEN; the Physical Multi-Database MVP remains mandatory and is NOT completed by this
guard, the spec it pins, or the fixture it pins. No Smoke C execution occurs here.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from typing import Dict, List, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_SPEC = _scan.REPO_ROOT / "docs" / "acceptance" / "SMOKE-C-SPEC-01.md"
_FIXTURE = _scan.BACKEND_ROOT / "tests" / "api_gateway" / "crypto_fixture.py"
_FIXTURE_TEST = _scan.BACKEND_ROOT / "tests" / "api_gateway" / "test_crypto_fixture.py"
_CONTAINMENT = _scan.BACKEND_ROOT / "tests" / "architecture" / "test_vendor_and_db_containment.py"
_PYPROJECT = _scan.BACKEND_ROOT / "pyproject.toml"
_TESTS_DIR = _scan.BACKEND_ROOT / "tests"
_B5_4_PROOF_RELP = "tests/control_plane/requires_pg/test_pg_b5_standing_topology.py"

# Every file this slice touches (hygiene needles sweep all of them, incl. this guard itself).
_B5_5_SURFACE = (_SPEC, _FIXTURE, _FIXTURE_TEST, _CONTAINMENT, pathlib.Path(__file__).resolve())

# --- dynamically built needles (so THIS guard never satisfies its own bans) -----------------------
_TOKEN_NEEDLE = "e" + "yJ"  # the base64 JWT prefix
_PEM_NEEDLE = "-----BE" + "GIN"
_CLOSURE_NEEDLE = "B5-BLK-4 CLO" + "SED"
_MVP_DONE_NEEDLE = "MVP COMPL" + "ETE"
_REQUIRES_PG_NEEDLE = "requires" + "_pg"
_SECRET_DIR_NEEDLE = "SNACKPORTAL_TENANT" + "_SECRET_DIR"
_BANNED_ALG_LITERALS = ("HS" + "256", "HS" + "384", "HS" + "512", "ES" + "256", "RS" + "384", "RS" + "512")

# --- the spec obligation census (exact substrings of docs/acceptance/SMOKE-C-SPEC-01.md) ----------
_SPEC_REQUIRED_NEEDLES = (
    # identity + authority anchors
    "SMOKE-C-SPEC-01",
    "AT-D15T1-3",
    "IC-010 §I",
    "IC-010 §K",
    "IC-010 §O",
    # boundary (granularity + no production/cluster overclaim)
    "database granularity",
    "cluster-level distinctness",
    "One Request -> One Active Tenant -> One Database",
    # execution topology
    "Gateway.handle",
    "in-process",
    "gateway ingress",
    "build_read_server_from_env",
    "build_authenticate_server_from_env",
    "build_dispatch_server_from_env",
    "serve_authenticate_api",
    "serve_dispatch_api",
    "single-threaded",
    "no runtime DDL",
    # preconditions + happy path (two standing tenants, fresh material, non-touch, distinctness)
    "b5_standing_alpha",
    "b5_standing_beta",
    "freshly minted",
    "RS256",
    "other-database non-touch",
    # failure modes — exact current envelopes, both layers
    "tenant_access_denied",
    "tenant_not_ready",
    "carrier_mismatch",
    "control_plane_unavailable",
    "bad_signature",
    "unknown_kid",
    "unknown_issuer",
    "unauthenticated",
    "forbidden",
    "unavailable",
    "never 503",
    # audit disclosure
    "in-memory",
    "DBR-AR-2",
    "durable",
    # evidence format (deterministic, redacted, references only)
    "token kid",
    "never the token",
    "correlation",
    "redacted",
    # no-execution + no-overclaim (the required standing-status block, verbatim)
    "does not execute Smoke C",
    "B5-BLK-4 OPEN.",
    "Physical Multi-Database MVP mandatory and NOT complete.",
    "Smoke C deferred / HARD-GATE.",
)

# The fixture's EXACT import surface (one module more or fewer fails; vendor set is closed).
_FIXTURE_IMPORT_ALLOW = frozenset(
    {
        "__future__",
        "dataclasses",
        "json",
        "time",
        "typing",
        "uuid",
        "jwt",
        "jwt.algorithms",
        "cryptography.hazmat.primitives.asymmetric",
    }
)
_FIXTURE_FORBIDDEN_CALLS = frozenset({"open", "print", "exec", "eval", "compile", "input", "breakpoint", "__import__"})
_FIXTURE_FORBIDDEN_ATTRS = frozenset(
    {"write_text", "write_bytes", "private_bytes", "mkstemp", "NamedTemporaryFile", "urlopen", "connect", "environ", "system", "popen"}
)

_ENV_NAME_RE = re.compile(r"\b(SP2_[A-Z0-9_]+|SNACKPORTAL_[A-Z0-9_]+)\b")
_ALLOWED_ENV_NAMES = {"SP2_AR_CONTROL_PLANE_READ_BASE_URL", "SP2_AR_ISSUERS"}  # existing knobs only — nothing new


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# --- shared predicates (used by the real pins AND the planted-mutant companions) -------------------
def _spec_problems(text: str) -> List[str]:
    problems = [f"missing:{needle}" for needle in _SPEC_REQUIRED_NEEDLES if needle not in text]
    for banned in (_CLOSURE_NEEDLE, _MVP_DONE_NEEDLE, _TOKEN_NEEDLE):
        if banned in text:
            problems.append(f"forbidden:{banned}")
    return problems


def _inertness_problems(tree: ast.Module) -> List[str]:
    problems: List[str] = []
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if index != 0:
                problems.append("bare string expression outside the module docstring")
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if value is not None and any(isinstance(inner, ast.Call) for inner in ast.walk(value)):
                problems.append("module-level assignment performs a call (work at import)")
            continue
        problems.append(f"unexpected top-level statement: {type(node).__name__}")
    return problems


def _import_set(tree: ast.Module) -> Set[str]:
    mods: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
    return mods


def _forbidden_call_hits(tree: ast.Module) -> Set[str]:
    hits: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FIXTURE_FORBIDDEN_CALLS:
            hits.add(node.func.id)
    return hits


def _forbidden_attr_hits(tree: ast.Module) -> Set[str]:
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr in _FIXTURE_FORBIDDEN_ATTRS}


def _encode_problems(tree: ast.Module) -> List[str]:
    """Every ``jwt.encode``-shaped call must pin ``algorithm="RS256"`` and set a headers kw (kid)."""
    encodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "encode"
    ]
    if not encodes:
        return ["no jwt.encode call found (the mint helper must exist)"]
    problems: List[str] = []
    for call in encodes:
        algorithms = [kw.value for kw in call.keywords if kw.arg == "algorithm"]
        if len(algorithms) != 1 or not isinstance(algorithms[0], ast.Constant) or algorithms[0].value != "RS256":
            problems.append('encode call does not pin algorithm="RS256" as a constant keyword')
        if not any(kw.arg == "headers" for kw in call.keywords):
            problems.append("encode call does not set the headers keyword (kid header required)")
    return problems


# --- the real pins ---------------------------------------------------------------------------------
def test_b5_5_surface_files_exist() -> None:
    for path in (_SPEC, _FIXTURE, _FIXTURE_TEST, _CONTAINMENT):
        assert path.is_file(), f"B5-5 surface file missing: {path}"


def test_spec_carries_every_obligation_and_never_claims_closure() -> None:
    problems = _spec_problems(_SPEC.read_text(encoding="utf-8"))
    assert not problems, f"SMOKE-C-SPEC-01 obligation census failed: {problems}"


def test_spec_census_non_vacuity() -> None:
    canonical = " ".join(_SPEC_REQUIRED_NEEDLES)
    assert _spec_problems(canonical) == [], "the canonical needle join must PASS the census"
    dropped = canonical.replace("AT-D15T1-3", "AT-XXXXX-X")
    assert "missing:AT-D15T1-3" in _spec_problems(dropped), "a dropped authority anchor must be caught"
    dropped = canonical.replace("in-memory", "im-memory")
    assert any(p.startswith("missing:in-memory") for p in _spec_problems(dropped)), "a dropped audit disclosure must be caught"
    dropped = canonical.replace("does not execute Smoke C", "executes Smoke C")
    assert any(p.startswith("missing:does not execute") for p in _spec_problems(dropped)), "a dropped no-execution pin must be caught"
    dropped = canonical.replace("B5-BLK-4 OPEN.", "")
    assert "missing:B5-BLK-4 OPEN." in _spec_problems(dropped), "a dropped standing-status line must be caught"
    closed = canonical + " " + _CLOSURE_NEEDLE
    assert f"forbidden:{_CLOSURE_NEEDLE}" in _spec_problems(closed), "a closure claim must be caught"


def test_fixture_is_import_inert() -> None:
    problems = _inertness_problems(_tree(_FIXTURE))
    assert not problems, f"crypto_fixture must be import-inert: {problems}"


def test_fixture_import_surface_is_exactly_the_required_set() -> None:
    mods = _import_set(_tree(_FIXTURE))
    assert mods == set(_FIXTURE_IMPORT_ALLOW), (
        f"crypto_fixture import surface drifted — extra: {sorted(mods - set(_FIXTURE_IMPORT_ALLOW))}, "
        f"missing: {sorted(set(_FIXTURE_IMPORT_ALLOW) - mods)}"
    )


def test_fixture_calls_no_file_write_print_or_serialization_api() -> None:
    tree = _tree(_FIXTURE)
    assert not _forbidden_call_hits(tree), f"forbidden call in crypto_fixture: {sorted(_forbidden_call_hits(tree))}"
    assert not _forbidden_attr_hits(tree), f"forbidden attribute in crypto_fixture: {sorted(_forbidden_attr_hits(tree))}"


def test_fixture_mints_rs256_only() -> None:
    problems = _encode_problems(_tree(_FIXTURE))
    assert not problems, f"RS256-only mint pin failed: {problems}"
    source = _FIXTURE.read_text(encoding="utf-8")
    for banned in _BANNED_ALG_LITERALS:
        assert banned not in source, f"non-RS256 JWS algorithm literal {banned!r} in crypto_fixture"


def test_fixture_pin_non_vacuity() -> None:
    # The SAME predicates must reject every planted mutant (each reintroduces one banned behavior).
    mutants: Dict[str, str] = {
        "module-level keygen": "import jwt\nKP = generate_rs256_keypair()\n",
        "top-level serve call": "import jwt\nserve()\n",
        "os import widening": "import jwt\nimport os\n",
        "second vendor package": "import jwt\nimport requests\n",
        "file write": "import jwt\ndef f():\n    open('k.pem', 'w')\n",
        "private serialization": "import jwt\ndef f(k):\n    return k.private_bytes()\n",
        "printed token": "import jwt\ndef f(t):\n    print(t)\n",
        "alg switched": 'import jwt\ndef f(k):\n    return jwt.encode({}, k, algorithm="' + _BANNED_ALG_LITERALS[0] + '", headers={})\n',
        "alg not constant": "import jwt\ndef f(k, a):\n    return jwt.encode({}, k, algorithm=a, headers={})\n",
        "kid header dropped": 'import jwt\ndef f(k):\n    return jwt.encode({}, k, algorithm="RS256")\n',
    }
    canonical = 'import jwt\ndef f(k):\n    return jwt.encode({}, k, algorithm="RS256", headers={"kid": "x"})\n'
    tree = ast.parse(canonical)
    assert not _inertness_problems(tree) and not _forbidden_call_hits(tree) and not _encode_problems(tree), "canonical shape must PASS"
    for label, source in mutants.items():
        mutant = ast.parse(source)
        rejected = (
            bool(_inertness_problems(mutant))
            or bool(_forbidden_call_hits(mutant))
            or bool(_forbidden_attr_hits(mutant))
            or bool(_encode_problems(mutant))
            and "encode" in source
            or bool(_import_set(mutant) - set(_FIXTURE_IMPORT_ALLOW))
        )
        assert rejected, f"fixture pins must reject mutant: {label}"


def test_fixture_test_module_imports_no_vendor() -> None:
    vendor_prefixes = ["jwt", "cryptography"]
    mods = _import_set(_tree(_FIXTURE_TEST))
    hits = {m for m in mods if any(m == p or m.startswith(p + ".") for p in vendor_prefixes)}
    assert not hits, f"the fixture TEST module must not import a JWT/crypto vendor (one blessed module only): {sorted(hits)}"
    # Non-vacuity: the same predicate flags a synthetic vendor import.
    synthetic = _import_set(ast.parse("from jwt.algorithms import RSAAlgorithm\n"))
    assert any(m.startswith("jwt") for m in synthetic), "vendor-import detector went vacuous"


def test_containment_allowance_constants_pinned_exactly() -> None:
    assigns: Dict[str, ast.expr] = {}
    for node in _tree(_CONTAINMENT).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigns[target.id] = node.value
    assert "JWT_CRYPTO_PREFIXES" in assigns and "JWT_CRYPTO_FIXTURE_ALLOW" in assigns, "containment census constants must exist"
    assert ast.literal_eval(assigns["JWT_CRYPTO_PREFIXES"]) == ["jwt", "cryptography"], "the vendor prefix census is pinned"
    allow = assigns["JWT_CRYPTO_FIXTURE_ALLOW"]
    assert isinstance(allow, ast.Constant) and isinstance(allow.value, str), (
        "the allowance must stay ONE plain string (a tuple/list/computed value is a widening)"
    )
    assert allow.value == "tests/api_gateway/crypto_fixture.py", "the allowance names exactly the one blessed fixture file"


def test_no_production_import_of_fixture() -> None:
    offenders: List[str] = []
    for path in _scan.py_files():
        if _TESTS_DIR in path.parents:
            continue
        if any("crypto_fixture" in mod for mod in _scan.imported_modules(path)):
            offenders.append(_scan.relposix(path))
    assert not offenders, f"production code must never import the crypto fixture: {offenders}"
    # Non-vacuity: the census detects a synthetic import.
    names = _import_set(ast.parse("import crypto_fixture\n"))
    assert "crypto_fixture" in names, "production-import census went vacuous"


def test_no_new_standing_fixture_invocation() -> None:
    # Only the existing B5-4 disposable proof may import the standing-topology ops harness; this
    # slice adds NO Smoke C executable and NO new standing-fixture caller.
    offenders: List[str] = []
    for path in _scan.py_files(_TESTS_DIR):
        if any("b5_standing_topology" in mod for mod in _scan.imported_modules(path)):
            offenders.append(_scan.relposix(path))
    assert set(offenders) <= {_B5_4_PROOF_RELP}, f"new standing-fixture invocation detected: {sorted(set(offenders) - {_B5_4_PROOF_RELP})}"
    for path, label in ((_FIXTURE, "fixture"), (_FIXTURE_TEST, "fixture test")):
        text = path.read_text(encoding="utf-8")
        assert _REQUIRES_PG_NEEDLE not in text, f"the {label} must not reference the live-PG harness zone"
        assert _SECRET_DIR_NEEDLE not in text, f"the {label} must not reference the tenant-secret directory"
    # Non-vacuity: the import census detects a synthetic harness import.
    assert any("b5_standing_topology" in m for m in _import_set(ast.parse("import b5_standing_topology\n")))


def test_no_new_env_var_names_in_the_new_modules() -> None:
    for path in (_FIXTURE, _FIXTURE_TEST):
        names = set(_ENV_NAME_RE.findall(path.read_text(encoding="utf-8")))
        unexpected = names - _ALLOWED_ENV_NAMES
        assert not unexpected, f"{path.name} introduces/references unexpected env names: {sorted(unexpected)}"
    # Non-vacuity: the pattern sees a planted sample.
    assert _ENV_NAME_RE.findall("x = SP2_NEW_KNOB and SNACKPORTAL_OTHER_THING") == ["SP2_NEW_KNOB", "SNACKPORTAL_OTHER_THING"]


def test_no_token_or_pem_material_on_the_whole_b5_5_surface() -> None:
    for path in _B5_5_SURFACE:
        text = path.read_text(encoding="utf-8")
        assert _TOKEN_NEEDLE not in text, f"token-shaped literal in {path.name}"
        assert _PEM_NEEDLE not in text, f"PEM header in {path.name}"
    # Non-vacuity: both needles detect planted samples.
    assert _TOKEN_NEEDLE in ("e" + "yJhbGciOi"), "token-literal detector went vacuous"
    assert _PEM_NEEDLE in ("-----BE" + "GIN RSA PRIVATE KEY-----"), "PEM detector went vacuous"


def test_pyproject_dependencies_unchanged() -> None:
    text = _PYPROJECT.read_text(encoding="utf-8")
    # The closing bracket is anchored to line start: an entry like "psycopg[binary]>=3" contains
    # `]` inline, so a lazy match to the first `]` would silently truncate the block.
    block = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", text, re.S | re.M)
    assert block is not None, "pyproject dependencies block must exist"
    entries = re.findall(r'"([^"]+)"', block.group(1))
    # The declared runtime dependency set is closed and reviewed. B5-5 adds none; the FastAPI
    # migration added exactly two — the HTTP serving stack (fastapi for the nine service edges,
    # uvicorn for the single shared ASGI runtime). Both are vendor-neutral open source over the
    # standard ASGI interface, so the anti-vendor-lock-in constraint is unaffected. Any further
    # entry needs the same explicit review this list represents.
    assert entries == ["pyjwt>=2", "cryptography", "psycopg[binary]>=3", "fastapi>=0.115", "uvicorn>=0.30"], (
        f"backend dependencies must stay EXACTLY the five reviewed entries: {entries}"
    )


if __name__ == "__main__":
    _scan.run(
        [
            test_b5_5_surface_files_exist,
            test_spec_carries_every_obligation_and_never_claims_closure,
            test_spec_census_non_vacuity,
            test_fixture_is_import_inert,
            test_fixture_import_surface_is_exactly_the_required_set,
            test_fixture_calls_no_file_write_print_or_serialization_api,
            test_fixture_mints_rs256_only,
            test_fixture_pin_non_vacuity,
            test_fixture_test_module_imports_no_vendor,
            test_containment_allowance_constants_pinned_exactly,
            test_no_production_import_of_fixture,
            test_no_new_standing_fixture_invocation,
            test_no_new_env_var_names_in_the_new_modules,
            test_no_token_or_pem_material_on_the_whole_b5_5_surface,
            test_pyproject_dependencies_unchanged,
        ]
    )
