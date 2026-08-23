"""The authorization policy — the one place a SnackPortal2 permission is evaluated.

Phase 0 found that **no permission engine existed anywhere in production code**: identity
was checked, membership was stored but never evaluated, residency was a side-effect of
routing, and edge role-gating lived inside the Gateway. This module is that engine
(IC-014 §0).

Three structural properties, each of which is tested rather than asserted:

1. **Deny is the default, not the exception** (§8.2). ``ALLOWED`` is returned from exactly
   one place, at the very end, after every check has passed. A missing branch, a
   fall-through, or an unhandled case therefore produces ``DENIED`` by construction — the
   only way to be allowed is to survive the whole function.
2. **No database, ever** (§2, §6). This module imports no driver, holds no DSN, and reads
   no tenant business data. The service that decides access must not be the service that
   has access.
3. **Ownership is an input, never an authority** (§7). It is consulted only where a rule
   names it, and it never grants.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, FrozenSet, Mapping, Optional

from ...shared.errors import ErrorCode
from ...shared.operations import SHARING_INERT_OPERATIONS, BffOperation, UnknownOperation, domain_of
from ...shared.security import RequestContext
from ...shared.types import DatabaseDomain, PlatformRole


class Decision(str, Enum):
    """The result. There is no third value (IC-014 §8.1).

    No "allowed with warnings", no partial allow, no allow-with-scope-narrowing: an
    operation is permitted in full or not at all.
    """

    ALLOWED = "allowed"
    DENIED = "denied"


class Permission(str, Enum):
    """The closed permission vocabulary (IC-014 §5.2).

    An operation requiring a permission absent from this set is denied. ``AI_INVOKE`` is
    **defined but unwired** (Canonical Overview Part 4B): it exists so the vocabulary is
    complete and so its ungranted state is testable, and it is granted to no principal
    under this revision.
    """

    MEMBERSHIPS_READ = "memberships.read"
    DIRECTORY_GLOBAL_STARTUP_READ = "directory.global.startup.read"
    DIRECTORY_GLOBAL_INVESTOR_READ = "directory.global.investor.read"
    IMPORT_INITIATE = "import.initiate"
    STARTUP_READ = "startup.read"
    STARTUP_CREATE = "startup.create"
    STARTUP_UPDATE = "startup.update"
    INVESTOR_READ = "investor.read"
    INVESTOR_CREATE = "investor.create"
    INVESTOR_UPDATE = "investor.update"
    DEAL_READ = "deal.read"
    DEAL_CREATE = "deal.create"
    DEAL_UPDATE = "deal.update"
    CONTACT_READ = "contact.read"
    CONTACT_CREATE = "contact.create"
    LINEAGE_READ = "lineage.read"
    SHARE_PROPOSE = "share.propose"
    SHARE_READ = "share.read"
    AI_INVOKE = "ai.invoke"


#: Operation -> the single permission it requires.
REQUIRED_PERMISSION: Mapping[BffOperation, Permission] = {
    BffOperation.LIST_MEMBERSHIPS: Permission.MEMBERSHIPS_READ,
    BffOperation.READ_GLOBAL_STARTUP_DIRECTORY: Permission.DIRECTORY_GLOBAL_STARTUP_READ,
    BffOperation.READ_GLOBAL_INVESTOR_DIRECTORY: Permission.DIRECTORY_GLOBAL_INVESTOR_READ,
    BffOperation.INITIATE_STARTUP_IMPORT: Permission.IMPORT_INITIATE,
    BffOperation.LIST_TENANT_STARTUPS: Permission.STARTUP_READ,
    BffOperation.READ_TENANT_STARTUP: Permission.STARTUP_READ,
    BffOperation.CREATE_TENANT_STARTUP: Permission.STARTUP_CREATE,
    BffOperation.UPDATE_TENANT_STARTUP: Permission.STARTUP_UPDATE,
    BffOperation.LIST_TENANT_INVESTORS: Permission.INVESTOR_READ,
    BffOperation.READ_TENANT_INVESTOR: Permission.INVESTOR_READ,
    BffOperation.CREATE_TENANT_INVESTOR: Permission.INVESTOR_CREATE,
    BffOperation.UPDATE_TENANT_INVESTOR: Permission.INVESTOR_UPDATE,
    BffOperation.LIST_TENANT_DEALS: Permission.DEAL_READ,
    BffOperation.READ_TENANT_DEAL: Permission.DEAL_READ,
    BffOperation.CREATE_TENANT_DEAL: Permission.DEAL_CREATE,
    BffOperation.UPDATE_TENANT_DEAL: Permission.DEAL_UPDATE,
    BffOperation.LIST_TENANT_CONTACTS: Permission.CONTACT_READ,
    BffOperation.READ_TENANT_CONTACT: Permission.CONTACT_READ,
    BffOperation.CREATE_TENANT_CONTACT: Permission.CONTACT_CREATE,
    BffOperation.READ_TENANT_LINEAGE: Permission.LINEAGE_READ,
    BffOperation.PROPOSE_DEAL_SHARE: Permission.SHARE_PROPOSE,
    BffOperation.READ_DEAL_SHARE: Permission.SHARE_READ,
}


# --- The role grant matrix -------------------------------------------------------------
# Derived from IC-009 §C (per-role × per-directory visibility) and its Import note F-4, not
# from any UI. Three readings of that matrix are load-bearing here:
#
#   * CONTROL holds a tenantless token and "can never reach a tenant DB" — so it holds no
#     tenant-record permission at all, not even read. Its authority is Control-resident.
#   * MASTER_AGENT, TENANT_ADMIN and TENANT_AGENT hold directory read + import + scoped
#     tenant-record access, always bound to the one signed active tenant. There is no
#     cross-tenant grant anywhere in this table (IC-007 deferral).
#   * STARTUP_USER and INVESTOR_USER hold own-kind directory discovery only. IC-009 §C
#     scopes their tenant-record access to *assigned* records, and the assignment model is
#     a contract-first dependency that does not yet exist — so those cells are denied here
#     rather than approximated. Fail closed is the correct answer to an unwritten rule.
_TENANT_AGENT_PERMISSIONS: FrozenSet[Permission] = frozenset(
    {
        Permission.MEMBERSHIPS_READ,
        Permission.DIRECTORY_GLOBAL_STARTUP_READ,
        Permission.DIRECTORY_GLOBAL_INVESTOR_READ,
        Permission.IMPORT_INITIATE,
        Permission.STARTUP_READ,
        Permission.STARTUP_CREATE,
        Permission.STARTUP_UPDATE,
        Permission.INVESTOR_READ,
        Permission.INVESTOR_CREATE,
        Permission.INVESTOR_UPDATE,
        Permission.DEAL_READ,
        Permission.DEAL_CREATE,
        Permission.DEAL_UPDATE,
        Permission.CONTACT_READ,
        Permission.CONTACT_CREATE,
        Permission.LINEAGE_READ,
    }
)

ROLE_PERMISSIONS: Mapping[PlatformRole, FrozenSet[Permission]] = {
    PlatformRole.CONTROL: frozenset(
        {
            Permission.MEMBERSHIPS_READ,
            Permission.DIRECTORY_GLOBAL_STARTUP_READ,
            Permission.DIRECTORY_GLOBAL_INVESTOR_READ,
        }
    ),
    PlatformRole.MASTER_AGENT: _TENANT_AGENT_PERMISSIONS,
    PlatformRole.TENANT_ADMIN: _TENANT_AGENT_PERMISSIONS,
    PlatformRole.TENANT_AGENT: _TENANT_AGENT_PERMISSIONS,
    PlatformRole.STARTUP_USER: frozenset({Permission.MEMBERSHIPS_READ, Permission.DIRECTORY_GLOBAL_STARTUP_READ}),
    PlatformRole.INVESTOR_USER: frozenset({Permission.MEMBERSHIPS_READ, Permission.DIRECTORY_GLOBAL_INVESTOR_READ}),
}


class AccessDecision:
    """A decision plus the canonical code a denial carries. Never a reason."""

    __slots__ = ("decision", "code", "domain")

    def __init__(self, decision: Decision, code: ErrorCode, domain: Optional[DatabaseDomain]) -> None:
        self.decision = decision
        self.code = code
        self.domain = domain

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOWED


def _denied(code: ErrorCode) -> AccessDecision:
    """Every denial funnels through here, and never carries a resolved domain.

    Returning ``domain=None`` on a denial is what makes "a denied request never causes a
    tenant-database connection" (IC-014 §3) structural: there is nothing for the caller to
    route to even if it ignored the verdict.
    """
    return AccessDecision(Decision.DENIED, code, None)


#: Looks up whether a principal is a member of a tenant. References only — it takes and
#: returns references, never rows, and it is the *only* external read this module performs.
MembershipLookup = Callable[[str, str], bool]


def resolve_single_domain(operation: BffOperation, context: RequestContext) -> Optional[DatabaseDomain]:
    """Resolve the one lawful database domain, or ``None`` to deny (IC-014 §5.4).

    This function is the single-domain *decision*. The BFF separately *enforces* that
    exactly one domain was decided (IC-013 §11) — a decision without enforcement is
    advisory, and enforcement without a decision is a guess.

    Note what cannot happen here: a TENANT operation can only ever yield ``TENANT``. There
    is no branch that answers ``CONTROL`` for a tenant operation, so "ACME DB unavailable →
    use the Control DB" is not a policy this engine is capable of expressing.
    """
    try:
        domain = domain_of(operation)
    except UnknownOperation:
        return None

    if domain is DatabaseDomain.TENANT:
        # A tenant operation without a signed tenant claim has no domain at all. There is
        # no default tenant and no Control fallback.
        if not context.tenant_context:
            return None
        return DatabaseDomain.TENANT

    return DatabaseDomain.CONTROL


def decide(
    operation: BffOperation,
    context: RequestContext,
    *,
    is_member: MembershipLookup,
    owner_agent_ref: Optional[str] = None,
    owner_ai_agent_ref: Optional[str] = None,
) -> AccessDecision:
    """Evaluate one authorization question.

    Every early return is a denial. ``Decision.ALLOWED`` appears exactly once, on the last
    line, which is what makes §8.2 ("a decision path that could produce Allowed by omission
    is a contract violation") a property of the code rather than a promise about it.
    """
    try:
        # --- context integrity: a malformed context decides nothing (§8.2) --------------
        if not context.principal_ref or not context.correlation_id:
            return _denied(ErrorCode.ACCESS_DENIED)

        # --- the operation must be in the enumerated surface (§5.2) ---------------------
        # This is the one deny branch in this function that survives mutation testing, and
        # deliberately so: with it deleted, the lookup at ``REQUIRED_PERMISSION[operation]``
        # below raises straight into the fail-closed handler, so the outcome is unchanged.
        # It is kept because "unknown operation" should be a stated rule rather than an
        # incidental KeyError, and because the two controls fail independently.
        if operation not in REQUIRED_PERMISSION:
            return _denied(ErrorCode.ACCESS_DENIED)

        # --- governed sharing is authored-but-inert until IC-007 is Final (§10) ---------
        if operation in SHARING_INERT_OPERATIONS:
            return _denied(ErrorCode.ACCESS_DENIED)

        # --- exactly one database domain, decided here (§5.4) ---------------------------
        domain = resolve_single_domain(operation, context)
        if domain is None:
            return _denied(ErrorCode.ISOLATION_VIOLATION)

        # --- ownership is an input, never an authority (§7) -----------------------------
        # A populated AI-owner reference is an ERROR condition pre-IC-006, never a grant
        # (IC-008 V10). It is checked before permissions so that it can never be mistaken
        # for a thing that widens them.
        if owner_ai_agent_ref:
            return _denied(ErrorCode.ACCESS_DENIED)

        # --- tenant membership, before any routing (§5.3) -------------------------------
        if domain is DatabaseDomain.TENANT:
            tenant_ref = context.tenant_context
            if not tenant_ref:
                return _denied(ErrorCode.ISOLATION_VIOLATION)
            if not is_member(context.principal_ref, tenant_ref):
                # Consistent denial: a principal who is not a member is indistinguishable
                # from one whose tenant does not exist (§8.3).
                return _denied(ErrorCode.ACCESS_DENIED)

        # --- the permission itself (§5.2) -----------------------------------------------
        # Membership established tenant *access*; this establishes what may be done there.
        # Both checks are required; neither substitutes for the other.
        required = REQUIRED_PERMISSION[operation]
        granted = ROLE_PERMISSIONS.get(context.role)
        if granted is None or required not in granted:
            return _denied(ErrorCode.ACCESS_DENIED)

        # --- ai.invoke is defined and ungranted platform-wide (§9) ----------------------
        if required is Permission.AI_INVOKE:
            return _denied(ErrorCode.ACCESS_DENIED)

        # ``owner_agent_ref`` is accepted and deliberately unused: ownership never grants
        # (IC-008 V6). It is present in the signature because a future rule may *name* it,
        # and reading it here documents that reading it is not the same as honouring it.
        del owner_agent_ref

    except Exception:
        # Any error, timeout, ambiguity or unhandled case is Denied (§8.2). This handler is
        # the backstop, not the mechanism: the mechanism is that Allowed is unreachable
        # except by falling off the end of the try block.
        return _denied(ErrorCode.ACCESS_DENIED)

    return AccessDecision(Decision.ALLOWED, ErrorCode.ACCESS_DENIED, domain)


__all__ = [
    "REQUIRED_PERMISSION",
    "ROLE_PERMISSIONS",
    "AccessDecision",
    "Decision",
    "MembershipLookup",
    "Permission",
    "decide",
    "resolve_single_domain",
]
