"""Bootstrap SecretStore provider: trust-anchor resolution only; no leakage (H-2 / D-14)."""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _h  # noqa: E402

from shared.adapters.providers.env_reference_secret_store import EnvReferenceSecretStore  # noqa: E402
from shared.secrets import SecretRef, SecretValue  # noqa: E402


def test_resolves_trust_anchor_from_env() -> None:
    os.environ["SNACKPORTAL_SECRET_BOOTSTRAP_TRUST_ANCHOR_V1"] = "anchor-xyz"
    store = EnvReferenceSecretStore()
    assert store.resolve(SecretRef("bootstrap/trust-anchor", "1")).material == "anchor-xyz"


def test_rejects_non_trust_anchor_reference() -> None:
    store = EnvReferenceSecretStore()
    try:
        store.resolve(SecretRef("tenant/db-creds", "1"))
        assert False, "should refuse non-trust-anchor resolution"
    except PermissionError:
        pass


def test_unresolved_reference_raises() -> None:
    os.environ.pop("SNACKPORTAL_SECRET_BOOTSTRAP_TRUST_ANCHOR_V9", None)
    store = EnvReferenceSecretStore(secret_dir=None)
    try:
        store.resolve(SecretRef("bootstrap/trust-anchor", "9"))
        assert False, "should raise on unresolved reference"
    except LookupError:
        pass


def test_secret_value_repr_is_redacted() -> None:
    assert "topsecret" not in repr(SecretValue(material="topsecret"))


if __name__ == "__main__":
    _h.run([
        test_resolves_trust_anchor_from_env,
        test_rejects_non_trust_anchor_reference,
        test_unresolved_reference_raises,
        test_secret_value_repr_is_redacted,
    ])
