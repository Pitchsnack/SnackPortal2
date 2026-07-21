"""Stable logical identities for SnackPortal2 environments (SP2-NEXT-A-PORTABILITY O-1/O-2).

Logical identities are the portable names the platform uses for environments and
databases. They are deliberately independent of every physical/runtime handle:
Windows hostnames, Docker container/volume/compose names, local ports, physical
database names, cloud resource IDs, file paths, and transient runtime IDs.
Physical endpoints are operator/profile *configuration*, resolved at composition
time through D-14 references (`shared.secrets.SecretRef` / config references);
they are never identity (master plan §7/§8; NEXT-A O-1/O-2/AC-4).

Architecture invariants are unchanged by this module: One Request → One Active
Tenant → One Database; Control DB ≠ Tenant DB (IC-001/IC-002); routing belongs to
the Database Router alone (IC-005). Pure stdlib; names and validation only — no
I/O, no environment reads, no runtime behavior, no activation surface (the B-5
production posture remains NOT READY / DO-NOT-ACTIVATE).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Tuple

# --- Logical database identities (O-2) ----------------------------------------
# One logical ID per physically distinct database of the official controlled
# local MVP fleet (IC-001/IC-002; master plan §8.1). These IDs are the portable
# names later environments (including cloud) must keep verbatim.

CONTROL_LOGICAL_DATABASE_ID = "control"
TENANT_LOGICAL_DATABASE_IDS: Tuple[str, ...] = ("tenant-acme", "tenant-zeta", "tenant-nova")
REQUIRED_LOGICAL_DATABASE_IDS: Tuple[str, ...] = (CONTROL_LOGICAL_DATABASE_ID,) + TENANT_LOGICAL_DATABASE_IDS

# --- Environment identities (O-1) ---------------------------------------------

OFFICIAL_LOCAL_ENVIRONMENT_ID = "SP2-LOCAL-MVP-01"
CLOUD_TEMPLATE_ENVIRONMENT_ID = "SP2-CLOUD-TEMPLATE-00"  # placeholder identity; a real cloud env mints its own in a future arc

LOCAL_PROFILE_ID = "sp2-local-mvp"
CLOUD_TEMPLATE_PROFILE_ID = "sp2-cloud-template"


class EnvironmentType(Enum):
    """Supported environment types (NEXT-A §8.2/§8.3). Closed vocabulary; unknown types fail closed."""

    CONTROLLED_LOCAL_MVP = "controlled-local-mvp"
    CLOUD_TEMPLATE = "cloud-template"


SUPPORTED_ENVIRONMENT_TYPES = frozenset(t.value for t in EnvironmentType)
# Only the controlled local MVP type may ever reach a running composition; the
# cloud template is non-operational by construction (O-5 / AC-2). Being
# runtime-capable does NOT activate anything — the B-5 activation gate is a
# separate, unchanged mechanism.
RUNTIME_CAPABLE_ENVIRONMENT_TYPES = frozenset({EnvironmentType.CONTROLLED_LOCAL_MVP.value})

# --- Identity grammars ---------------------------------------------------------
# Kebab-case grammars structurally exclude the operational-handle families
# (container/volume/database names use underscores; ports are digit runs;
# hostnames contain dots) so a physical handle can never pass as identity.

LOGICAL_DATABASE_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
ENVIRONMENT_ID_RE = re.compile(r"^SP2-[A-Z0-9]+(-[A-Z0-9]+)*$")
PROFILE_ID_RE = re.compile(r"^sp2-[a-z0-9]+(-[a-z0-9]+)*$")

# Substrings that mark a value as a physical/operational handle of the current
# fixture or host, never admissible as logical identity (belt-and-braces on top
# of the grammars; master plan §8.1 "must not be replaced with" list).
PHYSICAL_HANDLE_MARKERS: Tuple[str, ...] = (
    "sp2_b3a_",  # b3a container/volume handles
    "snackportal2-b3a",  # compose project name
    "snackportal2_",  # physical database names (…_local)
    "b3a",  # fixture generation tag in any spelling
    "localhost",
    "127.0.0.1",
    "::1",
)
_DIGIT_RUN_RE = re.compile(r"\d{4,}")  # port-length digit runs (5540…) are physical configuration, not identity
_DRIVE_PATH_RE = re.compile(r"[A-Za-z]:(?:\\{1,2}|/(?!/))")  # drive path; URI '://' schemes never match


class LogicalIdentityError(ValueError):
    """A value offered as logical identity is malformed or is a physical/operational handle."""


def is_physical_handle(value: str) -> bool:
    """True when the value carries a physical/operational marker (container, port, host, path…)."""
    lowered = value.lower()
    if any(marker in lowered for marker in PHYSICAL_HANDLE_MARKERS):
        return True
    if _DIGIT_RUN_RE.search(value) or _DRIVE_PATH_RE.search(value):
        return True
    return False


def validate_logical_database_id(value: str) -> None:
    """Fail closed unless the value is a well-formed, physically-independent logical database ID."""
    if not LOGICAL_DATABASE_ID_RE.fullmatch(value):
        raise LogicalIdentityError(f"logical database id does not match the kebab-case identity grammar: {value!r}")
    if is_physical_handle(value):
        raise LogicalIdentityError(f"logical database id must be independent of physical/operational handles: {value!r}")
    if len(value) > 63:
        raise LogicalIdentityError("logical database id exceeds 63 characters")


def validate_environment_id(value: str) -> None:
    if not ENVIRONMENT_ID_RE.fullmatch(value):
        raise LogicalIdentityError(f"environment id does not match the SP2-… identity grammar: {value!r}")
    if is_physical_handle(value):
        raise LogicalIdentityError(f"environment id must be independent of physical/operational handles: {value!r}")


def validate_profile_id(value: str) -> None:
    if not PROFILE_ID_RE.fullmatch(value):
        raise LogicalIdentityError(f"profile id does not match the sp2-… identity grammar: {value!r}")
    if is_physical_handle(value):
        raise LogicalIdentityError(f"profile id must be independent of physical/operational handles: {value!r}")
