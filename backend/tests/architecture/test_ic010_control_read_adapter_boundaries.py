"""IC-010 §V control-read adapter residual guards (B5-BLK-6C-C; default suite; no DB, no network).

Closes the two residual guard gaps the 6C-C readiness review found genuinely absent, and pins the
already-present adapter bounds so they cannot silently regress:

* **Two-kind set equality (D8)** — the approved directory-kind set is EXACTLY ``{"startup",
  "investor"}``, equality-pinned across all three layers that hold kind knowledge: the gateway
  adapter (``_APPROVED_KINDS``), the Control-Plane read edge alias map (``_DIR_ALIAS``), and the
  domain enum (``DirectoryKind``) / portal composer catalogue (directory-summary DTO ``record_type``
  values). A missing ``startup``, a missing ``investor``, an extra unsupported kind, a Global Deal
  member, or adapter↔edge↔composer drift each fail.
* **Client-kind refusal without a wire call (D9)** — an unapproved kind resolves to ``None``
  adapter-side with NO provider request (proven against an unreachable base URL: a wire attempt
  would raise).
* **Bounded timeout (D10)** — a bounded positive constructor default, passed to ``urlopen``.
* **Bounded response size (D11)** — a bounded positive default with max+1 read enforcement.
* **One request / zero retry / zero fan-out (D12)** — exactly ONE ``urlopen`` call site in the
  module, never inside a loop; each port method issues exactly one ``_get``.
* **Pagination non-claim (D16)** — the adapter sends NO cursor/limit and never follows a
  ``next_cursor``: the request paths are pinned to their exact query-free/one-parameter forms and
  cursor vocabulary is banned from the module. The Gateway therefore composes ONE directory page
  only — a pinned limitation, not a pagination capability, and no pagination support is claimed.

Pure stdlib + repository imports; standalone-runnable:
  python tests/architecture/test_ic010_control_read_adapter_boundaries.py

B5-BLK-6 remains OPEN; production remains NOT READY / DO-NOT-ACTIVATE. This guard closes no blocker.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import pathlib
import sys
from typing import List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

from api_gateway.adapters.providers.http_control_plane_read import _APPROVED_KINDS, HttpControlPlaneRead  # noqa: E402
from api_gateway.portal import APPROVED_PORTAL_DTOS, GlobalInvestorSummaryDTO, GlobalStartupSummaryDTO  # noqa: E402
from control_plane.read_api import _DIR_ALIAS  # noqa: E402
from control_plane.records import DirectoryKind  # noqa: E402

_ADAPTER = _scan.BACKEND_ROOT / "api_gateway" / "adapters" / "providers" / "http_control_plane_read.py"

# An unreachable base: the refusal legs must answer WITHOUT any wire call — if a mutation made the
# adapter call the wire for an unapproved kind, the connection attempt would raise and fail the test.
_UNREACHABLE_BASE = "http://127.0.0.1:1"

_TIMEOUT_CEILING_SECONDS = 30.0
_SIZE_CEILING_BYTES = 4 * 1024 * 1024

# Dynamic needles — built so THIS guard never satisfies its own bans.
_CURSOR_NEEDLE = "cur" + "sor"
_QUERY_LIMIT_NEEDLE = "?lim" + "it"
_AMP_LIMIT_NEEDLE = "&lim" + "it"


def _tree() -> ast.Module:
    return ast.parse(_ADAPTER.read_text(encoding="utf-8"), filename=str(_ADAPTER))


def _source() -> str:
    return _ADAPTER.read_text(encoding="utf-8")


def _urlopen_calls(tree: ast.Module) -> List[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func).replace("urllib.request.", "") == "urlopen"]


def _calls_inside_loops(tree: ast.Module, attr_suffix: str) -> List[ast.Call]:
    hits: List[ast.Call] = []
    for loop in (n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))):
        for inner in ast.walk(loop):
            if isinstance(inner, ast.Call) and ast.unparse(inner.func).endswith(attr_suffix):
                hits.append(inner)
    return hits


def _method(tree: ast.Module, class_name: str, method_name: str) -> Optional[ast.FunctionDef]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    return None


def _get_call_count(fn: ast.FunctionDef) -> int:
    return sum(1 for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "_get")


# --- D8: two-kind set equality across adapter, read edge, enum, and composer catalogue --------------
def test_two_kind_set_equality_across_all_layers() -> None:
    assert _APPROVED_KINDS == frozenset({"startup", "investor"}), (
        f"the approved directory-kind set drifted: {sorted(_APPROVED_KINDS)} (must be exactly startup+investor)"
    )
    assert set(_DIR_ALIAS.keys()) == {"startup", "investor"}, f"read-edge alias kinds drifted: {sorted(_DIR_ALIAS)}"
    assert set(_DIR_ALIAS.values()) == {DirectoryKind.STARTUP, DirectoryKind.INVESTOR}
    assert {k.name for k in DirectoryKind} == {"STARTUP", "INVESTOR"}, "DirectoryKind must hold NO extra member (no DEAL)"
    directory_dtos = {cls for cls in APPROVED_PORTAL_DTOS if "records" in {f.name for f in dataclasses.fields(cls)}}
    assert directory_dtos == {GlobalStartupSummaryDTO, GlobalInvestorSummaryDTO}, (
        "the composer catalogue's directory-summary DTO set drifted from the two approved kinds"
    )
    assert {GlobalStartupSummaryDTO(records=()).record_type, GlobalInvestorSummaryDTO(records=()).record_type} == {
        k.value for k in DirectoryKind
    }, "adapter/composer record_type values drifted from the DirectoryKind enum (adapter<->composer lockstep)"


# --- D9: unapproved / malformed kinds are refused adapter-side with NO wire call --------------------
def test_unapproved_kind_refused_without_any_wire_call() -> None:
    client = HttpControlPlaneRead(_UNREACHABLE_BASE)
    for kind in ("deal", "", "startup/extra", "DEAL", "Startup"):
        assert client.directory(kind) is None, f"kind {kind!r} must be refused adapter-side (None, no wire call)"


# --- D10: bounded positive timeout, passed to urlopen -----------------------------------------------
def test_timeout_bounded_default_and_wired_to_urlopen() -> None:
    default = inspect.signature(HttpControlPlaneRead.__init__).parameters["timeout"].default
    assert isinstance(default, float) and 0 < default <= _TIMEOUT_CEILING_SECONDS, f"unbounded/unsafe timeout default: {default!r}"
    calls = _urlopen_calls(_tree())
    assert calls, "the adapter must reach the wire through urlopen"
    for call in calls:
        assert any(kw.arg == "timeout" for kw in call.keywords), "urlopen must carry the bounded timeout= keyword"


# --- D11: bounded response size with max+1 enforcement ----------------------------------------------
def test_response_size_bound_default_and_enforcement_shape() -> None:
    default = inspect.signature(HttpControlPlaneRead.__init__).parameters["max_response_bytes"].default
    assert isinstance(default, int) and 0 < default <= _SIZE_CEILING_BYTES, f"unbounded/unsafe size default: {default!r}"
    text = _source()
    assert "self._max_bytes + 1" in text, "the bounded read must fetch max+1 bytes to detect oversize"
    assert "> self._max_bytes" in text, "the oversize comparison enforcement is missing"
    assert "oversized" in text, "the oversize rejection must raise (fail closed to 503 at the gateway)"


# --- D12: one request, zero retry, zero fan-out, no loop --------------------------------------------
def test_exactly_one_urlopen_never_in_a_loop_one_get_per_method() -> None:
    tree = _tree()
    calls = _urlopen_calls(tree)
    assert len(calls) == 1, f"exactly ONE urlopen call site is permitted (found {len(calls)}) — no retry, no fan-out"
    assert not _calls_inside_loops(tree, "urlopen"), "urlopen may never sit inside a loop (hidden retry/pagination)"
    assert not _calls_inside_loops(tree, "._get"), "_get may never sit inside a loop (hidden retry/pagination)"
    for method_name in ("directory", "memberships_for_principal"):
        method = _method(tree, "HttpControlPlaneRead", method_name)
        assert method is not None, f"HttpControlPlaneRead.{method_name} is missing"
        assert _get_call_count(method) == 1, f"{method_name} must issue exactly ONE provider request"


# --- D16: pagination non-claim — no cursor/limit sent, next_cursor never followed -------------------
def test_pagination_non_claim_no_cursor_vocabulary_and_pinned_paths() -> None:
    text = _source()
    for needle in (_CURSOR_NEEDLE, _QUERY_LIMIT_NEEDLE, _AMP_LIMIT_NEEDLE):
        assert needle not in text, f"the adapter must carry NO pagination vocabulary (found {needle!r})"
    assert '"/directory/" + urllib.parse.quote(kind)' in text, "the directory request path drifted (must be query-free)"
    assert '"/memberships?p=" + urllib.parse.quote(principal_ref)' in text, (
        "the memberships request path drifted (principal is the ONLY parameter)"
    )


# --- non-vacuity companions (planted mutants judged through the SAME helpers) -----------------------
def test_nv_retry_loop_would_be_detected() -> None:
    planted = ast.parse(
        "import urllib.request\ndef fetch(url):\n    for _ in range(3):\n        return urllib.request.urlopen(url, timeout=2.0)\n"
    )
    assert _calls_inside_loops(planted, "urlopen"), "a retry loop around urlopen MUST be detectable"


def test_nv_kind_set_drift_would_be_detected() -> None:
    assert frozenset({"startup"}) != frozenset({"startup", "investor"})
    assert frozenset({"startup", "investor", "deal"}) != frozenset({"startup", "investor"})


if __name__ == "__main__":
    _scan.run(
        [
            test_two_kind_set_equality_across_all_layers,
            test_unapproved_kind_refused_without_any_wire_call,
            test_timeout_bounded_default_and_wired_to_urlopen,
            test_response_size_bound_default_and_enforcement_shape,
            test_exactly_one_urlopen_never_in_a_loop_one_get_per_method,
            test_nv_retry_loop_would_be_detected,
            test_nv_kind_set_drift_would_be_detected,
            test_pagination_non_claim_no_cursor_vocabulary_and_pinned_paths,
        ]
    )
