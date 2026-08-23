"""Stage 5 — the D-23 integrity chain and the per-tenant lineage-key surface.

Two things are proven here, and they are different kinds of claim.

The **algorithm** claim is one of fidelity: the rebuild restates an accepted algorithm it is
forbidden to import, so the restatement is executed side by side with the original and the two
must agree byte for byte. A prose assertion that "this matches ``lineage_service/canonical.py``"
would be worth nothing the first time someone reordered a field.

The **key** claim is one of containment: a chain key is per tenant, resolves only server-side,
fails closed when absent, and appears in no repr, no log, no response, and no published
contract.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import pathlib
import subprocess
import sys
from typing import Any, Dict

import pytest

from snackportal2.shared import lineage_chain
from snackportal2.shared.errors import AppError, ErrorCode
from snackportal2.shared.lineage_keys import (
    ENV_LINEAGE_KEY_PREFIX,
    MINIMUM_KEY_CHARACTERS,
    EnvironmentLineageKeyResolver,
    LineageChainKey,
    build_lineage_key_resolver,
)

#: Test key material. Long enough to satisfy the configured floor, and obviously synthetic.
ACME_KEY = "acme-test-chain-key-0000000000000000"
ZETA_KEY = "zeta-test-chain-key-1111111111111111"

_ENV = {
    EnvironmentLineageKeyResolver.variable_name("acme"): ACME_KEY,
    EnvironmentLineageKeyResolver.variable_name("zeta"): ZETA_KEY,
    EnvironmentLineageKeyResolver.variable_name("nova"): "   ",
    EnvironmentLineageKeyResolver.variable_name("tiny"): "short",
}

_ROW: Dict[str, Any] = {
    "lineage_id": "ln-0001",
    "seq": 7,
    "event_type": "import",
    "occurred_at": "2026-08-23T10:00:00+00:00",
    "actor_ref": "p-agent",
    "source_ref": "gs-1",
    "target_ref": "ref:acme:startups:12",
    "operation": "global_startup_import",
    "schema_version": "1",
    "derivation_ref": "imp-abc",
    "parent_lineage_ref": None,
    # Deliberately present and deliberately not serialized.
    "correlation_id": "c-1",
    "segment_id": 1,
    "marker_version": 1,
}


# --- the algorithm, checked against the accepted implementation ------------------------------


def _accepted() -> Any:
    """The retired architecture's canonicalizer, imported by a *test* only.

    Neither package imports the other — import-linter's two forbidden contracts are about
    production dependency structure, and this module belongs to neither root package.
    Importing both here is the only way to execute them against each other, which is the
    entire point of the comparison.
    """
    return importlib.import_module("lineage_service.canonical")


def test_the_rebuilds_canonical_content_is_byte_identical_to_the_accepted_one() -> None:
    accepted = _accepted()
    for prev in ("", "deadbeef" * 8):
        mine = lineage_chain.canonical_content(_ROW, prev)
        theirs = accepted.canonical_content(_ROW, prev)
        assert mine == theirs, "the rebuild's v1 serialization drifted from the accepted one"


def test_the_rebuilds_marker_is_identical_to_the_accepted_marker() -> None:
    accepted = _accepted()
    assert lineage_chain.marker_for(ACME_KEY.encode("utf-8"), _ROW, "") == accepted.marker_for(ACME_KEY, _ROW, "")
    assert lineage_chain.CURRENT_MARKER_VERSION == accepted.CURRENT_MARKER_VERSION


def test_every_serialized_field_changes_the_marker() -> None:
    """A field the digest ignores is a field an attacker may edit freely."""
    key = ACME_KEY.encode("utf-8")
    baseline = lineage_chain.marker_for(key, _ROW, "")
    for name in lineage_chain._V1_FIELDS:
        mutated = dict(_ROW)
        mutated[name] = "tampered"
        assert lineage_chain.marker_for(key, mutated, "") != baseline, name + " is not covered by the digest"


def test_the_excluded_fields_are_genuinely_excluded() -> None:
    """Segmentation is a label and correlation is request metadata — neither orders the chain."""
    key = ACME_KEY.encode("utf-8")
    baseline = lineage_chain.marker_for(key, _ROW, "")
    for name in ("correlation_id", "segment_id", "marker_version", "integrity_marker", "prev_marker"):
        mutated = dict(_ROW)
        mutated[name] = "changed"
        assert lineage_chain.marker_for(key, mutated, "") == baseline, name + " unexpectedly entered the digest"


def test_the_previous_marker_chains_the_row() -> None:
    key = ACME_KEY.encode("utf-8")
    assert lineage_chain.marker_for(key, _ROW, "a") != lineage_chain.marker_for(key, _ROW, "b")


def test_a_different_tenant_key_produces_a_different_marker() -> None:
    """Per-tenant chains: one tenant key must not verify another tenant chain."""
    assert lineage_chain.marker_for(ACME_KEY.encode("utf-8"), _ROW, "") != lineage_chain.marker_for(
        ZETA_KEY.encode("utf-8"), _ROW, ""
    )


def test_an_unknown_marker_version_is_refused_not_defaulted() -> None:
    with pytest.raises(lineage_chain.UnknownMarkerVersion):
        lineage_chain.canonical_content(_ROW, "", marker_version=99)


# --- the key resolver ------------------------------------------------------------------------


def test_a_configured_tenant_key_resolves() -> None:
    resolver = build_lineage_key_resolver(_ENV)
    resolved = resolver.resolve_lineage_key("acme")
    assert isinstance(resolved, LineageChainKey)
    assert resolved.material == ACME_KEY.encode("utf-8")
    assert resolved.tenant_ref == "acme"


def test_acme_and_zeta_resolve_different_keys() -> None:
    resolver = build_lineage_key_resolver(_ENV)
    assert resolver.resolve_lineage_key("acme").material != resolver.resolve_lineage_key("zeta").material


def test_an_unconfigured_tenant_fails_closed() -> None:
    resolver = build_lineage_key_resolver(_ENV)
    with pytest.raises(AppError) as raised:
        resolver.resolve_lineage_key("absent")
    assert raised.value.status == 503
    assert raised.value.code is ErrorCode.TENANT_UNAVAILABLE


def test_an_empty_key_fails_closed_rather_than_resolving_to_empty_material() -> None:
    resolver = build_lineage_key_resolver(_ENV)
    with pytest.raises(AppError):
        resolver.resolve_lineage_key("nova")


def test_a_placeholder_key_below_the_floor_fails_closed() -> None:
    resolver = build_lineage_key_resolver(_ENV)
    with pytest.raises(AppError):
        resolver.resolve_lineage_key("tiny")
    assert MINIMUM_KEY_CHARACTERS >= 32


def test_a_tenantless_context_resolves_no_key() -> None:
    with pytest.raises(AppError):
        build_lineage_key_resolver(_ENV).resolve_lineage_key("")


def test_with_nothing_configured_every_tenant_fails_closed() -> None:
    """There is no default key and no shared key. Omission denies; it does not improvise."""
    resolver = build_lineage_key_resolver({})
    for tenant in ("acme", "zeta", "nova"):
        with pytest.raises(AppError):
            resolver.resolve_lineage_key(tenant)


def test_the_variable_name_is_derived_from_the_tenant_reference() -> None:
    assert EnvironmentLineageKeyResolver.variable_name("acme") == ENV_LINEAGE_KEY_PREFIX + "ACME"
    assert EnvironmentLineageKeyResolver.variable_name("odd-tenant.1") == ENV_LINEAGE_KEY_PREFIX + "ODD_TENANT_1"


# --- containment: the key reaches no repr, no log, no contract -------------------------------


def test_the_resolved_key_is_redacted_in_repr_and_str() -> None:
    resolved = build_lineage_key_resolver(_ENV).resolve_lineage_key("acme")
    for rendering in (repr(resolved), str(resolved), "{}".format(resolved), f"{resolved}"):
        assert ACME_KEY not in rendering, "the chain key rendered itself"
        assert "<redacted>" in rendering
    assert ACME_KEY not in repr({"key": resolved})


def test_a_traceback_carrying_the_key_object_discloses_no_material() -> None:
    """A denial raised while the key is in scope must not print it into the traceback."""
    resolved = build_lineage_key_resolver(_ENV).resolve_lineage_key("acme")
    try:
        raise ValueError("failed with " + repr(resolved))
    except ValueError as exc:
        assert ACME_KEY not in str(exc)


def test_resolving_a_key_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        build_lineage_key_resolver(_ENV).resolve_lineage_key("acme")
        try:
            build_lineage_key_resolver(_ENV).resolve_lineage_key("absent")
        except AppError:
            pass
    assert caplog.text == "", "the key resolver emitted log output"


def _generated_documents() -> Dict[str, Any]:
    """All fourteen documents, generated in a subprocess that *has* key variables set.

    A subprocess carrying real-looking key configuration, so the check is that the published
    contracts do not react to the secret surface being configured — not merely that they
    happen not to mention it in a process where nothing was configured at all.
    """
    backend_root = pathlib.Path(__file__).resolve().parents[2]
    generator = (
        "import json, sys\n"
        "from importlib import import_module\n"
        "from snackportal2.shared.config import SERVICE_REGISTRY\n"
        "documents = {}\n"
        "for key in SERVICE_REGISTRY:\n"
        "    documents[key] = import_module('snackportal2.services.' + key + '.main').app.openapi()\n"
        "sys.stdout.write(json.dumps(documents, sort_keys=True))\n"
    )
    child = {name: value for name, value in os.environ.items() if not name.startswith("SP2_")}
    child["PYTHONPATH"] = str(backend_root)
    child.update(_ENV)
    completed = subprocess.run(
        [sys.executable, "-c", generator],
        cwd=str(backend_root),
        env=child,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    documents: Dict[str, Any] = json.loads(completed.stdout)
    assert len(documents) == 14
    return documents


def test_no_published_contract_mentions_a_lineage_key() -> None:
    rendered = json.dumps(_generated_documents())
    for forbidden in (ACME_KEY, ZETA_KEY, ENV_LINEAGE_KEY_PREFIX, "chain_key", "chainkey", "lineage_key"):
        assert forbidden not in rendered, "a published contract names the lineage key surface: " + forbidden


#: The two pre-existing credential-shaped published properties, named exhaustively rather than
#: excused by loosening the rule. Both live on **internal service-to-service** surfaces that are
#: never client-reachable (IC-013 §13), and both predate Stage 5:
#:
#: * ``AuthenticationRequest.credential`` is the Authentication Service's *input* — the token
#:   presented for validation (IC-005) — not stored secret material; and
#: * ``TenantConnectionGrantResponse.dsn`` is the D-48 grant itself, which is the one value the
#:   Database Router exists to hand to a tenant-resident service.
#:
#: The set is a census, not a filter: a third entry appearing here is a regression, and Stage 5
#: must add none.
_PERMITTED_CREDENTIAL_PROPERTIES = {
    ("authentication", "AuthenticationRequest", "credential"),
    ("database_router", "TenantConnectionGrantResponse", "dsn"),
}


def test_no_published_schema_property_is_key_secret_or_credential_shaped() -> None:
    """Checked over the component schemas structurally, not by substring luck."""
    found = set()
    for service, document in _generated_documents().items():
        schemas = document.get("components", {}).get("schemas", {})
        for name, definition in schemas.items():
            for property_name in (definition.get("properties") or {}):
                folded = property_name.casefold()
                if any(forbidden in folded for forbidden in ("key", "secret", "dsn", "password", "credential")):
                    found.add((service, name, property_name))
    assert found == _PERMITTED_CREDENTIAL_PROPERTIES, "the published credential-shaped surface changed: " + repr(found)
