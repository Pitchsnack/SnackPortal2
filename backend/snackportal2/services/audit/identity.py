"""Emitter identity and read scope — both server-derived, never client-asserted.

The rule this module exists to enforce (3-day plan §10): an emitter does not get to say who
it is. Identity is derived from the authenticated credential presented, so an event's
``source_service`` is a fact about which key was used rather than a claim in a body.

Delegation follows the same discipline. A caller may read on behalf of another principal
only if it holds the delegation scope **and** that specific principal is in its explicitly
enumerated delegable set. A broad delegation permission is never authority to impersonate
every principal.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Mapping, Optional

#: Credential -> emitter identity and scopes, as JSON. Unset means the service accepts no
#: writes and no scoped reads: an audit sink nobody is configured to write to is inert, not
#: open.
ENV_CREDENTIALS = "SP2_AUDIT_CREDENTIALS"

SCOPE_WRITE = "audit:write"
SCOPE_READ = "audit:read"
SCOPE_READ_ALL = "audit:read:all"
SCOPE_DELEGATE = "audit:delegate"

KNOWN_SCOPES = frozenset({SCOPE_WRITE, SCOPE_READ, SCOPE_READ_ALL, SCOPE_DELEGATE})


@dataclass(frozen=True)
class AuditPrincipal:
    """A credential's derived identity, scopes and explicitly delegable targets."""

    emitter_ref: str
    scopes: FrozenSet[str]
    delegable_targets: FrozenSet[str] = field(default_factory=frozenset)

    def may_write(self) -> bool:
        return SCOPE_WRITE in self.scopes

    def may_read(self) -> bool:
        return SCOPE_READ in self.scopes or SCOPE_READ_ALL in self.scopes

    def reads_everything(self) -> bool:
        return SCOPE_READ_ALL in self.scopes

    def may_read_on_behalf_of(self, target: str) -> bool:
        """Scoped delegation: the scope *and* this specific target, never the scope alone."""
        return SCOPE_DELEGATE in self.scopes and target in self.delegable_targets


class CredentialDirectory:
    """Maps a presented credential to its derived principal."""

    def __init__(self, principals: Mapping[str, AuditPrincipal]) -> None:
        self._principals = dict(principals)

    def resolve(self, credential: str) -> Optional[AuditPrincipal]:
        return self._principals.get(credential)

    @classmethod
    def from_json(cls, raw: str) -> "CredentialDirectory":
        """Parse ``{"<credential>": {"emitter_ref": ..., "scopes": [...], "delegable_targets": [...]}}``."""
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("audit credential configuration must be a JSON object")

        principals: Dict[str, AuditPrincipal] = {}
        for credential, entry in parsed.items():
            if not isinstance(entry, dict):
                raise ValueError("audit credential entry must be a JSON object")
            emitter_ref = entry.get("emitter_ref")
            if not isinstance(emitter_ref, str) or not emitter_ref:
                raise ValueError("audit credential entry requires an emitter_ref")
            scopes = entry.get("scopes", [])
            if not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes):
                raise ValueError("audit credential scopes must be a list of strings")
            unknown = set(scopes) - KNOWN_SCOPES
            if unknown:
                # An unrecognized scope must fail at configuration time rather than being
                # silently ignored, which would look like a granted scope that does nothing.
                raise ValueError("unknown audit scope(s): " + ",".join(sorted(unknown)))
            targets = entry.get("delegable_targets", [])
            if not isinstance(targets, list) or not all(isinstance(target, str) for target in targets):
                raise ValueError("audit delegable_targets must be a list of strings")
            principals[credential] = AuditPrincipal(
                emitter_ref=emitter_ref,
                scopes=frozenset(scopes),
                delegable_targets=frozenset(targets),
            )
        return cls(principals)


def build_credential_directory(env: Optional[Mapping[str, str]] = None) -> CredentialDirectory:
    """Build the directory from configuration; empty (accepting nothing) by omission."""
    source: Mapping[str, str] = os.environ if env is None else env
    raw = source.get(ENV_CREDENTIALS, "").strip()
    if raw:
        return CredentialDirectory.from_json(raw)
    return CredentialDirectory({})


__all__ = [
    "ENV_CREDENTIALS",
    "KNOWN_SCOPES",
    "SCOPE_DELEGATE",
    "SCOPE_READ",
    "SCOPE_READ_ALL",
    "SCOPE_WRITE",
    "AuditPrincipal",
    "CredentialDirectory",
    "build_credential_directory",
]
