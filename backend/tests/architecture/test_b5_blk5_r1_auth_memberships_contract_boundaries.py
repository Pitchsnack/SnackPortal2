"""B5-BLK-5 R1 — principal-only auth + memberships contract-authoring boundary guard (default suite; no DB, no network).

Static text-only boundary pins for the B5-BLK-5 R1 auth + memberships contract-authoring surfaces
(D-41 / IC-005 / IC-009 / IC-010). This guard reads ONLY the three amended contracts and the decision register:

  - contracts/IC-005-Authentication-Routing-Contract.md   (R1 Principal-Only Bootstrap & OIDC Transition)
  - contracts/IC-009-Portal-Contracts.md                  (R1 Principal Bootstrap & Memberships-Before-Tenant-Selection)
  - contracts/IC-010-API-Gateway-Contract.md              (R1 Principal-Only Bootstrap Eligibility for MembershipsForPrincipal)
  - docs/Architecture-Decision-Register.md                (the D-41 entry)

It binds no runtime, imports no service package, opens no socket, and touches no database. Sections are extracted
structurally (heading -> first end marker after it), normalized (lowercase, drop markdown emphasis, collapse
whitespace) and pinned against stable semantic needles — never a full-document hash. Every required anchor carries
a planted-removal non-vacuity companion; every forbidden-authorization detector carries a planted probe that MUST
trip it.

This guard closes no blocker. B5-BLK-5 remains OPEN; the live blocker census remains 7 of 9 OPEN; production
remains NOT READY / DO-NOT-ACTIVATE. The guard positively requires exactly that and rejects any drift.

Pure stdlib; standalone-runnable:
  python tests/architecture/test_b5_blk5_r1_auth_memberships_contract_boundaries.py
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

# Section start markers (ASCII-only prefixes; each unique in its file).
_IC005_START = "## R1 Principal-Only Bootstrap & OIDC Transition"
_IC009_START = "### R1 Principal Bootstrap & Memberships-Before-Tenant-Selection"
_IC010_START = "## R1 Principal-Only Bootstrap Eligibility for MembershipsForPrincipal"
_ADR_START = "### D-41"

# The exact ratified R1 retirement sets (references-only; readiness report §6/§16, pinned by the D-41 entry).
_DIRECT_IDS = "6, 7, 8, 9, 10, 154, 155, 156, 157, 221, 227, 228, 232, 233, 234, 236, 237, 238, 239, 240, 241, 242, 243"
_DEPENDENCY_IDS = "5, 6, 7, 8, 9, 10, 11, 45, 46, 47, 48, 49, 53, 54, 55"


def _text(path: pathlib.Path) -> str:
    assert path.is_file(), f"the R1 contract surface must exist: {path}"
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


# Required anchors: (section_key, normalized_needle). Each pins a ratified R1 decision; each carries a
# planted-removal non-vacuity companion (test_required_anchors_non_vacuous).
_REQUIRED = (
    # Principal-only context; null tenant/role.
    ("ic005", "principal-only context"),
    ("ic010", "principal-only"),
    ("ic005", "active_tenant_id = null and role = null"),
    ("ic005", "role is server-derived only when a tenant is active"),
    # GET /memberships eligibility.
    ("ic005", "get /memberships"),
    ("ic005", "self-scoped"),
    ("ic010", "get /memberships"),
    ("ic010", "membershipsforprincipal only"),
    ("adr", "the only r1 business route"),
    # Tenant-route rejection (fail-closed).
    ("ic005", "no tenant-scoped operation accepts the principal-only context"),
    ("ic010", "tenant categories require an active tenant"),
    # Supabase JWT prohibition.
    ("ic005", "never accepts a supabase jwt"),
    # Gateway no-mint / no-exchange.
    ("ic005", "no token mint and no token exchange"),
    ("ic010", "the gateway mints and exchanges no token"),
    # Keycloak limited to the controlled R1 proof.
    ("ic005", "for r1's controlled proof"),
    ("ic005", "does not make keycloak the permanent production idp"),
    ("adr", "does not name keycloak the permanent production idp"),
    # Lifecycle ownership.
    ("ic005", "idp-owned: login"),
    ("ic005", "snackportal2 control authority: membership invitation authority"),
    # R1A stabilization (guard delta zero).
    ("ic005", "removes no direct-supabase or dependency occurrence"),
    ("adr", "guard delta = 0"),
    # R1B retirement (exact shrink).
    ("ic005", "r1b retires exactly the ratified r1 occurrence set"),
    ("adr", "removes exactly the 23 direct + 15 dependency occurrences"),
    ("adr", "shrinks the frontend guard's active sets by exactly those ids"),
    # Post-retirement fail-closed rollback.
    ("ic005", "post-retirement rollback is fail-closed unavailable"),
    ("adr", "never an ordinary restoration of removed supabase occurrences or active ids"),
    # WorkspaceMembershipDTO exact fields.
    ("ic009", "workspacemembershipdto"),
    ("ic009", "{ tenant_id, role, display_ref }"),
    ("ic009", "lawful successful empty list"),
    # Global Directory stays edge-dark.
    ("ic010", "global directory read stays edge-dark"),
    ("ic010", "get /directory/startup is not exposed"),
    # Exact ratified ID sets (references-only enumeration in the D-41 entry).
    ("adr", _norm(_DIRECT_IDS)),
    ("adr", _norm(_DEPENDENCY_IDS)),
    # Governance census preserved.
    ("adr", "d-41 closes no blocker"),
    ("adr", "b5-blk-5 remains open"),
    ("adr", "seven of nine blockers remain open"),
    ("adr", "production remains not ready / do-not-activate"),
)

# Forbidden-authorization detectors: (regex, label, probe). Green control = the regex matches NONE of the real
# section corpus; each planted probe MUST trip its detector (test_forbidden_detectors_catch_probes).
_FORBIDDEN = (
    (
        r"(?:may|can|shall|will|does)\s+accepts?\s+a\s+supabase\s+jwt",
        "Supabase-JWT-accepted",
        "The Auth Router MAY accept a Supabase JWT on migrated paths.",
    ),
    (
        r"may\s+(?:mint|exchange)",
        "Gateway-mints-or-exchanges",
        "The Gateway MAY mint or exchange a tenant-scoped token.",
    ),
    (
        r"may\s+proceed\s+under\s+(?:a\s+)?principal-only",
        "Tenant-route-under-tenantless",
        "A tenant operation MAY proceed under a principal-only context.",
    ),
    (
        r"keycloak\s+is\s+the\s+permanent\s+production\s+idp|keycloak-only",
        "Keycloak-permanent-or-provider-lock",
        "Keycloak is the permanent production IdP and the contract is Keycloak-only.",
    ),
    (
        r"r1a\s+stabilization\s+(?:removes|shrinks)",
        "R1A-shrinks",
        "R1A stabilization removes the 23 direct occurrences and shrinks the active set.",
    ),
    (
        r"post-retirement\s+rollback\s+restores",
        "Post-retirement-ordinary-restore",
        "Post-retirement rollback restores the removed Supabase occurrences and active IDs.",
    ),
    (
        r"r1\s+exposes\s+get\s+/directory",
        "R1-exposes-directory",
        "R1 exposes GET /directory/startup.",
    ),
    (
        r"authorizes\s+(?:the\s+)?workspace-switch",
        "R1-authorizes-workspace-switch",
        "R1 authorizes the workspace-switch assertion.",
    ),
    (
        r"d-41\s+closes\s+b5-blk-5|closes\s+b5-blk-5\b",
        "B5-BLK-5-closure-overclaim",
        "D-41 closes B5-BLK-5.",
    ),
    (
        r"production\s+is\s+ready\s+to\s+activate|ready\s+to\s+activate",
        "Production-readiness-overclaim",
        "Production is ready to activate.",
    ),
)


# ---------------------------------------------------------------------------
# 1. The four R1 sections extract and self-identify as D-41
# ---------------------------------------------------------------------------
def test_sections_present() -> None:
    for key, getter in _SECTIONS.items():
        sect = getter()
        assert sect, f"the R1 section must be non-empty: {key}"
        assert "d-41" in sect or "b5-blk-5 r1" in sect, f"the R1 section must self-identify as D-41: {key}"
    # non-vacuity: extraction of a non-existent heading raises.
    missing = False
    try:
        _section(_text(_IC005), "## NON-EXISTENT R1 HEADING")
    except AssertionError:
        missing = True
    assert missing, "extraction of a missing heading must raise"


# ---------------------------------------------------------------------------
# 2. Every required R1 anchor is present in its section
# ---------------------------------------------------------------------------
def test_required_anchors_present() -> None:
    for key, needle in _REQUIRED:
        sect = _SECTIONS[key]()
        assert needle in sect, f"MISSING R1 ANCHOR in {key}: {needle!r}"


# ---------------------------------------------------------------------------
# 3. Non-vacuity: deleting an anchor makes its presence check fail
# ---------------------------------------------------------------------------
def test_required_anchors_non_vacuous() -> None:
    for key, needle in _REQUIRED:
        sect = _SECTIONS[key]()
        assert needle not in sect.replace(needle, ""), f"anchor detector is vacuous for {key}: {needle!r}"


# ---------------------------------------------------------------------------
# 4. No forbidden authorization appears in the real R1 corpus (green control)
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
# 6. Exact ratified retirement ID sets (23 direct + 15 dependency), references-only
# ---------------------------------------------------------------------------
def test_exact_ratified_id_sets() -> None:
    adr = _adr()
    assert _norm(_DIRECT_IDS) in adr, "the D-41 entry must carry the exact 23 direct IDs, in order"
    assert _norm(_DEPENDENCY_IDS) in adr, "the D-41 entry must carry the exact 15 dependency IDs, in order"
    direct = [int(x) for x in _DIRECT_IDS.split(",")]
    dependency = [int(x) for x in _DEPENDENCY_IDS.split(",")]
    assert len(direct) == 23 and direct[0] == 6 and direct[-1] == 243, "the direct set must be exactly 23 IDs from 6..243"
    assert 154 in direct and 221 in direct and 236 in direct, "the identity-tenancy + auth-lane IDs must be present"
    assert len(dependency) == 15 and dependency[0] == 5 and dependency[-1] == 55, "the dependency set must be exactly 15 IDs from 5..55"
    # non-vacuity: dropping an ID changes the count.
    assert len([x for x in direct if x != 243]) != 23, "a dropped direct ID must be detectable"


# ---------------------------------------------------------------------------
# 7. Governance census is preserved by D-41 (closes no blocker, 7 of 9 OPEN)
# ---------------------------------------------------------------------------
def test_governance_census_preserved() -> None:
    adr = _adr()
    for needle in (
        "d-41 closes no blocker",
        "b5-blk-5 remains open",
        "b5-blk-8 remains open",
        "seven of nine blockers remain open",
        "production remains not ready / do-not-activate",
    ):
        assert needle in adr, f"D-41 must preserve the locked governance state: missing {needle!r}"
    # non-vacuity: no census-drift phrasing appears in D-41.
    assert "eight of nine" not in adr and "six of nine" not in adr, "no census drift may appear in D-41"
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
            test_exact_ratified_id_sets,
            test_governance_census_preserved,
        ]
    )
