"""IC-010 §V control-read + internal-transport-client residual guards (default suite; no DB, no network).

**Provenance.** The migrated successor of the B5-BLK-6C-C residual guards, which pinned the
API Gateway's ``http_control_plane_read`` adapter. That adapter was deleted with the Gateway.
Two of its three property groups outlived it and are re-aimed here; the third is recorded as
withdrawn rather than dropped in silence.

* **Two-kind set equality (D8)** — the approved directory-kind set is EXACTLY ``{"startup",
  "investor"}``, equality-pinned across the layers that still hold kind knowledge: the
  Control-Plane read edge alias map (``_DIR_ALIAS``) and the domain enum (``DirectoryKind``).
  A missing ``startup``, a missing ``investor``, an extra unsupported kind, a Global Deal
  member, or edge↔enum drift each fail.
  *Withdrawn legs:* the Gateway adapter's ``_APPROVED_KINDS`` and the portal composer's
  directory-summary DTO ``record_type`` values. Both lived in deleted modules, and
  ``GET /directory/<kind>`` is **REMOVE FROM MVP** — no served Gateway route ever exposed it,
  so it is dead surface being retired, not a capability regressing. The Control-Plane read
  edge still serves it internally, which is why the two surviving layers stay pinned.

* **Bounded internal clients (D9–D12, D16)** — the client bounds are re-aimed at the internal
  HTTP clients the Gateway-free MVP actually composes. Every one of them is a
  loopback/internal client called on a public request path, so the same rules bind:
  a bounded positive timeout passed to ``urlopen``; exactly ONE ``urlopen`` call site per
  module, never inside a loop (one request, zero retry, zero fan-out); and no
  cursor/limit pagination vocabulary (the MVP composes one page only — a pinned limitation,
  never a pagination capability).

Pure stdlib + repository imports; standalone-runnable:
  python tests/architecture/test_ic010_control_read_adapter_boundaries.py

B5-BLK-6 remains OPEN; production remains NOT READY / DO-NOT-ACTIVATE. This guard closes no blocker.
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

from control_plane.read_api import _DIR_ALIAS  # noqa: E402
from control_plane.records import DirectoryKind  # noqa: E402

# The internal HTTP clients the Gateway-free MVP composes on a public request path. Each is
# (module path, the ONE method through which its single urlopen is reached).
_INTERNAL_CLIENTS = (
    _scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "http_principal_authenticator.py",
    _scan.BACKEND_ROOT / "shared" / "adapters" / "providers" / "edge_audit.py",
    _scan.BACKEND_ROOT / "auth_router" / "adapters" / "providers" / "http_control_plane_read.py",
)

_TIMEOUT_CEILING_SECONDS = 30.0

# Dynamic needles — built so THIS guard never satisfies its own bans.
_CURSOR_NEEDLE = "cur" + "sor"
_QUERY_LIMIT_NEEDLE = "?lim" + "it"
_AMP_LIMIT_NEEDLE = "&lim" + "it"


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _urlopen_calls(tree: ast.Module) -> List[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func).replace("urllib.request.", "") == "urlopen"]


def _calls_inside_loops(tree: ast.Module, attr_suffix: str) -> List[ast.Call]:
    hits: List[ast.Call] = []
    for loop in (n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))):
        for inner in ast.walk(loop):
            if isinstance(inner, ast.Call) and ast.unparse(inner.func).endswith(attr_suffix):
                hits.append(inner)
    return hits


def _timeout_defaults(tree: ast.Module) -> List[float]:
    """Every ``timeout: float = <literal>`` default declared by a constructor in the module."""
    out: List[float] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "__init__":
            continue
        args = node.args
        named = args.args[len(args.args) - len(args.defaults) :] if args.defaults else []
        for arg, default in zip(named, args.defaults, strict=False):
            if arg.arg == "timeout" and isinstance(default, ast.Constant) and isinstance(default.value, (int, float)):
                out.append(float(default.value))
    return out


# --- D8: two-kind set equality across the SURVIVING control-plane layers ---------------------------
def test_two_kind_set_equality_across_all_layers() -> None:
    # `_DIR_ALIAS` maps the WIRE kind alias -> the DirectoryKind enum MEMBER. Both halves are
    # pinned: the wire vocabulary the read edge accepts, and the domain enum it resolves to.
    # Comparing a member against a string would silently never match, so the two layers are
    # compared on their own terms and then against each other.
    wire_kinds = frozenset(_DIR_ALIAS)
    resolved = frozenset(_DIR_ALIAS.values())
    enum_members = frozenset(DirectoryKind)
    assert wire_kinds == frozenset({"startup", "investor"}), (
        f"the Control-Plane read edge wire-kind vocabulary drifted: {sorted(wire_kinds)} (must be exactly startup+investor)"
    )
    assert resolved == enum_members, "every accepted wire kind must resolve to a DirectoryKind member, and every member must be reachable"
    assert len(enum_members) == 2, f"the DirectoryKind enum must hold exactly two members; found {len(enum_members)}"
    # A Global Deal member is never approved (IC-007 is Draft/Proposed and grants no capability).
    assert "deal" not in wire_kinds, "no Global Deal kind may be approved"
    assert not any("Deal" in k.value for k in enum_members), "no Global Deal directory may enter the enum"


def test_nv_kind_set_drift_would_be_detected() -> None:
    for drifted in (frozenset({"startup"}), frozenset({"investor"}), frozenset({"startup", "investor", "deal"}), frozenset()):
        assert drifted != frozenset({"startup", "investor"}), "the kind-set comparison must reject a drifted set"


# --- D10/D12: bounded timeout, one request, zero retry, zero fan-out --------------------------------
def test_timeout_bounded_default_and_wired_to_urlopen() -> None:
    for client in _INTERNAL_CLIENTS:
        assert client.is_file(), f"{_scan.relposix(client)} must exist — the census cannot be vacuous"
        tree = _tree(client)
        defaults = _timeout_defaults(tree)
        assert defaults, f"{_scan.relposix(client)} must declare a bounded timeout default"
        for value in defaults:
            assert 0 < value <= _TIMEOUT_CEILING_SECONDS, f"{_scan.relposix(client)} timeout default {value} is not bounded positive"
        for call in _urlopen_calls(tree):
            kwargs = {kw.arg for kw in call.keywords}
            assert "timeout" in kwargs, f"{_scan.relposix(client)} must pass timeout= to urlopen (an unbounded call hangs the edge)"


def test_exactly_one_urlopen_never_in_a_loop() -> None:
    for client in _INTERNAL_CLIENTS:
        tree = _tree(client)
        calls = _urlopen_calls(tree)
        assert len(calls) == 1, f"{_scan.relposix(client)} must own exactly ONE urlopen call site; found {len(calls)}"
        assert not _calls_inside_loops(tree, "urlopen"), (
            f"{_scan.relposix(client)} must never call urlopen inside a loop (no retry, no fan-out)"
        )


def test_nv_retry_loop_would_be_detected() -> None:
    looped = ast.parse("import urllib.request\nfor _ in range(3):\n    urllib.request.urlopen(r, timeout=1)\n")
    assert _urlopen_calls(looped), "the urlopen census must see a real call"
    assert _calls_inside_loops(looped, "urlopen"), "a retry loop around urlopen must be detectable"
    unbounded = ast.parse("import urllib.request\nurllib.request.urlopen(r)\n")
    assert not {kw.arg for kw in _urlopen_calls(unbounded)[0].keywords}, "an unbounded urlopen must be detectable"
    assert _timeout_defaults(ast.parse("class C:\n    def __init__(self, timeout: float = 900.0):\n        ...\n")) == [900.0], (
        "the timeout-default reader must see an out-of-bound value"
    )


# --- D16: pagination non-claim ----------------------------------------------------------------------
def test_pagination_non_claim_no_cursor_vocabulary() -> None:
    for client in _INTERNAL_CLIENTS:
        source = client.read_text(encoding="utf-8").lower()
        for banned in (_CURSOR_NEEDLE, _QUERY_LIMIT_NEEDLE, _AMP_LIMIT_NEEDLE, "next_page", "page_token"):
            assert banned not in source, f"{_scan.relposix(client)} must claim no pagination capability ({banned})"


if __name__ == "__main__":
    _scan.run(
        [
            test_two_kind_set_equality_across_all_layers,
            test_nv_kind_set_drift_would_be_detected,
            test_timeout_bounded_default_and_wired_to_urlopen,
            test_exactly_one_urlopen_never_in_a_loop,
            test_nv_retry_loop_would_be_detected,
            test_pagination_non_claim_no_cursor_vocabulary,
        ]
    )
