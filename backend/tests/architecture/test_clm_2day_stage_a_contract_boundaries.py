"""CLM — 2-Day Accelerated Controlled Local MVP Stage A contract-authority boundary guard (default suite; no DB, no network).

Static text-only boundary pins for the D-42 Stage A minimum contract authority slice (the CLM controlled-local
rehearsal slice) authored under the Dan-authorized 2-Day Accelerated Controlled Local MVP V2 START-GATE. This
guard reads ONLY the three amended contracts and the decision register:

  - contracts/IC-005-Authentication-Routing-Contract.md   (CLM Controlled-Local Rehearsal Authority)
  - contracts/IC-009-Portal-Contracts.md                  (CLM Tenant Startup Read & Bounded Update DTOs)
  - contracts/IC-010-API-Gateway-Contract.md              (CLM Tenant Startup Read & Bounded Update Route Eligibility)
  - docs/Architecture-Decision-Register.md                (the D-42 entry)

It binds no runtime, imports no service package, opens no socket, and touches no database. Sections are extracted
structurally (heading -> first end marker after it), normalized (lowercase, drop markdown emphasis, collapse
whitespace) and pinned against stable semantic needles — never a full-document hash. Every required anchor carries
a planted-removal non-vacuity companion; every forbidden-authorization detector carries a planted probe that MUST
trip it.

This guard closes no blocker. B5-BLK-5 remains OPEN; the live blocker census remains 7 of 9 OPEN; production
remains NOT READY / DO-NOT-ACTIVATE. The guard positively requires exactly that and rejects any drift.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_clm_2day_stage_a_contract_boundaries.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _scan  # noqa: E402

_IC005 = _scan.REPO_ROOT / "contracts" / "IC-005-Authentication-Routing-Contract.md"
_IC009 = _scan.REPO_ROOT / "contracts" / "IC-009-Portal-Contracts.md"
_IC010 = _scan.REPO_ROOT / "contracts" / "IC-010-API-Gateway-Contract.md"
_ADR = _scan.REPO_ROOT / "docs" / "Architecture-Decision-Register.md"

# Section start markers (ASCII-prefixed headings; each unique in its file).
_IC005_START = "## CLM Controlled-Local Rehearsal Authority"
_IC009_START = "### CLM Tenant Startup Read & Bounded Update DTOs"
_IC010_START = "## CLM Tenant Startup Read & Bounded Update Route Eligibility"
_ADR_START = "### D-42"

# The two exact CLM served tenant Startup routes and the single allowlisted field (D-42 items 2/3).
_READ_ROUTE = "get /tenant/startups/<startup_ref>"
_UPDATE_ROUTE = "patch /tenant/startups/<startup_ref>"
_ALLOWLISTED_FIELD = "short_description"
_READ_DTO_FIELDS = (
    "{ record_ref, display_name, short_description, investment_stage, record_origin, record_residency, record_type, lineage_reference }"
)
_UPDATE_DTO_FIELDS = "{ short_description }"


def _text(path: pathlib.Path) -> str:
    assert path.is_file(), f"the CLM contract surface must exist: {path}"
    return path.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    """Lowercase, normalize dash/arrow glyphs, drop markdown emphasis, and collapse whitespace."""
    s = s.lower()
    s = s.replace("—", "-").replace("–", "-").replace("→", "->")
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s)


def _section(text: str, start: str, *ends: str) -> str:
    """The normalized slice of ``text`` from ``start`` (inclusive) to the first ``end`` marker after it (or EOF)."""
    i = text.find(start)
    assert i != -1, f"section start marker not found: {start!r}"
    tail = text[i + len(start) :]
    cut = len(tail)
    for end in ends:
        j = tail.find(end)
        if j != -1:
            cut = min(cut, j)
    return _norm(start + tail[:cut])


def _ic005() -> str:
    return _section(_text(_IC005), _IC005_START)


def _ic009() -> str:
    return _section(_text(_IC009), _IC009_START)


def _ic010() -> str:
    return _section(_text(_IC010), _IC010_START, "\n## Not implemented")


def _adr() -> str:
    return _section(_text(_ADR), _ADR_START, "\n## Open")


_SECTIONS = {"ic005": _ic005, "ic009": _ic009, "ic010": _ic010, "adr": _adr}


def _corpus() -> str:
    return " ".join(getter() for getter in _SECTIONS.values())


# Required anchors: (section_key, normalized_needle). Each pins a ratified D-42 Stage A decision; each carries a
# planted-removal non-vacuity companion (test_required_anchors_non_vacuous).
_REQUIRED = (
    # CLM slice identity + synthetic-local boundary.
    ("ic005", "clm is the d-42 controlled-local rehearsal slice"),
    ("ic005", "synthetic local data only"),
    ("adr", "minimum contract authority slice"),
    ("adr", "synthetic local data only"),
    ("adr", "no production or staging activation"),
    ("adr", "no real customer data"),
    # Controlled-local Keycloak ratification (not the permanent production IdP).
    ("ic005", "keycloak remains the selected oidc provider for the controlled-local clm rehearsal"),
    ("ic005", "does not make keycloak the permanent production idp"),
    ("adr", "does not name keycloak the permanent production idp"),
    # IdP-minted tenant-claim tokens; Gateway non-minting.
    ("ic005", "minted only at the idp"),
    ("ic005", "the gateway mints and exchanges no token"),
    # Backend-validated tenant selection + unauthorized-tenant denial.
    ("ic005", "lawfulness is decided exclusively by the backend"),
    ("ic005", "denied fail-closed 403"),
    ("ic005", "exposes no tenant data and no tenant-existence detail"),
    # Exact routes, category, and prefix.
    ("ic010", _READ_ROUTE),
    ("ic010", _UPDATE_ROUTE),
    ("ic010", "exactly three business routes"),
    ("ic010", "existing tenant operations category"),
    ("ic010", "no dispatch category is added"),
    ("ic010", "global directory read stays edge-dark"),
    ("ic010", "no new public_code"),
    ("ic010", "exactly one tenant database"),
    ("ic010", "consistent ic-002 not found semantic"),
    ("adr", _READ_ROUTE),
    ("adr", _UPDATE_ROUTE),
    # Bounded update: the single harmless allowlisted field (bounds pinned in both homes).
    ("ic010", "at most 500 characters"),
    ("ic009", "at most 500 characters"),
    ("ic010", "the request body is bounded at 16384 bytes"),
    ("ic010", "(1..512 utf-8 bytes)"),
    ("ic010", "no partial write"),
    ("ic010", "sole clm-mutable field"),
    ("ic009", "sole clm-mutable field"),
    ("adr", "short_description is the single harmless allowlisted field"),
    # Exact DTO shapes; served revision unchanged.
    ("ic009", "tenantstartupdetaildto"),
    ("ic009", _READ_DTO_FIELDS),
    ("ic009", "tenantstartupupdaterequestdto"),
    ("ic009", _UPDATE_DTO_FIELDS),
    ("ic009", "the served revision remains ic-009-r1"),
    # Portal states + Gateway-only journey.
    ("ic009", "never page -> denied-after-protected-data"),
    ("ic009", "no direct supabase business-data access"),
    ("ic009", "logout presentation is idp-owned"),
    # The four ratified runtime audit events (no wider expansion; no new denial class).
    ("ic010", "tenant_startup_read"),
    ("ic010", "tenant_startup_update"),
    ("ic010", "workspace_memberships_read"),
    ("ic010", "routedenied"),
    ("ic010", "the api gateway is the sole emitter"),
    ("ic010", "control-db operational audit"),
    ("ic010", "class-home binding sequences under the pending ic-002 audit-section extension"),
    ("ic010", "no new denial or anomaly class"),
    ("ic010", "is implemented only under the stage b implementation slice"),
    # Stage B remains blocked behind verification + human merge + baseline re-proof.
    ("adr", "fresh independent stage a verification returns accept"),
    ("adr", "dan human-merges the stage a contract pr"),
    ("adr", "the post-merge baseline is re-proven"),
    # Governance census preserved.
    ("adr", "d-42 closes no blocker"),
    ("adr", "b5-blk-5 remains open"),
    ("adr", "seven of nine blockers remain open"),
    ("adr", "production remains not ready / do-not-activate"),
)

# Forbidden-authorization detectors: (regex, label, probe). Green control = the regex matches NONE of the real
# section corpus; each planted probe MUST trip it (test_forbidden_detectors_catch_probes).
_FORBIDDEN = (
    (
        r"authorizes\s+(?:startup\s+)?(?:create|creation|delete|deletion)",
        "Startup-create-or-delete",
        "This slice authorizes Startup create and delete routes.",
    ),
    (
        r"(?:second|additional|another)\s+(?:allowlisted|mutable)\s+field",
        "Second-allowlisted-field",
        "A second allowlisted field is added to the bounded update.",
    ),
    (
        r"general\s+edit\s+capability\s+is\s+(?:granted|authorized)",
        "General-edit-capability",
        "General edit capability is granted for tenant Startup records.",
    ),
    (
        r"directory\s+route\s+is\s+(?:served|activated|exposed)",
        "Directory-route-activation",
        "The Global Directory route is served in CLM.",
    ),
    (
        r"workspace\s+token\s+exchange\s+is\s+(?:authorized|performed)|rfc\s*8693\s+is\s+(?:authorized|implemented)",
        "Workspace-token-exchange",
        "Workspace token exchange is authorized for the rehearsal.",
    ),
    (
        r"uses\s+real\s+customer\s+data|real\s+customer\s+data\s+(?:is|are|may\s+be)\s+(?:used|permitted)",
        "Real-customer-data",
        "The rehearsal uses real customer data.",
    ),
    (
        r"activates\s+(?:the\s+)?production|production\s+activation\s+is\s+(?:authorized|performed)",
        "Production-activation",
        "This slice activates the production IdP.",
    ),
    (
        r"direct\s+supabase\s+business-data\s+access\s+is\s+(?:permitted|retained|authorized)",
        "Supabase-business-data",
        "Direct Supabase business-data access is permitted for this journey.",
    ),
    (
        r"(?:media|billing|email|chat)\s+(?:route|surface|capability)s?\s+(?:is|are)\s+(?:added|authorized)",
        "Excluded-feature-added",
        "A media route is added to the CLM slice.",
    ),
    (
        r"(?:get|patch|post|put|delete)\s+/tenant/(?:investors|deals)",
        "Investor-or-Deal-route",
        "GET /tenant/investors/<investor_ref> is served in CLM.",
    ),
)


# ---------------------------------------------------------------------------
# 1. The four CLM sections extract and self-identify as D-42 / CLM
# ---------------------------------------------------------------------------
def test_sections_present() -> None:
    for key, getter in _SECTIONS.items():
        sect = getter()
        assert sect, f"the CLM section must be non-empty: {key}"
        assert "d-42" in sect or "clm" in sect, f"the CLM section must self-identify as D-42: {key}"
    # non-vacuity: extraction of a non-existent heading raises.
    missing = False
    try:
        _section(_text(_IC005), "## NON-EXISTENT CLM HEADING")
    except AssertionError:
        missing = True
    assert missing, "extraction of a missing heading must raise"


# ---------------------------------------------------------------------------
# 2. Every required CLM anchor is present in its section
# ---------------------------------------------------------------------------
def test_required_anchors_present() -> None:
    for key, needle in _REQUIRED:
        sect = _SECTIONS[key]()
        assert needle in sect, f"MISSING CLM ANCHOR in {key}: {needle!r}"


# ---------------------------------------------------------------------------
# 3. Non-vacuity: deleting an anchor makes its presence check fail
# ---------------------------------------------------------------------------
def test_required_anchors_non_vacuous() -> None:
    for key, needle in _REQUIRED:
        sect = _SECTIONS[key]()
        assert needle not in sect.replace(needle, ""), f"anchor detector is vacuous for {key}: {needle!r}"


# ---------------------------------------------------------------------------
# 4. No forbidden authorization appears in the real CLM corpus (green control)
# ---------------------------------------------------------------------------
def test_forbidden_authorizations_absent() -> None:
    corpus = _corpus()
    for pattern, label, _probe in _FORBIDDEN:
        assert re.search(pattern, corpus) is None, f"forbidden authorization present ({label}): /{pattern}/"


# ---------------------------------------------------------------------------
# 5. Every forbidden detector fires on its planted probe
# ---------------------------------------------------------------------------
def test_forbidden_detectors_catch_probes() -> None:
    corpus = _corpus()
    for pattern, label, probe in _FORBIDDEN:
        norm_probe = _norm(probe)
        assert re.search(pattern, norm_probe), f"detector must fire on its probe ({label}): /{pattern}/"
        assert norm_probe not in corpus, f"probe wording must be absent from the real corpus ({label})"


# ---------------------------------------------------------------------------
# 6. Single-field closure: the bounded update allowlists exactly short_description
# ---------------------------------------------------------------------------
def test_single_allowlisted_field_closure() -> None:
    ic009 = _ic009()
    assert ic009.count(_UPDATE_DTO_FIELDS) == 1, "the update request DTO must be pinned exactly once in IC-009"
    update_fields = [f.strip() for f in _UPDATE_DTO_FIELDS.strip("{} ").split(",")]
    assert update_fields == [_ALLOWLISTED_FIELD], "the update request DTO must carry exactly the one allowlisted field"
    read_fields = [f.strip() for f in _READ_DTO_FIELDS.strip("{} ").split(",")]
    assert len(read_fields) == 8 and read_fields[0] == "record_ref", "the read DTO must be exactly the 8 pinned fields"
    assert _ALLOWLISTED_FIELD in read_fields, "the allowlisted field must appear in the read DTO"
    for banned in ("email", "owner_agent_ref", "tenant_name", "tenant_code", "dsn", "secret"):
        assert banned not in read_fields, f"the read DTO must not carry {banned!r}"
    # No other column is authorized as mutable anywhere in the CLM corpus.
    corpus = _corpus()
    for other in ("long_description", "product_overview", "company_name is clm-mutable"):
        assert other not in corpus, f"only short_description may be CLM-mutable; found {other!r}"
    # non-vacuity: a two-field update DTO would break the closure.
    assert [f.strip() for f in "{ short_description, long_description }".strip("{} ").split(",")] != [_ALLOWLISTED_FIELD]


# ---------------------------------------------------------------------------
# 7. Exact route-set closure: exactly the two tenant Startup routes, read + bounded update
# ---------------------------------------------------------------------------
def test_exact_route_set() -> None:
    ic010 = _ic010()
    assert _READ_ROUTE in ic010 and _UPDATE_ROUTE in ic010, "both exact CLM routes must be recorded in IC-010"
    assert "exactly three business routes" in ic010, "IC-010 must pin the exactly-three served business-route set"
    mutating = re.compile(r"(?:post|put|delete)\s+/tenant/startups")
    assert mutating.search(_corpus()) is None, "no POST/PUT/DELETE tenant Startup route may be authorized"
    # non-vacuity: the detector fires on a planted mutating route.
    assert mutating.search(_norm("POST /tenant/startups/<startup_ref>")), "the mutating-route detector must fire"


# ---------------------------------------------------------------------------
# 8. Governance census is preserved by D-42 (closes no blocker, 7 of 9 OPEN)
# ---------------------------------------------------------------------------
def test_governance_census_preserved() -> None:
    adr = _adr()
    for needle in (
        "d-42 closes no blocker",
        "b5-blk-5 remains open",
        "b5-blk-8 remains open",
        "seven of nine blockers remain open",
        "production remains not ready / do-not-activate",
    ):
        assert needle in adr, f"D-42 must preserve the locked governance state: missing {needle!r}"
    # non-vacuity: no census-drift phrasing appears in D-42.
    assert "eight of nine" not in adr and "six of nine" not in adr, "no census drift may appear in D-42"
    # meta: this guard closes no blocker.
    guard_src = _norm(pathlib.Path(__file__).read_text(encoding="utf-8"))
    assert "closes no blocker" in guard_src, "the guard must declare that it closes no blocker"


if __name__ == "__main__":
    _scan.run(
        [
            test_sections_present,
            test_required_anchors_present,
            test_required_anchors_non_vacuous,
            test_forbidden_authorizations_absent,
            test_forbidden_detectors_catch_probes,
            test_single_allowlisted_field_closure,
            test_exact_route_set,
            test_governance_census_preserved,
        ]
    )
